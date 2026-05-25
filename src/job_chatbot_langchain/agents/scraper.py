"""Scraper agent.

Calls the Workday search tool with the (company, keywords, location) parsed
by CompanyConfirm. Returns a list of `JobPosting` objects on the state.
"""

from __future__ import annotations

import os

from langchain_core.tools import tool

from ..models import JobPosting
from ..state import ChatState
from ..tools.companies import resolve_company
from ..tools.workday import search_jobs

SYSTEM_PROMPT = """You are the Scraper agent in a multi-agent job-search system.

You have been given a confirmed company, keyword string, and optional location.
Call the `workday_search_tool` exactly once with these arguments and return
the structured results. Do not paraphrase, summarize, or filter the rows.
"""


@tool
def workday_search_tool(
    company_alias: str,
    keywords: str = "",
    location: str | None = None,
    limit: int = 100,
) -> list[dict[str, str]]:
    """Search a known company's Workday tenant for job postings.

    Returns a list of dicts, each with keys: company, job_id, title,
    location, posted_on, url. Returns an empty list if the company alias is
    unknown.
    """
    company = resolve_company(company_alias)
    if company is None:
        return []
    postings = search_jobs(
        company=company,
        keywords=keywords,
        location=location,
        limit=limit,
    )
    return [p.to_dict() for p in postings]


def scraper_node(state: ChatState) -> ChatState:
    """LangGraph node: scrape Workday and attach postings to state."""
    messages = list(state.get("messages", []))

    if not state.get("company_resolved"):
        messages.append("[Scraper] Skipped: company was not resolved.")
        return {**state, "postings": [], "messages": messages}

    alias = state["company_alias"]
    keywords = state.get("keywords", "")
    location = state.get("location")
    limit = state.get("limit", 100)

    # The LLM "narrates" the call when a key is available; the actual scrape
    # is always done deterministically so the smoke test works offline.
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(
                model="claude-sonnet-4-5",
                temperature=0,
            ).bind_tools([workday_search_tool])
            llm.invoke(
                [
                    ("system", SYSTEM_PROMPT),
                    (
                        "user",
                        f"company_alias={alias!r} keywords={keywords!r} "
                        f"location={location!r} limit={limit}",
                    ),
                ]
            )
        except Exception:  # noqa: BLE001 - LLM narration is best-effort
            pass

    company = resolve_company(alias)
    postings: list[JobPosting] = []
    if company is not None:
        try:
            postings = search_jobs(
                company=company,
                keywords=keywords,
                location=location,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001 - report scrape failures
            messages.append(f"[Scraper] Scrape failed: {exc!r}")

    messages.append(
        f"[Scraper] Retrieved {len(postings)} postings from "
        f"{company.canonical_name if company else alias}."
    )
    return {**state, "postings": postings, "messages": messages}
