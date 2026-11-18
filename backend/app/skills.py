"""Skill extraction and skill-level estimation.

Each skill in the taxonomy has aliases. We find every alias in the resume,
keep the longest non-overlapping matches (so "React Native" is not also
counted as "React"), and record which section each mention came from.

Skill level (1 Beginner .. 4 Expert) comes from two kinds of evidence:

1. Explicit evidence on the same line: proficiency words ("proficient in",
   "familiar with") or durations ("3 years of Java").
2. Usage evidence: where the skill appears. Listing it only in Skills gives
   Beginner; using it in projects, internships/jobs and certifications
   raises the level.

When both exist they are averaged, so a claim of "expert" with no usage
anywhere is pulled down, and real usage backs up a modest claim.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
LEVEL_NAMES = {1: "Beginner", 2: "Intermediate", 3: "Advanced", 4: "Expert"}

PROFICIENCY_WORDS = [
    (4, r"\b(expert|mastery|extensive(ly)?|guru)\b"),
    (3, r"\b(advanced|proficient|strong|deep|highly skilled|excellent)\b"),
    (2, r"\b(intermediate|good knowledge|working knowledge|hands[- ]on|comfortable|experienced)\b"),
    (1, r"\b(basic|basics|beginner|familiar|exposure|learning|fundamentals|elementary|novice)\b"),
]
YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
RATING_SECTIONS = {"skills", "summary", "header"}


@dataclass
class SkillEvidence:
    name: str
    category: str
    level: int = 1
    level_name: str = "Beginner"
    mentions: int = 0
    sections: dict[str, int] = field(default_factory=dict)
    explicit_level: int | None = None
    usage_level: int = 1
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "category": self.category, "level": self.level,
            "level_name": self.level_name, "mentions": self.mentions,
            "sections": self.sections, "reasons": self.reasons,
        }


class SkillExtractor:
    def __init__(self, path: Path = DATA_DIR / "skills.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.skills = {s["name"]: s for s in data["skills"]}
        self.implies: dict[str, list[str]] = data.get("implies", {})
        self.patterns: list[tuple[str, re.Pattern, bool]] = []  # (skill, regex, strict)
        for s in data["skills"]:
            aliases = set(a.lower() for a in s.get("aliases", [])) | {s["name"].lower()}
            if s.get("strict"):
                aliases -= {a.lower() for a in s["strict"]}
                for a in s["strict"]:
                    self.patterns.append((s["name"], self._compile(a, case_sensitive=True), True))
            for a in aliases:
                self.patterns.append((s["name"], self._compile(a, case_sensitive=False), False))

    @staticmethod
    def _compile(alias: str, case_sensitive: bool) -> re.Pattern:
        body = re.escape(alias).replace(r"\ ", r"[\s-]+")
        pattern = rf"(?<![A-Za-z0-9+#.]){body}(?![A-Za-z0-9+#]|\.[A-Za-z])"
        return re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)

    def _find_mentions(self, text: str, strict_allowed: bool) -> list[tuple[int, int, str]]:
        hits = []
        for skill, rx, strict in self.patterns:
            if strict and not strict_allowed:
                continue
            for m in rx.finditer(text):
                hits.append((m.start(), m.end(), skill))
        # keep longest non-overlapping matches
        hits.sort(key=lambda h: (-(h[1] - h[0]), h[0]))
        taken: list[tuple[int, int, str]] = []
        for h in hits:
            if all(h[1] <= t[0] or h[0] >= t[1] for t in taken):
                taken.append(h)
        return sorted(taken)

    @staticmethod
    def _explicit_level(line: str) -> int | None:
        low = line.lower()
        y = YEARS_RE.search(low)
        if y:
            yrs = float(y.group(1))
            return 4 if yrs >= 5 else 3 if yrs >= 3 else 2 if yrs >= 1 else 1
        for lvl, pat in PROFICIENCY_WORDS:
            if re.search(pat, low):
                return lvl
        return None

    @staticmethod
    def _context(text: str, pos: int) -> tuple[str, str]:
        """Return (clause around the skill, part of the line before the skill)."""
        start = text.rfind("\n", 0, pos) + 1
        end = text.find("\n", pos)
        line = text[start:end if end != -1 else len(text)]
        rel = pos - start
        prefix = line[:rel]
        # 'Proficient: Python, SQL' -> the label holds the level word
        if ":" in prefix:
            return line[: line.index(":")], prefix
        seps = [",", ";", "|", "•", "(", ")"]
        left = max(line.rfind(sep, 0, rel) for sep in seps if sep not in "()")
        rights = [i for i in (line.find(sep, rel) for sep in [",", ";", "|", "•"]) if i != -1]
        right = min(rights) if rights else len(line)
        return line[left + 1:right], prefix

    @classmethod
    def _level_from_context(cls, clause: str, prefix: str) -> int | None:
        lvl = cls._explicit_level(clause)
        if lvl:
            return lvl
        # nearest proficiency word earlier on the same line
        low = prefix.lower()
        best_pos, best = -1, None
        for l, pat in PROFICIENCY_WORDS:
            for m in re.finditer(pat, low):
                if m.start() > best_pos:
                    best_pos, best = m.start(), l
        return best

    def extract(self, sections: dict[str, str]) -> list[SkillEvidence]:
        found: dict[str, SkillEvidence] = {}
        for sec_name, sec_text in sections.items():
            strict_ok = sec_name == "skills"
            for start, _end, skill in self._find_mentions(sec_text, strict_ok):
                ev = found.get(skill)
                if ev is None:
                    ev = found[skill] = SkillEvidence(skill, self.skills[skill]["category"])
                ev.mentions += 1
                ev.sections[sec_name] = ev.sections.get(sec_name, 0) + 1
                # self-ratings only count where people actually rate skills
                lvl = None
                if sec_name in RATING_SECTIONS:
                    lvl = self._level_from_context(*self._context(sec_text, start))
                if lvl and (ev.explicit_level is None or lvl > ev.explicit_level):
                    ev.explicit_level = lvl
        for ev in found.values():
            self._score(ev)
        self._apply_implications(found)
        return sorted(found.values(), key=lambda e: (-e.level, -e.mentions, e.name))

    def _apply_implications(self, found: dict[str, SkillEvidence]) -> None:
        """Using a framework proves its base skill one level lower
        (e.g. Advanced React => at least Intermediate JavaScript)."""
        changed = True
        while changed:  # propagate chains like Next.js -> React -> JavaScript
            changed = False
            for parent, children in self.implies.items():
                p = found.get(parent)
                if not p or p.level < 2:
                    continue
                for child in children:
                    target = p.level - 1
                    c = found.get(child)
                    if c is None:
                        c = found[child] = SkillEvidence(child, self.skills[child]["category"])
                        c.reasons = []
                    if c.level < target:
                        c.level, c.level_name = target, LEVEL_NAMES[target]
                        c.reasons = [r for r in c.reasons if not r.startswith("implied by")]
                        c.reasons.append(f"implied by {parent} ({p.level_name})")
                        changed = True

    @staticmethod
    def _score(ev: SkillEvidence) -> None:
        s = ev.sections
        exp = s.get("experience", 0)
        proj = s.get("projects", 0) + s.get("achievements", 0)
        cert = s.get("certifications", 0)
        usage = 1.0
        reasons = []
        if proj:
            usage += 1
            reasons.append(f"used in {proj} project mention(s)")
        if exp:
            usage += 1
            reasons.append(f"used in work/internship ({exp} mention(s))")
        if cert:
            usage += 0.5
            reasons.append("backed by a certification/course")
        if proj >= 2 or exp >= 2:
            usage += 0.5
        if not reasons:
            reasons.append("listed, but not shown in any project or job")
        ev.usage_level = max(1, min(4, int(usage)))
        if ev.explicit_level:
            reasons.insert(0, f"self-rated {LEVEL_NAMES[ev.explicit_level]}")
            # Average the claim and the evidence. Trust evidence over claims:
            # round up when usage backs the claim, round down when the claim
            # is bigger than the usage shown. Expert needs an explicit claim.
            avg = (ev.explicit_level + ev.usage_level) / 2
            ev.level = int(avg + 0.5) if ev.usage_level >= ev.explicit_level else int(avg)
            if ev.explicit_level < 4:
                ev.level = min(ev.level, 3)
        else:
            # without a self-rating, usage alone can show at most Advanced
            ev.level = min(3, ev.usage_level)
        ev.level = max(1, min(4, ev.level))
        ev.level_name = LEVEL_NAMES[ev.level]
        ev.reasons = reasons
