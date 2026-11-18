"""Data shapes shared by the scrapers, scoring and search."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Job:
    source: str
    source_id: str
    title: str
    company: str
    location: str
    url: str
    salary: str = ""
    experience_text: str = ""
    skills_text: str = ""
    description: str = ""
    posted: str = ""
    is_internship: bool = False
    min_years: float = 0.0
    max_years: float | None = None
    # filled by scoring / dedupe
    verdict: str = ""
    coverage: float = 0.0
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    also_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SiteStatus:
    source: str
    state: str = "pending"  # pending | running | done | failed | blocked
    message: str = ""
    count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)
