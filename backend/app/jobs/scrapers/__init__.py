"""Registry of site scrapers. Each import is guarded so one broken or
missing dependency (e.g. Playwright for Naukri) only drops that site."""
from __future__ import annotations

import importlib
import logging

from .base import Scraper

log = logging.getLogger(__name__)

# (module, class) in display order
_REGISTRY: list[tuple[str, str]] = [
    ("internshala", "InternshalaScraper"),
    ("shine", "ShineScraper"),
    ("apna", "ApnaScraper"),
    ("naukri", "NaukriScraper"),
]


def get_scrapers() -> list[Scraper]:
    out = []
    for mod, cls in _REGISTRY:
        try:
            out.append(getattr(importlib.import_module(f"{__name__}.{mod}"), cls)())
        except Exception as e:  # noqa: BLE001
            log.warning("scraper %s unavailable: %s", mod, e)
    return out
