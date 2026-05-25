"""CompanyConfirm agent.

Reads the raw user message, extracts the company alias / keywords / location,
and uses the `resolve_company` tool to confirm the alias maps to a known
Workday tenant. If it doesn't, the graph short-circuits.

The agent is implemented as a LangGraph node that owns a ChatAnthropic model
bound to a single `@tool` (resolve_company_tool). For robustness the node
also runs a deterministic regex pre-parse so the smoke test works without an
API key.
"""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.tools import tool

from ..state import ChatState
from ..tools.companies import known_companies, resolve_company

SYSTEM_PROMPT = """You are the CompanyConfirm agent in a multi-agent job-search system.

Your job:
1. Read the user's natural-language message.
2. Identify the COMPANY they want to search.
3. Identify the role KEYWORDS (e.g. "AI", "data engineer").
4. Identify the LOCATION if mentioned (e.g. "Bangalore", "remote").
5. Use the `resolve_company_tool` to confirm the company maps to a supported Workday tenant.
6. Reply with a single JSON object containing company_alias, keywords, location.

Supported companies: {companies}.

Be concise. Do not hallucinate companies that aren't on the supported list.
"""


@tool
def resolve_company_tool(name: str) -> dict[str, str]:
    """Resolve a company name or alias to a canonical Workday entry.

    Returns a dict with `canonical_name`, `tenant`, `site`, and `base_url`
    if the company is known, otherwise `{"error": "unknown"}`.
    """
    company = resolve_company(name)
    if company is None:
        return {"error": "unknown", "given": name}
    return {
        "canonical_name": company.canonical_name,
        "tenant": company.tenant,
        "site": company.site,
        "base_url": company.base_url,
    }


_COMPANY_HINTS = [
    "pwc", "pricewaterhousecoopers", "jpmorgan", "jp morgan", "jpmc",
    "salesforce", "sfdc", "cisco", "adobe", "nvidia", "netflix", "workday",
]


def _heuristic_parse(message: str) -> dict[str, Any]:
    """Deterministic fallback that doesn't need an API key.

    The Anthropic model would do this better, but we want a working
    offline path for the smoke test.
    """
    lower = message.lower()

    company = ""
    for hint in _COMPANY_HINTS:
        if hint in lower:
            company = hint
            break

    # crude keyword: anything that looks like "<verb> <kw> jobs"
    keywords = ""
    kw_match = re.search(r"(?:related to|about|in)\s+([A-Za-z][A-Za-z0-9+/ -]{1,40})", message, re.I)
    if kw_match:
        keywords = kw_match.group(1).strip()
    if not keywords:
        # try "AI jobs at PwC" pattern
        kw_match = re.search(r"\b([A-Z][A-Za-z0-9+/-]*(?:\s+[A-Za-z0-9+/-]+){0,2})\s+jobs\b", message)
        if kw_match:
            keywords = kw_match.group(1).strip()
    # strip trailing connectives
    keywords = re.sub(r"\b(at|jobs?|roles?|positions?)\b\s*$", "", keywords, flags=re.I).strip()

    location: str | None = None
    loc_match = re.search(r"\bin\s+([A-Z][A-Za-z .'-]{2,40})", message)
    if loc_match:
        candidate = loc_match.group(1).strip().rstrip(".")
        # don't treat "in AI" as a location
        if candidate.lower() not in _COMPANY_HINTS and len(candidate) > 2:
            location = candidate

    return {"company_alias": company, "keywords": keywords, "location": location}


def company_confirm_node(state: ChatState) -> ChatState:
    """LangGraph node: extract + confirm the company from the user message."""
    message = state.get("user_message", "")
    parsed = _heuristic_parse(message)

    # If an API key is set we let the model refine the parse. Otherwise we
    # fall back to the heuristic so the graph remains executable offline.
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(
                model="claude-sonnet-4-5",
                temperature=0,
            ).bind_tools([resolve_company_tool])
            prompt = SYSTEM_PROMPT.format(companies=", ".join(known_companies()))
            response = llm.invoke(
                [
                    ("system", prompt),
                    ("user", message),
                ]
            )
            # Pull tool calls out of the model response if present.
            for tc in getattr(response, "tool_calls", []) or []:
                if tc.get("name") == "resolve_company_tool":
                    args = tc.get("args", {})
                    if args.get("name"):
                        parsed["company_alias"] = args["name"]
        except Exception:  # noqa: BLE001 - model call is best-effort
            pass

    alias = parsed["company_alias"]
    company = resolve_company(alias) if alias else None

    new_state: ChatState = {
        **state,
        "company_alias": alias,
        "company_canonical": company.canonical_name if company else "",
        "company_resolved": company is not None,
        "keywords": parsed.get("keywords", ""),
        "location": parsed.get("location"),
        "limit": state.get("limit", 100),
    }
    messages = list(state.get("messages", []))
    if company:
        messages.append(
            f"[CompanyConfirm] Resolved '{alias}' -> {company.canonical_name}. "
            f"Keywords='{new_state['keywords']}', location='{new_state['location']}'."
        )
    else:
        messages.append(
            f"[CompanyConfirm] Could not resolve company from message: '{message}'."
        )
    new_state["messages"] = messages
    return new_state
