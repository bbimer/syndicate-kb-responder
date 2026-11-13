"""Multi-turn session engine for consecutive argumentative chess in Telegram threads.

Tracks dialogue history stack, dynamically retrieves fresh battlecards and chapters
while deprioritizing already used cards/sections, and coordinates with DeepSeekClient
for Turn 1 (Hook) and Turn 2+ (Counter Matrix).
"""

from __future__ import annotations
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set, Tuple

from src.retrieval.fts_router import FTSRouter
from src.generator.deepseek_client import DeepSeekClient, GenerationResult
from src.utils.humanizer import humanize_text


def extract_variant(text: str, choice: str | int) -> str:
    """Extracts a specific numbered or lettered variant block from generated text."""
    choice_clean = str(choice).strip().upper()
    pattern = rf'\[Вариант\s+{re.escape(choice_clean)}:[^\]]*\]\s*([\s\S]*?)(?=\n\[Вариант|\Z)'
    m = re.search(pattern, text, re.I)
    if m:
        return m.group(1).strip()
    return text.strip()


@dataclass
class DialogueTurn:
    turn_index: int
    role: str  # "opponent" or "us"
    text: str
    card_id: Optional[str] = None
    section_id: Optional[str] = None
    variant_chosen: Optional[int] = None
    timestamp: float = field(default_factory=time.time)


class SessionEngine:
    """Manages sequential multi-turn dialogue state, dynamic KB re-routing, and outbound persistence."""

    def __init__(
        self,
        router: FTSRouter,
        client: DeepSeekClient,
        chat_id: Optional[str] = None,
        deposit_est: str = "500_2000",
        module: Optional[str] = None
    ):
        self.router = router
        self.client = client
        self.chat_id = chat_id
        self.deposit_est = deposit_est
        self.module = module

        self.turns: List[DialogueTurn] = []
        self.used_cards: Set[str] = set()
        self.used_sections: Set[str] = set()

    @property
    def turn_count(self) -> int:
        """Returns number of completed our turns."""
        return sum(1 for t in self.turns if t.role == "us")

    def has_prior_turns(self) -> bool:
        """Returns True if at least one response has already been committed."""
        return any(t.role == "us" for t in self.turns)

    async def process_turn(
        self,
        opponent_text: str
    ) -> Tuple[str, Dict[str, Any], GenerationResult]:
        """Retrieves context with dynamic exclusion of used cards/sections,

        and generates 3 calibrated tactical angles (Turn 1: Hook, Turn 2+: Counter Matrix).
        """
        context = self.router.retrieve_context(
            opponent_text,
            module=self.module,
            deposit_est=self.deposit_est,
            chat_id=self.chat_id,
            exclude_cards=self.used_cards,
            exclude_sections=self.used_sections
        )

        if not self.has_prior_turns():
            # Turn 1: Public Hook Matrix
            result = await self.client.generate_hook(opponent_text, context)
        else:
            # Turn 2+: Multi-turn Counter Matrix
            dialogue_history = [
                {"role": t.role, "text": t.text}
                for t in self.turns
            ]
            result = await self.client.generate_counter(
                dialogue_history=dialogue_history,
                new_reply=opponent_text,
                context=context,
                deposit_est=self.deposit_est
            )

        humanized_output = humanize_text(result.text)
        return humanized_output, context, result

    def commit_turn(
        self,
        opponent_text: str,
        chosen_variant: int | str,
        generated_options: str,
        context: Dict[str, Any],
        message_id: Optional[int] = None
    ) -> str:
        """Appends the opponent's message and our selected variant to session history,

        updates used cards and sections, and commits to chat_outbound_history DB.
        """
        # 1. Record opponent turn
        self.turns.append(
            DialogueTurn(
                turn_index=len(self.turns) + 1,
                role="opponent",
                text=opponent_text
            )
        )

        # 2. Extract and humanize chosen variant
        chosen_str = str(chosen_variant).strip()
        raw_committed = extract_variant(generated_options, chosen_str) if chosen_str in ("1", "2", "3", "A", "B", "C") else generated_options.strip()
        committed_text = humanize_text(raw_committed)

        # 3. Track card and section to exclude in subsequent turns
        card = context.get("battlecard") or {}
        chapter = context.get("chapter") or {}

        card_num = card.get("card_num")
        card_mod = card.get("module")
        card_id = str(card_num) if card_num is not None else (str(card.get("id")) if card.get("id") else None)

        if card_mod and card_num is not None:
            self.used_cards.add(f"{card_mod}_{card_num}")
        if card_id:
            self.used_cards.add(card_id)
        if card.get("id"):
            self.used_cards.add(str(card["id"]))

        sec_num = chapter.get("section_num")
        sec_mod = chapter.get("module")
        sec_id = str(sec_num) if sec_num is not None else (str(chapter.get("id")) if chapter.get("id") else None)

        if sec_mod and sec_num is not None:
            self.used_sections.add(f"{sec_mod}_{sec_num}")
        if sec_id:
            self.used_sections.add(sec_id)
        if chapter.get("id"):
            self.used_sections.add(str(chapter["id"]))
        if chapter.get("section_title"):
            self.used_sections.add(str(chapter["section_title"]))

        # 4. Record our turn
        v_int = int(chosen_str) if chosen_str.isdigit() else None
        self.turns.append(
            DialogueTurn(
                turn_index=len(self.turns) + 1,
                role="us",
                text=committed_text,
                card_id=card_id,
                section_id=sec_id,
                variant_chosen=v_int
            )
        )

        # 5. Commit to chat outbound memory in DB
        chat_ref = self.chat_id or "global"
        self.router.record_outbound(
            chat_id=str(chat_ref),
            our_response_text=committed_text,
            module_id=card_mod or sec_mod,
            section_id=sec_id,
            card_id=card_id,
            thread_topic=opponent_text[:120]
        )

        return committed_text

    def get_history_summary(self) -> List[Dict[str, Any]]:
        """Returns structured history of all turns in this session."""
        return [
            {
                "index": t.turn_index,
                "role": t.role,
                "text": t.text,
                "card_id": t.card_id,
                "section_id": t.section_id,
                "variant_chosen": t.variant_chosen,
                "timestamp": t.timestamp
            }
            for t in self.turns
        ]
