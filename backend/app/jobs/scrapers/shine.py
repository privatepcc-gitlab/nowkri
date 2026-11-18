"""Shine.com scraper.

Keyword listing pages are server-rendered and allowed by robots.txt:
  /job-search/python-developer-jobs        /job-search/data-analyst-jobs-in-pune-2
Class names are CSS-module hashed (result-card_role__tUHBe), so we match
on the stable prefix only. Detail pages are not fetched.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Job
from .base import Scraper, slugify

BASE = "https://www.shine.com"
_ID_RE = re.compile(r"/(\d{6,})(?:[/?]|$)")
_EXP_RE = re.compile(r"\b(yrs?|years?|fresher)\b", re.I)
_PAY_RE = re.compile(r"lakh|lpa|₹|rs\.?|not disclosed|/yr|per annum|/month", re.I)


def listing_url(query: str, location: str, page: int) -> str:
    path = f"/job-search/{slugify(query)}-jobs"
    if location.strip():
        path += f"-in-{slugify(location)}"
    if page > 1:
        path += f"-{page}"
    return BASE + path


def _cls(prefix: str) -> str:
    return f'[class*="{prefix}"]'


def _text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def parse_listing(html: str) -> list[Job]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[Job] = []
    seen: set[str] = set()
    for card in soup.select("article" + _cls("result-card_card__")):
        link = card.select_one(_cls("result-card_role__") + " a[href]")
        if not link:
            continue
        href = link["href"].split("?")[0]
        m = _ID_RE.search(href)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        exp = pay = loc = ""
        for item in card.select(_cls("result-card_meta-text__")):
            t = _text(item)
            if not exp and _EXP_RE.search(t):
                exp = t
            elif not pay and _PAY_RE.search(t):
                pay = t
            elif not loc:
                loc = t
        skills = [_text(s).lstrip("·").strip() for s in card.select(_cls("result-card_skills-item__"))]
        jobs.append(Job(
            source="shine", source_id=m.group(1),
            title=_text(link),
            company=_text(card.select_one(_cls("result-card_company__"))),
            location=loc, url=BASE + href, salary=pay, experience_text=exp,
            skills_text=", ".join(s for s in skills if s),
            posted=_text(card.select_one(_cls("result-card_posted__"))),
        ))
    return jobs


class ShineScraper(Scraper):
    name = "shine"

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
        return out
