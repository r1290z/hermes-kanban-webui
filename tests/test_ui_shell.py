import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_tokens_have_spec_values():
    tokens = (STATIC / "design-tokens.css").read_text(encoding="utf-8")
    for pair in ["--bg: #0b0c0e", "--surface: #111417", "--line: #23272d", "--ink: #e6e8eb",
                 "--mut: #aab3c0", "--run: #5b9dff", "--blk: #e0a34a", "--ok: #4ec38a",
                 "--r-sm: 5px", "--r-md: 8px"]:
        assert pair in tokens, pair


def test_no_ai_style_markers():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "backdrop-filter" not in css
    assert "999px" not in css
    assert not re.search(r"background[^;{}]*gradient\(", css), "градиенты в фоне"
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html


def test_shell_has_four_tabs_and_five_views():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for view in ["now", "board", "list", "feed", "log"]:
        assert f'id="view{view.capitalize()}"' in html, view
    tabs = re.findall(r'data-tab="(\w+)"', html)
    assert tabs == ["now", "board", "feed", "log"]
    for control in ["boardSelect", "taskCreateBtn", "refreshBtn", "themeToggle", "langToggle", "searchInput"]:
        assert f'id="{control}"' in html, control


def test_assets_use_single_version_token():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    token = re.search(r'app\.js\?v=([^"\']+)', index).group(1)
    for path in STATIC.glob("*.js"):
        body = path.read_text(encoding="utf-8")
        for found in re.findall(r"\?v=([\w.-]+)", body):
            assert found == token, f"{path.name} uses ?v={found}, expected {token}"


def test_ready_status_renamed():
    i18n = (STATIC / "i18n.js").read_text(encoding="utf-8")
    assert "ready: 'На проверке'" in i18n
    assert "Готовы" not in i18n


# --- Тема по умолчанию (спека §5.1: тёмная — основная) -----------------------

THEME_PROBE = ROOT / "tests" / "helpers" / "theme_probe.js"


def test_empty_profile_opens_in_dark_theme():
    """Чистый профиль (нет localStorage) + светлая система → data-theme="dark"."""
    node = shutil.which("node") or ""
    if not node:
        pytest.skip("node is required for the theme probe")
    out = subprocess.run(
        [node, str(THEME_PROBE), str(STATIC / "theme.js")],
        check=True, capture_output=True, text=True, cwd=ROOT,
    ).stdout
    result = json.loads(out)
    assert result["resolved"] == "dark", result
    assert result["applied"] == "dark", result
    assert result["dataset"] == "dark", result
    assert result["colorScheme"] == "dark", result
    # Сохранённый выбор по-прежнему главнее дефолта, «как в системе» — отдельный путь.
    assert result["storedLight"] == "light", result
    assert result["systemChoice"] == "light", result


# --- Контраст вторичного текста (спека §5.2: ≥ 4.5:1 на своих фонах) ---------

def _lx(channel: float) -> float:
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def contrast_ratio(fg: str, bg: str) -> float:
    def luminance(color: str) -> float:
        h = color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return 0.2126 * _lx(r) + 0.7152 * _lx(g) + 0.0722 * _lx(b)
    hi, lo = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _token_block(css: str, selector: str) -> dict:
    head = css.index(selector)
    body = css[css.index("{", head) + 1:css.index("}", head)]
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", body))


def test_secondary_text_contrast():
    tokens = (STATIC / "design-tokens.css").read_text(encoding="utf-8")
    themes = {
        "dark": _token_block(tokens, ":root {"),
        "light": _token_block(tokens, ':root[data-theme="light"]'),
    }
    failures = []
    for theme, values in themes.items():
        for text in ("--mut", "--faint"):
            for surface in ("--bg", "--surface", "--surface-2"):
                ratio = contrast_ratio(values[text], values[surface])
                if ratio < 4.5:
                    failures.append(f"{theme} {text} на {surface} = {ratio:.2f}:1")
    assert not failures, "мелкий текст ниже 4.5:1: " + "; ".join(failures)
