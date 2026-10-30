import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_now_module_contract():
    now = (STATIC / "now.js").read_text(encoding="utf-8")
    assert "export async function loadNow" in now
    assert "export function renderNow" in now
    for marker in ["api.board", "api.pulse", "api.log"]:
        assert marker in now, marker
    for section in ["now-live", "now-attention", "now-queue", "now-done"]:
        assert section in now, section


def test_now_has_idle_and_error_states():
    now = (STATIC / "now.js").read_text(encoding="utf-8")
    assert "t('noActiveRuns')" in now
    assert "t('loadFailed')" in now
    assert "t('retry')" in now


def test_no_emoji_in_pulse_and_now():
    for name in ["pulse.js", "now.js"]:
        body = (STATIC / name).read_text(encoding="utf-8")
        assert "⏱" not in body, name
        assert not re.search(r"[\U0001F300-\U0001FAFF]", body), name


def test_progress_bar_only_with_limit():
    now = (STATIC / "now.js").read_text(encoding="utf-8")
    assert "max_runtime_seconds" in now
    assert "now-progress" in now


def test_now_view_wired_into_shell():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "from './now.js?v=" in app
    assert "loadNow()" in app
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="viewNow"' in html


def test_now_styles_present():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    for marker in [".now-block", ".now-empty", ".now-error", ".now-progress"]:
        assert marker in css, marker