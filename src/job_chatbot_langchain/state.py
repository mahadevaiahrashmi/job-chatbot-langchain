"""Shared state passed between LangGraph nodes."""

from __future__ import annotations

from typing import Any, TypedDict

from .models import JobPosting, ValidationReport


class ChatState(TypedDict, total=False):
    """State threaded through the four-agent graph.

    Fields are populated incrementally as the graph walks
    CompanyConfirm -> Scraper -> DB -> Tester.
    """

    # Inputs
    user_message: str

    # CompanyConfirm output
    company_alias: str          # the raw alias the user gave
    company_canonical: str      # resolved canonical name
    company_resolved: bool      # whether the alias matched the registry

    # Parsed query (also produced by CompanyConfirm)
    keywords: str
    location: str | None
    limit: int

    # Scraper output
    postings: list[JobPosting]

    # DB output
    csv_path: str
    db_path: str

    # Tester output
    validation: ValidationReport

    # Free-form chatter the agents can append for the final summary
    messages: list[str]

    # Anything else useful for downstream debugging
    extras: dict[str, Any]
