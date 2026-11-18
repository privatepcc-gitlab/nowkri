"""Tests pinning the final-review findings."""
from pathlib import Path

import httpx

from app.jobs.models import Job
from app.jobs.scrapers import base, internshala
from app.jobs.scrapers.base import MAX_RESULT_PAGES, Scraper
from app.jobs.search import SearchManager, SearchRequest, SkillIn
from app.jobs.store import JobCache

FIX = Path(__file__).parent / "fixtures" / "jobs"
LEVELS = [SkillIn(name=n, level=3) for n in "Python SQL Excel Tableau Pandas".split()]


def mock_transport(log):
    page = (FIX / "internshala_jobs.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request):
        log.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text=page)
    return httpx.MockTransport(handler)


async def test_pause_between_every_request_across_queries(tmp_path, monkeypatch):
    pauses, log = [], []

    async def fake_pause(delay):
        pauses.append(delay)
    monkeypatch.setattr(base, "polite_pause", fake_pause)
    sc = internshala.InternshalaScraper()
    sc.transport = mock_transport(log)
    mgr = SearchManager(JobCache(tmp_path / "c.sqlite"), lambda: [sc])
    sid = mgr.start(SearchRequest(titles=["Data Analyst", "Python", "SQL"], skills=LEVELS,
                                  experience_years=3))
    await mgr.run(sid)
    assert log.count("/robots.txt") == 1          # robots fetched once per site per search
    assert len(pauses) == len(log) - 1            # a pause before every request but the first


async def test_result_page_budget_shared_across_queries(tmp_path):
    used = []

    class Counting(Scraper):
        name = "counting"

        async def search(self, query, location, internship, pages=1):
            while self.take_page():
                used.append(query)
                if len([u for u in used if u == query]) >= pages:
                    break
            return []

    mgr = SearchManager(JobCache(tmp_path / "c.sqlite"), lambda: [Counting()])
    sid = mgr.start(SearchRequest(skills=LEVELS))   # 5 skill queries
    await mgr.run(sid)
    assert len(used) == MAX_RESULT_PAGES == 3


async def test_fresher_gets_internshala_jobs_and_internships(tmp_path, monkeypatch):
    async def no_pause(delay):
        pass
    monkeypatch.setattr(base, "polite_pause", no_pause)
    log = []
    sc = internshala.InternshalaScraper()
    sc.transport = mock_transport(log)
    async with sc:
        await sc.search("Data Analyst", "", True, 1)
    paths = [p for p in log if p != "/robots.txt"]
    assert paths == ["/internships/data-analyst-internship/", "/jobs/data-analyst-jobs/"]


class Flaky(Scraper):
    name = "flaky"
    fail = True

    async def search(self, query, location, internship, pages=1):
        if Flaky.fail:
            raise RuntimeError("timeout")
        return [Job("flaky", "1", "Data Analyst", "A", "Pune", "u", skills_text="Python, SQL")]


class Good(Scraper):
    name = "good"

    async def search(self, query, location, internship, pages=1):
        return [Job("good", "2", "Data Analyst", "B", "Pune", "u2", skills_text="Python, SQL")]


async def test_search_with_failed_site_is_not_cached(tmp_path):
    Flaky.fail = True
    mgr = SearchManager(JobCache(tmp_path / "c.sqlite"), lambda: [Flaky(), Good()])
    req = SearchRequest(titles=["Data Analyst"], skills=LEVELS)
    sid = mgr.start(req)
    await mgr.run(sid)
    Flaky.fail = False
    sid2 = mgr.start(req)
    assert not mgr.get(sid2)["cached"]
    await mgr.run(sid2)
    assert {j["source"] for j in mgr.get(sid2)["jobs"]} == {"flaky", "good"}


async def test_cached_search_keeps_site_statuses_and_refresh_bypasses(tmp_path):
    calls = []

    def factory():
        calls.append(1)
        return [Good()]
    mgr = SearchManager(JobCache(tmp_path / "c.sqlite"), factory)
    req = SearchRequest(titles=["Data Analyst"], skills=LEVELS)
    await mgr.run(mgr.start(req))
    cached = mgr.get(mgr.start(req))
    assert cached["cached"] and [s["source"] for s in cached["sites"]] == ["good"]
    sid = mgr.start(req.model_copy(update={"refresh": True}))
    await mgr.run(sid)
    assert len(calls) == 2 and not mgr.get(sid)["cached"]


async def test_search_always_finishes_even_if_publish_breaks(tmp_path, monkeypatch):
    import app.jobs.search as search
    mgr = SearchManager(JobCache(tmp_path / "c.sqlite"), lambda: [Good()])
    sid = mgr.start(SearchRequest(titles=["Data Analyst"], skills=LEVELS))

    def broken(jobs):
        raise ValueError("boom")
    monkeypatch.setattr(search, "dedupe", broken)
    try:
        await mgr.run(sid)
    except ValueError:
        pass
    assert mgr.get(sid)["state"] == "done"


async def test_internshala_retries_without_role_words(monkeypatch):
    async def no_pause(delay):
        pass
    monkeypatch.setattr(base, "polite_pause", no_pause)
    page = (FIX / "internshala_internships.html").read_text(encoding="utf-8")
    log = []

    def handler(request):
        log.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/internships/embedded-systems-engineer-internship/":
            return httpx.Response(302, headers={"Location": "https://internshala.com/internships/"})
        return httpx.Response(200, text=page)
    sc = internshala.InternshalaScraper()
    sc.transport = httpx.MockTransport(handler)
    async with sc:
        jobs = await sc.search("Embedded Systems Engineer", "", True, 1)
    assert "/internships/embedded-systems-internship/" in log and jobs
    assert internshala.simplify_query("Senior Python Developer") == "Python"
    assert internshala.simplify_query("Data Analyst") == "Data Analyst"
