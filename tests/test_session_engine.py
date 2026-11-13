import pytest
from unittest.mock import AsyncMock, MagicMock
from config.settings import settings
from src.retrieval.fts_router import FTSRouter
from src.generator.deepseek_client import DeepSeekClient, GenerationResult
from src.generator.session_engine import SessionEngine, extract_variant, DialogueTurn


@pytest.fixture(scope="module")
def router():
    return FTSRouter(settings.db_path)


def test_extract_variant():
    sample_text = """[Вариант 1: Контр-удар "Да, но..."]
Первый вариант текста.

[Вариант 2: Короткий подкол / Раппорт]
Второй вариант текста.

[Вариант 3: Перевод плоскости]
Третий вариант текста."""

    assert extract_variant(sample_text, 1) == "Первый вариант текста."
    assert extract_variant(sample_text, "2") == "Второй вариант текста."
    assert extract_variant(sample_text, 3) == "Третий вариант текста."
    assert extract_variant(sample_text, "A") == sample_text.strip()


def test_session_state_and_tracking(router):
    mock_client = MagicMock(spec=DeepSeekClient)
    session = SessionEngine(router=router, client=mock_client, chat_id="test_chat_999")

    assert not session.has_prior_turns()
    assert session.turn_count == 0
    assert len(session.turns) == 0

    mock_context = {
        "battlecard": {"module": "M04", "card_num": 3, "id": 10},
        "chapter": {"module": "M04", "section_num": 2, "id": 5, "section_title": "Order Types"},
    }

    generated = """[Вариант 1: Контр-удар "Да, но..."]
Серверный стоп в Тайгере режется биржевым matching engine.

[Вариант 2: Короткий подкол]
Типичный Тайгер на волатильности.

[Вариант 3: Перевод плоскости]
Переходи на межбиржевой спред."""

    committed = session.commit_turn(
        opponent_text="Проскальзывает стоп на 2.5%",
        chosen_variant=1,
        generated_options=generated,
        context=mock_context
    )

    assert session.has_prior_turns()
    assert session.turn_count == 1
    assert len(session.turns) == 2
    assert session.turns[0].role == "opponent"
    assert session.turns[0].text == "Проскальзывает стоп на 2.5%"
    assert session.turns[1].role == "us"
    assert "Серверный стоп" in session.turns[1].text
    assert session.turns[1].variant_chosen == 1

    # Verify exclusions tracking
    assert "M04_3" in session.used_cards
    assert "3" in session.used_cards
    assert "M04_2" in session.used_sections
    assert "2" in session.used_sections
    assert "Order Types" in session.used_sections


def test_dynamic_rerouting_exclusions(router):
    """Verifies that excluding the top card from Turn 1 produces a different card in Turn 2."""
    query = "серверный стоп проскальзывание тайгер treyder"
    c1 = router.search_battlecards(query, limit=2)
    assert len(c1) >= 2
    first_card = c1[0]
    first_key = f"{first_card['module']}_{first_card['card_num']}"

    # Search again with first_key excluded
    c2 = router.search_battlecards(query, limit=2, used_cards={first_key, str(first_card['card_num'])})
    assert len(c2) >= 2
    # The previously first card should now be deprioritized and replaced by a fresh card
    top_keys_turn2 = [f"{c['module']}_{c['card_num']}" for c in c2]
    assert first_key != top_keys_turn2[0]


@pytest.mark.asyncio
async def test_3turn_simulation_user_f(router):
    """Simulates the 3-turn argumentative chess duel on User F's real quotes from chat 2964644258."""
    mock_client = MagicMock(spec=DeepSeekClient)

    res1 = GenerationResult(
        text="""[Вариант 1: Контр-удар "Да, но..."]
Серверный тейк и стоп в стакане исполняются маркет-ордером.

[Вариант 2: Короткий подкол / Раппорт]
Тайгер по рынку в волатильность — классический донор для HFT.

[Вариант 3: Перевод плоскости]
Спред на делистингах собирается лимитками без таких сюрпризов.""",
        prompt_tokens=300,
        cached_tokens=0,
        completion_tokens=60,
        total_tokens=360,
        latency_sec=0.5,
        cost_usd=0.0001
    )

    res2 = GenerationResult(
        text="""[Вариант 1: Контр-удар "Да, но..."]
Убрал серверный — получил локальный триггер в софте. Если сокет моргнет, стоп вообще не выставится.

[Вариант 2: Короткий подкол / Раппорт]
Локальный стоп до первого чиха провайдера.

[Вариант 3: Перевод плоскости]
Чем ловить сокеты в приводе, проще забирать перекосы между биржами.""",
        prompt_tokens=400,
        cached_tokens=100,
        completion_tokens=70,
        total_tokens=470,
        latency_sec=0.6,
        cost_usd=0.00012
    )

    res3 = GenerationResult(
        text="""[Вариант 1: Контр-удар "Да, но..."]
При работе по совместительству интрадей в приводе всегда ведет к тильту.

[Вариант 2: Короткий подкол / Раппорт]
Совмещать работу со стаканом — верный способ кормить биржу комсой.

[Вариант 3: Перевод плоскости]
Я сам ушел от монитора — алерты на делистинги приходят раз в день, забираешь спред за 10 минут. Если интересно, маякни в ЛС, скину сетап.""",
        prompt_tokens=500,
        cached_tokens=200,
        completion_tokens=80,
        total_tokens=580,
        latency_sec=0.7,
        cost_usd=0.00014
    )

    mock_client.generate_hook = AsyncMock(return_value=res1)
    mock_client.generate_counter = AsyncMock(side_effect=[res2, res3])

    session = SessionEngine(router=router, client=mock_client, chat_id="2964644258", deposit_est="1000")

    # --- Turn 1: Initial complaint about slippage ---
    turn1_text = "Вообще тейк стоял 0.35. Но они издеваются что-ли. Проскальзывает всё. Один стоп 2% закрывает на 2.52%"
    out1, ctx1, r1 = await session.process_turn(turn1_text)
    assert mock_client.generate_hook.called
    assert not mock_client.generate_counter.called
    committed1 = session.commit_turn(turn1_text, 2, out1, ctx1)
    assert "Тайгер по рынку в волатильность" in committed1
    assert session.turn_count == 1

    # --- Turn 2: Opponent argues he disabled server stop ---
    turn2_text = "Убрал галочки - серверный стоп лосс и серверный тейк профит. Стали тейки тоже проскальзывать в плюс"
    out2, ctx2, r2 = await session.process_turn(turn2_text)
    assert mock_client.generate_counter.call_count == 1
    committed2 = session.commit_turn(turn2_text, 1, out2, ctx2)
    assert "локальный триггер в софте" in committed2
    assert session.turn_count == 2

    # --- Turn 3: Opponent admits lack of time & job burnout ---
    turn3_text = "Да у меня времени мало за графиками сидеть, приходится маневрировать между основной работой и трейдингом"
    out3, ctx3, r3 = await session.process_turn(turn3_text)
    assert mock_client.generate_counter.call_count == 2
    committed3 = session.commit_turn(turn3_text, 3, out3, ctx3)
    assert "алерты на делистинги" in committed3
    assert session.turn_count == 3

    # Check session history stack
    summary = session.get_history_summary()
    assert len(summary) == 6  # 3 opponent turns + 3 our turns
    assert summary[0]["role"] == "opponent"
    assert summary[1]["role"] == "us"
    assert summary[1]["variant_chosen"] == 2
    assert summary[3]["role"] == "us"
    assert summary[3]["variant_chosen"] == 1
    assert summary[5]["role"] == "us"
    assert summary[5]["variant_chosen"] == 3
