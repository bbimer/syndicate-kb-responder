"""Unit tests for slang humanizer and text post-processor."""

import pytest
from src.utils.humanizer import humanize_text


def test_dashes_and_quotes_normalization():
    input_text = "«CScalp» работает быстро — однако проскальзывание – неизбежно ― такова физика."
    res = humanize_text(input_text)
    assert "—" not in res
    assert "–" not in res
    assert "―" not in res
    assert "«" not in res
    assert "»" not in res
    assert " - " in res


def test_trading_terms_translation():
    input_text = "В терминал CScalp залетаешь через market order, платишь taker fee и получаешь slippage."
    res = humanize_text(input_text)
    assert "привод CScalp" in res
    assert "маркет" in res
    assert "комса по рынку" in res
    assert "протяжка" in res


def test_order_book_and_mark_price():
    input_text = "В order book видна плотность, но mark price разошлась с last price."
    res = humanize_text(input_text)
    assert "стакан" in res
    assert "маркировка" in res
    assert "ласт прайс" in res


def test_spacing_cleanup():
    input_text = "Текст   с   лишними    пробелами.\n\n\n\nНовый абзац."
    res = humanize_text(input_text)
    assert "   " not in res
    assert "\n\n\n" not in res
