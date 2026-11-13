"""Unit tests for prompt builders and option extractors."""

import pytest
from src.generator.prompts import (
    STATIC_SYSTEM_PREFIX,
    build_hook_prompt,
    build_shield_prompt,
    build_followup_prompt
)
from cli import extract_variant


def test_system_prefix_integrity():
    assert "Syndicate Intelligence" in STATIC_SYSTEM_PREFIX
    assert "Cash & Carry" in STATIC_SYSTEM_PREFIX
    assert "$50k+" in STATIC_SYSTEM_PREFIX
    assert "Secure Enclave" in STATIC_SYSTEM_PREFIX
    assert "App Attest" in STATIC_SYSTEM_PREFIX
    assert "НЕ продаем софт" in STATIC_SYSTEM_PREFIX
    assert "микро-тест $20" in STATIC_SYSTEM_PREFIX


def test_build_hook_prompt_mechanics_and_chat_memory():
    context = {
        "chapter": {
            "module": "M04",
            "section_num": "IV",
            "layer1_metaphor": "Метафора очереди на кассе",
            "layer2_case": "Кейс слива ликвидности"
        },
        "battlecard": {
            "objection": "Почему стоп выбило ниже цены?",
            "answer": "Серверный стоп посылает рыночный ордер в стакан"
        },
        "chat_memory": [
            "вчера разбирали задержку тигртрейда на 150мс",
            "стоп по рынку всегда съедает спред"
        ]
    }
    prompt = build_hook_prompt("Выбило стоп на 2.5% вместо 2%", context)
    
    assert "ИСТОРИЯ ТВОИХ ПРОШЛЫХ СООБЩЕНИЙ В ЭТОМ ЧАТЕ:" in prompt
    assert "вчера разбирали задержку" in prompt
    assert "Правило 80/20" in prompt
    assert "[Вариант 1: Короткая реплика]" in prompt
    assert "[Вариант 2: Разбор механики по делу]" in prompt
    assert "[Вариант 3: С мостиком на свой подход]" in prompt
    # Check that old hardcoded cliches are not forced
    assert "«База / Всё так...»" not in prompt
    assert "Gotbit, Delphi Digital" not in prompt


def test_build_shield_prompt_in_dm_rules():
    context = {"battlecard": {"answer": "Суть ответа"}}
    prompt = build_shield_prompt("А где гарантии?", context, stage="In_DM")
    assert "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО предлагать тест на $20" in prompt
    assert "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО просить скрин баланса" in prompt
    assert "Bybit, OKX" in prompt


def test_build_shield_prompt_legend_rules():
    context = {"battlecard": {"answer": "Суть ответа"}}
    prompt = build_shield_prompt("Зачем делишься?", context, stage="Legend_&_Media")
    assert "App Attest" in prompt
    assert "лимит 4 круга" in prompt


def test_build_followup_prompt():
    context = {"battlecard": {"answer": "Отложка в стакане экономит комиссию"}}
    prompt = build_followup_prompt(
        thread_context="Обсуждали проскальзывание стопов",
        last_our_message="стоп по рынку всегда бьет в чужой бид",
        lead_reply="я торгую через CScalp, там вроде быстро все",
        context=context
    )
    assert "[Вариант A: Раппорт и уточнение]" in prompt
    assert "[Вариант B: Скрытая наживка]" in prompt
    assert "[Вариант C: Мостик в ЛС]" in prompt
    assert "ноды" in prompt  # forbidden list check
    assert "без риска" in prompt  # forbidden list check
    assert "телемагазина" in prompt  # tv shop questions ban check


def test_extract_variant_helper():
    text = """[Вариант 1: Короткая реплика]
ты маркетом залетал или лимитку протянуло?

[Вариант 2: Разбор механики по делу]
Серверный стоп бьет маркетом в пустой стакан, поэтому и налило 2.52%.

[Вариант 3: С мостиком на свой подход]
Сам ушел в дельта-нейтральный фандинг, чтобы не кормить биржу тейкер-комсой."""

    v1 = extract_variant(text, "1")
    assert v1 == "ты маркетом залетал или лимитку протянуло?"
    v2 = extract_variant(text, "2")
    assert "Серверный стоп" in v2
    v3 = extract_variant(text, "3")
    assert "дельта-нейтральный" in v3
