"""CLI entry point: `job-chatbot-langchain`.

Reads user messages from stdin in a small REPL, invokes the LangGraph
state graph for each one, and prints a summary using Rich.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .graph import run_chat
from .tools.companies import known_companies


def _print_summary(console: Console, state: dict) -> None:
    messages = state.get("messages", [])
    for m in messages:
        console.print(f"  {m}")

    postings = state.get("postings", []) or []
    if postings:
        table = Table(title=f"Top {min(10, len(postings))} postings")
        for col in ("job_id", "title", "location", "posted_on"):
            table.add_column(col)
        for p in postings[:10]:
            table.add_row(p.job_id, p.title, p.location, p.posted_on)
        console.print(table)

    validation = state.get("validation")
    if validation is not None:
        status = "[green]PASS[/green]" if validation.ok else "[red]FAIL[/red]"
        console.print(
            Panel.fit(
                f"Validation: {status}\n"
                f"Rows: {validation.row_count}\n"
                f"Unique job IDs: {validation.unique_job_ids}\n"
                f"Issues: {validation.issues or 'none'}",
                title="Tester",
            )
        )


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="job-chatbot-langchain",
        description="Multi-agent job-search chatbot (LangChain + LangGraph).",
    )
    parser.add_argument(
        "message",
        nargs="?",
        help="Optional one-shot message. If omitted, drops into a REPL.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Where CSV and SQLite files are written.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max postings to retrieve per company.",
    )
    args = parser.parse_args()

    console = Console()
    console.print(
        Panel.fit(
            "[bold]Job Chatbot (LangChain + LangGraph)[/bold]\n"
            f"Supported companies: {', '.join(known_companies())}",
            title="Welcome",
        )
    )

    def handle(msg: str) -> None:
        console.rule(f"[bold]{msg}")
        state = run_chat(msg, output_dir=args.output_dir, limit=args.limit)
        _print_summary(console, state)

    if args.message:
        handle(args.message)
        return 0

    try:
        while True:
            console.print()
            msg = console.input("[bold cyan]you[/bold cyan] > ").strip()
            if not msg:
                continue
            if msg.lower() in {"quit", "exit", ":q"}:
                break
            handle(msg)
    except (EOFError, KeyboardInterrupt):
        console.print("\nGoodbye.")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual launch only
    sys.exit(main())
