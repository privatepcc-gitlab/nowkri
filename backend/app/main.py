"""Job Hunt API.

Run:  uvicorn app.main:app --port 8001   (from the backend folder)
App:  http://127.0.0.1:8001        (serves the built frontend in frontend/dist)
Docs: http://127.0.0.1:8001/docs
"""
from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .jobs.search import SearchManager, SearchRequest
from .jobs.store import JobCache
from .matcher import RECOMMEND_THRESHOLD, STRETCH_THRESHOLD, RoleMatcher
from .parser import extract_text, parse_resume
from .skills import SkillExtractor

MAX_BYTES = 5 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = ROOT / "samples"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DATA_DIR = Path(__file__).parent / "data"

app = FastAPI(title="Job Hunt API", version="1.0.0",
              description="Upload a resume, get job titles that match your skills and skill levels.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def no_stale_app_page(request, call_next):
    """The built JS/CSS files have content hashes in their names, but index.html
    does not: tell browsers to recheck it, so a rebuilt frontend shows up at once."""
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response

extractor = SkillExtractor()
matcher = RoleMatcher()
search_manager = SearchManager(JobCache(DATA_DIR / "cache" / "jobs.sqlite"))


class TextIn(BaseModel):
    text: str


def analyze_text(text: str) -> dict:
    if len(text.strip()) < 50:
        raise HTTPException(422, "Could not read enough text from the resume. "
                                 "If it is a scanned PDF, upload a text-based PDF or DOCX.")
    parsed = parse_resume(text)
    skills = extractor.extract(parsed.sections)
    if not skills:
        raise HTTPException(422, "No recognisable skills found in the resume.")
    matches = matcher.match(skills, parsed.text, parsed.experience_years)
    by = lambda v: [m.to_dict() for m in matches if m.verdict == v]
    return {
        "profile": {
            "name": parsed.name, "email": parsed.email, "phone": parsed.phone,
            "education": parsed.education,
            "experience_years": parsed.experience_years,
            "experience_source": parsed.experience_source,
            "sections_found": [k for k in parsed.sections if k != "header"],
        },
        "resume_text": parsed.text,
        "skills": [s.to_dict() for s in skills],
        "recommended": by("RECOMMENDED"),
        "stretch": by("STRETCH"),
        "not_recommended": by("NOT_RECOMMENDED"),
        "thresholds": {"recommend": RECOMMEND_THRESHOLD, "stretch": STRETCH_THRESHOLD},
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "roles": len(matcher.roles), "skills": len(extractor.skills)}


@app.get("/api/roles")
def roles():
    return matcher.roles


@app.get("/api/samples")
def samples():
    return sorted(p.name for p in SAMPLES_DIR.glob("*.txt"))


@app.get("/api/samples/{name}")
def sample(name: str):
    path = (SAMPLES_DIR / name).resolve()
    if path.parent != SAMPLES_DIR or not path.exists():
        raise HTTPException(404, "Sample not found")
    return analyze_text(path.read_text(encoding="utf-8"))


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large (max 5 MB)")
    try:
        text = extract_text(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(415, str(e))
    except Exception:
        raise HTTPException(422, "Could not read this file. Is it a valid PDF/DOCX?")
    return analyze_text(text)


@app.post("/api/analyze-text")
def analyze_plain(body: TextIn):
    return analyze_text(body.text)


@app.post("/api/jobs/search")
def start_job_search(body: SearchRequest, background: BackgroundTasks):
    """Start a live search on the job sites. Poll GET /api/jobs/search/{id} for results."""
    if not body.titles and not body.skills:
        raise HTTPException(422, "Send at least one job title or skill to search for.")
    sid = search_manager.start(body)
    background.add_task(search_manager.run, sid)
    return {"search_id": sid}


@app.get("/api/jobs/search/{search_id}")
def get_job_search(search_id: str):
    s = search_manager.get(search_id)
    if s is None:
        raise HTTPException(404, "Search not found (it may have expired). Start a new one.")
    return s


# Serve the built React app (frontend/dist) at "/" so the whole project runs
# from one command, without Node.js. Registered last so /api routes win.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
