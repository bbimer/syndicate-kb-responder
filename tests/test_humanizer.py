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


def test_artifact_words_cleanup():
    input_text = "Там риск нулевой, ибо нет движения. Зашел с тем же нотальным объемом. На какой плечо ты залетел?"
    res = humanize_text(input_text)
    assert "ибо" not in res.lower()
    assert "потому что" in res.lower()
    assert "нотальным" not in res.lower()
    assert "номинальным" in res.lower()
    assert "на какой плечо" not in res.lower()
    assert "на какое плечо" in res.lower()
