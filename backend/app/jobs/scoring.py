"""Score a live job posting against the resume.

The posting's skills (found with the same SkillExtractor used for resumes)
are the requirements. Coverage = share of them the resume has:
Intermediate or better counts fully, Beginner counts half.

APPLY  - coverage >= 0.7 and experience requirement met
ALMOST - coverage >= 0.5 and at most 1 year short
SKIP   - anything else
Postings with fewer than 2 recognisable skills fall back to TF-IDF text
similarity and are never labelled higher than ALMOST.
"""
from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..skills import SkillExtractor
from .models import Job

APPLY_COVERAGE = 0.7
ALMOST_COVERAGE = 0.5
MAX_YEARS_SHORT = 1.0
MIN_SKILLS_FOR_VERDICT = 2

_extractor = SkillExtractor()

_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:yrs?|years?)", re.I)
_PLUS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:yrs?|years?)", re.I)


def parse_experience(text: str) -> tuple[float, float | None]:
    """'0-2 Yrs' -> (0, 2); '2+ years' -> (2, None); 'Fresher' / '' / '0 Yrs' -> (0, None)."""
    text = text or ""
    m = _RANGE_RE.search(text)
    if m:
        return _num(m.group(1)), _num(m.group(2))
    m = _PLUS_RE.search(text)
    if m:
        return _num(m.group(1)), None
    return 0, None


def _num(s: str) -> float:
    v = float(s)
    return int(v) if v.is_integer() else v


def _text_similarity(a: str, b: str) -> float:
    if not a.strip() or not b.strip():
        return 0.0
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True,
                          token_pattern=r"(?u)\b[\w+#.]+\b")
    try:
        m = vec.fit_transform([a, b])
    except ValueError:  # only stop words
        return 0.0
    return float(cosine_similarity(m[0], m[1])[0, 0])


def score_job(job: Job, levels: dict[str, int], resume_years: float, resume_text: str = "") -> Job:
    job.min_years, job.max_years = parse_experience(job.experience_text)
    found = _extractor.extract({"skills": job.skills_text or "",
                                "other": f"{job.title}\n{job.description}"})
    names = [s.name for s in found]

    job.matched_skills, job.missing_skills, job.reasons = [], [], []
    credit = 0.0
    for n in names:
        lvl = levels.get(n, 0)
        if lvl >= 2:
            credit += 1
        elif lvl == 1:
            credit += 0.5
        if lvl > 0:
            job.matched_skills.append(n)
        else:
            job.missing_skills.append(n)

    few_skills = len(names) < MIN_SKILLS_FOR_VERDICT
    if few_skills:
        job.coverage = round(_text_similarity(resume_text, f"{job.title} {job.skills_text} {job.description}"), 3)
        if names:  # one skill: keep it in the picture
            job.coverage = max(job.coverage, credit / len(names) * 0.6)
    else:
        job.coverage = round(credit / len(names), 3)

    exp_gap = max(0.0, job.min_years - resume_years)
    if job.missing_skills:
        job.reasons.append("Missing: " + ", ".join(job.missing_skills))
    if exp_gap > 0:
        job.reasons.append(f"Needs {job.min_years:g}+ years; resume shows {resume_years:g}")
    if few_skills:
        job.reasons.append("Posting lists few skills; match based on text similarity")

    if not few_skills and job.coverage >= APPLY_COVERAGE and exp_gap == 0:
        job.verdict = "APPLY"
    elif job.coverage >= ALMOST_COVERAGE and exp_gap <= MAX_YEARS_SHORT:
        job.verdict = "ALMOST"
    elif few_skills and job.coverage >= APPLY_COVERAGE and exp_gap == 0:
        job.verdict = "ALMOST"  # capped
    else:
        job.verdict = "SKIP"
    return job
