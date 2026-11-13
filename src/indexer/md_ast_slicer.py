"""Markdown AST Slicer and Indexer for Syndicate Intelligence Knowledge Base.

Indexes 35 chapters (Layers 1, 2, 4, 5 without Layer 3 code/derivations),
74 battlecards (70 curriculum + 4 closer playbook), and 196+ glossary terms
into SQLite FTS5 for sub-millisecond retrieval and prefix caching.
"""

from __future__ import annotations
import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class KnowledgeBaseIndexer:
    def __init__(self, db_path: Path | str, kb_dir: Path | str):
        self.db_path = Path(db_path)
        self.kb_dir = Path(kb_dir)

    def init_db(self) -> None:
        """Initializes SQLite database with WAL mode and FTS5 tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Performance tuning
        cur.execute("PRAGMA journal_mode = WAL;")
        cur.execute("PRAGMA synchronous = NORMAL;")

        # 1. Chapters table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                section_num TEXT NOT NULL,
                section_title TEXT NOT NULL,
                layer1_metaphor TEXT,
                layer2_case TEXT,
                layer4_unit_econ TEXT,
                layer5_script TEXT,
                clean_text TEXT NOT NULL
            );
        """)

        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
                module,
                section_title,
                layer1_metaphor,
                layer2_case,
                layer4_unit_econ,
                layer5_script,
                clean_text,
                content='chapters',
                content_rowid='id'
            );
        """)

        # Sync triggers for chapters
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS chapters_ai AFTER INSERT ON chapters BEGIN
                INSERT INTO chapters_fts(rowid, module, section_title, layer1_metaphor, layer2_case, layer4_unit_econ, layer5_script, clean_text)
                VALUES (new.id, new.module, new.section_title, new.layer1_metaphor, new.layer2_case, new.layer4_unit_econ, new.layer5_script, new.clean_text);
            END;
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS chapters_ad AFTER DELETE ON chapters BEGIN
                INSERT INTO chapters_fts(chapters_fts, rowid, module, section_title, layer1_metaphor, layer2_case, layer4_unit_econ, layer5_script, clean_text)
                VALUES('delete', old.id, old.module, old.section_title, old.layer1_metaphor, old.layer2_case, old.layer4_unit_econ, old.layer5_script, old.clean_text);
            END;
        """)

        # 2. Battlecards table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS battlecards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                card_num INTEGER NOT NULL,
                objection TEXT NOT NULL,
                answer TEXT NOT NULL,
                raw_content TEXT NOT NULL
            );
        """)

        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS battlecards_fts USING fts5(
                module,
                objection,
                answer,
                content='battlecards',
                content_rowid='id'
            );
        """)

        # Sync triggers for battlecards
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS battlecards_ai AFTER INSERT ON battlecards BEGIN
                INSERT INTO battlecards_fts(rowid, module, objection, answer)
                VALUES (new.id, new.module, new.objection, new.answer);
            END;
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS battlecards_ad AFTER DELETE ON battlecards BEGIN
                INSERT INTO battlecards_fts(battlecards_fts, rowid, module, objection, answer)
                VALUES('delete', old.id, old.module, old.objection, old.answer);
            END;
        """)

        # 3. Glossary table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS glossary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                term TEXT NOT NULL,
                definition TEXT NOT NULL,
                raw_content TEXT NOT NULL
            );
        """)

        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS glossary_fts USING fts5(
                module,
                term,
                definition,
                content='glossary',
                content_rowid='id'
            );
        """)

        # Sync triggers for glossary
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS glossary_ai AFTER INSERT ON glossary BEGIN
                INSERT INTO glossary_fts(rowid, module, term, definition)
                VALUES (new.id, new.module, new.term, new.definition);
            END;
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS glossary_ad AFTER DELETE ON glossary BEGIN
                INSERT INTO glossary_fts(glossary_fts, rowid, module, term, definition)
                VALUES('delete', old.id, old.module, old.term, old.definition);
            END;
        """)

        # 4. Outbound chat history for chat memory & anti-repetition (persists across reindexing)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_outbound_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                module_id TEXT,
                section_id TEXT,
                card_id TEXT,
                thread_topic TEXT,
                our_response_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_outbound_chat_id ON chat_outbound_history (chat_id, created_at);
        """)

        conn.commit()
        conn.close()

    @staticmethod
    def _strip_code_blocks(text: str) -> str:
        """Removes code blocks (python/cpp/solidity/etc.) to save tokens."""
        return re.sub(r'```[a-zA-Z0-9_-]*\n.*?```', '', text, flags=re.S).strip()

    @staticmethod
    def _clean_quotes(text: str) -> str:
        """Strips surrounding quotes and brackets from objection text."""
        return text.strip().strip('«»"\'*[]').strip()

    def parse_module_file(self, file_path: Path, module: str) -> Tuple[int, int, int]:
        """Parses a single curriculum module file (M01-M07).

        Returns: (chapters_count, battlecards_count, glossary_count)
        """
        raw_text = file_path.read_text(encoding="utf-8")

        # 1. Cut off Section VIII entirely
        s8_match = re.search(r'^##\s+РАЗДЕЛ VIII', raw_text, re.M)
        if s8_match:
            text = raw_text[:s8_match.start()]
        else:
            text = raw_text

        chapters_indexed = 0
        battlecards_indexed = 0
        glossary_indexed = 0

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # 2. Extract Section I to V (Chapters)
        section_pattern = re.compile(
            r'^##\s+РАЗДЕЛ\s+([IVX]+):\s*(.+?)$(.*?)(?=^##\s+РАЗДЕЛ|\Z)',
            re.M | re.S
        )

        for sec_match in section_pattern.finditer(text):
            sec_num = sec_match.group(1).strip()
            sec_title = sec_match.group(2).strip()
            sec_body = sec_match.group(3)

            # Skip Section VI (Battlecards) and VII (Glossary) here
            if sec_num in ("VI", "VII"):
                continue

            # Split section into H3 blocks
            h3_blocks = re.split(r'(^###\s+\d+\.\d+\..*?)(?=^###\s+\d+\.\d+|\Z)', sec_body, flags=re.M | re.S)

            layer1_metaphor = ""
            layer2_case = ""
            layer4_unit_econ = ""
            layer5_script = ""

            for block in h3_blocks:
                b = block.strip()
                if not b:
                    continue

                # Layer 1: Metaphor
                if re.search(r'^###\s+\d+\.\d+\.\s*(?:МЕТАФОРА|Метафора & Интуиция)', b, re.M | re.I):
                    layer1_metaphor = self._strip_code_blocks(b)
                # Layer 2: Case & Forensics
                elif re.search(r'^###\s+\d+\.\d+\.\s*(?:КЕЙС|Институциональный прецедент)', b, re.M | re.I):
                    layer2_case = self._strip_code_blocks(b)
                # Layer 3: Technical Proof -> STRIP (Both X.3 and X.5)
                elif re.search(r'^###\s+\d+\.\d+\.\s*(?:ТЕХНИЧЕСКИЙ ПРУФ|Технический пруф)', b, re.M | re.I):
                    continue
                # Layer 4: Unit Economics
                elif re.search(r'^###\s+\d+\.\d+\.\s*(?:UNIT-ЭКОНОМИКА|Unit-экономика)', b, re.M | re.I):
                    layer4_unit_econ = self._strip_code_blocks(b)
                # Layer 5: Closing Script
                elif re.search(r'^###\s+\d+\.\d+\.\s*(?:СКРИПТ ЗАКРЫТИЯ|Боевой скрипт закрытия)', b, re.M | re.I):
                    cleaned_script = self._strip_code_blocks(b)
                    # In M01 and M04-M07, prioritize Vector A for retail $500-$2k
                    va_match = re.search(r'(####\s+Вектор\s+[AА].*?)(?=####\s+Вектор|\Z)', cleaned_script, re.S)
                    if va_match:
                        layer5_script = va_match.group(1).strip()
                    else:
                        layer5_script = cleaned_script

            # Assemble compact clean_text
            clean_parts = []
            if layer1_metaphor:
                clean_parts.append(layer1_metaphor)
            if layer2_case:
                clean_parts.append(layer2_case)
            if layer4_unit_econ:
                clean_parts.append(layer4_unit_econ)
            if layer5_script:
                clean_parts.append(layer5_script)

            clean_text = "\n\n".join(clean_parts)

            cur.execute("""
                INSERT INTO chapters (module, section_num, section_title, layer1_metaphor, layer2_case, layer4_unit_econ, layer5_script, clean_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (module, sec_num, sec_title, layer1_metaphor, layer2_case, layer4_unit_econ, layer5_script, clean_text))
            chapters_indexed += 1

        # 3. Extract Section VI (Battlecards)
        s6_match = re.search(r'^##\s+РАЗДЕЛ VI.*?(?=^##\s+РАЗДЕЛ VII|\Z)', text, re.M | re.S)
        if s6_match:
            s6_text = s6_match.group(0)
            if module in ("M02", "M03"):
                card_regex = re.compile(r'^###\s+КАРТОЧКА\s+(\d+)[:\.]?\s*(.+?)$(.*?)(?=^###\s+КАРТОЧКА|\Z)', re.M | re.S | re.I)
            else:
                card_regex = re.compile(r'^####\s+Боевая карточка\s+(\d+)[:\.]?\s*(.+?)$(.*?)(?=^####\s+Боевая карточка|\Z)', re.M | re.S | re.I)

            for cm in card_regex.finditer(s6_text):
                card_num = int(cm.group(1))
                objection = self._clean_quotes(cm.group(2))
                body = self._strip_code_blocks(cm.group(3)).strip()
                raw_card = f"{objection}\n\n{body}"

                cur.execute("""
                    INSERT INTO battlecards (module, card_num, objection, answer, raw_content)
                    VALUES (?, ?, ?, ?, ?);
                """, (module, card_num, objection, body, raw_card))
                battlecards_indexed += 1

        # 4. Extract Section VII (Glossary)
        s7_match = re.search(r'^##\s+РАЗДЕЛ VII.*?(?=^##\s+РАЗДЕЛ VIII|\Z)', raw_text, re.M | re.S)
        if s7_match:
            s7_text = s7_match.group(0)
            # Match: 1. **CLOB (Central Limit Order Book):** ...
            term_matches = re.finditer(r'^\d+\.\s+\*\*(.+?)\*\*[:\s]+(.*?)(?=^\d+\.\s+\*\*|\Z)', s7_text, re.M | re.S)
            for tm in term_matches:
                term = self._clean_quotes(tm.group(1))
                definition = self._strip_code_blocks(tm.group(2)).strip()
                raw_term = f"{term}: {definition}"

                cur.execute("""
                    INSERT INTO glossary (module, term, definition, raw_content)
                    VALUES (?, ?, ?, ?);
                """, (module, term, definition, raw_term))
                glossary_indexed += 1

        conn.commit()
        conn.close()
        return chapters_indexed, battlecards_indexed, glossary_indexed

    def parse_closer_playbook(self, file_path: Path) -> int:
        """Parses M01_Fast_Track_Closer.md for the 4 core objection answers.

        Returns: count of battlecards indexed (4)
        """
        raw_text = file_path.read_text(encoding="utf-8")
        idx = raw_text.find("## МОДУЛЬ 4. БОЕВЫЕ ОТВЕТЫ НА ГЛАВНЫЕ ВОЗРАЖЕНИЯ")
        if idx == -1:
            return 0

        sec_text = raw_text[idx:]
        cards = re.findall(r'\*\s+\*\*«(.+?)»\*\*\s*\n(.*?)(?=\*\s+\*\*«|\Z)', sec_text, re.S)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        indexed = 0

        for i, (q, a) in enumerate(cards, 1):
            objection = self._clean_quotes(q)
            answer = self._strip_code_blocks(a).strip()
            raw_card = f"{objection}\n\n{answer}"

            cur.execute("""
                INSERT INTO battlecards (module, card_num, objection, answer, raw_content)
                VALUES (?, ?, ?, ?, ?);
            """, ("FAST_TRACK", i, objection, answer, raw_card))
            indexed += 1

        conn.commit()
        conn.close()
        return indexed

    def parse_day1_dictionary(self, file_path: Path) -> int:
        """Parses Day 1 Dictionary of 55 market mechanics and terms into glossary table."""
        raw_text = file_path.read_text(encoding="utf-8")
        matches = list(re.finditer(r'^###\s+(\d+)\.\s*(.+?)$', raw_text, re.M))
        if not matches:
            return 0

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        indexed = 0

        for i, m in enumerate(matches):
            raw_title = m.group(2).strip()
            clean_title = re.sub(r'[\s`]*\[(?:YT|WEB)\][\s`]*$', '', raw_title).strip()
            clean_title = self._clean_quotes(clean_title)

            start_pos = m.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
            body = raw_text[start_pos:end_pos].strip()

            # Clean source tags, markdown horizontal rules, and code blocks
            body = re.sub(r'^\*Источник:.*?\*\s*', '', body, flags=re.M)
            body = re.sub(r'^---\s*$', '', body, flags=re.M).strip()
            body = self._strip_code_blocks(body)

            raw_term = f"{clean_title}: {body}"

            cur.execute("""
                INSERT INTO glossary (module, term, definition, raw_content)
                VALUES (?, ?, ?, ?);
            """, ("M01", clean_title, body, raw_term))
            indexed += 1

        conn.commit()
        conn.close()
        return indexed

    def index_all(self) -> Dict[str, int]:
        """Discovers knowledge base files and runs full indexing.
        
        Preserves chat_outbound_history across re-indexing runs!
        """
        # Initialize DB and tables if not already present
        self.init_db()

        # Reset KB content tables while strictly PRESERVING chat_outbound_history
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.executescript("""
            DROP TABLE IF EXISTS chapters_fts;
            DROP TABLE IF EXISTS chapters;
            DROP TABLE IF EXISTS battlecards_fts;
            DROP TABLE IF EXISTS battlecards;
            DROP TABLE IF EXISTS glossary_fts;
            DROP TABLE IF EXISTS glossary;
        """)
        conn.commit()
        conn.close()

        # Re-initialize dropped tables
        self.init_db()

        module_paths = {
            "M01": self.kb_dir / "20_Практика_и_Кейсы" / "M01_Analytical_Playbook.md",
            "M02": self.kb_dir / "10_База_знаний" / "📖 День 2 — Архитектура бирж и маркет-мейкинг.md",
            "M03": self.kb_dir / "10_База_знаний" / "📖 День 3 — Деривативы и дельта-нейтральность.md",
            "M04": self.kb_dir / "10_База_знаний" / "📖 День 4 — Микроструктура биржевого стакана и поток ордеров.md",
            "M05": self.kb_dir / "10_База_знаний" / "📖 День 5 — Блокчейн-инфраструктура и ончейн-логистика.md",
            "M06": self.kb_dir / "10_База_знаний" / "📖 День 6 — Управление рисками, хеджирование и безопасность.md",
            "M07": self.kb_dir / "10_База_знаний" / "📖 День 7 — Аналитический стек и системное преимущество.md",
        }

        closer_path = self.kb_dir / "20_Практика_и_Кейсы" / "M01_Fast_Track_Closer.md"

        day1_paths = [
            self.kb_dir / "10_База_знаний" / "📖 День 1 — Словарь терминов и механик рынка.md",
            Path(r"D:\Obsidian\Syndicate Intelligence\Syndicate Intelligence\10_База_знаний\📖 День 1 — Словарь терминов и механик рынка.md"),
            Path(r"C:\Users\root\Desktop\_Intelligence\nullspread-research-academy\exports\notebooklm_pack\Day_1_Dictionary_Master_55_Terms.md"),
        ]

        total_chapters = 0
        total_battlecards = 0
        total_glossary = 0

        # Index Day 1 Dictionary (55 terms)
        for d1_p in day1_paths:
            if d1_p.exists():
                d1_count = self.parse_day1_dictionary(d1_p)
                total_glossary += d1_count
                break

        for mod, path in module_paths.items():
            if path.exists():
                c, b, g = self.parse_module_file(path, mod)
                total_chapters += c
                total_battlecards += b
                total_glossary += g

        if closer_path.exists():
            fc = self.parse_closer_playbook(closer_path)
            total_battlecards += fc

        return {
            "modules": len(module_paths),
            "chapters": total_chapters,
            "battlecards": total_battlecards,
            "glossary": total_glossary,
        }
