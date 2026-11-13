#!/usr/bin/env python3
"""Syndicate Knowledge Base Responder CLI.

Ultra-fast objection-handling, public hook generator, and follow-up dialog responder
powered by DeepSeek v4.1, AST Markdown slicing of the 7-module Obsidian curriculum,
Day 1 55-term dictionary, FTS5 BM25 retrieval with chat history deprioritization,
and strict prefix caching.
"""

from __future__ import annotations
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config.settings import settings
from src.indexer.md_ast_slicer import KnowledgeBaseIndexer
from src.retrieval.fts_router import FTSRouter
from src.generator.deepseek_client import DeepSeekClient
from src.generator.session_engine import SessionEngine, extract_variant
from src.utils.json_loader import load_lead_context
from src.utils.humanizer import humanize_text

console = Console()


def copy_to_clipboard(text: str) -> bool:
    """Copies text to the system clipboard on Windows using built-in clip.exe."""
    if not text:
        return False
    try:
        subprocess.run(["clip"], input=text, text=True, encoding="utf-8", capture_output=True, check=True)
        return True
    except Exception:
        return False


def prompt_user_choice(prompt_msg: str) -> str:
    """Safely prompts the operator for a choice.
    
    Supports both interactive TTY and piped console runs on Windows.
    Safely skips in automated/headless agent runs.
    """
    # If running in automated agent harness without interactive user attached, skip
    if os.environ.get("ANTIGRAVITY_AGENT") == "1" and not sys.stdin.isatty():
        return ""

    # 1. Direct interactive TTY
    if sys.stdin.isatty():
        try:
            return input(prompt_msg).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    # 2. Piped input on Windows: attach to console input device
    if os.name == 'nt':
        try:
            with open("CONIN$", "r") as con:
                sys.stdout.write(prompt_msg)
                sys.stdout.flush()
                return con.readline().strip()
        except Exception:
            pass

    return ""


def cmd_index(args: argparse.Namespace) -> None:
    """Indexes the Obsidian knowledge base into SQLite FTS5."""
    kb_dir = Path(args.kb_dir) if args.kb_dir else settings.kb_dir
    db_path = Path(args.db_path) if args.db_path else settings.db_path

    if not kb_dir.exists():
        console.print(f"[bold red]Knowledge base directory not found: {kb_dir}[/bold red]")
        sys.exit(1)

    console.print(f"[bold cyan]Indexing knowledge base from:[/bold cyan] {kb_dir}")
    console.print(f"[bold cyan]Target database:[/bold cyan] {db_path}")

    indexer = KnowledgeBaseIndexer(db_path, kb_dir)
    stats = indexer.index_all()

    table = Table(title="Knowledge Base Index Summary", show_header=True, header_style="bold green")
    table.add_column("Entity", style="cyan")
    table.add_column("Count", justify="right", style="bold yellow")
    table.add_row("Modules (M01–M07)", str(stats["modules"]))
    table.add_row("Chapters (Layers 1, 2, 4, 5)", str(stats["chapters"]))
    table.add_row("Battlecards (70 module + 4 closer)", str(stats["battlecards"]))
    table.add_row("Glossary Terms (Day 1 + M02–M07)", str(stats["glossary"]))
    console.print(table)


async def cmd_hook(args: argparse.Namespace) -> None:
    """Generates a public Telegram chat hook under a user quote/pain."""
    quote_text = args.text or ""
    module_filter = args.module
    deposit_est = args.deposit or "500_2000"
    chat_id = args.chat

    from_json_src = "-" if args.from_export else args.from_json
    if from_json_src:
        lead_data = load_lead_context(from_json_src)
        if not quote_text:
            quote_text = lead_data.get("quote_sample") or ""
        if not module_filter:
            module_filter = lead_data.get("matched_module")
        if not args.deposit and lead_data.get("deposit_est"):
            deposit_est = lead_data["deposit_est"]
        if not chat_id:
            chat_id = lead_data.get("chat_id")

    if not quote_text:
        console.print("[bold red]Error: No text provided. Use --text, --from-json, or --from-export.[/bold red]")
        sys.exit(1)

    router = FTSRouter(settings.db_path)
    context = router.retrieve_context(quote_text, module=module_filter, deposit_est=deposit_est, chat_id=chat_id)

    client = DeepSeekClient()
    result = await client.generate_hook(quote_text, context)

    # Humanize output text (typography, quotes, scalper slang)
    humanized_output = humanize_text(result.text)

    # Output result
    console.print(Panel(
        humanized_output,
        title="[bold green]🎯 Tactical Public Hook Matrix (3 Calibrated Angles)[/bold green]",
        subtitle=f"Chat: {chat_id or 'Global'} | Module: {module_filter or 'Auto'}"
    ))
    console.print(f"[dim]{result.format_telemetry()}[/dim]")

    # Commit to chat outbound memory (either explicit --commit or interactive prompt)
    choice = str(args.commit).strip() if args.commit else prompt_user_choice("Сохранить вариант в память чата? [1/2/3, Enter — пропустить]: ")
    if choice:
        clean_choice = choice.strip().upper()
        committed_text = extract_variant(humanized_output, clean_choice) if clean_choice in ("1", "2", "3") else humanized_output
        row_id = router.record_outbound(
            chat_id=str(chat_id or "global"),
            our_response_text=committed_text,
            module_id=(context.get("chapter") or {}).get("module"),
            section_id=(context.get("chapter") or {}).get("section_num"),
            card_id=str((context.get("battlecard") or {}).get("card_num", "")),
            thread_topic=quote_text[:120]
        )
        console.print(f"[bold green]✓ Записано в память чата {chat_id or 'global'} (Вариант {clean_choice}, row #{row_id})[/bold green]")
        if copy_to_clipboard(committed_text):
            console.print("[bold green]✓ Текст скопирован в буфер обмена (готов к отправке в Telegram)[/bold green]")


async def cmd_followup(args: argparse.Namespace) -> None:
    """Generates 3 follow-up dialog options (Rapport, Hidden Bait, DM Bridge)."""
    thread_context = args.context or ""
    last_our = args.last_our or ""
    lead_reply = args.reply or ""
    module_filter = args.module
    deposit_est = args.deposit or "500_2000"
    chat_id = args.chat

    from_json_src = "-" if args.from_export else args.from_json
    if from_json_src:
        lead_data = load_lead_context(from_json_src)
        if not chat_id:
            chat_id = lead_data.get("chat_id")
        if not thread_context:
            thread_context = lead_data.get("quote_sample") or ""
        thread_msgs = lead_data.get("thread", [])
        if not lead_reply and thread_msgs:
            lead_reply = thread_msgs[-1].get("text", "")
        if not module_filter:
            module_filter = lead_data.get("matched_module")
        if not args.deposit and lead_data.get("deposit_est"):
            deposit_est = lead_data["deposit_est"]

    router = FTSRouter(settings.db_path)

    # If last_our is not given, attempt to pull our most recent outbound message from DB
    if not last_our and chat_id:
        recent = router.get_recent_outbound(chat_id, limit=1)
        if recent:
            last_our = recent[0]["our_response_text"]

    query_for_context = f"{thread_context} {lead_reply}".strip()
    context = router.retrieve_context(query_for_context, module=module_filter, deposit_est=deposit_est, chat_id=chat_id)

    client = DeepSeekClient()
    result = await client.generate_followup(thread_context, last_our, lead_reply, context)

    humanized_output = humanize_text(result.text)

    console.print(Panel(
        humanized_output,
        title="[bold yellow]⚡ Tactical Follow-up Matrix (Rapport, Bait, DM Bridge)[/bold yellow]",
        subtitle=f"Chat: {chat_id or 'Global'} | Lead Reply: {lead_reply[:50] or 'N/A'}"
    ))
    console.print(f"[dim]{result.format_telemetry()}[/dim]")

    # Commit to chat outbound memory (either explicit --commit or interactive prompt)
    choice = str(args.commit).strip() if args.commit else prompt_user_choice("Сохранить вариант в память чата? [A/B/C, Enter — пропустить]: ")
    if choice:
        clean_choice = choice.strip().upper()
        committed_text = extract_variant(humanized_output, clean_choice) if clean_choice in ("A", "B", "C") else humanized_output
        row_id = router.record_outbound(
            chat_id=str(chat_id or "global"),
            our_response_text=committed_text,
            module_id=(context.get("chapter") or {}).get("module"),
            section_id=(context.get("chapter") or {}).get("section_num"),
            card_id=str((context.get("battlecard") or {}).get("card_num", "")),
            thread_topic=lead_reply[:120] or thread_context[:120]
        )
        console.print(f"[bold green]✓ Записано в память чата {chat_id or 'global'} (Вариант {clean_choice}, row #{row_id})[/bold green]")
        if copy_to_clipboard(committed_text):
            console.print("[bold green]✓ Текст скопирован в буфер обмена (готов к отправке в Telegram)[/bold green]")


async def cmd_shield(args: argparse.Namespace) -> None:
    """Generates a DM objection response tailored to the lead's stage and deposit."""
    incoming_text = args.text or ""
    stage = args.stage or "In_DM"
    deposit_est = args.deposit or "500_2000"
    module_filter = args.module
    chat_id = args.chat

    from_json_src = "-" if args.from_export else args.from_json
    if from_json_src:
        lead_data = load_lead_context(from_json_src)
        if not incoming_text:
            incoming_text = lead_data.get("quote_sample") or ""
        if not module_filter:
            module_filter = lead_data.get("matched_module")
        if not args.stage and lead_data.get("current_stage"):
            stage = lead_data["current_stage"]
        if not args.deposit and lead_data.get("deposit_est"):
            deposit_est = lead_data["deposit_est"]
        if not chat_id:
            chat_id = lead_data.get("chat_id")

    if not incoming_text:
        console.print("[bold red]Error: No incoming text provided. Use --text, --from-json, or --from-export.[/bold red]")
        sys.exit(1)

    router = FTSRouter(settings.db_path)
    context = router.retrieve_context(incoming_text, module=module_filter, deposit_est=deposit_est, chat_id=chat_id)

    client = DeepSeekClient()
    result = await client.generate_shield(incoming_text, context, stage=stage, deposit_est=deposit_est)

    humanized_output = humanize_text(result.text)

    # Output result
    console.print(Panel(
        humanized_output,
        title="[bold blue]DM Objection Shield[/bold blue]",
        subtitle=f"Stage: {stage} | Deposit: ${deposit_est} | Module: {module_filter or 'Auto'}"
    ))
    console.print(f"[dim]{result.format_telemetry()}[/dim]")

    if args.commit:
        row_id = router.record_outbound(
            chat_id=str(chat_id or "dm_global"),
            our_response_text=humanized_output,
            module_id=(context.get("chapter") or {}).get("module"),
            section_id=(context.get("chapter") or {}).get("section_num"),
            card_id=str((context.get("battlecard") or {}).get("card_num", "")),
            thread_topic=incoming_text[:120]
        )
        console.print(f"[bold green]✓ Recorded DM shield response to chat memory (row #{row_id})[/bold green]")


async def cmd_session(args: argparse.Namespace) -> None:
    """Runs a multi-turn interactive dialogue session (argumentative chess in Telegram)."""
    quote_text = args.text or ""
    module_filter = args.module
    deposit_est = args.deposit or "500_2000"
    chat_id = args.chat

    from_json_src = "-" if args.from_export else args.from_json
    if from_json_src:
        lead_data = load_lead_context(from_json_src)
        if not quote_text:
            quote_text = lead_data.get("quote_sample") or ""
        if not module_filter:
            module_filter = lead_data.get("matched_module")
        if not args.deposit and lead_data.get("deposit_est"):
            deposit_est = lead_data["deposit_est"]
        if not chat_id:
            chat_id = lead_data.get("chat_id")

    router = FTSRouter(settings.db_path)
    client = DeepSeekClient()
    session = SessionEngine(
        router=router,
        client=client,
        chat_id=chat_id,
        deposit_est=deposit_est,
        module=module_filter
    )

    console.print("[bold cyan]=== Syndicate Dialogue Session Started ===[/bold cyan]")
    console.print(f"[dim]Chat: {chat_id or 'Global'} | Module: {module_filter or 'Auto'} | Deposit: {deposit_est}[/dim]\n")

    simulated_turns = []
    if args.simulated_turns:
        sim_str = args.simulated_turns.strip()
        if Path(sim_str).exists() and Path(sim_str).is_file():
            sim_str = Path(sim_str).read_text(encoding="utf-8")
        simulated_turns = json.loads(sim_str)

    if simulated_turns:
        # Automated non-interactive playback of simulated turns
        for i, turn in enumerate(simulated_turns, 1):
            opp_text = turn.get("text") or (quote_text if i == 1 else "")
            choice = str(turn.get("choice", 1))
            console.print(f"[bold cyan]─── Ход {i} (Собеседник) ───[/bold cyan]\n«{opp_text}»\n")
            humanized_output, context, result = await session.process_turn(opp_text)

            card_info = (context.get("battlecard") or {}).get("card_num", "none")
            sec_info = (context.get("chapter") or {}).get("section_num", "none")
            title = f"[bold green]🎯 Tactical Hook Matrix (Turn {i})[/bold green]" if i == 1 else f"[bold green]⚔️ Counter Matrix (Turn {i})[/bold green]"
            subtitle = f"Card: #{card_info} | Section: {sec_info} | Cost: ${result.cost_usd:.5f}"

            console.print(Panel(humanized_output, title=title, subtitle=subtitle))
            console.print(f"[dim]{result.format_telemetry()}[/dim]")

            committed = session.commit_turn(opp_text, choice, humanized_output, context)
            console.print(f"[bold green]✓ Записан Вариант {choice}:[/bold green] {committed[:80]}...\n")
            copy_to_clipboard(committed)
        return

    # Interactive loop
    current_opponent_text = quote_text
    turn_idx = 1
    while True:
        if not current_opponent_text:
            prompt = f"\n[Ход {turn_idx}] Введите ответ собеседника [Enter/q — выход]: "
            current_opponent_text = prompt_user_choice(prompt)
            if not current_opponent_text or current_opponent_text.strip().lower() in ("q", "quit", "exit"):
                console.print("[dim]Сессия завершена оператором.[/dim]")
                break

        console.print(f"\n[bold cyan]─── Ход {turn_idx} (Генерация 3 ракурсов) ───[/bold cyan]")
        humanized_output, context, result = await session.process_turn(current_opponent_text)

        card_info = (context.get("battlecard") or {}).get("card_num", "none")
        sec_info = (context.get("chapter") or {}).get("section_num", "none")
        title = f"[bold green]🎯 Tactical Hook Matrix (Turn {turn_idx})[/bold green]" if turn_idx == 1 else f"[bold green]⚔️ Counter Matrix (Turn {turn_idx})[/bold green]"
        subtitle = f"Chat: {chat_id or 'Global'} | Card: #{card_info} | Section: {sec_info}"

        console.print(Panel(humanized_output, title=title, subtitle=subtitle))
        console.print(f"[dim]{result.format_telemetry()}[/dim]")

        choice = prompt_user_choice("Выберите вариант для отправки [1/2/3, Enter — пропустить, q — выход]: ")
        if choice.strip().lower() in ("q", "quit", "exit"):
            console.print("[dim]Сессия завершена.[/dim]")
            break

        clean_choice = choice.strip().upper()
        if clean_choice in ("1", "2", "3", "A", "B", "C"):
            committed = session.commit_turn(current_opponent_text, clean_choice, humanized_output, context)
            console.print(f"[bold green]✓ Записано в память чата (Вариант {clean_choice})[/bold green]")
            if copy_to_clipboard(committed):
                console.print("[bold green]✓ Текст скопирован в буфер обмена (готов к отправке в Telegram)[/bold green]")
        else:
            console.print("[yellow]Ход пропущен без коммита в память чата.[/yellow]")

        turn_idx += 1
        current_opponent_text = None


def cmd_card(args: argparse.Namespace) -> None:
    """Displays battlecard(s) by search query or card number."""
    router = FTSRouter(settings.db_path)

    if args.num and args.module:
        card = router.get_battlecard(args.module, args.num)
        cards = [card] if card else []
    elif args.search:
        cards = router.search_battlecards(args.search, module=args.module, limit=5)
    else:
        console.print("[bold red]Please provide --search <query> or --num <card_num> with --module.[/bold red]")
        return

    if not cards:
        console.print("[yellow]No battlecards found.[/yellow]")
        return

    for c in cards:
        title = f"[bold green][{c['module']}] Card #{c['card_num']}: {c['objection']}[/bold green]"
        console.print(Panel(c["answer"], title=title))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Syndicate KB Responder: Fast objection & hook generator for crypto sales closers."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # index
    p_index = subparsers.add_parser("index", help="Index Obsidian KB into SQLite FTS5")
    p_index.add_argument("--kb-dir", help="Path to Obsidian knowledge base folder")
    p_index.add_argument("--db-path", help="Path to SQLite database file")

    # hook
    p_hook = subparsers.add_parser("hook", help="Generate public group hook")
    p_hook.add_argument("--text", help="Message or pain text from group")
    p_hook.add_argument("--module", help="Module filter (e.g. M01, M04)")
    p_hook.add_argument("--deposit", help="Estimated deposit (500_2000, 1000, etc.)")
    p_hook.add_argument("--chat", help="Chat ID for memory and anti-repetition")
    p_hook.add_argument("--commit", help="Commit chosen variant (1, 2, or 3) to chat outbound memory")
    p_hook.add_argument("--from-json", help="Path, JSON string, or '-' for stdin from tg-closer-crm")
    p_hook.add_argument("--from-export", action="store_true", help="Read exported JSON thread from stdin")

    # followup
    p_followup = subparsers.add_parser("followup", help="Generate follow-up responses (Rapport, Bait, DM Bridge)")
    p_followup.add_argument("--context", help="Thread background context")
    p_followup.add_argument("--last-our", help="Text of our previous message")
    p_followup.add_argument("--reply", help="Incoming reply from lead")
    p_followup.add_argument("--chat", help="Chat ID for memory and anti-repetition")
    p_followup.add_argument("--module", help="Module filter (e.g. M01, M04)")
    p_followup.add_argument("--deposit", help="Estimated deposit")
    p_followup.add_argument("--commit", help="Commit chosen variant (A, B, or C) to chat outbound memory")
    p_followup.add_argument("--from-json", help="Path, JSON string, or '-' for stdin from tg-closer-crm")
    p_followup.add_argument("--from-export", action="store_true", help="Read exported JSON thread from stdin")

    # shield
    p_shield = subparsers.add_parser("shield", help="Generate DM objection response")
    p_shield.add_argument("--text", help="Objection message from lead in DM")
    p_shield.add_argument("--stage", help="Funnel stage (In_DM, Legend_&_Media, Test_20, Passed)")
    p_shield.add_argument("--deposit", help="Estimated deposit (500_2000, 1000_2000, or exact amount)")
    p_shield.add_argument("--module", help="Module filter (e.g. M01, M04)")
    p_shield.add_argument("--chat", help="Chat ID / Lead ID for outbound history")
    p_shield.add_argument("--commit", action="store_true", help="Commit response to chat memory")
    p_shield.add_argument("--from-json", help="Path, JSON string, or '-' for stdin from tg-closer-crm")
    p_shield.add_argument("--from-export", action="store_true", help="Read exported JSON thread from stdin")

    # card
    p_card = subparsers.add_parser("card", help="Lookup battlecards")
    p_card.add_argument("--search", help="Search query")
    p_card.add_argument("--module", help="Module code (M01-M07, FAST_TRACK)")
    p_card.add_argument("--num", type=int, help="Card number (1-10)")

    # session
    p_session = subparsers.add_parser("session", help="Multi-turn interactive dialogue session / argumentative chess")
    p_session.add_argument("--chat", help="Chat ID for memory and anti-repetition")
    p_session.add_argument("--deposit", help="Estimated deposit (500_2000, 1000, etc.)")
    p_session.add_argument("--module", help="Module filter (e.g. M01, M04)")
    p_session.add_argument("--text", help="Initial message / quote from lead")
    p_session.add_argument("--from-json", help="Path, JSON string, or '-' for stdin from tg-closer-crm")
    p_session.add_argument("--from-export", action="store_true", help="Read exported JSON thread from stdin")
    p_session.add_argument("--simulated-turns", help="Path to JSON or JSON array string of simulated turns for automated testing")

    args = parser.parse_args()

    if args.command == "index":
        cmd_index(args)
    elif args.command == "hook":
        asyncio.run(cmd_hook(args))
    elif args.command == "followup":
        asyncio.run(cmd_followup(args))
    elif args.command == "shield":
        asyncio.run(cmd_shield(args))
    elif args.command == "card":
        cmd_card(args)
    elif args.command == "session":
        asyncio.run(cmd_session(args))


if __name__ == "__main__":
    main()
