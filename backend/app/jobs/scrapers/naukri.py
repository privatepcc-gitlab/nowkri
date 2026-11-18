"""Naukri placeholder.

Naukri can't be searched from this app: its pages load jobs from an internal
feed that answers 'recaptcha required' to automated clients, and its pages
refuse headless browsers (Akamai 'Access Denied'). Getting past either would
mean bot-detection evasion, which this project rules out. The placeholder
makes no network requests; it shows Naukri as unavailable in the results so
the reason is visible instead of the site silently missing.
"""
from __future__ import annotations

from ..models import Job
from .base import BlockedError, Scraper

MESSAGE = ("Naukri asks for a CAPTCHA before it shows jobs to automated searches, "
           "so it can't be searched from here. Search it directly on naukri.com.")


class NaukriScraper(Scraper):
    name = "naukri"

    async def search(self, query: str, location: str, internship: bool, pages: int = 1) -> list[Job]:
        raise BlockedError(MESSAGE)
