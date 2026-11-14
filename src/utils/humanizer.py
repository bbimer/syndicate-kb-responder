"""Slang humanizer and typography post-processor for TG chat responses.

Normalizes typographic artifacts (em-dashes, guillemets, extra quotes),
cleans whitespace, and enforces strict public chat anti-ban sanitization
(mapping internal jargon like 'ноды', 'шлюзы', 'без риска' to organic terms).
Grammatical inflection of scalper slang is handled directly by LLM prompt rules
to preserve correct Russian case declensions.
"""

from __future__ import annotations
import re
from typing import List, Tuple

# Public chat anti-ban sanitization (convert internal syndicate jargon to organic trader terms)
ANTI_BAN_REPLACEMENTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\b(?:региональн(?:ых|ые|ым|ой|ую)|азиатск(?:их|ие|им|ой|ую))\s+нод(?:ах|ы|ам|е|у|ами)?\b', re.I), 'региональных площадках'),
    (re.compile(r'\bнод(?:ах|ы|ам|е|у|ами)\b', re.I), 'площадках'),
    (re.compile(r'\bшлюз(?:ах|ы|ам|е|у|ами|ов)?\b', re.I), 'маршрутах'),
    (re.compile(r'\bбез\s+риска\b', re.I), 'без направленного риска'),
]


def humanize_text(text: str) -> str:
    """Post-processes generated model text to remove AI slop, typography artifacts, and apply safety filters."""
    if not text:
        return ""

    out = text

    # 1. Replace typographic dashes: em-dash (—), en-dash (–), horizontal bar (―) with simple hyphen
    out = re.sub(r'\s*[—–―]\s*', ' - ', out)
    out = re.sub(r'[—–―]', '-', out)

    # 2. Replace guillemets « » with standard quotes
    out = out.replace('«', '"').replace('»', '"')

    # 3. Apply anti-ban safety sanitization (nodes -> platforms, gateways -> routes, zero-risk -> delta-neutral)
    for pattern, replacement in ANTI_BAN_REPLACEMENTS:
        out = pattern.sub(replacement, out)

    # 4. Clean double quotes around already lowercase words: e.g. "отложка" -> отложка
    out = re.sub(r'"([а-яёa-z0-9_-]{2,20})"', r'\1', out)

    # 5. Clean excessive spaces and newlines
    out = re.sub(r'[ \t]+', ' ', out)
    out = re.sub(r' \n', '\n', out)
    out = re.sub(r'\n{3,}', '\n\n', out)

    return out.strip()
