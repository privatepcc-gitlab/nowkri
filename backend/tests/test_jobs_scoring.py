import pytest

from app.jobs.models import Job
from app.jobs.scoring import parse_experience, score_job


def j(**kw):
    return Job(source="t", source_id="1", title="Dev", company="C", location="Pune", url="u", **kw)


@pytest.mark.parametrize("text,expected", [
    ("0-2 Yrs", (0, 2)), ("2+ years", (2, None)), ("3 - 5 years", (3, 5)),
    ("Fresher", (0, None)), ("", (0, None)), ("0 Yrs", (0, None)), ("1 to 3 years", (1, 3)),
])
def test_parse_experience(text, expected):
    assert parse_experience(text) == expected


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
