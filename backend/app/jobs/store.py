"""Short-lived SQLite cache for search results, and cross-site de-duplication."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

from .models import Job

_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _SPACE.sub(" ", _PUNCT.sub(" ", (s or "").lower())).strip()


def _key(job: Job) -> tuple[str, str, str]:
    city = (job.location or "").split(",")[0]
    return _norm(job.company), _norm(job.title), _norm(city)


def dedupe(jobs: list[Job]) -> list[Job]:
    """Merge postings with the same (company, title, city). Keep the most
    detailed one and list the other sources in ``also_on``."""
    groups: dict[tuple, list[Job]] = {}
    for j in jobs:
        groups.setdefault(_key(j), []).append(j)
    out = []
    for group in groups.values():
        best = max(group, key=lambda j: len(j.description) + len(j.skills_text))
        others = set(best.also_on)
        for j in group:
            others.update(j.also_on)
            if j.source != best.source:
                others.add(j.source)
        others.discard(best.source)
        best.also_on = sorted(others)
        out.append(best)
    return out


def cache_key(request: dict) -> str:
    r = dict(request)
    if "titles" in r:
        r["titles"] = sorted(t.strip().lower() for t in r["titles"])
    if "location" in r:
        r["location"] = (r["location"] or "").strip().lower()
    return hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()


class JobCache:
    def __init__(self, path: Path, ttl_seconds: int = 6 * 3600):
        self.path = Path(path)
        self.ttl = ttl_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS searches "
                      "(key TEXT PRIMARY KEY, created_at REAL, jobs TEXT)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def get(self, key: str):
        with self._conn() as c:
            row = c.execute("SELECT created_at, jobs FROM searches WHERE key = ?", (key,)).fetchone()
        if not row or time.time() - row[0] > self.ttl:
            return None
        return json.loads(row[1])

    def put(self, key: str, jobs) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO searches VALUES (?, ?, ?)",
                      (key, time.time(), json.dumps(jobs)))
