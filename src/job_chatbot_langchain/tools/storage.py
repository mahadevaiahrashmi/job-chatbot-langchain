"""CSV + SQLite persistence for job postings."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from ..models import JobPosting

_CSV_FIELDS = ["company", "job_id", "title", "location", "posted_on", "url"]


def write_csv(postings: list[JobPosting], path: Path) -> Path:
    """Write postings to a CSV at `path`. Returns the path written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for posting in postings:
            writer.writerow(posting.to_dict())
    return path


def write_sqlite(postings: list[JobPosting], path: Path) -> Path:
    """Persist postings to a SQLite DB at `path`. Returns the path written.

    The schema uses (company, job_id) as a primary key so repeated runs upsert.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_postings (
                company   TEXT NOT NULL,
                job_id    TEXT NOT NULL,
                title     TEXT NOT NULL,
                location  TEXT,
                posted_on TEXT,
                url       TEXT,
                PRIMARY KEY (company, job_id)
            )
            """
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO job_postings
                (company, job_id, title, location, posted_on, url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    p.company,
                    p.job_id,
                    p.title,
                    p.location,
                    p.posted_on,
                    p.url,
                )
                for p in postings
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return path
