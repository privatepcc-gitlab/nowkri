"""Manual live check of every job-site scraper (not part of pytest).

Run from the backend folder:
    venv\\Scripts\\python -m scripts.smoke_scrapers ["search words"] ["city"]

Prints how many postings each site returned, or why it couldn't. Use it when
a site shows "unavailable" in the app: site layouts change, and this tells
you which parser needs updating.
"""
from __future__ import annotations

import asyncio
import sys

from app.jobs.scrapers import get_scrapers
from app.jobs.scrapers.base import BlockedError


async def main(query: str, location: str) -> None:
    for sc in get_scrapers():
        try:
            jobs = await sc.search(query, location, False, 1)
            sample = f'  e.g. "{jobs[0].title}" at {jobs[0].company}' if jobs else ""
            print(f"{sc.name:12} {len(jobs):3} jobs{sample}")
        except BlockedError as e:
            print(f"{sc.name:12} blocked: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"{sc.name:12} failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "python developer",
                     sys.argv[2] if len(sys.argv) > 2 else ""))
