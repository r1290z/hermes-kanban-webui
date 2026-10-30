"""Контракт типографики (спека §5.2): минимальный кегль вторичного текста — 11.5px.

11px допускается ТОЛЬКО для секционных меток: правило с таким кеглем обязано
объявлять text-transform: uppercase и letter-spacing. Всё остальное — от 11.5px.
Тест читает static/style.css как текст: он ловит регресс, который живой прогон
поймает только глазами (в CSS нет рантайм-ошибки для мелкого кегля).
"""
import re
from pathlib import Path

STYLE = Path(__file__).resolve().parents[1] / "static" / "style.css"

COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
FONT_SIZE_RE = re.compile(r"font-size:\s*([0-9.]+)px")

MIN_SECONDARY_PX = 11.5


def _rules():
    css = COMMENT_RE.sub("", STYLE.read_text(encoding="utf-8"))
    # Вложенные @media разбираются как отдельные правила: внешний блок содержит
    # фигурные скобки и под шаблон не попадает, а внутренние правила — попадают.
    for selector, body in RULE_RE.findall(css):
        selector = " ".join(selector.split())
        yield selector, body


def _small_font_rules():
    out = []
    for selector, body in _rules():
        for value in FONT_SIZE_RE.findall(body):
            if float(value) < MIN_SECONDARY_PX:
                out.append((selector, float(value), body))
    return out


def test_no_secondary_text_below_min_px():
    offenders = [
        f"{selector} → {value:g}px"
        for selector, value, body in _small_font_rules()
        if "text-transform: uppercase" not in body or "letter-spacing" not in body
    ]
    assert not offenders, (
        "вторичный текст мельче "
        f"{MIN_SECONDARY_PX}px и это не секционная метка (§5.2): " + "; ".join(offenders)
    )


def test_no_font_size_below_11px():
    too_small = [
        f"{selector} → {value:g}px"
        for selector, value, body in _small_font_rules()
        if value < 11
    ]
    assert not too_small, "кегль ниже 11px запрещён (§5.2): " + "; ".join(too_small)


def test_section_labels_are_uppercase_and_tracked():
    """Обратная сторона контракта: у мелких меток есть и uppercase, и трекинг."""
    labels = [(sel, val, body) for sel, val, body in _small_font_rules() if val < MIN_SECONDARY_PX]
    assert labels, "ожидались секционные метки 11px — если их нет, правило из спеки пропало"
    for selector, value, body in labels:
        assert "text-transform: uppercase" in body, selector
        assert re.search(r"letter-spacing:\s*\.[0-9]+em", body), selector
