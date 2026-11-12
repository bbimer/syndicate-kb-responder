#!/usr/bin/env python3
"""Syndicate Knowledge Base Responder CLI.

Ultra-fast objection-handling and public hook generator powered by DeepSeek v4.1,
AST Markdown slicing of the 7-module Obsidian curriculum, FTS5 BM25 retrieval,
and strict prefix caching.
"""

from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config.settings import settings
from src.indexer.md_ast_slicer import KnowledgeBaseIndexer
from src.retrieval.fts_router import FTSRouter
from src.generator.deepseek_client import DeepSeekClient
from src.utils.json_loader import load_lead_context

console = Console()


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
    table.add_row("Glossary Terms (Section VII)", str(stats["glossary"]))
    console.print(table)


async def cmd_hook(args: argparse.Namespace) -> None:
    """Generates a public Telegram chat hook under a user quote/pain."""
    quote_text = args.text or ""
    module_filter = args.module
    deposit_est = "500_2000"

    if args.from_json:
        lead_data = load_lead_context(args.from_json)
        if not quote_text:
            quote_text = lead_data.get("quote_sample") or ""
        if not module_filter:
            module_filter = lead_data.get("matched_module")
        deposit_est = lead_data.get("deposit_est") or deposit_est

    if not quote_text:
        console.print("[bold red]Error: No text provided. Use --text or --from-json.[/bold red]")
        sys.exit(1)

    router = FTSRouter(settings.db_path)
    context = router.retrieve_context(quote_text, module=module_filter, deposit_est=deposit_est)

    client = DeepSeekClient()
    result = await client.generate_hook(quote_text, context)

    # Output result
    console.print(Panel(result.text, title="[bold green]🎯 Tactical Public Hook Matrix (3 Angles)[/bold green]", subtitle=f"Module: {module_filter or 'Auto'}"))
    console.print(f"[dim]{result.format_telemetry()}[/dim]")


async def cmd_shield(args: argparse.Namespace) -> None:
    """Generates a DM objection response tailored to the lead's stage and deposit."""
    incoming_text = args.text or ""
    stage = args.stage or "In_DM"
    deposit_est = args.deposit or "500_2000"
    module_filter = args.module

    if args.from_json:
        lead_data = load_lead_context(args.from_json)
        if not incoming_text:
            incoming_text = lead_data.get("quote_sample") or ""
        if not module_filter:
            module_filter = lead_data.get("matched_module")
        if not args.stage and lead_data.get("current_stage"):
            stage = lead_data["current_stage"]
        if not args.deposit and lead_data.get("deposit_est"):
            deposit_est = lead_data["deposit_est"]

    if not incoming_text:
        console.print("[bold red]Error: No incoming text provided. Use --text or --from-json.[/bold red]")
        sys.exit(1)

    router = FTSRouter(settings.db_path)
    context = router.retrieve_context(incoming_text, module=module_filter, deposit_est=deposit_est)

    client = DeepSeekClient()
    result = await client.generate_shield(incoming_text, context, stage=stage, deposit_est=deposit_est)

    # Output result
    console.print(Panel(
        result.text,
        title="[bold blue]DM Objection Shield[/bold blue]",
        subtitle=f"Stage: {stage} | Deposit: {deposit_est} | Module: {module_filter or 'Auto'}"
    ))
    console.print(f"[dim]{result.format_telemetry()}[/dim]")


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
    p_hook.add_argument("--from-json", help="Path, JSON string, or '-' for stdin from tg-closer-crm")

    # shield
    p_shield = subparsers.add_parser("shield", help="Generate DM objection response")
    p_shield.add_argument("--text", help="Objection message from lead in DM")
    p_shield.add_argument("--stage", help="Funnel stage (In_DM, Legend_&_Media, Test_20, Passed)")
    p_shield.add_argument("--deposit", help="Estimated deposit (500_2000, 1000_2000, or exact amount)")
    p_shield.add_argument("--module", help="Module filter (e.g. M01, M04)")
    p_shield.add_argument("--from-json", help="Path, JSON string, or '-' for stdin from tg-closer-crm")

    # card
    p_card = subparsers.add_parser("card", help="Lookup battlecards")
    p_card.add_argument("--search", help="Search query")
    p_card.add_argument("--module", help="Module code (M01-M07, FAST_TRACK)")
    p_card.add_argument("--num", type=int, help="Card number (1-10)")

    args = parser.parse_args()

    if args.command == "index":
        cmd_index(args)
    elif args.command == "hook":
        asyncio.run(cmd_hook(args))
    elif args.command == "shield":
        asyncio.run(cmd_shield(args))
    elif args.command == "card":
        cmd_card(args)


if __name__ == "__main__":
    main()
