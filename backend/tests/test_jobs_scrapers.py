"""Scraper parsers run against saved copies of real pages (tests/fixtures/jobs).
No test here touches the network."""
from pathlib import Path

import pytest

from app.jobs.scrapers import internshala

FIX = Path(__file__).parent / "fixtures" / "jobs"


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


def common_checks(jobs, host):
    assert len(jobs) >= 5
    for j in jobs:
        assert j.title and j.company and j.url.startswith(host), j
        assert j.source_id
    assert any(j.skills_text for j in jobs)
    assert len({j.source_id for j in jobs}) == len(jobs)


def test_internshala_internships():
    jobs = internshala.parse_listing(read("internshala_internships.html"), internship=True)
    common_checks(jobs, "https://internshala.com/")
    assert all(j.is_internship for j in jobs)
    assert any("month" in j.salary.lower() for j in jobs)


def test_internshala_jobs():
    jobs = internshala.parse_listing(read("internshala_jobs.html"), internship=False)
    common_checks(jobs, "https://internshala.com/")
    assert not any(j.is_internship for j in jobs)
    first = jobs[0]
    assert first.title == "Data Analyst" and first.experience_text == "No experience required"
    assert "Power BI" in first.skills_text
    assert first.salary.count("₹") == 1   # desktop + mobile copies collapsed


@pytest.mark.parametrize("q,loc,intern,url", [
    ("Data Analyst", "", False, "https://internshala.com/jobs/data-analyst-jobs/"),
    ("Python", "Pune", True, "https://internshala.com/internships/python-internship-in-pune/"),
    ("C++ Developer", "", True, "https://internshala.com/internships/c-developer-internship/"),
])
def test_internshala_urls(q, loc, intern, url):
    assert internshala.listing_url(q, loc, intern, 1) == url
    assert internshala.listing_url(q, loc, intern, 2) == url + "page-2/"


from app.jobs.scrapers import shine  # noqa: E402


def test_shine_listing():
    jobs = shine.parse_listing(read("shine_search.html"))
    common_checks(jobs, "https://www.shine.com/jobs/")
    j = next(x for x in jobs if x.source_id == "19985359")
    assert j.title == "Python Developer"
    assert j.company == "WHITE HORSE MANPOWER CONSULTANCY (P) LTD"
    assert j.experience_text == "4 to 9 Yrs" and j.salary == "5 - 10 Lakh/Yr"
    assert j.location == "Pune, Bangalore, Chennai" and j.posted == "2 weeks ago"
    assert "framework" in j.skills_text
    assert "?" not in j.url


@pytest.mark.parametrize("q,loc,page,url", [
    ("Python Developer", "", 1, "https://www.shine.com/job-search/python-developer-jobs"),
    ("Python Developer", "", 2, "https://www.shine.com/job-search/python-developer-jobs-2"),
    ("Data Analyst", "Pune", 1, "https://www.shine.com/job-search/data-analyst-jobs-in-pune"),
    ("Data Analyst", "Pune", 3, "https://www.shine.com/job-search/data-analyst-jobs-in-pune-3"),
])
def test_shine_urls(q, loc, page, url):
    assert shine.listing_url(q, loc, page) == url


from app.jobs.scrapers import apna  # noqa: E402


def test_apna_listing():
    jobs = apna.parse_listing(read("apna_search.html"))
    assert len(jobs) >= 5 and len({j.source_id for j in jobs}) == len(jobs)
    j = next(x for x in jobs if x.source_id == "1476675125")
    assert j.title == "Specialist - Data Sciences"
    assert j.company == "Larsen & Toubro Infotech Ltd (LTI)"
    assert j.location == "Bengaluru/Bangalore" and j.salary == "Not disclosed"
    assert j.experience_text == "Min. 5 years"
    assert j.url == "https://apna.co/job/1476675125"
    assert all(x.url.startswith("https://apna.co/job/") and x.title and x.company for x in jobs)


def test_apna_detail_adds_description():
    job = apna.parse_listing(read("apna_search.html"))[0]
    job = next(x for x in apna.parse_listing(read("apna_search.html")) if x.source_id == "1476675125")
    apna.parse_detail(read("apna_detail.html"), job)
    assert "Python" in job.description and "<" not in job.description
    assert job.posted == "2026-11-13"


@pytest.mark.parametrize("q,loc,page,url", [
    ("Python Developer", "", 1, "https://apna.co/jobs/python-developer-jobs"),
    ("Python Developer", "", 2, "https://apna.co/jobs/python-developer-jobs?page=2"),
    ("Data Analyst", "Pune", 1, "https://apna.co/jobs/data-analyst-jobs-in-pune"),
])
def test_apna_urls(q, loc, page, url):
    assert apna.listing_url(q, loc, page) == url
