"""Контракты экрана «Доска»: карточка без шума, пустые статусы в рейл,
режим «Секции | Таблица» внутри вкладки «Доска».
"""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"


def test_card_template_has_no_zero_noise():
    board = (STATIC / "board.js").read_text(encoding="utf-8")
    assert "💬" not in board
    assert "↑ ${parents} ↓ ${children}" not in board
    assert "profile-missing-badge" in board and "missing-assignee-chip" not in board


def test_card_contract_selectors_preserved():
    board = (STATIC / "board.js").read_text(encoding="utf-8")
    for attr in ["data-task-id", "data-parent-count", "data-child-count", "data-pulse-id"]:
        assert attr in board, attr
    assert "dependency-port" in board


def test_running_card_has_pulse_line_and_progress():
    board = (STATIC / "board.js").read_text(encoding="utf-8")
    pulse = (STATIC / "pulse.js").read_text(encoding="utf-8")
    assert "max_runtime_seconds" in board
    assert "data-pulse-progress" in board
    assert "data-pulse-progress" in pulse


def test_empty_columns_render_rail():
    board = (STATIC / "board.js").read_text(encoding="utf-8")
    assert "is-empty" in board and "board-rail" in board
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="boardRail"' in html
    assert 'id="boardSections"' in html


def test_board_responsive_rules():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".board-column{min-width:0" in css.replace(" ", "") or "min-width: 0" in css
    assert "@media (max-width: 759px)" in css
    # пустая колонка — узкий рейл, рейл чипов на телефоне
    assert ".board-column.is-empty" in css
    assert ".board-rail" in css
    # тень-подсказка скролла и sticky-шапка секции
    assert "can-scroll-right" in css
    assert ".board-column header { position: sticky" in css


def test_board_bar_has_filters_and_mode_switch():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for control in ["listSearch", "listStatusFilter", "listAssigneeFilter", "listArchived", "boardToActive"]:
        assert f'id="{control}"' in html, control
    assert 'data-board-mode="sections"' in html
    assert 'data-board-mode="table"' in html
    # отдельной вкладки «Таблица» нет — по-прежнему четыре вкладки
    assert re.findall(r'data-tab="(\w+)"', html) == ["now", "board", "feed", "log"]


def test_table_mode_reuses_list_view_inside_board_tab():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    board_tab = html.split('id="viewBoard"', 1)[1]
    assert 'id="viewList"' in board_tab
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "boardSections" in app
    assert "data-board-mode" in app
