"""Tester agent.

Validates the persisted output: schema completeness, row count > 0,
and that job IDs are unique within the result set.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

from langchain_core.tools import tool

from ..models import ValidationReport
from ..state import ChatState

REQUIRED_FIELDS = ["company", "job_id", "title", "location", "posted_on", "url"]

SYSTEM_PROMPT = """You are the Tester agent in a multi-agent job-search system.

Validate the output of the DB agent. Run `validate_csv_tool` against the
CSV path and summarise whether the run is healthy. Failure conditions:
  - CSV missing or unreadable
  - Row count is 0
  - Missing any required header
  - Duplicate job_id values
"""


@tool
def validate_csv_tool(path: str) -> dict[str, object]:
    """Validate the CSV produced by the DB agent.

    Returns a dict with `ok`, `row_count`, `unique_job_ids`, and `issues`.
    """
    issues: list[str] = []
    p = Path(path)
    if not p.exists():
        return {
            "ok": False,
            "row_count": 0,
            "unique_job_ids": 0,
            "issues": [f"CSV not found at {path}"],
        }
    rows: list[dict[str, str]] = []
    with p.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [f for f in REQUIRED_FIELDS if f not in (reader.fieldnames or [])]
        if missing:
            issues.append(f"Missing CSV columns: {missing}")
        rows = list(reader)

    job_ids = [r.get("job_id", "") for r in rows]
    unique = {jid for jid in job_ids if jid}
    if len(rows) == 0:
        issues.append("CSV has no data rows.")
    if len(unique) != len(job_ids):
        issues.append("Duplicate job_id values detected.")

    return {
        "ok": not issues,
        "row_count": len(rows),
        "unique_job_ids": len(unique),
        "issues": issues,
    }


def tester_node(state: ChatState) -> ChatState:
    """LangGraph node: validate the CSV and attach a ValidationReport."""
    messages = list(state.get("messages", []))
    csv_path = state.get("csv_path", "")

    if not csv_path:
        report = ValidationReport(
            ok=False,
            row_count=0,
            unique_job_ids=0,
            issues=["No CSV produced by DB agent."],
        )
        messages.append("[Tester] FAIL: no CSV to validate.")
        return {**state, "validation": report, "messages": messages}

    # Optional LLM narration.
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(
                model="claude-sonnet-4-5",
                temperature=0,
            ).bind_tools([validate_csv_tool])
            llm.invoke(
                [
                    ("system", SYSTEM_PROMPT),
                    ("user", f"Validate the CSV at {csv_path}."),
                ]
            )
        except Exception:  # noqa: BLE001
            pass

    result = validate_csv_tool.invoke({"path": csv_path})
    report = ValidationReport(
        ok=bool(result["ok"]),
        row_count=int(result["row_count"]),
        unique_job_ids=int(result["unique_job_ids"]),
        issues=list(result["issues"]),
    )
    status = "PASS" if report.ok else "FAIL"
    messages.append(
        f"[Tester] {status}: rows={report.row_count}, "
        f"unique_ids={report.unique_job_ids}, issues={report.issues}"
    )
    return {**state, "validation": report, "messages": messages}
