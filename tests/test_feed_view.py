from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"


def test_feed_module_contract():
    feed = (STATIC / "feed.js").read_text(encoding="utf-8")
    assert "export async function loadFeed" in feed
    assert "export function renderFeed" in feed
    assert "api.logEvents" in feed
    for part in ["feed-day", "feed-event", "feed-chips"]:
        assert part in feed, part


def test_feed_day_grouping():
    feed = (STATIC / "feed.js").read_text(encoding="utf-8")
    assert "toDateString" in feed or "dayKey" in feed


def test_log_view_uses_tokens():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".log-row" in css and "var(--line)" in css


def test_feed_wired_into_shell():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "loadFeed" in app and "setupFeedView" in app
    assert "viewFeed" in html and 'data-tab="feed"' in html


def test_feed_and_log_use_shared_tokens():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    for selector in [".feed-chips", ".feed-day", ".feed-event", ".feed-time", ".feed-actions"]:
        assert selector in css, selector
    # Плотность строки лога 40-44px: min-height в этом диапазоне.
    log_row = css.split(".log-row {", 1)[1].split("}", 1)[0]
    assert "min-height:" in log_row
    density = int(log_row.split("min-height:", 1)[1].split("px", 1)[0].strip())
    assert 40 <= density <= 44, density


def test_feed_has_no_emoji():
    feed = (STATIC / "feed.js").read_text(encoding="utf-8")
    ranges = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0xFE0F, 0xFE0F)]
    banned = [ch for ch in feed if any(low <= ord(ch) <= high for low, high in ranges)]
    assert banned == [], banned
