"""Runs a live job search across all sites and tracks its progress.

POST /api/jobs/search -> SearchManager.start() -> search_id
background            -> SearchManager.run(search_id)  (all sites at once)
GET  /api/jobs/search/{id} -> SearchManager.get()       (polled by the UI)
"""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Callable

from pydantic import BaseModel

from .models import Job, SiteStatus
from .scoring import score_job
from .scrapers import get_scrapers
from .scrapers.base import MAX_RESULT_PAGES, BlockedError, Scraper
from .store import JobCache, cache_key, dedupe

MAX_TITLE_QUERIES = 3
MAX_SKILL_QUERIES = 5
MAX_KEPT_SEARCHES = 50
VERDICT_ORDER = {"APPLY": 0, "ALMOST": 1, "SKIP": 2}


class SkillIn(BaseModel):
    name: str
    level: int


class SearchRequest(BaseModel):
    titles: list[str] = []
    skills: list[SkillIn] = []
    experience_years: float = 0
    location: str = ""
    include_internships: bool | None = None
    refresh: bool = False  # skip the cache ("Search again")

    def internships(self) -> bool:
        if self.include_internships is not None:
            return self.include_internships
        return self.experience_years < 1


def build_queries(req: SearchRequest) -> list[str]:
    seen, out = set(), []
    for t in req.titles:
        t = re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", t)).strip()  # 'X (Entry Level)' -> 'X'
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    if out:
        return out[:MAX_TITLE_QUERIES]
    ranked = sorted(req.skills, key=lambda s: -s.level)  # stable: keeps resume order on ties
    return [s.name for s in ranked][:MAX_SKILL_QUERIES]


_STOP = {"and", "the", "for", "with", "jobs", "job", "senior", "junior", "intern", "internship",
         "engineer", "developer", "executive", "associate", "specialist", "trainee", "fresher", "manager"}


def is_relevant(job: Job, query: str) -> bool:
    """Some sites pad results with unrelated postings. Keep a posting only if it
    shares a meaningful word (3+ letters, not a generic job word) with the query.
    Queries with no such word (e.g. 'C', 'Go') keep everything."""
    words = {w for w in re.findall(r"[a-z0-9+#.]+", query.lower()) if len(w) >= 3 and w not in _STOP}
    if not words:
        return True
    hay = f"{job.title} {job.skills_text} {job.description}".lower()
    return any(w in hay for w in words)


def _sort(jobs: list[Job]) -> list[Job]:
    return sorted(jobs, key=lambda j: (VERDICT_ORDER.get(j.verdict, 3), -j.coverage))


class SearchManager:
    def __init__(self, cache: JobCache, scrapers_factory: Callable[[], list[Scraper]] = get_scrapers):
        self.cache = cache
        self.factory = scrapers_factory
        self.searches: dict[str, dict] = {}

    def start(self, req: SearchRequest) -> str:
        sid = uuid.uuid4().hex[:12]
        key = cache_key(req.model_dump(exclude={"refresh"}))
        cached = None if req.refresh else self.cache.get(key)
        if isinstance(cached, list):  # older cache format: jobs only
            cached = {"jobs": cached, "sites": []}
        self.searches[sid] = {
            "id": sid, "state": "done" if cached is not None else "running",
            "cached": cached is not None, "queries": build_queries(req),
            "sites": cached["sites"] if cached else [], "jobs": cached["jobs"] if cached else [],
            "_req": req, "_key": key,
        }
        while len(self.searches) > MAX_KEPT_SEARCHES:
            self.searches.pop(next(iter(self.searches)))
        return sid

    def get(self, sid: str) -> dict | None:
        s = self.searches.get(sid)
        if s is None:
            return None
        return {k: v for k, v in s.items() if not k.startswith("_")}

    async def run(self, sid: str) -> None:
        s = self.searches.get(sid)
        if s is None or s["state"] == "done":
            return
        try:
            await self._run(s)
        finally:
            s["state"] = "done"  # whatever happens, the UI must stop waiting

    async def _run(self, s: dict) -> None:
        req: SearchRequest = s["_req"]
        queries = s["queries"]
        levels = {sk.name: sk.level for sk in req.skills}
        resume_text = " ".join(req.titles + [sk.name for sk in req.skills])
        internship = req.internships()
        # per-query cap; each scraper's pages_left budget caps the total per site
        pages = max(1, MAX_RESULT_PAGES // max(1, len(queries)))

        try:
            scrapers = self.factory()
        except Exception as e:  # noqa: BLE001 - never leave a search hanging
            s["sites"] = [SiteStatus("all", "failed", f"could not load scrapers: {e}").to_dict()]
            return
        statuses = {sc.name: SiteStatus(sc.name) for sc in scrapers}
        found: list[Job] = []

        def publish():
            s["sites"] = [st.to_dict() for st in statuses.values()]
            s["jobs"] = [j.to_dict() for j in _sort(dedupe(found))]

        async def run_site(sc: Scraper):
            st = statuses[sc.name]
            st.state = "running"
            try:
                async with sc:  # one polite client for all of this site's queries
                    for q in queries:
                        if sc.pages_left <= 0:
                            break
                        jobs = [j for j in await sc.search(q, req.location, internship, pages)
                                if is_relevant(j, q)]
                        for j in jobs:
                            score_job(j, levels, req.experience_years, resume_text)
                        found.extend(jobs)
                        st.count += len(jobs)
                        publish()
                st.state = "done"
            except BlockedError as e:
                st.state, st.message = "blocked", str(e)
            except Exception as e:  # noqa: BLE001 - one site failing must not stop the rest
                st.state, st.message = "failed", f"{type(e).__name__}: {e}"[:300]
            try:
                publish()
            except Exception:  # noqa: BLE001
                pass

        publish()
        await asyncio.gather(*(run_site(sc) for sc in scrapers), return_exceptions=True)
        publish()
        states = [st.state for st in statuses.values()]
        # only cache complete answers: a site that failed (e.g. timed out) should be retried next time
        if "done" in states and "failed" not in states:
            self.cache.put(s["_key"], {"jobs": s["jobs"], "sites": s["sites"]})
