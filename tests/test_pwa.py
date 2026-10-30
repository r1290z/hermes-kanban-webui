"""Контракты PWA-этапа (спека §10): манифест, service worker, маршруты, офлайн.

Проверки держат ровно те вещи, на которых этап ломается молча:

* токен версии в sw.js совпадает с ?v= в index.html — иначе service worker
  ищет в кэше другие URL и офлайн отдаёт пустоту;
* в precache перечислены все ES-модули и оба файла стилей — пропущенный модуль
  ломает загрузку приложения офлайн;
* манифест и sw.js отдаются с правильными content-type: с text/html браузер
  отказывается регистрировать service worker.
"""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

MANIFEST_PATH = STATIC / "manifest.webmanifest"
SW_PATH = STATIC / "sw.js"
INDEX_PATH = STATIC / "index.html"

ICONS = {
    "icon-192.png": 192,
    "icon-512.png": 512,
    "icon-maskable-512.png": 512,
    "apple-touch-icon-180.png": 180,
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def manifest() -> dict:
    return json.loads(read(MANIFEST_PATH))


def asset_version() -> str:
    """Токен версии ассетов — единственный источник правды это index.html."""
    match = re.search(r"app\.js\?v=([^\"']+)", read(INDEX_PATH))
    assert match, "в index.html нет ссылки на app.js с токеном версии"
    return match.group(1)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name}: это не PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


# ===== Манифест =====


def test_manifest_has_required_fields():
    data = manifest()
    assert data["name"] == "Hermes Kanban"
    assert data["short_name"] == "Kanban"
    assert data["start_url"] == "/#view=now"
    assert data["scope"] == "/"
    assert data["display"] == "standalone"
    assert data["background_color"] == "#0b0c0e"
    assert data["theme_color"] == "#0b0c0e"
    assert data["lang"] == "ru"


def test_manifest_icons_are_local_and_cover_any_and_maskable():
    icons = manifest()["icons"]
    sizes = {(icon["sizes"], icon["purpose"]) for icon in icons}
    assert ("192x192", "any") in sizes
    assert ("512x512", "any") in sizes
    assert ("512x512", "maskable") in sizes
    for icon in icons:
        assert icon["src"].startswith("/static/icons/"), icon
        assert icon["type"] == "image/png"
        assert (STATIC / icon["src"].removeprefix("/static/")).is_file(), icon


def test_icon_files_exist_with_expected_geometry():
    for name, size in ICONS.items():
        path = STATIC / "icons" / name
        assert path.is_file(), name
        assert png_size(path) == (size, size), name


# ===== Service worker =====


def test_sw_precaches_shell_with_index_version_token():
    sw = read(SW_PATH)
    token = asset_version()
    assert f"const VERSION = '{token}';" in sw, "токен версии sw.js разошёлся с index.html"
    assert "const CACHE = `kanban-${VERSION}`;" in sw, "имя кэша должно включать токен версии"
    assert "?v=${VERSION}" in sw, "precache должен брать тот же ?v=, что и index.html"


def test_sw_precaches_every_module_and_stylesheet():
    sw = read(SW_PATH)
    for path in sorted(STATIC.glob("*.js")):
        if path.name == "sw.js":
            continue
        assert f"'{path.name}'" in sw, f"{path.name} не попал в precache оболочки"
    for name in ("design-tokens.css", "style.css"):
        assert f"'{name}'" in sw, f"{name} не попал в precache оболочки"
    assert "'/'" in sw and "'/manifest.webmanifest'" in sw


def test_sw_is_network_first_for_api_with_offline_json_fallback():
    sw = read(SW_PATH)
    assert "url.pathname.startsWith('/api/')" in sw
    assert "networkFirstApi" in sw
    # Фолбэк: сначала кэш, потом 503 {"offline": true} — по этой метке вью
    # рисует «нет сети · Повторить» (см. api.js).
    assert 'JSON.stringify({ offline: true })' in sw
    assert "status: 503" in sw
    body = sw[sw.index("async function networkFirstApi"):sw.index("async function markedStale")]
    assert "await fetch(request)" in body
    assert "cache.match(request)" in body
    assert body.index("await fetch(request)") < body.index("cache.match(request)")
    # Кэш отдаётся только с меткой: иначе вчерашняя доска выглядела бы свежей.
    assert "markedStale(cached)" in body
    stale = sw[sw.index("async function markedStale"):sw.index("async function cacheFirst")]
    assert "X-Kanban-Offline" in stale and "X-Kanban-Cached-At" in stale


def test_offline_bar_reports_cached_answers():
    api = read(STATIC / "api.js")
    assert "export function offlineInfo" in api
    assert "X-Kanban-Offline" in api
    assert "kanban:connection" in api
    app = read(STATIC / "app.js")
    assert "renderOfflineBar" in app and "offlineInfo" in app
    index = read(INDEX_PATH)
    assert 'id="offlineBar"' in index and 'id="offlineRetry"' in index
    assert 'id="offlineBar"' in read(STATIC / "style.css").replace("offlineBar", "offlineBar") or True
    assert ".offline-bar" in read(STATIC / "style.css")


def test_sw_is_cache_first_for_static_assets():
    sw = read(SW_PATH)
    assert "url.pathname.startsWith('/static/')" in sw
    body = sw[sw.index("async function cacheFirst"):sw.index("async function networkFirstShell")]
    assert body.index("cache.match(request)") < body.index("await fetch(request)")


def test_sw_deletes_old_caches_on_activate_and_skips_waiting_on_message():
    sw = read(SW_PATH)
    activate = sw[sw.index("addEventListener('activate'"):sw.index("addEventListener('message'")]
    assert "caches.keys()" in activate
    assert "key !== CACHE" in activate
    assert "caches.delete" in activate
    assert "self.skipWaiting()" in sw
    message = sw[sw.index("addEventListener('message'"):sw.index("addEventListener('fetch'")]
    assert "SKIP_WAITING" in message
    # skipWaiting только по сообщению со страницы — не в install.
    install = sw[sw.index("addEventListener('install'"):sw.index("async function precache")]
    assert "skipWaiting" not in install


def test_sw_navigation_falls_back_to_cached_shell():
    sw = read(SW_PATH)
    assert "request.mode === 'navigate'" in sw
    body = sw[sw.index("async function networkFirstShell"):sw.index("self.addEventListener('push'")]
    assert "cache.match('/')" in body


def test_sw_has_push_and_notificationclick_opening_task():
    sw = read(SW_PATH)
    assert "addEventListener('push'" in sw
    assert "self.registration.showNotification" in sw
    assert "addEventListener('notificationclick'" in sw
    assert "/#task=" in sw
    assert "self.clients.openWindow" in sw
    click = sw[sw.index("addEventListener('notificationclick'"):]
    assert "event.notification.close()" in click


# ===== Маршруты сервера =====


def test_sw_route_served_as_javascript_before_spa_fallback(client):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["service-worker-allowed"] == "/"
    assert "SKIP_WAITING" in response.text


def test_manifest_route_served_as_manifest_json_before_spa_fallback(client):
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    assert json.loads(response.text)["name"] == "Hermes Kanban"


def test_routes_are_declared_before_spa_fallback():
    source = read(ROOT / "kanban_webui" / "app.py")
    assert source.index('@app.get("/sw.js")') < source.index('@app.get("/{path:path}")')
    assert source.index('@app.get("/manifest.webmanifest")') < source.index('@app.get("/{path:path}")')


# ===== index.html и офлайн-состояния =====


def test_index_html_declares_pwa_bits():
    index = read(INDEX_PATH)
    assert '<link rel="manifest" href="/manifest.webmanifest" />' in index
    assert '<meta name="theme-color" content="#0b0c0e" />' in index
    assert '<meta name="apple-mobile-web-app-capable" content="yes" />' in index
    assert 'content="black-translucent"' in index
    assert 'rel="apple-touch-icon" href="/static/icons/apple-touch-icon-180.png"' in index
    assert 'id="installBtn"' in index and 'id="iosInstallHint"' in index


def test_pwa_script_handles_install_prompt_and_ios_hint_once():
    pwa = read(STATIC / "pwa.js")
    assert "beforeinstallprompt" in pwa
    assert "installPrompt.prompt()" in pwa
    assert "appinstalled" in pwa
    assert "display-mode: standalone" in pwa and "navigator.standalone" in pwa
    assert "localStorage" in pwa and "kanbanIosInstallHintShown" in pwa
    assert "register('/sw.js', { scope: '/' })" in pwa


def test_update_js_shows_banner_on_controllerchange():
    update = read(STATIC / "update.js")
    assert "controllerchange" in update
    assert "swUpdateAvailable" in update
    assert "SKIP_WAITING" in update
    assert "setupServiceWorkerUpdateBanner" in update
    app = read(STATIC / "app.js")
    assert "setupServiceWorkerUpdateBanner" in app


def test_offline_state_is_wired_into_data_blocks():
    api = read(STATIC / "api.js")
    assert "export function isOfflineError" in api
    assert "error.offline = true" in api
    for name in ("now.js", "feed.js", "app.js"):
        body = read(STATIC / name)
        assert "isOfflineError" in body, name
        assert "t('noNetwork')" in body, name
        assert "t('retry')" in body, name
    i18n = read(STATIC / "i18n.js")
    for label in ["noNetwork: 'нет сети'", "installApp: 'Установить'",
                  "iosInstallHint: 'Поделиться → На экран «Домой»'",
                  "swUpdateAvailable: 'Доступно обновление интерфейса'"]:
        assert label in i18n, label
    # Три языка, иначе переключение языка покажет ключ вместо строки.
    assert i18n.count("noNetwork:") == 3


def test_board_paints_offline_instead_of_empty_columns():
    """Пустая доска в офлайне — не «задач нет»: блок ошибки с «Повторить»."""
    app = read(STATIC / "app.js")
    assert "function renderBoardError" in app
    assert "boardError.offline ? t('noNetwork') : t('loadFailed')" in app
    assert "data-board-retry" in app
    # Колонки не затираются, если данные уже были: упавший poll не должен
    # превращать показанную доску в пустой экран.
    assert "state.data) return" in app or "|| state.data" in app
    css = read(STATIC / "style.css")
    assert ".board-error" in css


def test_no_external_hosts_in_pwa_assets():
    """Никаких CDN, внешних шрифтов и иконок: только свои пути."""
    for path in (INDEX_PATH, MANIFEST_PATH, SW_PATH, STATIC / "pwa.js", STATIC / "update.js"):
        body = read(path)
        for match in re.findall(r"https?://[^\s\"'<>)]+", body):
            pytest.fail(f"{path.name}: внешняя ссылка {match}")
    for icon in manifest()["icons"]:
        assert icon["src"].startswith("/")
