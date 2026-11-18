"""Shared scraper pieces: the Scraper interface and a polite HTTP client.

Polite means: one request at a time per site, a random 2-4 s pause between
requests, robots.txt respected, a normal browser User-Agent, and stopping
as soon as a site looks like it is blocking us. No CAPTCHA solving, no
proxies, no retry loops.
"""
from __future__ import annotations

import asyncio
import random
import re
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..models import Job

MAX_RESULT_PAGES = 3   # per site, per search (shared across queries)
MAX_DETAIL_PAGES = 20  # per site, per search
DEFAULT_DELAY = (2.0, 4.0)
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": USER_AGENT,
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-IN,en;q=0.9"}

_STRONG_MARKERS = ("cf-challenge", "challenge-platform", "are you a robot", "access denied",
                   "unusual traffic", "verify you are human")
_SMALL_PAGE = 30_000


def slugify(s: str) -> str:
    """'C++ Developer' -> 'c-developer' (for keyword-in-path listing URLs)."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")


class BlockedError(Exception):
    """The site refused us (403/429, challenge page, robots.txt disallow)."""


def looks_blocked(status: int, html: str) -> bool:
    if status in (403, 429):
        return True
    low = (html or "").lower()
    if any(m in low for m in _STRONG_MARKERS):
        return True
    # 'captcha' appears in normal pages' scripts too, so only trust it on small pages
    return "captcha" in low and len(low) < _SMALL_PAGE


async def polite_pause(delay: tuple[float, float]) -> None:
    lo, hi = delay
    if hi > 0:
        await asyncio.sleep(random.uniform(lo, hi))


class PoliteClient:
    """async with PoliteClient() as c: html = await c.get(url)

    One client per site per search: the pause and the robots.txt cache only
    work if every request to that site goes through the same client."""

    def __init__(self, delay: tuple[float, float] = DEFAULT_DELAY, timeout: float = 20.0,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.delay = delay
        self.timeout = timeout
        self.transport = transport
        self._client: httpx.AsyncClient | None = None
        self._robots: dict[str, RobotFileParser | None] = {}
        self._requests = 0
        self.last_url = ""

    async def __aenter__(self) -> "PoliteClient":
        self._client = httpx.AsyncClient(headers=HEADERS, timeout=self.timeout, follow_redirects=True,
                                         transport=self.transport)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()

    async def _fetch(self, url: str) -> httpx.Response:
        """Every request, robots.txt included, waits its turn."""
        if self._requests:
            await polite_pause(self.delay)
        self._requests += 1
        return await self._client.get(url)

    async def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            rp: RobotFileParser | None = None
            try:
                r = await self._fetch(host + "/robots.txt")
                if r.status_code == 200:
                    rp = RobotFileParser()
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp = None  # unreachable robots.txt: treat as no rules
            self._robots[host] = rp
        rp = self._robots[host]
        return rp is None or rp.can_fetch(USER_AGENT, url)

    async def get(self, url: str) -> str:
        if not await self._allowed(url):
            raise BlockedError(f"robots.txt disallows {urlsplit(url).path}")
        r = await self._fetch(url)
        self.last_url = str(r.url)
        if r.status_code == 404:
            return ""  # no listing page for this keyword
        if looks_blocked(r.status_code, r.text):
            raise BlockedError(f"site refused the request (HTTP {r.status_code})")
        r.raise_for_status()
        return r.text


class Scraper(ABC):
    """One per site. A fresh instance is made for every search, so instance
    counters are per-search budgets:
      pages_left      result pages this site may still read (shared by all queries)
      details_fetched detail pages read so far
    Use ``async with scraper:`` around a whole search so every query shares one
    PoliteClient; outside that, each search() call opens its own."""

    name: str = ""
    transport: httpx.AsyncBaseTransport | None = None  # tests inject a mock transport

    def __init__(self, delay: tuple[float, float] = DEFAULT_DELAY):
        self.delay = delay
        self.details_fetched = 0
        self.pages_left = MAX_RESULT_PAGES
        self.client: PoliteClient | None = None

    async def __aenter__(self) -> "Scraper":
        self.client = await PoliteClient(self.delay, transport=self.transport).__aenter__()
        return self

    async def __aexit__(self, *exc) -> None:
        if self.client:
            await self.client.__aexit__(*exc)
            self.client = None

    @asynccontextmanager
    async def http(self):
        if self.client:
            yield self.client
        else:
            async with PoliteClient(self.delay, transport=self.transport) as c:
                yield c

    def take_page(self) -> bool:
        """Spend one result page from the per-search budget; False when none are left."""
        if self.pages_left <= 0:
            return False
        self.pages_left -= 1
        return True

    @abstractmethod
    async def search(self, query: str, location: str, internship: bool, pages: int = 1) -> list[Job]:
        """Return postings for one query, reading at most ``pages`` result pages
        and never more than the remaining budget (``take_page()``)."""
