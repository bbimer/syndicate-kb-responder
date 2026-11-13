"""Slang humanizer and typography post-processor for TG chat responses.

Replaces bookish, formal academic phrases and AI typography artifacts (em-dashes,
guillemets) with authentic crypto scalper Telegram chat slang.
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple

# Mapping of formal trading and exchange terms to native scalper chat slang
SLANG_REPLACEMENTS: List[Tuple[re.Pattern, str]] = [
    # Taker / Maker fees (captures optional leading "комиссия/комиссии" to prevent "комиссии комса по рынку")
    (re.compile(r'\b(?:комисси[яиейюь]|комиссиях|комиссиям)?\s*taker\s*fees?\b|\bкомисси[яиейюь]\s+тейкера\b', re.I), 'комса по рынку'),
    (re.compile(r'\b(?:комисси[яиейюь]|комиссиях|комиссиям)?\s*maker\s*fees?\b|\bкомисси[яиейюь]\s+мейкера\b', re.I), 'мейкер-комса'),
    
    # Slippage & market impact
    (re.compile(r'\b(?:market\s*impact)\b', re.I), 'размазывание об стакан'),
    (re.compile(r'\b(?:проскальзывани[еяюем]|slippage)\b', re.I), 'протяжка'),
    
    # Orderbook
    (re.compile(r'\b(?:order\s*book|книг[аеуыой]\s+ордеров)\b', re.I), 'стакан'),
    
    # Prices
    (re.compile(r'\b(?:mark\s*price|цен[аеуыой]\s+маркировки)\b', re.I), 'маркировка'),
    (re.compile(r'\b(?:last\s*price|последн(?:яя|ей|юю)\s+цен[аеуыой])\b', re.I), 'ласт прайс'),
    
    # Orders
    (re.compile(r'\b(?:pending\s*orders?|отложенн(?:ые|ых|ым)\s+ордер(?:а|ов|ам)?)\b', re.I), 'отложки'),
    (re.compile(r'\b(?:pending\s*order|отложенн(?:ый|ого|ому)\s+ордер(?:а|у)?)\b', re.I), 'отложка'),
    (re.compile(r'\b(?:limit\s*orders?|лимитн(?:ые|ых|ым)\s+ордер(?:а|ов|ам)?)\b', re.I), 'лимитки'),
    (re.compile(r'\b(?:limit\s*order|лимитн(?:ый|ого|ому)\s+ордер(?:а|у)?)\b', re.I), 'лимитка'),
    (re.compile(r'\b(?:market\s*orders?|рыночн(?:ые|ых|ым)\s+ордер(?:а|ов|ам)?)\b', re.I), 'маркет-ордера'),
    (re.compile(r'\b(?:market\s*order|рыночн(?:ый|ого|ому)\s+ордер(?:а|у)?)\b', re.I), 'маркет'),

    # Stop hunting / manipulations
    (re.compile(r'\b(?:stop\s*hunting|охот[аеуыой]\s+за\s+стопами)\b', re.I), 'вынос стопов'),
    
    # Terminals
    (re.compile(r'\bтерминал(?:а|е|у|ом)?\s+(CScalp|TigerTrade|Tiger)\b', re.I), r'привод \1'),

    # Public chat anti-ban sanitization (convert internal jargon to organic trader terms)
    (re.compile(r'\b(?:региональн(?:ых|ые|ым|ой|ую)|азиатск(?:их|ие|им|ой|ую))\s+нод(?:ах|ы|ам|е|у|ами)?\b', re.I), 'региональных площадках'),
    (re.compile(r'\bнод(?:ах|ы|ам|е|у|ами)\b', re.I), 'площадках'),
    (re.compile(r'\bшлюз(?:ах|ы|ам|е|у|ами|ов)?\b', re.I), 'маршрутах'),
    (re.compile(r'\bбез\s+риска\b', re.I), 'без направленного риска'),
]


def humanize_text(text: str) -> str:
    """Post-processes generated model text to remove AI slop and apply TG chat styling."""
    if not text:
        return ""

    out = text

    # 1. Replace typographic dashes: em-dash (—), en-dash (–), horizontal bar (―) with simple hyphen
    out = re.sub(r'\s*[—–―]\s*', ' - ', out)
    out = re.sub(r'[—–―]', '-', out)

    # 2. Replace guillemets « » with standard quotes or remove around single slang terms
    out = out.replace('«', '"').replace('»', '"')

    # 3. Apply scalper slang replacements
    for pattern, replacement in SLANG_REPLACEMENTS:
        out = pattern.sub(replacement, out)

    # 4. Clean accidental duplicate words like "комиссия комса" or "комиссии комса"
    out = re.sub(r'\bкомисси[яиейюь]\s+комс([аеуыой])\b', r'комс\1', out, flags=re.I)

    # 5. Clean double quotes around already lowercase words: e.g. "отложка" -> отложка
    out = re.sub(r'"([а-яёa-z0-9_-]{2,20})"', r'\1', out)

    # 6. Clean excessive spaces
    out = re.sub(r'[ \t]+', ' ', out)
    out = re.sub(r' \n', '\n', out)
    out = re.sub(r'\n{3,}', '\n\n', out)

    return out.strip()
