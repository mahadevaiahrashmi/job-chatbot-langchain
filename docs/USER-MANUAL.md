# User Manual

A non-technical walkthrough of `job-chatbot-langchain`. If you can copy and
paste commands into a terminal, you can use this tool — no Python experience
required.

## What this tool does

`job-chatbot-langchain` is a small command-line chatbot that searches the
public careers websites of well-known companies and gives you a clean,
structured list of their current openings. You type a request in plain
English — for example, *"find AI jobs at PwC in Bangalore"* — and the bot
goes off, fetches the matching postings, saves them to a spreadsheet on your
computer, and prints a short summary of what it found.

Under the hood it runs four small "agents" in a fixed sequence: one figures
out which company you meant, one fetches the postings from that company's
Workday careers site, one writes them to disk, and a final one double-checks
the saved file looks healthy. You don't need to know any of that to use it,
but it's why the tool can validate its own output and tell you whether the
run succeeded or failed.

## What you need before starting

You need three things on your machine:

1. **Python 3.11 or newer.** Check with `python3 --version`. If you don't
   have it, install it from [python.org](https://www.python.org/downloads/)
   or via Homebrew (`brew install python@3.11`).
2. **An Anthropic API key.** Sign up at
   [console.anthropic.com](https://console.anthropic.com/) and create a key.
   It looks like `sk-ant-...`. The tool will still run without one (using a
   regex-based fallback), but the natural-language understanding is much
   better with a real key.
3. **`uv`**, a fast Python package manager. Install it with:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

That's it. You don't need to install LangChain, LangGraph, or any other
library by hand — `uv` will do that for you.

## Installing for the first time

Open a terminal, then run these commands one at a time:

```bash
# 1. Grab the code.
git clone git@github.com:mahadevaiahrashmi/job-chatbot-langchain.git
cd job-chatbot-langchain

# 2. Create an isolated Python environment for this project.
uv venv

# 3. Install all the dependencies (LangChain, LangGraph, httpx, etc.).
uv sync

# 4. Copy the example environment file and add your API key.
cp .env.example .env
```

Now open `.env` in any text editor (TextEdit, VS Code, nano) and replace
`sk-ant-...` with your real Anthropic API key. Save and close.

You're done. You won't need to repeat these steps unless you move the
project to another machine.

## Running the bot

From inside the `job-chatbot-langchain` folder, run:

```bash
uv run job-chatbot-langchain
```

You will see a welcome panel listing the supported companies, followed by
a prompt:

```
you >
```

Type your query in plain English and press Enter. The bot will narrate each
step ("CompanyConfirm…", "Scraper…", "DB…", "Tester…") and finish with a
PASS or FAIL summary plus a table of the first 10 postings it found.

To exit, type `quit`, `exit`, `:q`, or press Ctrl-D.

You can also run a **one-shot** query without entering the REPL:

```bash
uv run job-chatbot-langchain "find AI jobs at PwC in Bangalore"
```

Useful flags:

- `--output-dir some/folder` — write the CSV and SQLite files somewhere
  other than `output/`.
- `--limit 50` — cap the number of postings retrieved per company
  (default is 100).

## Example queries

The bot is tolerant of plain English. Anything that mentions one of the
supported companies plus a role keyword will usually work.

| You type | What happens |
|---|---|
| `find AI jobs at PwC in Bangalore` | PwC openings matching "AI" in Bangalore. |
| `get all jobs from Salesforce related to data engineering` | Salesforce openings matching "data engineering" (no location filter). |
| `show me NVIDIA roles about machine learning` | NVIDIA openings matching "machine learning". |
| `find product manager positions at Adobe` | Adobe openings matching "product manager". |
| `cisco security engineer jobs` | Cisco openings matching "security engineer". |
| `jpmorgan jobs in New York related to risk` | JPMorgan Chase openings filtered to New York and the keyword "risk". |
| `netflix data scientist jobs` | Netflix openings matching "data scientist". |
| `workday platform engineer roles` | Workday openings matching "platform engineer". |

Tips:

- Capitalised location words help (e.g. *"in Bangalore"*, not *"in bangalore"*) —
  the parser uses capitalisation as a hint that something is a place.
- Aliases work: *pwc*, *jpmc*, *sfdc* all resolve to the canonical name.
- If you don't include a location, the bot will fetch postings worldwide.

## Where the results live

After a run completes, you'll find two files in the `output/` folder (or
whichever folder you passed to `--output-dir`):

- `output/<company-slug>.csv` — a spreadsheet you can open in Excel,
  Numbers, or Google Sheets. The slug is derived from the company's
  canonical name; for example, PwC produces `pricewaterhousecoopers.csv`.
- `output/<company-slug>.sqlite` — a tiny self-contained database with
  the same rows. Useful if you want to query the data with SQL or load it
  into a tool like DB Browser for SQLite.

Re-running the bot for the same company **overwrites** the CSV and
**upserts** into the SQLite table (the primary key is `(company, job_id)`,
so duplicates merge cleanly).

## Reading the CSV

Every row is one job posting. The columns are:

| Column | What it means |
|---|---|
| `company` | The full canonical company name (e.g. *PricewaterhouseCoopers*). |
| `job_id` | The company's internal requisition ID (e.g. *712616WD*). Useful for tracking — paste this into the company's careers search to find the same posting later. |
| `title` | The job title as the company wrote it. |
| `location` | The full location string from Workday, often including city and country (e.g. *Bengaluru, India*). |
| `posted_on` | A relative date string from Workday (e.g. *"Posted 2 days ago"*). |
| `url` | A direct link you can click to apply or read the full description. |

## Supported companies

Eight companies are wired up out of the box. Aliases (lowercase, ignoring
spaces) are accepted for any of them.

| Canonical name | Aliases you can use |
|---|---|
| PricewaterhouseCoopers | `pwc`, `pricewaterhousecoopers`, `price waterhouse coopers`, `pwc india` |
| JPMorgan Chase | `jpmorgan`, `jp morgan`, `jpmc`, `jpmorgan chase`, `chase` |
| Salesforce | `salesforce`, `sfdc` |
| Cisco | `cisco` |
| Adobe | `adobe` |
| NVIDIA | `nvidia` |
| Netflix | `netflix` |
| Workday | `workday` |

To add a new company, edit
`src/job_chatbot_langchain/tools/companies.py` — see the developer-facing
[system design doc](./SYSTEM-DESIGN.md) for details.

## Common questions and troubleshooting

**Q: The bot says "Could not resolve company from message". What now?**
The company you mentioned isn't in the supported list, or you spelled it in
a way the alias table doesn't cover. Try one of the names from the
"Supported companies" table above. If you want a new company added, see the
extension instructions in the system-design doc.

**Q: It says PASS but `row_count=0`. Is that good?**
No — a zero-row run is reported as FAIL by the Tester. If you see
`rows=0, unique_ids=0`, the Workday site returned no postings matching your
keywords. Try a broader keyword (e.g. *"engineering"* instead of *"staff
machine-learning research engineer"*) or drop the location filter.

**Q: I get an HTTP error or a timeout.**
The bot talks directly to each company's Workday endpoint. Those endpoints
are public but occasionally rate-limit or rotate. Wait a minute and retry.
If a specific company is persistently failing, the tenant or site name in
`tools/companies.py` may have changed — open an issue.

**Q: I don't have an Anthropic API key. Will it still work?**
Yes, but with a caveat. Without `ANTHROPIC_API_KEY` set, the bot falls back
to a deterministic regex parser for the user's message. Simple queries
("AI jobs at PwC in Bangalore") work fine; more unusual phrasings may not
extract the keywords correctly. The Workday scrape, CSV write, and
validation all run normally either way.

**Q: How do I see only postings from the last week?**
The Workday `postedOn` field is a free-text relative date ("Posted today",
"Posted 5 days ago"), so the bot doesn't filter by date today. Sort the
CSV by `posted_on` in your spreadsheet tool, or query the SQLite DB
directly.

**Q: Can I run this on a schedule?**
Yes — wrap the one-shot form in cron or a launchd plist:
`uv run job-chatbot-langchain "find AI jobs at PwC"`. Each run will
overwrite the CSV for that company.

**Q: Where are the test results stored?**
Nowhere on disk — the Tester agent's report is printed to the terminal as a
PASS/FAIL panel and held in the in-memory `ChatState` for the duration of
the run.

## Privacy and cost

**Privacy.** Everything runs locally on your machine. The only outbound
network calls are (a) to each company's public Workday careers endpoint
(no authentication, no cookies, no personal data — just the keyword and
location you typed) and (b) optionally to Anthropic's API for the
natural-language parsing step. No telemetry, no analytics, no third-party
trackers. The CSV and SQLite files stay on your laptop.

**Cost.** Each query makes at most a handful of short calls to Claude
Sonnet 4.5 (one per agent, four agents). At current Anthropic pricing
this works out to well under a US cent per query in typical use. If you
run the bot without an API key, your cost is zero — only the regex
fallback runs.
