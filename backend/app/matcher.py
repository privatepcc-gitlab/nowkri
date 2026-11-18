"""Hybrid job-role matcher.

For every role in the knowledge base we compute three scores:

* must_score  (60%) - how well the candidate meets each must-have skill at
                      the required level. Partial credit = level / required.
* nice_score  (25%) - share of good-to-have skills present (level-weighted).
* text_score  (15%) - TF-IDF cosine similarity between the whole resume and
                      the role description, rescaled so the closest role = 1.

Then a rule-based gate decides the verdict:

* RECOMMENDED     - every must-have met, experience requirement met,
                    and overall score >= RECOMMEND_THRESHOLD.
* STRETCH         - close: at most one must-have gap (one level short, or one
                    missing skill while the other must-haves are met), and
                    experience short by <= 1 year.
                    Shown with an upskilling plan.
* NOT_RECOMMENDED - anything else. These are never suggested; the reasons
                    are returned so the user understands why.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .skills import LEVEL_NAMES, SkillEvidence

DATA_DIR = Path(__file__).parent / "data"

W_MUST, W_NICE, W_TEXT = 0.60, 0.25, 0.15
RECOMMEND_THRESHOLD = 55.0
STRETCH_THRESHOLD = 40.0


@dataclass
class Requirement:
    skills: list[str]
    min_level: int
    met: bool = False
    best_skill: str | None = None
    best_level: int = 0

    @property
    def label(self) -> str:
        return " / ".join(self.skills) if len(self.skills) <= 3 else \
            " / ".join(self.skills[:3]) + " (or similar)"

    def to_dict(self) -> dict:
        return {"requirement": self.label, "min_level": self.min_level,
                "min_level_name": LEVEL_NAMES[self.min_level], "met": self.met,
                "your_skill": self.best_skill, "your_level": self.best_level,
                "your_level_name": LEVEL_NAMES.get(self.best_level, "Not found")}


@dataclass
class RoleMatch:
    title: str
    family: str
    description: str
    min_years: float
    score: float = 0.0
    must_score: float = 0.0
    nice_score: float = 0.0
    text_score: float = 0.0
    verdict: str = "NOT_RECOMMENDED"
    requirements: list[Requirement] = field(default_factory=list)
    matched_nice: list[str] = field(default_factory=list)
    missing_nice: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    upskill: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title, "family": self.family, "description": self.description,
            "min_years": self.min_years, "score": round(self.score, 1),
            "breakdown": {"must_have": round(self.must_score * 100, 1),
                          "good_to_have": round(self.nice_score * 100, 1),
                          "text_similarity": round(self.text_score * 100, 1)},
            "verdict": self.verdict,
            "requirements": [r.to_dict() for r in self.requirements],
            "matched_good_to_have": self.matched_nice,
            "missing_good_to_have": self.missing_nice,
            "reasons": self.reasons, "upskill": self.upskill,
        }


class RoleMatcher:
    def __init__(self, path: Path = DATA_DIR / "roles.json"):
        self.roles = json.loads(path.read_text(encoding="utf-8"))["roles"]
        self.role_docs = [self._role_doc(r) for r in self.roles]

    @staticmethod
    def _role_doc(role: dict) -> str:
        must = " ".join(" ".join(m["skills"]) for m in role["must_have"])
        nice = " ".join(role.get("good_to_have", []))
        # repeat must-haves so they carry more weight in TF-IDF
        return f"{role['title']} {role['description']} {must} {must} {nice}"

    def _text_scores(self, resume_text: str) -> list[float]:
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True,
                              token_pattern=r"(?u)\b[\w+#.]+\b")
        matrix = vec.fit_transform(self.role_docs + [resume_text])
        sims = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        top = sims.max() if sims.size and sims.max() > 0 else 1.0
        return [float(s / top) for s in sims]

    def match(self, skills: list[SkillEvidence], resume_text: str, experience_years: float) -> list[RoleMatch]:
        levels = {s.name: s.level for s in skills}
        text_scores = self._text_scores(resume_text)
        results = []
        for role, ts in zip(self.roles, text_scores):
            results.append(self._evaluate(role, levels, ts, experience_years))
        order = {"RECOMMENDED": 0, "STRETCH": 1, "NOT_RECOMMENDED": 2}
        results.sort(key=lambda r: (order[r.verdict], -r.score))
        return results

    def _evaluate(self, role: dict, levels: dict[str, int], text_score: float, years: float) -> RoleMatch:
        rm = RoleMatch(role["title"], role["family"], role["description"], role.get("min_years", 0))
        rm.text_score = text_score

        # must-have requirements
        credit = []
        for m in role["must_have"]:
            req = Requirement(m["skills"], m["min_level"])
            for s in m["skills"]:
                if levels.get(s, 0) > req.best_level:
                    req.best_level, req.best_skill = levels[s], s
            req.met = req.best_level >= req.min_level
            credit.append(min(1.0, req.best_level / req.min_level))
            rm.requirements.append(req)
        rm.must_score = sum(credit) / len(credit) if credit else 1.0

        # good-to-have
        nice = role.get("good_to_have", [])
        got = 0.0
        for s in nice:
            if s in levels:
                rm.matched_nice.append(s)
                got += min(1.0, 0.5 + levels[s] / 4)  # presence counts, level adds a bit
            else:
                rm.missing_nice.append(s)
        rm.nice_score = got / len(nice) if nice else 1.0

        rm.score = 100 * (W_MUST * rm.must_score + W_NICE * rm.nice_score + W_TEXT * rm.text_score)

        # ---- verdict gate ----
        missing = [r for r in rm.requirements if r.best_level == 0]
        under = [r for r in rm.requirements if 0 < r.best_level < r.min_level]
        exp_gap = max(0.0, rm.min_years - years)

        for r in missing:
            rm.reasons.append(f"Missing must-have skill: {r.label} (needs {LEVEL_NAMES[r.min_level]})")
        for r in under:
            rm.reasons.append(
                f"{r.best_skill} is {LEVEL_NAMES[r.best_level]}, role needs {LEVEL_NAMES[r.min_level]}")
        if exp_gap > 0:
            rm.reasons.append(
                f"Needs {rm.min_years:g}+ years of experience; resume shows {years:g}")

        gaps = len(missing) + len(under)
        small_gap = (gaps == 0) or (gaps == 1 and (
            (under and under[0].min_level - under[0].best_level == 1) or
            (missing and missing[0].min_level <= 2 and rm.must_score >= 0.66)))

        if gaps == 0 and exp_gap == 0 and rm.score >= RECOMMEND_THRESHOLD:
            rm.verdict = "RECOMMENDED"
            rm.reasons.insert(0, "Meets every must-have skill at the required level")
        elif small_gap and exp_gap <= 1 and rm.score >= STRETCH_THRESHOLD:
            rm.verdict = "STRETCH"
            if gaps == 0 and exp_gap == 0:
                rm.reasons.insert(0, f"Skills fit, but overall match ({rm.score:.0f}%) is below "
                                     f"{RECOMMEND_THRESHOLD:.0f}% - strengthen good-to-have skills")
        else:
            rm.verdict = "NOT_RECOMMENDED"

        # upskilling plan for anything not recommended
        if rm.verdict != "RECOMMENDED":
            for r in missing:
                rm.upskill.append(f"Learn {r.skills[0]} and use it in a project "
                                  f"(target: {LEVEL_NAMES[r.min_level]})")
            for r in under:
                rm.upskill.append(f"Take {r.best_skill} from {LEVEL_NAMES[r.best_level]} to "
                                  f"{LEVEL_NAMES[r.min_level]}: build a project or internship using it")
            if exp_gap > 0:
                rm.upskill.append(f"Gain about {exp_gap:g} more year(s) of work/internship experience")
            for s in rm.missing_nice[:2]:
                rm.upskill.append(f"Bonus: add {s}")
        return rm
