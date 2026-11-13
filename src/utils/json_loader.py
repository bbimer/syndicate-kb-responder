"""Robust JSON handoff loader from tg-closer-crm CLI export.

Supports file paths, raw JSON strings, and stdin (-) with automatic regex extraction
to safely ignore surrounding log lines.
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional


def load_lead_context(source: str) -> Dict[str, Any]:
    """Loads lead JSON from stdin ('-'), file path, or raw JSON string."""
    raw_str = ""
    clean_src = source.strip()

    if clean_src == "-":
        raw_str = sys.stdin.read()
    elif Path(clean_src).exists() and Path(clean_src).is_file():
        raw_str = Path(clean_src).read_text(encoding="utf-8")
    else:
        raw_str = clean_src

    # Robust JSON extraction (strip leading/trailing log statements)
    json_match = re.search(r'(\{[\s\S]*\})', raw_str)
    if not json_match:
        raise ValueError(f"Could not parse valid JSON from input: {raw_str[:150]}...")

    payload = json.loads(json_match.group(1))
    return parse_lead_fields(payload)


def parse_lead_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizes lead JSON fields for syndicate-kb-responder routing."""
    raw_mod = payload.get("matched_module", "")
    module_code = None
    if raw_mod:
        mod_match = re.search(r'M0[1-7]', str(raw_mod).upper())
        if mod_match:
            module_code = mod_match.group(0)

    deposit_est = payload.get("deposit_est", "500_2000")
    current_stage = payload.get("current_stage", "In_DM")
    quote_sample = payload.get("quote_sample", "")
    if not quote_sample:
        if payload.get("assembled_thread_text"):
            quote_sample = payload["assembled_thread_text"]
        elif payload.get("messages") and isinstance(payload["messages"], list) and len(payload["messages"]) > 0:
            thread_lines = [f"{m.get('author', 'User')}: {m.get('text', '')}" for m in payload["messages"]]
            quote_sample = "\n".join(thread_lines)
        elif payload.get("thread") and isinstance(payload["thread"], list) and len(payload["thread"]) > 0:
            thread_lines = [f"{m.get('sender_name', m.get('author', 'User'))}: {m.get('text', '')}" for m in payload["thread"]]
            quote_sample = "\n".join(thread_lines)

    chat_id = payload.get("chat_id") or payload.get("source_chat_id")

    return {
        "user_id": payload.get("user_id"),
        "username": payload.get("username"),
        "display_name": payload.get("display_name"),
        "chat_id": chat_id,
        "source_chat_id": chat_id,
        "source_chat_title": payload.get("source_chat_title"),
        "pain_category": payload.get("pain_category", "general"),
        "matched_module": module_code,
        "raw_matched_module": raw_mod,
        "deposit_est": deposit_est,
        "current_stage": current_stage,
        "quote_sample": quote_sample,
        "lead_segment": payload.get("lead_segment", "clean_retail"),
        "thread": payload.get("thread", []),
        "top_slang": payload.get("top_slang", []),
        "raw_payload": payload
    }
