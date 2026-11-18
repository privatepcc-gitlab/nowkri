"""Apna.co scraper.

Listing pages (/jobs/python-developer-jobs?page=2) are server-rendered and
allowed by robots.txt. Cards show no skills, so for the first few postings we
also read the job page's schema.org JobPosting description, which the
skill extractor then scans for skills.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from ..models import Job
from .base import Scraper, slugify

BASE = "https://apna.co"
DETAIL_LIMIT = 10  # per search; each one costs a 2-4 s polite pause
_ID_RE = re.compile(r"^/job/(?:[^/]+/)*?(?:[^/]*-)?(\d{6,})$")
_EXP_RE = re.compile(r"\b(years?|yrs?|fresher|experience)\b", re.I)
_PAY_RE = re.compile(r"₹|not disclosed|lakh|/month|per month", re.I)
_SKIP_TAGS = re.compile(r"^(work from (office|home)|full time|part time|field job|night shift|hybrid)$", re.I)


def listing_url(query: str, location: str, page: int) -> str:
    path = f"/jobs/{slugify(query)}-jobs"
    if location.strip():
        path += f"-in-{slugify(location)}"
    return BASE + path + (f"?page={page}" if page > 1 else "")


def _text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def parse_listing(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[Job] = []
    seen: set[str] = set()
    for card in soup.select('a[data-testid="job-card"][href]'):
        href = card["href"].split("?")[0]
        m = _ID_RE.match(href)
        title = card.select_one("h2")
        if not m or not title or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        company = title.find_next_sibling("span") or card.select_one("h2 + span")
        lines = [_text(s) for s in card.select("span.text-sm.text-secondary-text")]
        loc = pay = exp = ""
        for t in lines:
            if not t or _SKIP_TAGS.match(t):
                continue
            if not exp and _EXP_RE.search(t):
                exp = t
            elif not pay and _PAY_RE.search(t):
                pay = t
            elif not loc:
                loc = t
        jobs.append(Job(source="apna", source_id=m.group(1), title=_text(title),
                        company=_text(company), location=loc, url=BASE + href,
                        salary=pay, experience_text=exp))
    return jobs


def parse_detail(html: str, job: Job) -> Job:
    """Fill description (and date / experience if missing) from the JobPosting JSON-LD."""
    soup = BeautifulSoup(html, "lxml")
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if not isinstance(d, dict) or d.get("@type") != "JobPosting":
                continue
            desc = BeautifulSoup(d.get("description", ""), "lxml").get_text(" ", strip=True)
            job.description = desc[:5000]
            job.posted = job.posted or (d.get("datePosted") or "")[:10]
            months = (d.get("experienceRequirements") or {}).get("monthsOfExperience")
            if not job.experience_text and isinstance(months, (int, float)):
                job.experience_text = f"{months / 12:g}+ years" if months else "Fresher"
            return job
    return job


class ApnaScraper(Scraper):
    name = "apna"

    async def search(self, query: str, location: str, internship: bool, pages: int = 1) -> list[Job]:
        out: list[Job] = []
        async with self.http() as c:
            for page in range(1, pages + 1):
                if not self.take_page():
                    break
                html = await c.get(listing_url(query, location, page))
                found = parse_listing(html) if html else []
                if not found:
                    break
                out.extend(found)
            for job in out:
                if self.details_fetched >= DETAIL_LIMIT:
                    break
                self.details_fetched += 1
                html = await c.get(job.url)
                if html:
                    parse_detail(html, job)
        return out
