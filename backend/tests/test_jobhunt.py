"""Unit tests for Job Hunt. Run from the backend folder:  pytest -q"""
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, analyze_text
from app.parser import estimate_experience, parse_resume, split_sections
from app.skills import SkillExtractor

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
client = TestClient(app)
ex = SkillExtractor()


def levels(text):
    return {s.name: s.level for s in ex.extract(split_sections(text))}


def titles(result, key):
    return [m["title"] for m in result[key]]


def test_sections_detected():
    s = split_sections("John Doe\nSkills\nPython, SQL\nProjects\nChatbot using Python\nEducation\nB.E. CSE")
    assert {"skills", "projects", "education"} <= set(s)


def test_bullet_is_not_heading():
    s = split_sections("Projects\n- Strong communication skills shown in demo")
    assert "skills" not in s and "projects" in s


def test_longest_match_wins():
    lv = levels("Skills\nReact Native, Java\n")
    assert "React Native" in lv and "React" not in lv
    assert "JavaScript" not in lv  # 'Java' must not match JavaScript and vice versa


def test_short_skills_only_in_skills_section():
    assert "Go" not in levels("Summary\nGo getter who likes to learn\n")
    assert "Go" in levels("Skills\nGo, Rust\n")


def test_usage_raises_level():
    only_listed = levels("Skills\nDocker\n")["Docker"]
    used = levels("Skills\nDocker\nExperience\nIntern, Jun 2024 - Aug 2024\n- Containerised app with Docker\n"
                  "Projects\nDeployed API with Docker")["Docker"]
    assert only_listed == 1 and used >= 3


def test_overclaim_is_pulled_down():
    # claims expert, shows no usage anywhere
    assert levels("Skills\nExpert in Kubernetes\n")["Kubernetes"] <= 2


def test_implied_skills():
    lv = levels("Skills\nReact\nProjects\nTodo app in React\nExperience\nBuilt React dashboard")
    assert lv["JavaScript"] >= 2 and lv["HTML"] >= 2


def test_experience_from_dates():
    secs = {"experience": "Intern, Jan 2024 - Dec 2024\nEngineer, Jan 2025 - Present"}
    yrs, _ = estimate_experience(secs, "", today=date(2026, 1, 1))
    assert 1.9 <= yrs <= 2.2


def test_overlapping_dates_not_double_counted():
    secs = {"experience": "A, Jan 2024 - Dec 2024\nB, Jun 2024 - Dec 2024"}
    yrs, _ = estimate_experience(secs, "", today=date(2026, 1, 1))
    assert yrs == 1.0


def test_data_science_sample():
    r = analyze_text((SAMPLES / "data_science_student.txt").read_text())
    assert "Data Scientist (Entry Level)" in titles(r, "recommended")
    assert "Data Analyst" in titles(r, "recommended")
    # never suggest senior roles to a student
    assert "Senior Data Scientist" in titles(r, "not_recommended")
    # never suggest unrelated roles
    for bad in ["iOS Developer", "Game Developer", "Penetration Tester"]:
        assert bad in titles(r, "not_recommended")


def test_frontend_sample():
    r = analyze_text((SAMPLES / "frontend_developer.txt").read_text())
    assert titles(r, "recommended")[0] == "Frontend Developer"
    assert "Data Scientist (Entry Level)" in titles(r, "not_recommended")


def test_fresher_gets_no_senior_roles():
    r = analyze_text((SAMPLES / "fresher_basic.txt").read_text())
    rec = titles(r, "recommended") + titles(r, "stretch")
    assert not any("Senior" in t or "Manager" in t for t in rec)
    assert "Embedded Systems Engineer" in rec


def test_not_recommended_has_reasons():
    r = analyze_text((SAMPLES / "fresher_basic.txt").read_text())
    assert all(m["reasons"] for m in r["not_recommended"])


def test_roles_reference_known_skills():
    import json
    roles = json.loads((Path(__file__).resolve().parents[1] / "app/data/roles.json").read_text())["roles"]
    for role in roles:
        for m in role["must_have"]:
            for s in m["skills"]:
                assert s in ex.skills, f"{role['title']}: unknown skill {s}"
        for s in role.get("good_to_have", []):
            assert s in ex.skills, f"{role['title']}: unknown skill {s}"


def test_api_health_and_text():
    assert client.get("/api/health").json()["status"] == "ok"
    body = {"text": (SAMPLES / "frontend_developer.txt").read_text()}
    assert client.post("/api/analyze-text", json=body).status_code == 200


def test_api_upload_txt_and_reject_bad_type():
    data = (SAMPLES / "frontend_developer.txt").read_bytes()
    assert client.post("/api/analyze", files={"file": ("r.txt", data)}).status_code == 200
    assert client.post("/api/analyze", files={"file": ("r.exe", b"x" * 100)}).status_code == 415


def test_api_rejects_empty_resume():
    assert client.post("/api/analyze-text", json={"text": "hi"}).status_code == 422
