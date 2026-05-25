"""Smoke tests for the job-chatbot-langchain graph.

These tests must NOT call the Anthropic API. We unset ANTHROPIC_API_KEY
and monkeypatch the Workday HTTP client so the graph can run fully offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Ensure no live API calls before importing the agents (which read os.environ).
os.environ.pop("ANTHROPIC_API_KEY", None)

from job_chatbot_langchain.graph import build_graph, run_chat
from job_chatbot_langchain.models import JobPosting
from job_chatbot_langchain.tools import workday as workday_module
from job_chatbot_langchain.tools.companies import resolve_company
from job_chatbot_langchain.tools.workday import _extract_job_id


def test_graph_builds() -> None:
    """The state graph compiles into an invocable object."""
    graph = build_graph()
    assert graph is not None
    assert callable(getattr(graph, "invoke", None))


def test_job_id_regex_strips_suffix() -> None:
    """The job-id regex strips a trailing -N suffix."""
    assert _extract_job_id(
        "/Global_Experienced_Careers/job/Bangalore/Some-Title_712616WD-2"
    ) == "712616WD"
    assert _extract_job_id(
        "/site/job/loc/Some-Title_712616WD"
    ) == "712616WD"


def test_company_registry_has_eight_companies() -> None:
    """The registry covers the eight target companies, including PwC."""
    from job_chatbot_langchain.tools.companies import known_companies

    names = known_companies()
    assert len(names) == 8
    assert "PricewaterhouseCoopers" in names


def test_pwc_resolves_via_alias() -> None:
    """PwC resolves to the configured Workday tenant."""
    company = resolve_company("PwC")
    assert company is not None
    assert company.tenant == "pwc"
    assert company.site == "Global_Experienced_Careers"
    assert company.base_url == "https://pwc.wd3.myworkdayjobs.com"


def test_end_to_end_offline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Full graph runs end-to-end with the Workday call stubbed."""

    fake_postings = [
        JobPosting(
            company="PricewaterhouseCoopers",
            job_id="712616WD",
            title="Senior AI Engineer",
            location="Bangalore, India",
            posted_on="Posted 2 days ago",
            url="https://pwc.wd3.myworkdayjobs.com/foo/_712616WD",
        ),
        JobPosting(
            company="PricewaterhouseCoopers",
            job_id="712617WD",
            title="ML Platform Engineer",
            location="Bangalore, India",
            posted_on="Posted 3 days ago",
            url="https://pwc.wd3.myworkdayjobs.com/foo/_712617WD",
        ),
    ]

    def fake_search_jobs(company, keywords="", location=None, limit=100):
        return fake_postings

    monkeypatch.setattr(workday_module, "search_jobs", fake_search_jobs)
    # Patch the symbol that the scraper agent imported by name.
    import job_chatbot_langchain.agents.scraper as scraper_mod

    monkeypatch.setattr(scraper_mod, "search_jobs", fake_search_jobs)

    state = run_chat(
        "find AI jobs at PwC in Bangalore",
        output_dir=str(tmp_path),
    )

    assert state["company_resolved"] is True
    assert state["company_canonical"] == "PricewaterhouseCoopers"
    assert len(state["postings"]) == 2
    assert state["csv_path"].endswith(".csv")
    assert state["db_path"].endswith(".sqlite")
    assert Path(state["csv_path"]).exists()
    assert Path(state["db_path"]).exists()

    validation = state["validation"]
    assert validation.ok is True
    assert validation.row_count == 2
    assert validation.unique_job_ids == 2
    assert validation.issues == []


def test_unknown_company_short_circuits(tmp_path: Path) -> None:
    """An unknown company resolves cleanly to a failed validation, not a crash."""
    state = run_chat(
        "find data engineer jobs at Acme Corp",
        output_dir=str(tmp_path),
    )
    assert state["company_resolved"] is False
    assert state["postings"] == []
    assert state["validation"].ok is False
