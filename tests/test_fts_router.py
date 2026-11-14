import pytest
from config.settings import settings
from src.retrieval.fts_router import FTSRouter


@pytest.fixture(scope="module")
def router():
    # Uses the indexed db at settings.db_path
    return FTSRouter(settings.db_path)


def test_sanitize_query():
    q = FTSRouter._sanitize_query("У проекта официальный аудит, смарт-контракт надежен?")
    assert '"проекта"' in q
    assert '"официальный"' in q
    assert '"аудит"' in q
    assert "?" not in q


def test_search_battlecard_adspower(router):
    cards = router.search_battlecards("Почему ты не наделаешь 50 профилей в AdsPower?")
    assert len(cards) > 0
    top = cards[0]
    assert "AdsPower" in top["objection"] or "AdsPower" in top["answer"]
    assert top["module"] == "FAST_TRACK"


def test_search_battlecard_audit(router):
    cards = router.search_battlecards("У проекта официальный аудит смарт-контракта", module="M01")
    assert len(cards) > 0
    top = cards[0]
    assert "аудит" in top["objection"].lower()
    assert top["module"] == "M01"


def test_search_chapters(router):
    chapters = router.search_chapters("механика газа EIP-1559 аукцион приоритета", module="M01")
    assert len(chapters) > 0
    top = chapters[0]
    assert "1559" in top["section_title"]
    assert top["module"] == "M01"


def test_search_glossary(router):
    terms = router.search_glossary("CLOB order book")
    assert len(terms) > 0
    top = terms[0]
    assert "CLOB" in top["term"]


def test_retrieve_context(router):
    ctx = router.retrieve_context(
        text="Зачем мне ваш софт, если у проекта есть аудит?",
        module="M01",
        deposit_est="500_2000"
    )
    assert ctx["battlecard"] is not None
    assert "аудит" in ctx["battlecard"]["objection"].lower()
    assert ctx["chapter"] is not None
    assert ctx["deposit_est"] == "500_2000"


def test_chat_outbound_history_and_deprioritization(router):
    test_chat = "test_chat_deprioritize_999"
    
    # 1. Record outbound response
    row_id = router.record_outbound(
        chat_id=test_chat,
        our_response_text="Тут дело в сервере TigerTrade, серверный стоп бьет по рынку.",
        module_id="M04",
        section_id="IV",
        card_id="FAST_TRACK_1",
        thread_topic="stop loss issue"
    )
    assert row_id > 0

    # 2. Get recent outbound
    recent = router.get_recent_outbound(test_chat, limit=5)
    assert len(recent) >= 1
    assert "TigerTrade" in recent[-1]["our_response_text"]

    # 3. Get used sections and cards
    used_sections, used_cards = router.get_used_sections_and_cards(test_chat, days=14)
    assert "IV" in used_sections
    assert "FAST_TRACK_1" in used_cards

    # 4. Search battlecards with used_cards should deprioritize used card
    cards = router.search_battlecards("AdsPower ферма", used_cards={"FAST_TRACK_1"})
    if len(cards) > 1:
        # If multiple cards matched, the first one should not be FAST_TRACK_1 unless all are used
        assert f"{cards[0]['module']}_{cards[0]['card_num']}" != "FAST_TRACK_1" or len(cards) == 1

    # 5. Retrieve context with chat_id
    ctx = router.retrieve_context(
        text="Почему выбило стоп на 2.5% вместо 2.0%?",
        chat_id=test_chat
    )
    assert ctx["chat_id"] == test_chat
    assert len(ctx["chat_memory"]) >= 1
    assert "TigerTrade" in ctx["chat_memory"][-1]


def test_slang_query_expansion_and_module_inference():
    # 1. Martingale / averaging / falling knife -> M07
    q1 = "на падающем ноже сижу не дышу маржи впритык"
    expanded1 = FTSRouter.expand_query(q1)
    assert "мартингейл" in expanded1
    assert "ликвидация" in expanded1
    assert FTSRouter.infer_module_from_slang(q1) == "M07"

    # 2. Stop loss / breakeven / slippage -> M04
    q2 = "сняло тиком в безубыток серверный стоп протянуло"
    expanded2 = FTSRouter.expand_query(q2)
    assert "проскальзывание" in expanded2
    assert FTSRouter.infer_module_from_slang(q2) == "M04"

    # 3. Delisting / cross-exchange / stuck -> M02
    q3 = "делистинг монеты с биржи вывод закрыли"
    expanded3 = FTSRouter.expand_query(q3)
    assert "спред" in expanded3
    assert FTSRouter.infer_module_from_slang(q3) == "M02"

    # 4. AML / dirty crypto -> M06
    q4 = "помытые usdt грязный амл чекер блок вывод"
    expanded4 = FTSRouter.expand_query(q4)
    assert "Chainalysis" in expanded4
    assert FTSRouter.infer_module_from_slang(q4) == "M06"

    # 5. Pump / abnormal volume -> M01
    q5 = "памп без новостей в стакане плотности айсберг"
    expanded5 = FTSRouter.expand_query(q5)
    assert "манипуляции" in expanded5
    assert FTSRouter.infer_module_from_slang(q5) == "M01"

    # 6. Funding / cash & carry -> M03
    q6 = "фандинг ставка финансирования дельта хедж"
    expanded6 = FTSRouter.expand_query(q6)
    assert "бессрочные" in expanded6
    assert FTSRouter.infer_module_from_slang(q6) == "M03"

