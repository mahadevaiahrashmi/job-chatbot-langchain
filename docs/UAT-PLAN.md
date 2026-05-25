# User Acceptance Test (UAT) Plan

This document is the **product / business-side** test plan for
`job-chatbot-langchain`. It describes how a non-engineer should exercise
the running chatbot from the outside, what "passing" looks like for each
scenario, and how to report problems.

For developer-facing tests (the pytest suite, mocking strategy, CI), see
[`TESTING.md`](TESTING.md). The two documents are complementary:

- **This file** = scenarios you click through from the REPL.
- **`TESTING.md`** = unit + integration tests engineers run with
  `uv run pytest`.

---

## 1. What UAT covers

UAT here means **end-to-end behaviour from the user's seat**. You sit at a
terminal, type a natural-language request such as *"find AI jobs at PwC in
Bangalore"*, and check that the chatbot:

1. Recognises the company you meant (including common aliases such as
   `pwc`, `PwC`, `pricewaterhousecoopers`, `sfdc`).
2. Walks all four graph nodes in order — CompanyConfirm, Scraper, DB,
   Tester — and surfaces a line of evidence from each one.
3. Retrieves a reasonable number of postings from Workday.
4. Writes the postings to `output/<slug>.csv` and `output/<slug>.sqlite`.
5. Validates the output and prints a clear PASS / FAIL summary panel.

UAT does **not** cover:

- Internal Python correctness (covered by `tests/test_smoke.py` — see
  `docs/TESTING.md`).
- Live Anthropic billing accuracy (you only spot-check cost in UAT-010).
- Workday's own search-relevance — if Workday says there are 3 AI jobs at
  PwC, UAT verifies the bot collected 3 rows, not that "AI" is the right
  filter.

---

## 2. Prerequisites

Before starting UAT you need:

| Item | Why |
|---|---|
| macOS, Linux, or WSL on Windows | Tested platforms |
| Python 3.11 or newer | Required by `pyproject.toml` |
| `uv` installed | Dependency + virtualenv tool |
| Anthropic API key | Recommended — enables the LangGraph nodes' `ChatAnthropic` calls. Without it the bot still runs via a regex fallback in `CompanyConfirm`, but you won't be exercising the model. |
| Network access | The Scraper node calls Workday over HTTPS |
| ~50 MB disk space | Output CSVs + SQLite files |
| A spreadsheet app (Excel, Numbers, LibreOffice) | To open the CSV in UAT-009 |

---

## 3. Setup checklist

Run these once before you start the test scenarios. Tick each box as you
go.

- [ ] **Clone the repo**

  ```bash
  git clone git@github.com:mahadevaiahrashmi/job-chatbot-langchain.git
  cd job-chatbot-langchain
  ```

- [ ] **Install dependencies**

  ```bash
  uv sync
  ```

  This creates `.venv/` and installs `langchain`, `langgraph`,
  `langchain-anthropic`, `httpx`, `rich`, `python-dotenv`, and pytest.

- [ ] **Create your `.env`**

  ```bash
  cp .env.example .env
  ```

  Open `.env` and paste your real key after `ANTHROPIC_API_KEY=`.

- [ ] **Run the smoke tests** (sanity check that the install works)

  ```bash
  uv run pytest -q
  ```

  Expected: all tests pass (currently 6) in a few seconds, no network
  calls, no API key needed.

- [ ] **Launch the chatbot REPL**

  ```bash
  uv run job-chatbot-langchain
  ```

  You should see a Rich "Welcome" panel listing the eight supported
  companies, then a `you >` prompt.

If any of the above fails, stop and report it as a setup bug (see
section 8). Don't proceed into the scenario table.

---

## 4. Acceptance test scenarios

Run each scenario from the same REPL session unless instructed otherwise.
"Expected" is what a passing run looks like; "PASS criteria" is the
specific thing to tick.

| ID | Scenario | Input | Expected outcome | PASS criteria |
|---|---|---|---|---|
| UAT-001 | Happy path (PwC) | `find AI jobs at PwC in Bangalore` | All four `[CompanyConfirm]` / `[Scraper]` / `[DB]` / `[Tester]` lines appear; results table renders; Tester panel shows green **PASS**. | `output/pricewaterhousecoopers.csv` exists and has > 0 data rows. |
| UAT-002 | Alias resolution (SFDC) | `data engineer jobs at sfdc` | CompanyConfirm resolves `sfdc` to `Salesforce` (per `_ALIASES` in `tools/companies.py`). | Output filename slug starts with `salesforce`; Tester PASSes. |
| UAT-003 | Unknown company short-circuit | `find AI jobs at Acme Corp` | CompanyConfirm reports it could not resolve the company. Scraper, DB, Tester print their "Skipped" / "no CSV" branches. | Final Tester panel shows **FAIL** with the issue *"No CSV produced by DB agent."* and no file is written. |
| UAT-004 | Empty result set | `find quantum cryogenics jobs at PwC` (or any very rare keyword) | Workday returns zero matches; DB node skips persistence. | `[Scraper] Retrieved 0 postings...`, `[DB] Skipped: no postings to persist.`, Tester FAIL with row_count = 0. No partial CSV left behind. |
| UAT-005 | Multiple roles + alternate company | `ML engineer jobs at Adobe` | Adobe canonical name resolves; postings come back. | Output saved under `output/adobe.csv`; row count > 0. |
| UAT-006 | Location filter is applied | `find AI jobs at PwC in Bangalore` | Only Bangalore postings should appear in the CSV. | Open the CSV in a spreadsheet; the `location` column contains "Bangalore" (or "Bengaluru") for every row. |
| UAT-007 | No location given | `find AI jobs at PwC` | Postings come back from any location. | CSV contains rows whose `location` is NOT all the same city. |
| UAT-008 | Idempotent re-run | Run UAT-001 a second time without deleting `output/` | Same query repeated; existing files are overwritten cleanly. | No duplicate rows in the SQLite table — the PK `(company, job_id)` upserts. Tester PASSes both times. |
| UAT-009 | CSV is spreadsheet-readable | After UAT-001, open `output/pricewaterhousecoopers.csv` in Excel / Numbers / LibreOffice | The file opens, columns line up, UTF-8 characters render. | Header row reads `company, job_id, title, location, posted_on, url`; no broken cells; clickable URLs. |
| UAT-010 | Cost sanity (with API key) | Run UAT-001 once with `ANTHROPIC_API_KEY` set | Each of the four nodes calls `ChatAnthropic` once with `temperature=0` on `claude-sonnet-4-5`. | A single query should consume a small, predictable token budget (well under $0.10). Check your Anthropic console after the run. |
| **UAT-011** | **Graph traversal** | `find AI jobs at PwC in Bangalore` | The REPL prints one progress line *per node, in order*. | Output contains, in this order: `[CompanyConfirm] ...`, `[Scraper] ...`, `[DB] ...`, `[Tester] ...`. Missing any one of the four = FAIL. |
| **UAT-012** | **Graph short-circuit on validation failure** | First run UAT-003 (unknown company), then re-run UAT-001 in the same REPL session | When validation fails, the final Tester panel must surface the cause in plain language. | For UAT-003: Tester panel shows `Validation: FAIL` and the `Issues:` line names the cause (`No CSV produced by DB agent.`). The subsequent UAT-001 run still PASSes — the failure did not contaminate the session. |

### How to read the REPL output

Each invocation prints a horizontal rule with your message, then four
`[NodeName] ...` log lines (one per graph node), then a results table of
up to 10 postings, then a Rich "Tester" panel.

Example of UAT-011 passing output:

```
─────────────── find AI jobs at PwC in Bangalore ───────────────
  [CompanyConfirm] Resolved 'pwc' -> PricewaterhouseCoopers. Keywords='AI', location='Bangalore'.
  [Scraper] Retrieved 14 postings from PricewaterhouseCoopers.
  [DB] Persisted 14 postings -> .../output/pricewaterhousecoopers.csv and .../output/pricewaterhousecoopers.sqlite.
  [Tester] PASS: rows=14, unique_ids=14, issues=[]
```

If you see fewer than four `[...]` lines, UAT-011 fails — capture the
full transcript when reporting.

---

## 5. Negative tests

These are deliberate "make it fail nicely" probes. The bot must degrade
gracefully, never traceback.

| ID | Provocation | Expected behaviour |
|---|---|---|
| NEG-01 | Empty input — just press Enter at the `you >` prompt | The REPL re-prompts on the next line. No graph invocation. |
| NEG-02 | Type `exit` (or `quit`, `:q`) | The REPL prints `Goodbye.` and returns to the shell with exit code 0. |
| NEG-03 | Press Ctrl+C mid-query | The REPL exits cleanly with `Goodbye.` Not a Python traceback. |
| NEG-04 | Garbled input: `asdjkhasd 12387` | CompanyConfirm cannot extract a company; full short-circuit path as in UAT-003. No crash. |
| NEG-05 | Bogus API key in `.env` | The four nodes' `ChatAnthropic` calls fail silently (wrapped in `try/except Exception`) and the deterministic fallbacks still produce a valid CSV. Run still PASSes the Tester. |
| NEG-06 | Workday endpoint unreachable (simulate by disabling Wi-Fi mid-run) | Scraper logs `[Scraper] Scrape failed: <httpx error>` and an empty postings list. DB skips. Tester FAILs cleanly with row_count = 0. |
| NEG-07 | `output/` is read-only | DB node raises during `write_csv` / `write_sqlite`. This is acceptable — capture the traceback and file a bug if the message is unfriendly. |

---

## 6. Performance expectations

The graph compiles once per `run_chat()` call and walks four nodes
sequentially. With a key set, each node makes its own `ChatAnthropic`
call, so latency is roughly *(4 x model latency) + (Workday pagination)*.

| Scenario | Typical wall time |
|---|---|
| Full graph with API key, ~50 postings | **15–40 seconds** |
| Offline / no API key (regex fallback path) | < 5 seconds |
| Smoke test suite (`uv run pytest -q`) | < 3 seconds |
| Unknown company short-circuit | < 10 seconds (CompanyConfirm still calls the LLM once if a key is set) |

If a run exceeds **60 seconds**, capture the transcript and file a bug —
that usually means Workday pagination is stuck or the model is retrying.

---

## 7. Sign-off template

Copy this block into your UAT report and fill it in.

```
Project       : job-chatbot-langchain
Build / SHA   : <git rev-parse --short HEAD>
Tester name   : ____________________
Date          : YYYY-MM-DD
Environment   : <macOS 14.x / Ubuntu 22.04 / WSL ...>
Python        : <python --version>
uv version    : <uv --version>
API key used  : yes / no

Results:
  UAT-001 Happy path PwC ................. [ PASS / FAIL ]
  UAT-002 Alias SFDC ..................... [ PASS / FAIL ]
  UAT-003 Unknown company ................ [ PASS / FAIL ]
  UAT-004 Empty result set ............... [ PASS / FAIL ]
  UAT-005 ML + Adobe ..................... [ PASS / FAIL ]
  UAT-006 Location filter ................ [ PASS / FAIL ]
  UAT-007 No location .................... [ PASS / FAIL ]
  UAT-008 Idempotent re-run .............. [ PASS / FAIL ]
  UAT-009 CSV readable in spreadsheet .... [ PASS / FAIL ]
  UAT-010 Cost sanity .................... [ PASS / FAIL ]
  UAT-011 Graph traversal (4 nodes) ...... [ PASS / FAIL ]
  UAT-012 Short-circuit on validation .... [ PASS / FAIL ]

Negative tests: NEG-01..07 ............... [ PASS / FAIL ]

Notes / deviations:
  ____________________________________________

Sign-off:
  Tester signature : ____________________
  Product owner    : ____________________
```

A release is **approved** only when all UAT-### scenarios are PASS and
the negative tests behave as documented. A single FAIL blocks the
release until either the bug is fixed or the product owner explicitly
accepts the deviation in writing.

---

## 8. Reporting bugs

When a scenario fails, file an issue with this shape:

1. **Title** — start with the UAT ID, e.g. *"UAT-006: location filter
   includes Hyderabad rows for a Bangalore query"*.
2. **Environment block** — OS, Python version, `uv --version`, whether
   `ANTHROPIC_API_KEY` was set, git SHA.
3. **Steps to reproduce** — the exact REPL input.
4. **Expected vs actual** — quote the PASS criteria from the table.
5. **Transcript** — the full REPL output for the failing run, including
   all four `[NodeName] ...` lines. This is critical for diagnosing
   *which* graph node misbehaved.
6. **Artefacts** — attach the generated `output/<slug>.csv` (or note
   that no file was produced).
7. **Severity** — Blocker (release stops), Major (workaround exists),
   Minor (cosmetic).

Do not include your real `ANTHROPIC_API_KEY` in the report. Redact it
with `sk-ant-...REDACTED...`.

Triage owner: see `CODEOWNERS` if present, otherwise the repository
owner listed in `pyproject.toml`.
