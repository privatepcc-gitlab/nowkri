import asyncio

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.jobs.models import Job
from app.jobs.scrapers.base import BlockedError, Scraper, looks_blocked
from app.jobs.search import SearchManager, SearchRequest, SkillIn, build_queries
from app.jobs.store import JobCache

LEVELS = [SkillIn(name="Python", level=3), SkillIn(name="SQL", level=3), SkillIn(name="Pandas", level=2)]


class GoodFake(Scraper):
    name = "good"

    async def search(self, query, location, internship, pages=1):
        return [Job("good", "1", "Data Analyst", "Acme", "Pune", "u1", skills_text="Python, SQL, Pandas"),
                Job("good", "2", "Data Platform Engineer", "Beta", "Pune", "u2", skills_text="Docker, AWS, Kubernetes")]


class BoomFake(Scraper):
    name = "boom"

    async def search(self, query, location, internship, pages=1):
        raise RuntimeError("layout changed")


class BlockedFake(Scraper):
    name = "blocked"

    async def search(self, query, location, internship, pages=1):
        raise BlockedError("captcha page")


def test_build_queries_falls_back_to_skills():
    req = SearchRequest(skills=[SkillIn(name=n, level=3) for n in "Python SQL Excel Tableau Pandas Git".split()])
    assert build_queries(req) == ["Python", "SQL", "Excel", "Tableau", "Pandas"]


def test_build_queries_top_three_titles():
    assert build_queries(SearchRequest(titles=["A", "B", "C", "D"])) == ["A", "B", "C"]


def test_looks_blocked():
    assert looks_blocked(429, "")
    assert looks_blocked(403, "")
    assert looks_blocked(200, "<div id=cf-challenge>")
    assert not looks_blocked(200, "<ul>jobs</ul>")


async def test_failing_site_does_not_stop_others(tmp_path):
    mgr = SearchManager(JobCache(tmp_path / "c.sqlite"), lambda: [GoodFake(), BoomFake(), BlockedFake()])
    sid = mgr.start(SearchRequest(titles=["Data Analyst"], skills=LEVELS))
    await mgr.run(sid)
    s = mgr.get(sid)
    assert s["state"] == "done"
    assert {x["source"]: x["state"] for x in s["sites"]} == {"good": "done", "boom": "failed", "blocked": "blocked"}
    assert len(s["jobs"]) == 2 and s["jobs"][0]["verdict"] == "APPLY" and s["jobs"][1]["verdict"] == "SKIP"


async def test_second_identical_search_hits_cache(tmp_path):
    calls = []

    def factory():
        calls.append(1)
        return [GoodFake()]

    mgr = SearchManager(JobCache(tmp_path / "c.sqlite"), factory)
    req = SearchRequest(titles=["Data Analyst"], skills=LEVELS)
    sid = mgr.start(req)
    await mgr.run(sid)
    sid2 = mgr.start(req)
    await mgr.run(sid2)
    assert len(calls) == 1
    s = mgr.get(sid2)
    assert s["state"] == "done" and s["cached"] and len(s["jobs"]) == 2


async def test_empty_titles_still_searches(tmp_path):
    seen = []

    class Rec(GoodFake):
        async def search(self, query, location, internship, pages=1):
            seen.append((query, internship))
            return []

    mgr = SearchManager(JobCache(tmp_path / "c.sqlite"), lambda: [Rec()])
    sid = mgr.start(SearchRequest(skills=LEVELS, experience_years=0))
    await mgr.run(sid)
    assert [q for q, _ in seen] == ["Python", "SQL", "Pandas"] and all(i for _, i in seen)
    assert mgr.get(sid)["state"] == "done"


def test_api_start_and_poll(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "search_manager", SearchManager(JobCache(tmp_path / "c.sqlite"), lambda: [GoodFake()]))
    client = TestClient(main.app)
    r = client.post("/api/jobs/search", json={"titles": ["Data Analyst"], "skills": [s.model_dump() for s in LEVELS]})
    assert r.status_code == 200
    sid = r.json()["search_id"]
    s = client.get(f"/api/jobs/search/{sid}").json()   # TestClient runs background tasks before returning
    assert s["state"] == "done" and len(s["jobs"]) == 2
    assert client.get("/api/jobs/search/nope").status_code == 404


async def test_irrelevant_postings_dropped(tmp_path):
    class Noisy(GoodFake):
        name = "noisy"

        async def search(self, query, location, internship, pages=1):
            return [Job("noisy", "1", "Graphic Designer", "X", "Mumbai", "u", skills_text="Photoshop"),
                    Job("noisy", "2", "Junior Data Analyst", "Y", "Pune", "u2", skills_text="Excel"),
                    Job("noisy", "3", "Reporting Associate", "Z", "Pune", "u3", skills_text="Data analysis, SQL")]

    mgr = SearchManager(JobCache(tmp_path / "c.sqlite"), lambda: [Noisy()])
    sid = mgr.start(SearchRequest(titles=["Data Analyst"], skills=LEVELS))
    await mgr.run(sid)
    assert sorted(j["source_id"] for j in mgr.get(sid)["jobs"]) == ["2", "3"]
    assert mgr.get(sid)["sites"][0]["count"] == 2


def test_relevance_short_query_keeps_everything():
    from app.jobs.search import is_relevant
    assert is_relevant(Job("s", "1", "Embedded Engineer", "X", "Pune", "u"), "C")
    assert is_relevant(Job("s", "1", "Golang Backend", "X", "Pune", "u"), "Go")


def test_build_queries_strips_brackets_and_dupes():
    req = SearchRequest(titles=["Data Scientist (Entry Level)", "Data Scientist", "Data Analyst"])
    assert build_queries(req) == ["Data Scientist", "Data Analyst"]
