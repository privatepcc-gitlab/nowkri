# Live job search — design

Date: 2026-11-18
Status: draft, waiting for approval

## Intent

Today Job Hunt tells you which job *titles* fit your resume (Apply / Almost there / Skip).
This feature adds **real, current job postings**. After a resume is analysed, you click
**Find jobs**. The app searches Internshala, Naukri, LinkedIn (public pages) and Foundit for
postings that fit the resume, scores each one with the existing skill matcher, and lists
them with a link to the original posting.

Why: so the app goes from "these roles suit you" to "here are openings you can apply to today".

## Goals

- One click from an analysed resume gives a combined, de-duplicated list of live postings
  from several sites.
- Each posting gets the same kind of verdict as roles (Apply / Almost there / Skip), with the
  skills you have and the skills you're missing.
- Results arrive site by site. A site that fails or blocks you doesn't stop the others; it
  shows as "unavailable".
- Runs on one Windows PC through the existing `start.bat`.

## Non-goals

- No official or paid job APIs ("no source APIs").
- No hosting for many users, no accounts, no auto-apply, no saved job history beyond a short cache.
- No background or scheduled crawling. Searches happen only when you click.
- Indeed and Glassdoor are left out for now (Cloudflare bot walls).

## Anti-goals (failure even if it "works")

- Hammering sites: many requests, fast retries or parallel page loads on one site, which
  could get your IP blocked.
- Showing Apply on postings whose required skills the resume clearly doesn't have, which
  would undo the honesty the role matcher is built around.
- Breaking the existing analyse flow or tests, or making `start.bat` fail when a scraper or
  Playwright isn't available.
- Copying posting content into the repo. Only the cache, which is gitignored, holds it.

## Constraints

- Local use only. Backend is FastAPI on Python 3.14 (the version on this PC); frontend is React 18 + Vite.
- Scraping means reading the sites' web pages. **Rule on internal data feeds:** the scraper
  must not call a site's internal JSON endpoint directly. When a page loads its jobs that
  way (Naukri), read what the browser page received or rendered through Playwright.
- Be polite: follow robots.txt for the paths you fetch, wait 2–4 s (randomised) between
  requests to the same site, one request at a time per site, at most about 3 result pages
  plus about 20 detail pages per site per search. Use a normal desktop browser User-Agent.
  No CAPTCHA solving and no proxy rotation. If blocked, stop that site for this search.
- `start_backend.bat` only installs packages when it creates the venv, so the new packages
  (`beautifulsoup4`, `lxml`, `playwright`) wouldn't reach existing installs. The script must
  reinstall when `requirements.txt` changes (for example by storing a hash of it), and it
  must run `playwright install chromium` once. If Playwright install fails, the app still
  starts and Naukri shows as unavailable.

## Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| **A. Search on click** — scrape when you press Find jobs; cache results a few hours | Jobs are current and tailored to the resume, few requests, nothing in the background; costs a 10–30 s wait per new search | **Chosen** (by you) |
| B. Scheduled crawl into a local database, then instant matching | No wait and you can browse widely, but many more requests (block risk), the app must stay running, and more to maintain | Rejected: suits many users, not one person |
| Official or third-party job APIs | Stable, but against the "no source APIs" rule and often paid | Excluded |

Within A: plain HTTP (`httpx` + BeautifulSoup) wherever the HTML holds the jobs; headless
Chromium (Playwright) only where the page needs JavaScript (Naukri).

## Design

### Flow

1. The frontend already has the analyse result (skills with levels, experience, Apply and
   Almost there titles). **Find jobs** sends `POST /api/jobs/search` with:
   `{ titles, skills: [{name, level}], experience_years, location?, include_internships }`.
   The backend doesn't store the resume, so the request carries everything the search needs.
2. The backend builds queries: the top 3 titles from Apply, then Almost there, and if both
   are empty, the top 5 skills. `include_internships` defaults to true when experience is
   under 1 year.
3. The backend returns `{ search_id }` straight away and runs one scraper per site in
   background tasks (sites run in parallel, but each site's requests are sequential).
4. The frontend polls `GET /api/jobs/search/{search_id}` every 2 s. The response has the
   status of each site (`pending | running | done | failed | blocked`, plus a message) and
   the scored jobs found so far. Polling stops once every site is finished.
5. Identical searches (same normalised request) within 6 hours return the cached result
   straight away.

### Backend layout

```
backend/app/jobs/
  models.py      Job dataclass: source, source_id, title, company, location, salary,
                 experience_text, min_years, max_years, skills_text, description,
                 url, posted, is_internship
  scrapers/
    base.py      Scraper interface: async search(query, location, internship) -> list[Job];
                 shared polite HTTP client (delays, robots.txt check, User-Agent, timeouts)
    internshala.py   httpx + BeautifulSoup (internships, and jobs for freshers)
    naukri.py        Playwright (read the rendered page or the responses the page loaded)
    linkedin.py      httpx, public guest job-search pages (no login)
    foundit.py       httpx + BeautifulSoup
  scoring.py     scores a Job against the resume's skills and experience
  search.py      runs searches, merges, de-duplicates, stores in the cache, tracks progress
  cache.py       SQLite file in backend/app/data/cache/jobs.sqlite (gitignored)
```

The new endpoints go in `main.py` next to the existing ones.

### Scoring a posting (`scoring.py`)

- Run the existing `SkillExtractor` on the posting text, passing the posting's skills or
  requirements part as the `"skills"` section so short names (C, R, Go) are allowed there,
  and the rest as `"other"`. Only the skill *names* are used; levels from posting text mean nothing.
- **Skill coverage** = the share of the posting's skills that the resume has at level 2
  (Intermediate) or higher, with half credit for level 1.
- **Experience** comes from text like "0-2 Yrs" or "2+ years" into `min_years`. If it's
  missing, no experience requirement is assumed.
- Verdict:
  - **Apply:** coverage ≥ 0.7 and the resume meets `min_years`.
  - **Almost there:** coverage ≥ 0.5, and short by at most 1 year of experience.
  - **Skip:** anything else, with reasons ("Missing: Docker, AWS", "Needs 3+ years").
- If a posting lists fewer than 2 recognisable skills, fall back to TF-IDF similarity between
  the resume and the posting, and never give it a verdict higher than Almost there.
- Sort by verdict, then coverage, then most recent posting date.

### De-duplication

Two postings are treated as one when their normalised `(company, title, city)` match. Keep
the one with the most detail and list the other sources as "also on".

### Frontend

- After a resume is analysed, a new **Live jobs** section appears with a **Find jobs**
  button and an optional location box (blank means anywhere in India).
- While searching: one status chip per site (spinner, then the number of jobs found, or
  "unavailable: blocked").
- Results: job cards showing title, company, location, salary, experience, a verdict badge,
  matched and missing skills, the source site, and an **Open posting** link (new tab).
  Filters: verdict, source, internships only. Uses the existing lane styling.
- `api.js` gets `startJobSearch()` and `getJobSearch(id)`. Rebuild `frontend/dist` afterwards.

### Testing

- Save one real listing page (and one detail page where used) per site under
  `backend/tests/fixtures/jobs/`. Parser tests run against these saved pages, never the live sites.
- Unit tests for scoring (coverage, experience parsing, verdicts), de-duplication, cache
  expiry, and the search lifecycle (with fake scrapers, including one that fails).
- An API test for `POST /api/jobs/search` and polling, using fake scrapers.
- A manual smoke script, `backend/scripts/smoke_scrapers.py`, runs one live query per site
  and prints how many jobs it found. Not part of pytest.

## Calls I made (please check)

- The rule on internal data feeds (above): read what the Naukri page loads, never call its endpoints directly.
- Request limits: 2–4 s between requests, about 3 result pages and about 20 detail pages per site.
- A 6-hour cache in SQLite.
- Polling every 2 s instead of streaming updates. It's simpler, and fine for local use.
- Verdict thresholds 0.7 / 0.5 for job postings.
- Default location is anywhere in India, with an optional location box.
- The first four sites: Internshala, Naukri, LinkedIn public pages, Foundit.

## Left to the builder

- The exact HTML selectors for each site (from the saved fixture pages).
- The wording of user-facing status messages, and the card layout details within the existing style.
- How to detect "blocked" pages (CAPTCHA page, 403/429, empty results with a challenge script).
