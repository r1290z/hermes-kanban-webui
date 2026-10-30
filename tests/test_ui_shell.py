import re
from pathlib import Path

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
