# Live Job Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Find jobs" button that searches Internshala, Naukri, LinkedIn (public pages) and Foundit for live postings that fit the analysed resume. Each posting gets an Apply / Almost there / Skip label, and results appear site by site.

**Architecture:** `POST /api/jobs/search` starts one background task per site and returns a `search_id`. The frontend polls `GET /api/jobs/search/{id}`. Each scraper returns `Job` objects. `scoring.py` labels each one using the existing `SkillExtractor`. `search.py` merges and removes duplicates, then caches the result in SQLite for 6 hours.

**Tech Stack:** FastAPI, httpx (async), BeautifulSoup + lxml, Playwright (Chromium, Naukri only), sqlite3 (stdlib), React 18 + Vite, pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-live-job-search-design.md`

**Repo note:** `D:\jobhunt` is not a git repository. Skip the "Commit" steps unless the user runs `git init` first.

## Global Constraints

- No official or paid job APIs. The scrapers never call a site's internal JSON endpoint directly. For Naukri, read only what the Playwright page loaded or rendered.
- Per site: requests one at a time, a random 2–4 s delay between them, at most 3 result pages and 20 detail pages per search. Check robots.txt before each path. Use a normal desktop Chrome User-Agent. No CAPTCHA solving, no proxies.
- If a site blocks you (403/429, a CAPTCHA or challenge page, or a challenge script with no results), mark that site `blocked` and stop it for this search. Never retry in a loop.
- Cache: SQLite at `backend/app/data/cache/jobs.sqlite` (gitignored), 6-hour lifetime.
- Labels: Apply when coverage ≥ 0.7 and experience is met. Almost there when coverage ≥ 0.5 and short by at most 1 year. Otherwise Skip. A posting with fewer than 2 recognised skills is capped at Almost there.
- Search queries: the top 3 titles from `recommended`, then `stretch`; if both are empty, the top 5 skills. `include_internships` defaults to true when experience is under 1 year. Blank location means anywhere in India.
- The existing analyse flow, endpoints and tests must keep working. If Playwright is missing, the app still starts and Naukri reports `failed`.
- Tests never touch the network. Scraper tests parse saved pages in `backend/tests/fixtures/jobs/`.

## Review Focus

1. **A posting with no experience text, or text like "Fresher" or "0 Yrs"**: treated as `min_years = 0`, never as a parse error. Test goes in Task 1.
2. **One scraper raising an error in the middle of a search**: that site is marked `failed` with a message, the other sites still finish, and the search reaches `done`. Test goes in Task 3.
3. **The same posting on two sites, with case and whitespace differences in company or title**: merged into one, with the other site listed in `also_on`. Test goes in Task 2.
4. **A cached search older than 6 hours**: a new search runs instead of returning stale results. Test goes in Task 2.
5. **An analyse result with empty `recommended` and `stretch`**: the queries fall back to the top skills and the search still runs. Test goes in Task 3.

---

## File Structure

```
backend/app/jobs/__init__.py
backend/app/jobs/models.py            Job, SiteStatus dataclasses
backend/app/jobs/scoring.py           parse_experience(), score_job()
backend/app/jobs/store.py             JobCache (SQLite), dedupe()
backend/app/jobs/search.py            SearchRequest, build_queries(), SearchManager
backend/app/jobs/scrapers/__init__.py SCRAPERS registry
backend/app/jobs/scrapers/base.py     Scraper ABC, PoliteClient, BlockedError, looks_blocked()
backend/app/jobs/scrapers/internshala.py
backend/app/jobs/scrapers/linkedin.py
backend/app/jobs/scrapers/foundit.py
backend/app/jobs/scrapers/naukri.py
backend/app/main.py                   + /api/jobs/search endpoints
backend/scripts/smoke_scrapers.py     manual live check (not pytest)
backend/tests/test_jobs_*.py
backend/tests/fixtures/jobs/*.html
frontend/src/api.js, LiveJobs.jsx, App.jsx, styles.css
start_backend.bat, backend/requirements.txt, .gitignore, README.md
```

---

### Task 1: Job model and scoring

**Files:**
- Create: `backend/app/jobs/__init__.py`, `backend/app/jobs/models.py`, `backend/app/jobs/scoring.py`
- Test: `backend/tests/test_jobs_scoring.py`

**Interfaces:**
- Produces:
  - `@dataclass Job(source: str, source_id: str, title: str, company: str, location: str, url: str, salary: str = "", experience_text: str = "", skills_text: str = "", description: str = "", posted: str = "", is_internship: bool = False, min_years: float = 0.0, max_years: float | None = None, verdict: str = "", coverage: float = 0.0, matched_skills: list[str] = [], missing_skills: list[str] = [], reasons: list[str] = [], also_on: list[str] = [])`. Use `field(default_factory=list)` for the lists. Add `to_dict() -> dict`, built with `dataclasses.asdict`.
  - `@dataclass SiteStatus(source: str, state: str = "pending", message: str = "", count: int = 0)`, where `state` is one of `pending | running | done | failed | blocked`.
  - `parse_experience(text: str) -> tuple[float, float | None]`
  - `score_job(job: Job, levels: dict[str, int], resume_years: float, resume_text: str = "") -> Job`. Sets verdict (`APPLY | ALMOST | SKIP`), coverage, matched, missing and reasons, and returns the same object.

- [ ] **Step 1: Write failing tests**

```python
from app.jobs.models import Job
from app.jobs.scoring import parse_experience, score_job

def j(**kw): return Job(source="t", source_id="1", title="Dev", company="C", location="Pune", url="u", **kw)

@pytest.mark.parametrize("text,expected", [
    ("0-2 Yrs", (0, 2)), ("2+ years", (2, None)), ("3 - 5 years", (3, 5)),
    ("Fresher", (0, None)), ("", (0, None)), ("0 Yrs", (0, None)),
])
def test_parse_experience(text, expected): assert parse_experience(text) == expected

def test_apply_when_skills_and_experience_met():
    r = score_job(j(skills_text="Python, SQL, Pandas", experience_text="0-1 Yrs"),
                  {"Python": 3, "SQL": 2, "Pandas": 2}, 0.5)
    assert r.verdict == "APPLY" and r.coverage == 1.0

def test_level_one_skill_gets_half_credit():
    r = score_job(j(skills_text="Python, SQL"), {"Python": 3, "SQL": 1}, 0)
    assert r.coverage == 0.75

def test_almost_when_one_year_short():
    r = score_job(j(skills_text="Python, SQL", experience_text="1-3 Yrs"), {"Python": 3, "SQL": 3}, 0)
    assert r.verdict == "ALMOST" and any("1+ years" in x for x in r.reasons)

def test_skip_lists_missing_skills():
    r = score_job(j(skills_text="Docker, AWS, Kubernetes"), {"Python": 3}, 0)
    assert r.verdict == "SKIP" and set(r.missing_skills) == {"Docker", "AWS", "Kubernetes"}

def test_few_skills_capped_at_almost():
    r = score_job(j(skills_text="Python", description="python developer role"), {"Python": 4}, 2,
                  resume_text="python developer")
    assert r.verdict == "ALMOST"
```

Check `skills.json` for the exact canonical skill names (e.g. "AWS", "Kubernetes") and adjust the assertions to match.

- [ ] **Step 2: Run** `cd backend && venv\Scripts\python -m pytest tests/test_jobs_scoring.py -q`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement `models.py` and `scoring.py`**

  - **Experience:** a regex for `N-M` or `N to M` followed by yrs/years gives `(N, M)`. `N+` gives `(N, None)`. "fresher" or no match gives `(0, None)`.
  - **Skills:** use one module-level `SkillExtractor()`. Call `extract({"skills": job.skills_text, "other": job.title + " " + job.description})` and use only the names.
  - **Coverage:** level ≥ 2 counts 1, level 1 counts 0.5, missing counts 0. Divide by the number of posting skills. Matched and missing lists come from the same loop.
  - **Fewer than 2 skills:** coverage is the TF-IDF cosine between the resume and the posting text (same vectoriser settings as `matcher._text_scores`). Cap the verdict at ALMOST.
  - **Reasons:** "Missing: A, B" and "Needs N+ years; resume shows Y".

- [ ] **Step 4: Run tests.** Expected: PASS. Also run the full suite, `pytest -q`. Expected: all existing tests pass.

- [ ] **Step 5: Commit** `feat(jobs): job model and posting scoring`

---

### Task 2: Cache and de-duplication

**Files:**
- Create: `backend/app/jobs/store.py`
- Modify: `.gitignore` (add `backend/app/data/cache/`)
- Test: `backend/tests/test_jobs_store.py`

**Interfaces:**
- Consumes: `Job` (Task 1)
- Produces:
  - `dedupe(jobs: list[Job]) -> list[Job]`. The key is the normalised `(company, title, city)`: lowercase, collapsed whitespace, punctuation removed, city = the first comma part of the location. Keep the posting with the longest `description + skills_text`. Add the other sites to `also_on`.
  - `class JobCache(path: Path, ttl_seconds: int = 6 * 3600)` with `get(key: str) -> list[dict] | None` and `put(key: str, jobs: list[dict]) -> None`. Store JSON plus `created_at`. Treat an entry as missing once it's older than `ttl_seconds`. Create the parent folder if needed.
  - `cache_key(request_dict: dict) -> str`: sha256 of `json.dumps(request_dict, sort_keys=True)`, after lowercasing titles and location and sorting titles.

- [ ] **Step 1: Write failing tests**

```python
def test_dedupe_merges_across_sources():
    a = Job("naukri","1","Data Analyst ","ACME Pvt. Ltd","Pune, Maharashtra","u1", description="long text here")
    b = Job("foundit","9","data analyst","Acme Pvt Ltd","pune","u2")
    out = dedupe([a, b])
    assert len(out) == 1 and out[0].source == "naukri" and out[0].also_on == ["foundit"]

def test_cache_expires(tmp_path, monkeypatch):
    c = JobCache(tmp_path / "c.sqlite", ttl_seconds=10)
    c.put("k", [{"title": "x"}]); assert c.get("k") == [{"title": "x"}]
    monkeypatch.setattr(store.time, "time", lambda: real_now + 11)   # capture real_now before put
    assert c.get("k") is None

def test_cache_key_ignores_order_and_case():
    assert cache_key({"titles": ["B", "a"], "location": "Pune"}) == cache_key({"titles": ["A", "b"], "location": "pune"})
```

- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement `store.py`** with `import time` at module level, so the test can patch the clock.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(jobs): sqlite cache and cross-site dedupe`

---

### Task 3: Scraper base, search manager and API

**Files:**
- Create: `backend/app/jobs/scrapers/__init__.py`, `backend/app/jobs/scrapers/base.py`, `backend/app/jobs/search.py`
- Modify: `backend/app/main.py` (add endpoints after `/api/analyze-text`)
- Modify: `backend/requirements.txt` (add `beautifulsoup4`, `lxml`, `playwright`)
- Test: `backend/tests/test_jobs_search.py`

**Interfaces:**
- Consumes: `Job`, `SiteStatus`, `score_job`, `dedupe`, `JobCache`, `cache_key`
- Produces:
  - `class BlockedError(Exception)`
  - `looks_blocked(status: int, html: str) -> bool`: true for 403/429, or when the HTML contains any of `captcha`, `cf-challenge`, `Access Denied`, `are you a robot` (case-insensitive).
  - `class PoliteClient` (async context manager): `async get(url: str) -> str`. Checks robots.txt with `urllib.robotparser` (fetched once per host and cached) and raises `BlockedError` if the path is disallowed. Sleeps `random.uniform(2, 4)` before every request after the first. Uses a Chrome UA and a 20 s timeout. Raises `BlockedError` when `looks_blocked`. The delay range is a constructor argument, `delay=(2, 4)`, so tests can pass `(0, 0)`.
  - `class Scraper(ABC)`: `name: str`, `async search(query: str, location: str, internship: bool) -> list[Job]`. Limits are the constants `MAX_RESULT_PAGES = 3` and `MAX_DETAIL_PAGES = 20`.
  - `scrapers/__init__.py`: `def get_scrapers() -> list[Scraper]`. Imports each site module inside try/except, so a missing Playwright drops only Naukri. Starts as an empty list; Tasks 4–6 add to it.
  - `search.py`:
    - `class SearchRequest(BaseModel)`: `titles: list[str] = []`, `skills: list[SkillIn] = []` (where `SkillIn` has `name: str` and `level: int`), `experience_years: float = 0`, `location: str = ""`, `include_internships: bool | None = None`.
    - `build_queries(req) -> list[str]`
    - `class SearchManager(cache: JobCache, scrapers_factory=get_scrapers)`:
      - `start(req) -> str`: returns the search_id. On a cache hit it creates a finished search straight away.
      - `async run(search_id)`
      - `get(search_id) -> dict | None`, shaped `{"id", "state": "running"|"done", "sites": [SiteStatus dicts], "jobs": [Job dicts]}`.
    - Searches are kept in memory in a dict.
  - API: `POST /api/jobs/search` (body `SearchRequest`) returns `{"search_id"}` and schedules `run` with FastAPI `BackgroundTasks`. `GET /api/jobs/search/{id}` returns `get()` or 404.

**Behaviour of `run`:** one `asyncio` task per scraper, all running at once. Each scraper runs every query in turn (with `internship = req.include_internships`, which defaults to `experience_years < 1`). After each query it scores the new jobs, adds them to the search's job list, and runs `dedupe` again. A site's status goes `running` → `done` with a count. On `BlockedError` it becomes `blocked`. On any other exception it becomes `failed` with the error text. Jobs are sorted by verdict (APPLY, ALMOST, SKIP), then coverage (highest first), then `posted` (newest first). When every site has finished, the search state is `done` and the results are written to the cache.

- [ ] **Step 1: Write failing tests** using fake scrapers (subclasses of `Scraper` that return fixed jobs or raise):

```python
def test_build_queries_falls_back_to_skills():
    req = SearchRequest(skills=[SkillIn(name=n, level=3) for n in "Python SQL Excel Tableau Pandas Git".split()])
    assert build_queries(req) == ["Python", "SQL", "Excel", "Tableau", "Pandas"]

def test_build_queries_top_three_titles():
    assert build_queries(SearchRequest(titles=["A","B","C","D"])) == ["A","B","C"]

async def test_failing_site_does_not_stop_others(tmp_path):
    mgr = SearchManager(JobCache(tmp_path/"c.sqlite"), lambda: [GoodFake(), BoomFake(), BlockedFake()])
    sid = mgr.start(SearchRequest(titles=["Data Analyst"])); await mgr.run(sid)
    s = mgr.get(sid)
    assert s["state"] == "done"
    assert {x["source"]: x["state"] for x in s["sites"]} == {"good": "done", "boom": "failed", "blocked": "blocked"}
    assert len(s["jobs"]) == 2 and s["jobs"][0]["verdict"] == "APPLY"

async def test_second_identical_search_hits_cache(tmp_path): ...  # the factory's call counter stays at 1

def test_api_start_and_poll(monkeypatch): ...  # patch main.search_manager with fakes; POST, then GET -> done

def test_looks_blocked():
    assert looks_blocked(429, "") and looks_blocked(200, "<div id=cf-challenge>") and not looks_blocked(200, "<ul>jobs</ul>")
```

Add `pytest-asyncio` to requirements and set `asyncio_mode = auto` in a new `backend/pytest.ini`.

- [ ] **Step 2: Run** `pytest tests/test_jobs_search.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `base.py`, `search.py`, `scrapers/__init__.py` and the endpoints. In `main.py`: `search_manager = SearchManager(JobCache(DATA_DIR / "cache" / "jobs.sqlite"))`, where `DATA_DIR = Path(__file__).parent / "data"`.
- [ ] **Step 4: Run** `pytest -q`. Expected: all pass, old and new.
- [ ] **Step 5: Commit** `feat(jobs): search manager, polite client, jobs API`

---

### Task 4: Internshala scraper

**Files:**
- Create: `backend/app/jobs/scrapers/internshala.py`, `backend/tests/fixtures/jobs/internshala_internships.html`, `backend/tests/fixtures/jobs/internshala_jobs.html`
- Modify: `backend/app/jobs/scrapers/__init__.py` (register it)
- Test: `backend/tests/test_jobs_scrapers.py`

**Interfaces:**
- Consumes: `Scraper`, `PoliteClient`, `Job`
- Produces: `class InternshalaScraper(Scraper)` with `name = "internshala"` and a pure function `parse_listing(html: str, internship: bool) -> list[Job]`.

- [ ] **Step 1: Save fixtures.** Fetch one internships page and one jobs page for the query "python" from internshala.com (look up the current search URL format in the browser), and save the HTML into fixtures. Check the site's robots.txt allows those paths first; if not, stop and report back.
- [ ] **Step 2: Write failing tests:** `parse_listing(fixture)` returns ≥ 5 jobs. Every job has a non-empty title, company, and a `url` starting with `https://internshala.com/`. At least one has non-empty `skills_text` or `salary`. `is_internship` is true for the internships fixture.
- [ ] **Step 3: Run them.** Expected: FAIL.
- [ ] **Step 4: Implement.** Build the search URL from query, location and internship. `search()` fetches up to `MAX_RESULT_PAGES` listing pages with `PoliteClient` and stops early if a page returns nothing. Listing cards are enough; don't fetch detail pages for Internshala unless the cards have no skills, and even then no more than `MAX_DETAIL_PAGES`.
- [ ] **Step 5: Run them.** Expected: PASS.
- [ ] **Step 6: Commit** `feat(jobs): internshala scraper`

---

### Task 5: LinkedIn (public pages) and Foundit scrapers

**Files:**
- Create: `backend/app/jobs/scrapers/linkedin.py`, `backend/app/jobs/scrapers/foundit.py`, and fixtures `linkedin_search.html`, `linkedin_detail.html`, `foundit_search.html`
- Modify: `scrapers/__init__.py`, `tests/test_jobs_scrapers.py`

**Interfaces:**
- Produces: `LinkedInScraper` (`name = "linkedin"`) with `parse_listing(html) -> list[Job]` and `parse_detail(html, job) -> Job` (fills in description and experience). `FounditScraper` (`name = "foundit"`) with `parse_listing(html) -> list[Job]`.

- [ ] **Step 1: Save fixtures.** Use the logged-out public job-search page for LinkedIn and a public job page for the detail fixture. Use Foundit's public search results page. Check robots.txt first. If Foundit's results only appear after JavaScript runs, note it and switch that scraper to use the Playwright helper from Task 6 (do Task 6 first in that case).
- [ ] **Step 2: Write failing tests,** same assertions as Task 4 per site. Also, `parse_detail` fills in a non-empty `description`.
- [ ] **Step 3: Run them.** Expected: FAIL.
- [ ] **Step 4: Implement.** LinkedIn fetches detail pages for the first `MAX_DETAIL_PAGES` jobs across all queries, because its listing cards don't show skills.
- [ ] **Step 5: Run them.** Expected: PASS.
- [ ] **Step 6: Commit** `feat(jobs): linkedin public and foundit scrapers`

---

### Task 6: Naukri scraper (Playwright)

**Files:**
- Create: `backend/app/jobs/scrapers/naukri.py`, fixture `naukri_search.html` (the rendered DOM, saved from Playwright with `page.content()`)
- Modify: `scrapers/__init__.py`, `tests/test_jobs_scrapers.py`

**Interfaces:**
- Produces: `NaukriScraper` (`name = "naukri"`) with `parse_listing(html) -> list[Job]` (pure, used by the tests). The async `search()` launches headless Chromium once per search, opens one page, and visits up to 3 result pages with the 2–4 s delay between them. It gets each page's HTML with `page.content()` and calls `looks_blocked` on it, raising `BlockedError` if blocked. It closes the browser in `finally`.

- [ ] **Step 1: Save the fixture** with a short throwaway script (scratchpad, not the repo) that opens the Naukri search page for "python developer" and saves `page.content()`.
- [ ] **Step 2: Write failing tests:** `parse_listing` returns ≥ 5 jobs with title, company, `experience_text`, and a `url` on naukri.com. At least one has non-empty `skills_text` (Naukri cards show skill tags).
- [ ] **Step 3: Run them.** Expected: FAIL.
- [ ] **Step 4: Implement.** Parse the rendered DOM only. Don't call `naukri.com/jobapi` URLs directly (global constraint).
- [ ] **Step 5: Run them.** Expected: PASS.
- [ ] **Step 6: Commit** `feat(jobs): naukri scraper via rendered page`

---

### Task 7: Setup script, smoke script, README

**Files:**
- Modify: `start_backend.bat`, `README.md`
- Create: `backend/scripts/smoke_scrapers.py`

- [ ] **Step 1: `start_backend.bat`.** After creating the venv, compare `certutil -hashfile requirements.txt SHA256` with `venv\.req_hash`. If they differ, run `pip install -r requirements.txt` and then `venv\Scripts\python.exe -m playwright install chromium`. Only write the hash once the pip install succeeds. If the Playwright install fails, print a warning ("Naukri search will be unavailable") and keep going; don't `goto :fail`.
- [ ] **Step 2: Verify.** Run `start_backend.bat` on the existing venv. Expected: it installs the new packages once, and a second run skips the install. Then `GET http://127.0.0.1:8001/api/health` returns `ok`.
- [ ] **Step 3: `smoke_scrapers.py`.** Runs `search("python developer", "", False)` on each registered scraper and prints `site: N jobs / blocked / failed: msg`. Run it with `venv\Scripts\python -m scripts.smoke_scrapers` from `backend`. Expected: every site prints a count or a clear blocked/failed line (report them as they are).
- [ ] **Step 4: README.** Add a "Live jobs" section: how it works, the four sites, the limits and the 6-hour cache, that results depend on the sites' current page layouts, the smoke script, and a note to use it for personal, low-volume searching.
- [ ] **Step 5: Commit** `chore: install new deps on change, smoke script, docs`

---

### Task 8: Frontend "Live jobs" section

**Files:**
- Create: `frontend/src/LiveJobs.jsx`
- Modify: `frontend/src/api.js`, `frontend/src/App.jsx` (render `<LiveJobs result={result} />` below the role lanes when `result` is set), `frontend/src/styles.css`

**Interfaces:**
- Consumes: `POST /api/jobs/search`, `GET /api/jobs/search/{id}` (Task 3). The request is built from the analyse `result`: `titles = [...result.recommended, ...result.stretch].map(m => m.title)`, `skills = result.skills.map(s => ({name: s.name, level: s.level}))`, `experience_years = result.profile.experience_years`.
- Produces: `startJobSearch(body) -> Promise<{search_id}>` and `getJobSearch(id) -> Promise<Search>` in `api.js`.

- [ ] **Step 1: Implement `LiveJobs`.**
  - An optional location input and a **Find jobs** button.
  - While searching, poll every 2000 ms until `state === "done"`, and clear the interval on unmount or when a new resume is analysed.
  - One chip per site: spinner while running, "N jobs" when done, "unavailable" with the message as a tooltip when failed or blocked.
  - Filter controls: verdict (Apply / Almost there / Skip, mapped from APPLY/ALMOST/SKIP), source, and "internships only".
  - Each job card shows title, company, location, salary, experience, a verdict badge (reuse the `apply`/`almost`/`skip` tones), matched skills, missing skills, the source plus `also_on`, and an **Open posting** link (`target="_blank" rel="noopener noreferrer"`).
  - Empty state after the search finishes: "No postings found. Try another location or check the site statuses above."
- [ ] **Step 2: Build** with `cd frontend && npm run build`. Expected: build succeeds and `dist` is updated.
- [ ] **Step 3: Verify in the browser.** Start the backend, open http://127.0.0.1:8001, analyse `samples/data_science_student.txt`, and click Find jobs. Expected: the chips update, cards appear, filters work, links open the original posting, and the console has no errors. Check at phone width (375 px) too.
- [ ] **Step 4: Commit** `feat(ui): live jobs section`

---

## Self-review notes

- **Spec coverage:** flow and polling (Task 3, Task 8); four sites (Tasks 4–6); scoring rules (Task 1); dedupe and cache (Task 2); polite limits and robots.txt (Task 3 `PoliteClient`); the rule on internal feeds (Task 6); setup script and Playwright fallback (Tasks 3 and 7); fixture-based tests and smoke script (Tasks 4–7); UI (Task 8).
- **Left to the implementer:** the HTML selectors for each site and the card layout details, as the spec leaves them.
