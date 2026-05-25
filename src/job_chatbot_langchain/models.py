"""Data models for job postings and search queries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JobQuery:
    company: str
    keywords: str
    location: str | None = None
    limit: int = 100


@dataclass
class JobPosting:
    company: str
    job_id: str
    title: str
    location: str
    posted_on: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "company": self.company,
            "job_id": self.job_id,
            "title": self.title,
            "location": self.location,
            "posted_on": self.posted_on,
            "url": self.url,
        }


@dataclass
class ValidationReport:
    ok: bool
    row_count: int
    unique_job_ids: int
    issues: list[str] = field(default_factory=list)
