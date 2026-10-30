"""Контракты web-push (спека §10.2): подписки, отбор событий, пейлоад.

Проверки держат то, что ломается молча и дорого:

* upsert по ``endpoint`` — телефон после переустановки PWA присылает новый
  набор ключей на тот же endpoint, и вторая строка означала бы две доставки;
* отбор событий — ``heartbeat`` занимает больше половины ``task_events``
  (575 из 1300 на живой базе), и пуш на каждый пульс превращает уведомления
  в шум, который выключают;
* пейлоад по умолчанию без заголовка задачи — он виден на локскрине;
* ``410``/``404`` от FCM — мёртвая подписка, её надо удалять, а не долбить.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import sqlite3
import time
from pathlib import Path

import pytest
from pywebpush import WebPushException

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load_script(name: str):
    """Загрузить ``scripts/<name>.py`` по пути, а не по имени пакета.

    Имя ``scripts`` на sys.path занято пакетом сторонних плагинов Hermes
    (``plugins/web-search-plus/scripts/__init__.py``), и в общем прогоне
    ``from scripts import push_notifier`` попадает туда и падает ImportError.
    """
    module_name = f"_kanban_webui_scripts_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


from kanban_webui import push_view


def state_dir() -> Path:
    """Каталог состояния, который фикстура подставила приложению."""
    return Path(os.environ["HERMES_KANBAN_WEBUI_STATE"])


@pytest.fixture(autouse=True)
def push_state(tmp_path, monkeypatch):
    """Свой каталог состояния на каждый тест (как в conftest для client)."""
    directory = tmp_path / "kanban-webui-state"
    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_KANBAN_WEBUI_STATE", str(directory))
    return directory


def write_vapid_pair(directory: Path) -> Path:
    """Сгенерировать пару ровно тем же кодом, что и scripts/make_vapid.py."""
    from py_vapid import Vapid

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "vapid-private.pem"
    vapid = Vapid()
    vapid.generate_keys()
    vapid.save_key(str(path))
    path.chmod(0o600)
    return path


# ===== Подписки (маршруты) =====


def test_key_endpoint_returns_base64url_public_key(client):
    write_vapid_pair(state_dir())
    response = client.get("/api/push/key")
    assert response.status_code == 200
    key = response.json()["public_key"]
    # base64url без паддинга, распакованная точка P-256: 0x04 + 32 + 32 байта
    assert "=" not in key and "+" not in key and "/" not in key
    import base64

    raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
    assert len(raw) == 65 and raw[0] == 0x04


def test_key_endpoint_says_so_when_vapid_key_is_missing(client):
    assert not (state_dir() / "vapid-private.pem").exists()
    response = client.get("/api/push/key")
    assert response.status_code == 503
    assert "vapid" in response.json()["detail"].lower()


def test_subscribe_upserts_by_endpoint(client):
    body = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "keys": {"p256dh": "first-p256dh", "auth": "first-auth"},
        "ua": "Pixel 8",
    }
    first = client.post("/api/push/subscribe", json=body)
    assert first.status_code == 201

    # Тот же endpoint после переустановки PWA: ключи новые, строка одна.
    body["keys"] = {"p256dh": "second-p256dh", "auth": "second-auth"}
    second = client.post("/api/push/subscribe", json=body)
    assert second.status_code == 201

    rows = push_view.list_subscriptions(push_view.connect())
    assert len(rows) == 1
    assert rows[0]["endpoint"] == body["endpoint"]
    assert rows[0]["p256dh"] == "second-p256dh"
    assert rows[0]["auth"] == "second-auth"
    assert rows[0]["ua"] == "Pixel 8"


def test_subscribe_requires_keys(client):
    response = client.post(
        "/api/push/subscribe",
        json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {}},
    )
    assert response.status_code == 422


def test_subscribe_rejects_non_http_endpoint(client):
    response = client.post(
        "/api/push/subscribe",
        json={"endpoint": "не-url", "keys": {"p256dh": "p", "auth": "a"}},
    )
    assert response.status_code == 422


def test_delete_removes_subscription(client):
    body = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/del",
        "keys": {"p256dh": "p", "auth": "a"},
    }
    assert client.post("/api/push/subscribe", json=body).status_code == 201
    response = client.request("DELETE", "/api/push/subscribe", json={"endpoint": body["endpoint"]})
    assert response.status_code == 204
    assert push_view.list_subscriptions(push_view.connect()) == []


def test_delete_unknown_endpoint_is_still_204(client):
    response = client.request(
        "DELETE", "/api/push/subscribe", json={"endpoint": "https://fcm.googleapis.com/fcm/send/none"}
    )
    assert response.status_code == 204


# ===== Отправитель: отбор событий =====

T0 = 1_790_000_000


def notifier_db(path: Path) -> Path:
    """Мини-копия схемы kanban.db: только то, что читает отправитель."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL,
                            started_at INTEGER, last_heartbeat_at INTEGER);
        CREATE TABLE task_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                                profile TEXT, status TEXT NOT NULL, started_at INTEGER NOT NULL,
                                ended_at INTEGER, outcome TEXT);
        CREATE TABLE task_events (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                                  run_id INTEGER, kind TEXT NOT NULL, payload TEXT,
                                  created_at INTEGER NOT NULL);
        """
    )
    conn.execute("INSERT INTO tasks VALUES ('t_done', 'Проверить кассу', 'done', ?, ?)", (T0, T0))
    conn.execute("INSERT INTO tasks VALUES ('t_crash', 'Собрать отчёт', 'running', ?, ?)", (T0, T0))
    conn.execute(
        "INSERT INTO task_runs (task_id, status, started_at, ended_at, outcome) VALUES (?,?,?,?,?)",
        ("t_done", "done", T0, T0 + 1800, "completed"),
    )
    conn.execute(
        "INSERT INTO task_runs (task_id, status, started_at, ended_at, outcome) VALUES (?,?,?,?,?)",
        ("t_crash", "crashed", T0, T0 + 300, "crashed"),
    )
    # (task_id, run_id, kind, payload, сдвиг created_at от старта прогона)
    events = [
        ("t_done", 1, "created", "{}", 0),
        ("t_done", 1, "heartbeat", None, 5),
        ("t_done", 1, "heartbeat", None, 10),
        ("t_done", 1, "edited", "{}", 15),
        ("t_done", 1, "promoted", None, 20),
        ("t_done", 1, "completed", '{"result_len": 12}', 1800),
        ("t_done", 1, "worker_result", '{"exit_code": 0}', 1801),
        ("t_crash", 2, "crashed", '{"error": "segfault"}', 300),
        ("t_crash", 2, "worker_result", '{"exit_code": 2}', 300),
        ("t_crash", 2, "timed_out", None, 420),
        ("t_crash", 2, "blocked", '{"reason": "нет доступа"}', 500),
        ("t_crash", 2, "dependency_wait", None, 510),
    ]
    for task_id, run_id, kind, payload, offset in events:
        conn.execute(
            "INSERT INTO task_events (task_id, run_id, kind, payload, created_at) VALUES (?,?,?,?,?)",
            (task_id, run_id, kind, payload, T0 + offset),
        )
    conn.commit()
    conn.row_factory = sqlite3.Row
    return path


def read_events(db_path: Path, after_id: int = 0) -> list[dict]:
    select_events = load_script("push_notifier").select_events

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return select_events(conn, after_id=after_id)
    finally:
        conn.close()


def test_select_events_skips_noise(tmp_path):
    db = notifier_db(tmp_path / "kanban.db")
    kinds = [event["kind"] for event in read_events(db)]
    assert "heartbeat" not in kinds
    assert "created" not in kinds
    assert "edited" not in kinds
    assert "promoted" not in kinds
    assert "dependency_wait" not in kinds
    assert "completed" in kinds
    assert "crashed" in kinds
    assert "timed_out" in kinds
    assert "blocked" in kinds


def test_select_events_keeps_only_failed_worker_result(tmp_path):
    db = notifier_db(tmp_path / "kanban.db")
    payloads = [event["payload"] for event in read_events(db) if event["kind"] == "worker_result"]
    assert payloads == [{"exit_code": 2}]


def test_select_events_respects_cursor(tmp_path):
    db = notifier_db(tmp_path / "kanban.db")
    events = read_events(db)
    assert events, "фикстура должна содержать события"
    last = events[0]["id"]
    later = read_events(db, after_id=last)
    assert all(event["id"] > last for event in later)
    assert len(later) == len(events) - 1


# ===== Пейлоад =====


def payload_for(db_path: Path, kind: str, *, include_title: bool = False) -> dict:
    build_payload = load_script("push_notifier").build_payload

    event = next(event for event in read_events(db_path) if event["kind"] == kind)
    return build_payload(event, include_title=include_title)


def test_payload_hides_task_title_by_default(tmp_path):
    db = notifier_db(tmp_path / "kanban.db")
    payload = payload_for(db, "completed")
    assert payload["title"] == "Kanban"
    assert payload["task_id"] == "t_done"
    assert payload["tag"] == "task:t_done"
    assert payload["url"] == "/#task=t_done"
    assert "t_done" in payload["body"]
    assert "Проверить кассу" not in payload["body"]
    assert "Прогон завершён" in payload["body"]
    assert "30 мин" in payload["body"]  # 1800 с прогона


def test_payload_includes_task_title_on_demand(tmp_path):
    db = notifier_db(tmp_path / "kanban.db")
    payload = payload_for(db, "completed", include_title=True)
    assert "Проверить кассу" in payload["body"]


def test_payload_wording_per_event_kind(tmp_path):
    db = notifier_db(tmp_path / "kanban.db")
    assert "упал" in payload_for(db, "worker_result")["body"]
    assert "код 2" in payload_for(db, "worker_result")["body"]
    assert "сорвался" in payload_for(db, "crashed")["body"]
    assert "таймаут" in payload_for(db, "timed_out")["body"]
    assert "заблокирована" in payload_for(db, "blocked")["body"]


# ===== Прогон отправителя =====


def seed_subscription(endpoint: str = "https://fcm.googleapis.com/fcm/send/sub") -> str:
    conn = push_view.connect()
    push_view.upsert_subscription(conn, endpoint=endpoint, p256dh="bp", auth="ba", ua="Pixel 8")
    return endpoint


def test_dry_run_prints_payloads_and_sends_nothing(tmp_path, monkeypatch):
    push_notifier = load_script("push_notifier")

    db = notifier_db(tmp_path / "kanban.db")
    seed_subscription()
    sent = []

    def sender(*args, **kwargs):  # pragma: no cover - не должен вызываться
        sent.append(args)
        raise AssertionError("--dry-run отправил пуш")

    out = io.StringIO()
    result = push_notifier.run(
        db_path=db,
        state_dir=state_dir(),
        dry_run=True,
        sender=sender,
        out=out,
        lookback=1000,
        include_title=False,
    )
    printed = out.getvalue()
    assert sent == []
    assert result.sent == 0
    # completed, crashed, worker_result(exit 2), timed_out, blocked
    assert "t_done" in printed and "t_crash" in printed
    assert "heartbeat" not in printed
    # Курсор в dry-run не двигается: иначе реальный прогон «съест» эти события.
    assert not (state_dir() / "push-cursor.json").exists()


def test_run_sends_and_advances_cursor(tmp_path):
    push_notifier = load_script("push_notifier")

    db = notifier_db(tmp_path / "kanban.db")
    seed_subscription()
    push_notifier.save_cursor(0, state_dir())
    sent = []

    def sender(subscription, payload, private_key_path):
        sent.append((subscription["endpoint"], payload["tag"]))

    out = io.StringIO()
    result = push_notifier.run(
        db_path=db,
        state_dir=state_dir(),
        dry_run=False,
        sender=sender,
        out=out,
        lookback=1000,
    )
    assert len(sent) == result.events
    cursor = json.loads((state_dir() / "push-cursor.json").read_text())
    assert cursor["last_event_id"] == max(event["id"] for event in read_events(db))

    # Второй прогон: новых событий нет, ничего не отправляем.
    sent.clear()
    again = push_notifier.run(
        db_path=db,
        state_dir=state_dir(),
        dry_run=False,
        sender=sender,
        out=out,
    )
    assert again.events == 0 and sent == []


def test_gone_subscription_is_deleted(tmp_path):
    push_notifier = load_script("push_notifier")

    db = notifier_db(tmp_path / "kanban.db")
    endpoint = seed_subscription("https://fcm.googleapis.com/fcm/send/dead")
    push_notifier.save_cursor(0, state_dir())

    class Gone:
        status_code = 410
        text = "Gone"

    def sender(subscription, payload, private_key_path):
        raise WebPushException("push failed: 410", response=Gone())

    out = io.StringIO()
    result = push_notifier.run(
        db_path=db,
        state_dir=state_dir(),
        dry_run=False,
        sender=sender,
        out=out,
        lookback=1000,
    )
    # Подписка умерла на первом же событии: она удаляется, остальные события
    # уходят «в никуда» (отправлять некому) и курсор всё равно идёт вперёд.
    assert result.dropped == 1
    assert result.events == 5
    assert push_view.list_subscriptions(push_view.connect()) == []
    # Мёртвая подписка не мешает курсору идти вперёд.
    assert json.loads((state_dir() / "push-cursor.json").read_text())["last_event_id"] > 0


def test_transient_failure_keeps_cursor_before_failed_event(tmp_path):
    push_notifier = load_script("push_notifier")

    db = notifier_db(tmp_path / "kanban.db")
    seed_subscription()
    push_notifier.save_cursor(0, state_dir())

    class Boom:
        status_code = 500
        text = "server error"

    def sender(subscription, payload, private_key_path):
        raise WebPushException("push failed: 500", response=Boom())

    out = io.StringIO()
    result = push_notifier.run(
        db_path=db,
        state_dir=state_dir(),
        dry_run=False,
        sender=sender,
        out=out,
        lookback=1000,
    )
    assert result.failed >= 1
    # Курсор не перепрыгнул событие, которое не удалось отправить:
    # следующий тик попробует снова.
    first = read_events(db)[0]
    cursor = json.loads((state_dir() / "push-cursor.json").read_text())["last_event_id"]
    assert cursor == first["id"] - 1


def test_first_real_run_starts_from_now_and_does_not_blast_history(tmp_path):
    push_notifier = load_script("push_notifier")

    db = notifier_db(tmp_path / "kanban.db")
    seed_subscription()
    sent = []

    def sender(subscription, payload, private_key_path):
        sent.append(payload)

    out = io.StringIO()
    result = push_notifier.run(
        db_path=db, state_dir=state_dir(), dry_run=False, sender=sender, out=out
    )
    assert sent == []
    assert result.events == 0
    # Курсор встаёт на текущий максимум task_events: история не отправляется.
    conn = sqlite3.connect(db)
    try:
        newest = conn.execute("SELECT MAX(id) FROM task_events").fetchone()[0]
    finally:
        conn.close()
    assert json.loads((state_dir() / "push-cursor.json").read_text())["last_event_id"] == newest


# ===== Клиент =====


def test_client_button_and_states_are_wired():
    root = Path(__file__).resolve().parents[1]
    index = (root / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="pushBtn"' in index and 'id="pushState"' in index

    push = (root / "static" / "push.js").read_text(encoding="utf-8")
    assert "Notification.requestPermission" in push
    assert "pushManager.subscribe" in push
    assert "applicationServerKey" in push
    assert "/api/push/key" in push
    assert "/api/push/subscribe" in push
    assert "не поддерживается" in push
    assert "запрещены" in push

    app = (root / "static" / "app.js").read_text(encoding="utf-8")
    assert "setupPush" in app


def test_service_worker_notification_opens_task():
    root = Path(__file__).resolve().parents[1]
    sw = (root / "static" / "sw.js").read_text(encoding="utf-8")
    assert "addEventListener('push'" in sw
    assert "addEventListener('notificationclick'" in sw
    assert "/#task=" in sw


# ===== VAPID-пара =====


def test_make_vapid_creates_private_key_with_600_and_is_idempotent(tmp_path):
    make_vapid = load_script("make_vapid")

    directory = tmp_path / "vapid"
    assert make_vapid.main(["--state-dir", str(directory)]) == 0
    pem = directory / "vapid-private.pem"
    assert pem.is_file()
    assert oct(pem.stat().st_mode & 0o777) == "0o600", "приватный ключ должен быть 600"
    first = push_view.vapid_public_key(pem)

    assert make_vapid.main(["--state-dir", str(directory)]) == 0
    assert push_view.vapid_public_key(pem) == first, "без --force ключ не перегенерируется"

    assert make_vapid.main(["--state-dir", str(directory), "--force"]) == 0
    assert push_view.vapid_public_key(pem) != first, "--force должен дать новую пару"
