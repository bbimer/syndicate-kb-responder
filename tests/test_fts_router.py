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
