"""LangGraph state-graph wiring the four agents.

Topology:

    START -> company_confirm -> scraper -> db -> tester -> END

`build_graph()` returns a compiled graph; `run_chat(message)` is a small
convenience wrapper used by the CLI.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .agents import company_confirm_node, db_node, scraper_node, tester_node
from .state import ChatState


def build_graph():
    """Construct and compile the four-node multi-agent state graph."""
    graph = StateGraph(ChatState)
    graph.add_node("company_confirm", company_confirm_node)
    graph.add_node("scraper", scraper_node)
    graph.add_node("db", db_node)
    graph.add_node("tester", tester_node)

    graph.add_edge(START, "company_confirm")
    graph.add_edge("company_confirm", "scraper")
    graph.add_edge("scraper", "db")
    graph.add_edge("db", "tester")
    graph.add_edge("tester", END)

    return graph.compile()


def run_chat(message: str, *, output_dir: str = "output", limit: int = 100) -> ChatState:
    """Invoke the compiled graph for a single user message."""
    compiled = build_graph()
    initial: ChatState = {
        "user_message": message,
        "limit": limit,
        "messages": [],
        "extras": {"output_dir": output_dir},
    }
    return compiled.invoke(initial)
