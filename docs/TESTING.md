# Testing Guide

Developer-facing reference for the test suite in `tests/`. For the
product / business-side acceptance plan see [`UAT-PLAN.md`](UAT-PLAN.md).

---

## 1. Testing philosophy

The repository is wired so the entire test suite can run:

- **Offline** — no DNS, no outbound HTTP.
- **Fast** — the suite completes in a few seconds.
- **No live Anthropic calls** — the test module pops
  `ANTHROPIC_API_KEY` from `os.environ` *before* importing any agent,
  so every node falls back to its deterministic path.
- **No live Workday HTTP** — `tools.workday.search_jobs` is
  monkeypatched in the end-to-end test (see section 5).
- **Deterministic** — no randomness, no time-of-day dependence.

This is enforced at the top of `tests/test_smoke.py`:

```python
import os
# Ensure no live API calls before importing the agents (which read os.environ).
os.environ.pop("ANTHROPIC_API_KEY", None)

from job_chatbot_langchain.graph import build_graph, run_chat
```

The placement matters: the agent modules check `os.environ` *at node
call time*, so unsetting the key before import (and never re-setting it
in tests) is sufficient to keep them on the offline path.

---

## 2. What's covered today

The complete current suite lives in `tests/test_smoke.py`. Each function
is listed below with a one-line description of what it asserts.

| Test function | What it covers |
|---|---|
| `test_graph_builds` | `build_graph()` returns an object with a callable `.invoke`. This is the graph **construction** smoke test — proves the LangGraph node + edge declarations in `graph.py` compile. |
| `test_job_id_regex_strips_suffix` | The `_JOB_ID_RE` regex in `tools/workday.py` extracts `712616WD` from both `..._712616WD-2` and `..._712616WD` paths. Protects the dedup logic. |
| `test_company_registry_has_eight_companies` | `known_companies()` returns exactly 8 entries, and `"PricewaterhouseCoopers"` is among them. Pinned because UAT and the slug routing depend on the canonical names. |
| `test_pwc_resolves_via_alias` | `resolve_company("PwC")` returns the right tenant (`pwc`), site (`Global_Experienced_Careers`), and base URL. Exercises case-insensitive lookup. |
| `test_end_to_end_offline` | Full graph runs via `run_chat(...)`. Workday is monkeypatched to return two fake postings; the test asserts CompanyConfirm resolved PwC, Scraper attached 2 postings, DB wrote CSV + SQLite under `tmp_path`, and Tester returned `ok=True` with `row_count=2`, `unique_job_ids=2`, `issues=[]`. |
| `test_unknown_company_short_circuits` | `run_chat("find data engineer jobs at Acme Corp", ...)` resolves no company, scraper returns `[]`, and Tester returns `ok=False`. Confirms the failure path doesn't crash. |

Total: **6 tests**. Run them all with `uv run pytest -q`.

---

## 3. Test categories

The six tests fall into two categories.

**Unit tests** (pure functions, no I/O beyond `tmp_path`):

| Module under test | Test |
|---|---|
| `tools/workday.py` (`_extract_job_id` regex) | `test_job_id_regex_strips_suffix` |
| `tools/companies.py` (registry + alias) | `test_company_registry_has_eight_companies`, `test_pwc_resolves_via_alias` |
| `tools/storage.py` | Exercised indirectly via `test_end_to_end_offline`. |

**Integration tests** (graph wiring):

| Scope | Test |
|---|---|
| LangGraph construction (nodes + edges compile) | `test_graph_builds` |
| Compiled graph end-to-end with Workday stubbed | `test_end_to_end_offline` |
| Unknown-company short-circuit path | `test_unknown_company_short_circuits` |

The **build** of the state graph is tested; the **runtime behaviour of
each node's `ChatAnthropic` call is not**. Because the tests never set
`ANTHROPIC_API_KEY`, every `if os.environ.get(...)` branch in
`agents/*.py` is skipped. `test_end_to_end_offline` exercises the
deterministic regex pre-parse in `CompanyConfirm._heuristic_parse`, the
direct `search_jobs(...)` call (monkeypatched), `write_csv` /
`write_sqlite`, and `validate_csv_tool.invoke(...)` against a real CSV.
The four `ChatAnthropic(...).bind_tools([...]).invoke([...])` calls are
deliberately untested — see section 10.

---

## 4. How to run tests

```bash
# Run the full suite, quietly
uv run pytest -q

# Run one file
uv run pytest tests/test_smoke.py -q

# Run one test by name
uv run pytest tests/test_smoke.py::test_end_to_end_offline -q

# Verbose with stdout from the agents
uv run pytest -v -s

# Stop at the first failure, drop into pdb
uv run pytest -x --pdb
```

Pytest finds tests through its default discovery (`test_*.py` files,
`test_*` functions). No `conftest.py` is required at the moment — if
you add fixtures shared across multiple files, put them there.

---

## 5. Mocking strategy (the double-monkey-patch gotcha)

The most important pattern in this suite: `tools.workday.search_jobs`
must be patched at **two** import sites or the test silently calls the
real Workday endpoint.

`agents/scraper.py` does:

```python
from ..tools.workday import search_jobs
```

That creates a *second* binding to the function object inside the
`agents.scraper` namespace. Patching only `tools.workday.search_jobs`
leaves the binding inside `agents.scraper` pointing at the original —
and `scraper_node` calls it through that binding. This is a generic
Python `from X import Y` gotcha, but it bites hard here because the
agent imports look innocuous.

The fix used in `test_end_to_end_offline`:

```python
def fake_search_jobs(company, keywords="", location=None, limit=100):
    return fake_postings

# Patch the canonical home of the function.
monkeypatch.setattr(workday_module, "search_jobs", fake_search_jobs)

# Patch the symbol that the scraper agent imported by name.
import job_chatbot_langchain.agents.scraper as scraper_mod
monkeypatch.setattr(scraper_mod, "search_jobs", fake_search_jobs)
```

Both `setattr` calls are required.

**Rule of thumb.** When stubbing a function used by an agent node, ask:
*does the agent do `from X import Y`?* If yes, patch both the source
module and the agent module. If the agent does `from . import tools`
and calls `tools.workday.search_jobs(...)`, one patch is enough. Check
the agent's `import` block before writing the patches.

---

## 6. Adding a new test

Add to `tests/test_smoke.py` (split into `tests/test_<topic>.py` once
that file grows past ~200 lines). Conventions:

1. Name as `test_<unit>_<behaviour>`, snake_case, present tense.
2. One-line docstring describing the assertion.
3. Use `tmp_path` for any file I/O. Never touch the repo's `output/`.
4. Use `monkeypatch` for env vars and module attributes — don't mutate
   `os.environ` directly.
5. Assert specific values, not truthiness.
6. If the test runs the graph end-to-end, apply the double-patch from
   section 5.

Skeleton:

```python
def test_salesforce_alias(monkeypatch, tmp_path):
    """`sfdc` resolves to Salesforce and the graph completes."""
    def fake(company, keywords="", location=None, limit=100):
        return []
    monkeypatch.setattr(workday_module, "search_jobs", fake)
    import job_chatbot_langchain.agents.scraper as s
    monkeypatch.setattr(s, "search_jobs", fake)

    state = run_chat("data engineer jobs at sfdc", output_dir=str(tmp_path))
    assert state["company_canonical"] == "Salesforce"
```

---

## 7. Adding a new graph node

The graph topology in `graph.py` is linear:
`START -> company_confirm -> scraper -> db -> tester -> END`. To add a
new node (say, an `Enricher` between Scraper and DB):

### 7.1 Create `agents/enricher.py`

```python
# src/job_chatbot_langchain/agents/enricher.py
from __future__ import annotations
from ..state import ChatState

def enricher_node(state: ChatState) -> ChatState:
    """LangGraph node: enrich each posting with derived fields."""
    messages = list(state.get("messages", []))
    postings = state.get("postings", []) or []
    # ... do the work ...
    messages.append(f"[Enricher] Enriched {len(postings)} postings.")
    return {**state, "postings": postings, "messages": messages}
```

Every node has the same signature: `(state: ChatState) -> ChatState`. It
must return a *new* dict; mutating `state` in place is discouraged.

### 7.2 Export the node from `agents/__init__.py`

```python
from .enricher import enricher_node
__all__ = [..., "enricher_node"]
```

### 7.3 Wire it into `graph.py`

```python
from .agents import company_confirm_node, db_node, enricher_node, scraper_node, tester_node

graph.add_node("enricher", enricher_node)
graph.add_edge("scraper", "enricher")
graph.add_edge("enricher", "db")
# remove the old direct scraper->db edge
```

### 7.4 Conditional vs unconditional

The current graph uses only unconditional edges (`add_edge`). If the
new node should branch — e.g. skip DB when there are no postings —
use `add_conditional_edges`:

```python
def has_postings(state: ChatState) -> str:
    return "db" if state.get("postings") else "tester"

graph.add_conditional_edges("enricher", has_postings, {"db": "db", "tester": "tester"})
```

### 7.5 Test the node

Two layers: a unit test that calls `enricher_node({...})` with a
hand-built `ChatState` and asserts the returned dict; and tests for any
new helpers in `tools/`. Do **not** add a test that exercises the live
`ChatAnthropic` call. If the new node re-imports a function used
elsewhere, apply the double-patch rule from section 5.

---

## 8. Adding a new tool to an existing node

Each agent's LLM gets a list of LangChain tools via `.bind_tools(...)`.
Adding a new tool means three steps:

1. **Write the tool** — add a `@tool`-decorated function in the
   appropriate `tools/` module (or a new module). Keep tools small,
   pure where possible, and well-docstring'd — LangChain feeds the
   docstring to the model.

   ```python
   # src/job_chatbot_langchain/tools/enrichment.py
   from langchain_core.tools import tool

   @tool
   def normalise_location_tool(raw: str) -> str:
       """Return a canonical city name for the raw Workday location string."""
       return raw.split(",")[0].strip()
   ```

2. **Bind it to the node's model** — find the node's
   `bind_tools([...])` call and append the new tool. For example, in
   `agents/scraper.py` the existing call is:

   ```python
   llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)
       .bind_tools([workday_search_tool])
   ```

   Add the new tool to the list:

   ```python
   .bind_tools([workday_search_tool, normalise_location_tool])
   ```

   Also update the node's `SYSTEM_PROMPT` to tell the model when to
   call it.

3. **Test the tool, not the binding** — `bind_tools` is not exercised
   in offline tests. Write a unit test for the tool's underlying
   logic:

   ```python
   def test_normalise_location_strips_country():
       from job_chatbot_langchain.tools.enrichment import normalise_location_tool
       assert normalise_location_tool.invoke({"raw": "Bangalore, India"}) == "Bangalore"
   ```

   Call the tool via `.invoke({...})` (the LangChain `BaseTool`
   interface), not as a plain function — this is how `tester_node`
   already calls `validate_csv_tool` in production code, and it
   verifies the schema is correctly inferred.

---

## 9. Test data / fixtures

No fixture files on disk today; all inputs are constructed inline.
`test_end_to_end_offline` builds two `JobPosting` objects in the body
and returns them from `fake_search_jobs`. `tmp_path` isolates generated
CSV + SQLite from the repo's `output/`. Env vars go through
`monkeypatch.setenv` / `delenv`. If you repeat the same fake posting
list across tests, hoist it to a `pytest.fixture` in a new
`tests/conftest.py`.

---

## 10. What's deliberately NOT tested

To keep the suite fast, offline, and free, these surfaces are excluded:

| Surface | Why excluded | Compensating control |
|---|---|---|
| Live `ChatAnthropic` calls in any node | Costs money, flaky, requires a secret | UAT-010 spot-checks token cost manually. |
| Workday HTTP endpoint | External dependency, not in our control | UAT-001 / UAT-005 exercise the live endpoint by hand. |
| The compiled graph's **runtime** behaviour with the model in the loop | Requires live Anthropic | UAT-011 verifies all four `[NodeName]` lines print in order. |
| Rich console rendering in `main.py::_print_summary` | UI, hard to assert | Visually inspected during UAT. |
| `dotenv` loading | Trivial wrapper | Covered by `uv run job-chatbot-langchain` in setup. |
| `__main__` entry (`if __name__ == "__main__":`) | Marked `# pragma: no cover` | N/A |

When you add a new feature, decide which list it belongs in. A new
deterministic function should grow a unit test; a new live-LLM behaviour
should grow a UAT scenario.

---

## 11. Coverage

Coverage is not measured in CI. To run locally:

```bash
uv pip install coverage
uv run coverage run -m pytest
uv run coverage report -m
```

Realistic target: **~70 %** line coverage of
`src/job_chatbot_langchain/`. The gap is mostly the four
`if os.environ.get("ANTHROPIC_API_KEY"):` branches and the `main.py`
REPL loop — both intentionally untested. Above ~80 % you are probably
testing the LLM wrappers, which is the wrong tradeoff; prefer broader
UAT instead.

---

## 12. Continuous integration

A minimal GitHub Actions workflow that runs the suite on every push and
PR — paste into `.github/workflows/tests.yml`:

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Set up Python
        run: uv python install 3.11

      - name: Sync dependencies
        run: uv sync --all-extras

      - name: Run tests
        run: uv run pytest -q
        env:
          # Belt and braces: the test file already pops this, but make
          # absolutely sure no live calls leak from CI secrets.
          ANTHROPIC_API_KEY: ""
```

Notes:

- The suite is offline, so no secrets are needed. Deliberately set
  `ANTHROPIC_API_KEY: ""` to make that contract explicit.
- Add a `matrix:` over Python 3.11 / 3.12 once you confirm both work
  (the `requires-python = ">=3.11"` in `pyproject.toml` claims it).
- Do not add the workflow until you're ready to enforce it — a red CI
  badge on `main` is worse than no badge.

---

## 13. Test smells

Push back on a PR if you see any of these:

- A test that needs `ANTHROPIC_API_KEY` set. None should.
- A test that hits a real URL (stub `httpx` or `search_jobs` at both
  sites).
- A test that touches the repo's `./output/`. Use `tmp_path`.
- `time.sleep(...)` in a test — graph nodes are synchronous.
- `assert state["postings"]` without checking the count. Be specific.
- A new agent node in `graph.py` with no corresponding test — at
  minimum extend `test_graph_builds`.
- Single-site monkeypatch on a function the agent re-imports
  (section 5 — silently makes live HTTP calls).

---

## 14. Linting + type-checking

The project does not currently ship a lint / type-check configuration.
If you add one, the recommended settings are:

```bash
uv pip install ruff mypy
uv run ruff check src tests
uv run mypy src
```

Recommended `pyproject.toml` additions:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
```

**LangChain type-stub caveat.** LangChain and LangGraph ship partial
type information that does not cooperate cleanly with `mypy --strict`.
In particular: `@tool`-decorated functions are typed as `BaseTool` not
as the wrapped callable; `StateGraph`'s state `TypeVar` does not always
propagate through `add_node` / `add_edge`; and
`ChatAnthropic.bind_tools(...)` returns a `Runnable` that loses the
model's methods at the type level. If you adopt `mypy`, expect to pass
`--ignore-missing-imports` (or add per-module overrides) for the
LangChain / LangGraph packages. Reserve `# type: ignore` for
unavoidable third-party gaps; don't use it to paper over real errors
in our own code.
