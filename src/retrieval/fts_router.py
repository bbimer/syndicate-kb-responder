"""Fast SQLite FTS5 BM25 Retrieval Router for Syndicate Knowledge Base.

Performs sub-5ms BM25 keyword searches over 70+ battlecards, 35 chapters,
and 196+ glossary terms with module-level filtering.
"""

from __future__ import annotations
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.indexer.unit_econ_scaler import scale_unit_econ_text


class FTSRouter:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _sanitize_query(query: str) -> str:
        """Sanitizes raw text into safe FTS5 query tokens."""
        # Find words (Latin, Cyrillic, digits)
        tokens = re.findall(r'[a-zA-Zа-яА-Я0-9_]+', query)
        # Keep tokens with length >= 2
        clean_tokens = [t for t in tokens if len(t) >= 2]
        if not clean_tokens:
            return ""
        # Build OR query for high recall
        return " OR ".join(f'"{t}"' for t in clean_tokens)

    def search_battlecards(self, query: str, module: Optional[str] = None, limit: int = 3) -> List[Dict[str, Any]]:
        """Search battlecards via FTS5 BM25 rank.

        If module filter produces no hits, falls back to global search.
        """
        fts_q = self._sanitize_query(query)
        if not fts_q:
            return []

        conn = self._get_connection()
        cur = conn.cursor()

        results = []
        # 1. Search with module filter if specified
        if module:
            clean_mod = module.strip().upper()
            if not clean_mod.startswith("M0") and clean_mod.startswith("M"):
                clean_mod = clean_mod  # e.g. M04
            sql = """
                SELECT b.id, b.module, b.card_num, b.objection, b.answer, b.raw_content, bm25(battlecards_fts) as rank
                FROM battlecards_fts f
                JOIN battlecards b ON f.rowid = b.id
                WHERE battlecards_fts MATCH ? AND b.module = ?
                ORDER BY rank
                LIMIT ?;
            """
            cur.execute(sql, (fts_q, clean_mod, limit))
            results = [dict(row) for row in cur.fetchall()]

        # 2. If no results or no module filter, do global search
        if not results:
            sql = """
                SELECT b.id, b.module, b.card_num, b.objection, b.answer, b.raw_content, bm25(battlecards_fts) as rank
                FROM battlecards_fts f
                JOIN battlecards b ON f.rowid = b.id
                WHERE battlecards_fts MATCH ?
                ORDER BY rank
                LIMIT ?;
            """
            cur.execute(sql, (fts_q, limit))
            results = [dict(row) for row in cur.fetchall()]

        conn.close()
        return results

    def get_battlecard(self, module: str, card_num: int) -> Optional[Dict[str, Any]]:
        """Direct lookup of a battlecard by module and card number."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, module, card_num, objection, answer, raw_content FROM battlecards WHERE module = ? AND card_num = ?;",
            (module.strip().upper(), card_num)
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def search_chapters(self, query: str, module: Optional[str] = None, limit: int = 2) -> List[Dict[str, Any]]:
        """Search chapters (Layers 1, 2, 4, 5) via FTS5 BM25 rank."""
        fts_q = self._sanitize_query(query)
        if not fts_q:
            return []

        conn = self._get_connection()
        cur = conn.cursor()

        results = []
        if module:
            clean_mod = module.strip().upper()
            sql = """
                SELECT c.id, c.module, c.section_num, c.section_title,
                       c.layer1_metaphor, c.layer2_case, c.layer4_unit_econ, c.layer5_script,
                       c.clean_text, bm25(chapters_fts) as rank
                FROM chapters_fts f
                JOIN chapters c ON f.rowid = c.id
                WHERE chapters_fts MATCH ? AND c.module = ?
                ORDER BY rank
                LIMIT ?;
            """
            cur.execute(sql, (fts_q, clean_mod, limit))
            results = [dict(row) for row in cur.fetchall()]

        if not results:
            sql = """
                SELECT c.id, c.module, c.section_num, c.section_title,
                       c.layer1_metaphor, c.layer2_case, c.layer4_unit_econ, c.layer5_script,
                       c.clean_text, bm25(chapters_fts) as rank
                FROM chapters_fts f
                JOIN chapters c ON f.rowid = c.id
                WHERE chapters_fts MATCH ?
                ORDER BY rank
                LIMIT ?;
            """
            cur.execute(sql, (fts_q, limit))
            results = [dict(row) for row in cur.fetchall()]

        conn.close()
        return results

    def search_glossary(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search glossary terms via FTS5 BM25 rank."""
        fts_q = self._sanitize_query(query)
        if not fts_q:
            return []

        conn = self._get_connection()
        cur = conn.cursor()
        sql = """
            SELECT g.id, g.module, g.term, g.definition, bm25(glossary_fts) as rank
            FROM glossary_fts f
            JOIN glossary g ON f.rowid = g.id
            WHERE glossary_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
        """
        cur.execute(sql, (fts_q, limit))
        results = [dict(row) for row in cur.fetchall()]
        conn.close()
        return results

    def retrieve_context(
        self,
        text: str,
        module: Optional[str] = None,
        deposit_est: Optional[str] = "500_2000"
    ) -> Dict[str, Any]:
        """Unified context retrieval for prompt construction:

        1. Best battlecard
        2. Best chapter (with scaled unit economics)
        3. Relevant glossary terms
        """
        cards = self.search_battlecards(text, module=module, limit=1)
        best_card = cards[0] if cards else None

        chapters = self.search_chapters(text, module=module, limit=1)
        best_chapter = None
        if chapters:
            ch = chapters[0]
            # Scale Layer 4 unit economics for retail deposit
            scaled_l4 = ""
            if ch.get("layer4_unit_econ"):
                scaled_l4 = scale_unit_econ_text(ch["layer4_unit_econ"], deposit_est=deposit_est)
            
            best_chapter = {
                "id": ch["id"],
                "module": ch["module"],
                "section_num": ch["section_num"],
                "section_title": ch["section_title"],
                "layer1_metaphor": ch.get("layer1_metaphor", ""),
                "layer2_case": ch.get("layer2_case", ""),
                "layer4_unit_econ_scaled": scaled_l4,
                "layer5_script": ch.get("layer5_script", ""),
                "clean_text": ch.get("clean_text", "")
            }

        glossary = self.search_glossary(text, limit=2)

        return {
            "query": text,
            "module_filter": module,
            "deposit_est": deposit_est,
            "battlecard": best_card,
            "chapter": best_chapter,
            "glossary": glossary
        }
