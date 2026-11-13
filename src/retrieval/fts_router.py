"""Fast SQLite FTS5 BM25 Retrieval Router for Syndicate Knowledge Base.

Performs sub-5ms BM25 keyword searches over 70+ battlecards, 35 chapters,
and 196+ glossary terms with module-level filtering.
"""

from __future__ import annotations
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

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

    def record_outbound(
        self,
        chat_id: str,
        our_response_text: str,
        module_id: Optional[str] = None,
        section_id: Optional[str] = None,
        card_id: Optional[str] = None,
        thread_topic: Optional[str] = None
    ) -> int:
        """Records an outbound response to preserve chat memory and continuity."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_outbound_history (
                chat_id, module_id, section_id, card_id, thread_topic, our_response_text
            ) VALUES (?, ?, ?, ?, ?, ?);
        """, (str(chat_id), module_id, section_id, card_id, thread_topic, our_response_text.strip()))
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def get_recent_outbound(self, chat_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieves the most recent outbound responses for a given chat in chronological order."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, chat_id, module_id, section_id, card_id, thread_topic, our_response_text, created_at
            FROM chat_outbound_history
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?;
        """, (str(chat_id), limit))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        # Return in chronological order (oldest to newest)
        return rows[::-1]

    def get_used_sections_and_cards(self, chat_id: str, days: int = 14) -> Tuple[Set[str], Set[str]]:
        """Returns set of section_ids and card_ids used in this chat within the last N days."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT section_id, card_id
            FROM chat_outbound_history
            WHERE chat_id = ? AND created_at >= datetime('now', ?);
        """, (str(chat_id), f"-{days} days"))
        rows = cur.fetchall()
        conn.close()
        used_sections = {str(r["section_id"]) for r in rows if r["section_id"]}
        used_cards = {str(r["card_id"]) for r in rows if r["card_id"]}
        return used_sections, used_cards

    def search_battlecards(
        self,
        query: str,
        module: Optional[str] = None,
        limit: int = 3,
        used_cards: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search battlecards via FTS5 BM25 rank.

        If module filter produces no hits, falls back to global search.
        Deprioritizes battlecards present in used_cards.
        """
        fts_q = self._sanitize_query(query)
        if not fts_q:
            return []

        conn = self._get_connection()
        cur = conn.cursor()

        fetch_limit = max(limit * 3, 10) if used_cards else limit
        results = []
        # 1. Search with module filter if specified
        if module:
            clean_mod = module.strip().upper()
            sql = """
                SELECT b.id, b.module, b.card_num, b.objection, b.answer, b.raw_content, bm25(battlecards_fts) as rank
                FROM battlecards_fts f
                JOIN battlecards b ON f.rowid = b.id
                WHERE battlecards_fts MATCH ? AND b.module = ?
                ORDER BY rank
                LIMIT ?;
            """
            cur.execute(sql, (fts_q, clean_mod, fetch_limit))
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
            cur.execute(sql, (fts_q, fetch_limit))
            results = [dict(row) for row in cur.fetchall()]

        conn.close()

        if used_cards and results:
            unused = []
            used = []
            for r in results:
                card_key_1 = f"{r['module']}_{r['card_num']}"
                card_key_2 = str(r['id'])
                card_key_3 = str(r['card_num'])
                if card_key_1 in used_cards or card_key_2 in used_cards or card_key_3 in used_cards:
                    used.append(r)
                else:
                    unused.append(r)
            results = (unused + used)[:limit]
        else:
            results = results[:limit]

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

    def search_chapters(
        self,
        query: str,
        module: Optional[str] = None,
        limit: int = 2,
        used_sections: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search chapters (Layers 1, 2, 4, 5) via FTS5 BM25 rank.
        
        Deprioritizes sections present in used_sections.
        """
        fts_q = self._sanitize_query(query)
        if not fts_q:
            return []

        conn = self._get_connection()
        cur = conn.cursor()

        fetch_limit = max(limit * 3, 10) if used_sections else limit
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
            cur.execute(sql, (fts_q, clean_mod, fetch_limit))
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
            cur.execute(sql, (fts_q, fetch_limit))
            results = [dict(row) for row in cur.fetchall()]

        conn.close()

        if used_sections and results:
            unused = []
            used = []
            for r in results:
                sec_key_1 = f"{r['module']}_{r['section_num']}"
                sec_key_2 = str(r['id'])
                sec_key_3 = str(r['section_title'])
                if sec_key_1 in used_sections or sec_key_2 in used_sections or sec_key_3 in used_sections:
                    used.append(r)
                else:
                    unused.append(r)
            results = (unused + used)[:limit]
        else:
            results = results[:limit]

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
        deposit_est: Optional[str] = "500_2000",
        chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Unified context retrieval for prompt construction:

        1. Best battlecard (deprioritizing cards used recently in this chat)
        2. Best chapter (with scaled unit economics, deprioritizing used sections)
        3. Relevant glossary terms
        4. Recent chat history / outbound memory for continuity & anti-repetition
        """
        used_sections: Set[str] = set()
        used_cards: Set[str] = set()
        recent_outbound: List[Dict[str, Any]] = []

        if chat_id:
            used_sections, used_cards = self.get_used_sections_and_cards(chat_id, days=14)
            recent_outbound = self.get_recent_outbound(chat_id, limit=5)

        cards = self.search_battlecards(text, module=module, limit=1, used_cards=used_cards if chat_id else None)
        best_card = cards[0] if cards else None

        chapters = self.search_chapters(text, module=module, limit=1, used_sections=used_sections if chat_id else None)
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
            "chat_id": chat_id,
            "chat_memory": [item["our_response_text"] for item in recent_outbound],
            "recent_outbound": recent_outbound,
            "battlecard": best_card,
            "chapter": best_chapter,
            "glossary": glossary
        }
