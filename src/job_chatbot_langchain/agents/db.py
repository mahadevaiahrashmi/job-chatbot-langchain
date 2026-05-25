"""DB agent.

Persists the scraped postings to a CSV file and a SQLite database under
`output/`. Filenames are derived from the company canonical name.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from langchain_core.tools import tool

from ..models import JobPosting
from ..state import ChatState
from ..tools.storage import write_csv, write_sqlite

SYSTEM_PROMPT = """You are the DB agent in a multi-agent job-search system.

You receive a list of job postings and must persist them in two places:
  1. A CSV file (one row per posting, header row first).
  2. A SQLite database table `job_postings` keyed on (company, job_id).

Call `write_csv_tool` then `write_sqlite_tool`. Do not modify the rows.
"""


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "jobs"


@tool
def write_csv_tool(rows: list[dict[str, str]], path: str) -> str:
    """Write job postings to a CSV file. Returns the absolute output path."""
    postings = [
        JobPosting(
            company=r.get("company", ""),
            job_id=r.get("job_id", ""),
            title=r.get("title", ""),
            location=r.get("location", ""),
            posted_on=r.get("posted_on", ""),
            url=r.get("url", ""),
        )
        for r in rows
    ]
    return str(write_csv(postings, Path(path)).resolve())


@tool
def write_sqlite_tool(rows: list[dict[str, str]], path: str) -> str:
    """Write job postings to a SQLite database. Returns the absolute output path."""
    postings = [
        JobPosting(
            company=r.get("company", ""),
            job_id=r.get("job_id", ""),
            title=r.get("title", ""),
            location=r.get("location", ""),
            posted_on=r.get("posted_on", ""),
            url=r.get("url", ""),
        )
        for r in rows
    ]
    return str(write_sqlite(postings, Path(path)).resolve())


def db_node(state: ChatState) -> ChatState:
    """LangGraph node: persist postings to CSV + SQLite."""
    messages = list(state.get("messages", []))
    postings: list[JobPosting] = state.get("postings", []) or []

    if not postings:
        messages.append("[DB] Skipped: no postings to persist.")
        return {**state, "csv_path": "", "db_path": "", "messages": messages}

    output_dir = Path(state.get("extras", {}).get("output_dir", "output"))
    slug = _slug(state.get("company_canonical") or state.get("company_alias", "jobs"))
    csv_path = output_dir / f"{slug}.csv"
    db_path = output_dir / f"{slug}.sqlite"

    # Best-effort LLM narration when a key is available.
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(
                model="claude-sonnet-4-5",
                temperature=0,
            ).bind_tools([write_csv_tool, write_sqlite_tool])
            llm.invoke(
                [
                    ("system", SYSTEM_PROMPT),
                    (
                        "user",
                        f"Persist {len(postings)} postings to "
                        f"{csv_path} and {db_path}.",
                    ),
                ]
            )
        except Exception:  # noqa: BLE001 - narration only
            pass

    csv_out = write_csv(postings, csv_path)
    db_out = write_sqlite(postings, db_path)
    messages.append(
        f"[DB] Persisted {len(postings)} postings -> {csv_out} and {db_out}."
    )
    return {
        **state,
        "csv_path": str(csv_out.resolve()),
        "db_path": str(db_out.resolve()),
        "messages": messages,
    }
