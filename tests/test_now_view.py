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


def test_empty_sections_collapse_to_one_status_line():
    """Пустая секция — строка-статус, а не карточка с заголовком и словом «Нет»."""
    now = (STATIC / "now.js").read_text(encoding="utf-8")
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "t('empty')" not in now, "в «Сейчас» не должно оставаться голого «Нет»"
    for key in ["attentionNone", "queueNone", "doneNone"]:
        assert f"t('{key}')" in now, key
    assert "is-status" in now and "now-status" in css
    # Высота строки-статуса — 40–44px по §5.2, без рамки и фона.
    assert re.search(r"\.now-status \{[^}]*min-height: 4[0-4]px", css)
    assert re.search(r"\.now-block\.is-status \{[^}]*border: 0", css)


def test_completed_rows_do_not_repeat_status_word():
    """Внутри «Завершено» строки печатают длительность и «N назад», без исхода."""
    now = (STATIC / "now.js").read_text(encoding="utf-8")
    done_row = now[now.index("function doneRow"):now.index("function doneSummary")]
    assert "outcomeLabel" not in done_row
    assert "done-ago" in done_row and "formatDuration(run.duration_sec)" in done_row


def test_queue_row_labels_age_and_priority_slot():
    now = (STATIC / "now.js").read_text(encoding="utf-8")
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    queue_row = now[now.index("function queueRow"):now.index("function queueBody")]
    assert "queue-priority" in queue_row, "приоритет — отдельный слот"
    assert "t('queueWaiting')" in queue_row, "возраст подписан словами"
    assert re.search(r"\.queue-meta \.queue-priority \{[^}]*tabular-nums", css)