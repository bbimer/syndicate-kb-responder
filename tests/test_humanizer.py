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


def test_anti_ban_replacements():
    input_text = "Мы на азиатских нодах забираем спред без риска через быстрые шлюзы."
    res = humanize_text(input_text)
    assert "нодах" not in res
    assert "азиатских нодах" not in res
    assert "региональных площадках" in res
    assert "без риска" not in res
    assert "без направленного риска" in res
    assert "шлюзы" not in res
    assert "маршрутах" in res


def test_quote_unwrapping_on_lowercase_words():
    input_text = 'Обычная "отложка" и "лимитка" в стакане.'
    res = humanize_text(input_text)
    assert '"отложка"' not in res
    assert 'отложка' in res
    assert '"лимитка"' not in res
    assert 'лимитка' in res


def test_spacing_cleanup():
    input_text = "Текст   с   лишними    пробелами.\n\n\n\nНовый абзац."
    res = humanize_text(input_text)
    assert "   " not in res
    assert "\n\n\n" not in res
