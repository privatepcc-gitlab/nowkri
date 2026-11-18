"""Resume text extraction and section splitting.

Supports PDF, DOCX and plain-text resumes. The text is split into sections
(skills, experience, projects, education, certifications, summary, other)
using common heading keywords, so later stages can weigh where a skill
appears: a skill used in an internship counts for more than one that is
only listed.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date

SECTION_KEYWORDS = {
    "skills": ["technical skills", "skills", "core competencies", "technologies", "tech stack",
               "tools", "skill set", "key skills", "technical proficiency"],
    "experience": ["work experience", "professional experience", "experience", "internships",
                   "internship", "employment", "work history"],
    "projects": ["projects", "academic projects", "personal projects", "key projects", "project work"],
    "education": ["education", "academic background", "academics", "qualifications"],
    "certifications": ["certifications", "certificates", "courses", "certification",
                       "training", "online courses"],
    "achievements": ["achievements", "awards", "accomplishments", "extracurricular",
                     "positions of responsibility", "activities", "leadership"],
    "summary": ["summary", "objective", "profile", "about me", "career objective",
                "professional summary"],
}

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

_MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_RE = rf"(?:{_MONTH_RE}\s*[,']?\s*)?((?:19|20)\d{{2}})"
_END_RE = rf"(?:{_DATE_RE}|(present|current|now|till date|ongoing))"
RANGE_RE = re.compile(rf"{_DATE_RE}\s*(?:-|–|—|to|till)\s*{_END_RE}", re.IGNORECASE)
YEARS_EXP_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+|industry\s+|work\s+)?experience",
    re.IGNORECASE)


@dataclass
class ParsedResume:
    text: str
    sections: dict[str, str] = field(default_factory=dict)
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    experience_years: float = 0.0
    experience_source: str = ""
    education: str | None = None


def extract_text(filename: str, data: bytes) -> str:
    """Return plain text from an uploaded resume file."""
    name = filename.lower()
    if name.endswith(".pdf"):
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    if name.endswith(".docx"):
        import docx
        doc = docx.Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Unsupported file type. Upload a PDF, DOCX or TXT resume.")


def _heading_section(line: str) -> str | None:
    """If the line looks like a section heading, return the section key."""
    stripped = line.strip()
    if not stripped or stripped[0] in "•-*–●▪◦·>" or stripped.endswith((".", ",")):
        return None
    words = [w for w in re.findall(r"[A-Za-z]+", stripped)]
    small = {"and", "of", "&", "in", "on", "the"}
    if not words or not all(w[0].isupper() or w.lower() in small for w in words):
        return None  # headings are Title Case or UPPER CASE
    clean = re.sub(r"[^a-z &/]", "", line.lower()).strip()
    if not clean or len(clean) > 40 or len(clean.split()) > 5:
        return None
    for key, words in SECTION_KEYWORDS.items():
        for w in words:
            if clean == w or clean.startswith(w + " ") or clean.endswith(" " + w):
                return key
    return None


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # "Skills: Python, SQL" style lines: heading + content on one line
        if ":" in line:
            head, rest = line.split(":", 1)
            key = _heading_section(head)
            if key and len(head) < 30 and key == "skills":
                sections.setdefault(key, []).append(rest.strip())
                continue
        key = _heading_section(line)
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v) for k, v in sections.items() if v}


def _months_between(y1: int, m1: int, y2: int, m2: int) -> int:
    return max(0, (y2 - y1) * 12 + (m2 - m1) + 1)


def estimate_experience(sections: dict[str, str], full_text: str, today: date | None = None) -> tuple[float, str]:
    """Estimate total experience in years.

    Uses an explicit "N years of experience" statement if present, otherwise
    sums date ranges found in the Experience section (internships included),
    merging overlapping periods.
    """
    today = today or date.today()
    explicit = [float(m.group(1)) for m in YEARS_EXP_RE.finditer(full_text)]
    exp_text = sections.get("experience", "")
    intervals = []
    for m in RANGE_RE.finditer(exp_text):
        sm, sy, em, ey, present = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        start = (int(sy), MONTHS.get((sm or "jan")[:3].lower(), 1))
        if present:
            end = (today.year, today.month)
        else:
            end = (int(ey), MONTHS.get((em or "dec")[:3].lower(), 12))
        if end >= start:
            intervals.append((start[0] * 12 + start[1], end[0] * 12 + end[1]))
    months = 0
    if intervals:
        intervals.sort()
        cs, ce = intervals[0]
        for s, e in intervals[1:]:
            if s <= ce:
                ce = max(ce, e)
            else:
                months += ce - cs + 1
                cs, ce = s, e
        months += ce - cs + 1
    from_ranges = round(months / 12, 1)
    if explicit:
        return max(explicit), "Stated in the resume."
    if intervals:
        n = len(intervals)
        return from_ranges, f"Calculated from {n} date range{'s' if n > 1 else ''} in the Experience section."
    return 0.0, "No work or internship dates found, so treated as a fresher."


def _guess_name(text: str) -> str | None:
    for line in text.splitlines()[:5]:
        line = line.strip()
        if not line or "@" in line or any(ch.isdigit() for ch in line):
            continue
        words = line.split()
        if 1 < len(words) <= 4 and all(w[0].isupper() for w in words if w[0].isalpha()):
            if not _heading_section(line):
                return line.title() if line.isupper() else line
    return None


def _guess_education(sections: dict[str, str]) -> str | None:
    edu = sections.get("education", "")
    for line in edu.splitlines():
        if re.search(r"\b(b\.?\s?e|b\.?\s?tech|m\.?\s?tech|bachelor|master|bca|mca|b\.?sc|m\.?sc|mba|ph\.?d)\b",
                     line, re.IGNORECASE):
            return line.strip()
    first = edu.splitlines()[0].strip() if edu else None
    return first


def parse_resume(text: str, today: date | None = None) -> ParsedResume:
    text = text.replace("\r", "")
    sections = split_sections(text)
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(?:\+?\d{1,3}[\s-]?)?\d{10}|\+?\d{1,3}[\s-]\d{5}[\s-]\d{5}", text)
    years, source = estimate_experience(sections, text, today)
    return ParsedResume(
        text=text,
        sections=sections,
        name=_guess_name(text),
        email=email.group(0) if email else None,
        phone=phone.group(0) if phone else None,
        experience_years=years,
        experience_source=source,
        education=_guess_education(sections),
    )
