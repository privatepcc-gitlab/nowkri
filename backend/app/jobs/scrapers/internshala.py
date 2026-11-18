"""Internshala scraper.

robots.txt disallows /internship/search/, /job/search/, detail pages and any
URL with '?' or ','. So we read only the keyword listing pages, e.g.
  /internships/python-internship/          /jobs/data-analyst-jobs-in-pune/page-2/
and use what the listing cards show (title, company, location, pay,
experience, skill tags). Detail pages are never fetched.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Job
from .base import Scraper, slugify as _slug

BASE = "https://internshala.com"
# generic role words: Internshala has pages for "embedded-systems" but not "embedded-systems-engineer"
_ROLE_WORDS = {"engineer", "developer", "executive", "associate", "specialist", "trainee", "intern",
               "lead", "senior", "junior", "entry", "level", "fresher"}


def simplify_query(query: str) -> str:
    """'Senior Python Developer' -> 'Python'; unchanged if nothing would be left."""
    kept = [w for w in query.split() if w.lower() not in _ROLE_WORDS]
    return " ".join(kept) if kept else query


def listing_url(query: str, location: str, internship: bool, page: int) -> str:
    kind, suffix = ("internships", "internship") if internship else ("jobs", "jobs")
    path = f"/{kind}/{_slug(query)}-{suffix}"
    if location.strip():
        path += f"-in-{_slug(location)}"
    path += "/"
    if page > 1:
        path += f"page-{page}/"
    return BASE + path


def _collapse_repeat(text: str) -> str:
    """'₹ 2,00 - 6,00 ₹ 2,00 - 6,00 /year' -> '₹ 2,00 - 6,00 /year' (desktop + mobile copies)."""
    words = text.split()
    for n in range(1, len(words) // 2 + 1):
        if words[:n] == words[n:2 * n]:
            return " ".join(words[n:])
    return text


def parse_listing(html: str, internship: bool) -> list[Job]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[Job] = []
    seen: set[str] = set()
    for card in soup.select(".individual_internship[internshipid]"):
        sid = card.get("internshipid", "")
        link = card.select_one("a.job-title-href")
        company = card.select_one(".company-name")
        if not sid or not link or not company or sid in seen:
            continue
        seen.add(sid)
        location = salary = experience = ""
        for item in card.select(".detail-row-1 .row-1-item"):
            icon = " ".join(item.select_one("i").get("class", [])) if item.select_one("i") else ""
            text = _collapse_repeat(item.get_text(" ", strip=True))
            if "locations" in item.get("class", []) or "map-pin" in icon:
                location = text
            elif "money" in icon:
                salary = text
            elif "briefcase" in icon or "experience" in text.lower():
                experience = text
        posted = card.select_one(".detail-row-2 .color-labels span")
        about = card.select_one(".about_job .text")
        jobs.append(Job(
            source="internshala", source_id=sid,
            title=link.get_text(" ", strip=True),
            company=company.get_text(" ", strip=True),
            location=location,
            url=BASE + (card.get("data-href") or link.get("href", "")),
            salary=salary,
            experience_text=experience,
            skills_text=", ".join(s.get_text(" ", strip=True) for s in card.select(".job_skill")),
            description=about.get_text(" ", strip=True) if about else "",
            posted=posted.get_text(" ", strip=True) if posted else "",
            is_internship=internship,
        ))
    return jobs


class InternshalaScraper(Scraper):
    name = "internshala"

    async def search(self, query: str, location: str, internship: bool, pages: int = 1) -> list[Job]:
        """Freshers (internship=True) get internships first, then full-time jobs.
        If Internshala has no page for the exact title, retry once without role words."""
        out: list[Job] = []
        kinds = [True, False] if internship else [False]
        async with self.http() as c:
            for kind in kinds:
                q = query
                for page in range(1, pages + 1):
                    if not self.take_page():
                        return out
                    html = await c.get(listing_url(q, location, kind, page))
                    # no page for this keyword, or redirected to an unrelated generic listing
                    if not html or _slug(q) not in c.last_url:
                        simpler = simplify_query(q)
                        if page == 1 and simpler != q and self.take_page():
                            q = simpler
                            html = await c.get(listing_url(q, location, kind, page))
                            if not html or _slug(q) not in c.last_url:
                                break
                        else:
                            break
                    found = parse_listing(html, kind)
                    if not found:
                        break
                    out.extend(found)
        return out
