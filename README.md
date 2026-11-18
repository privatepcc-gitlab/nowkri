# Job Hunt — resume to job-title matcher

Upload a resume (PDF, DOCX or TXT). Job Hunt extracts your skills, estimates the level of each skill
(Beginner → Expert), and matches you to job titles in three lanes:

| Lane | Meaning |
|---|---|
| **Apply** | You meet every must-have skill at the required level and the experience requirement. |
| **Almost there** | One small gap (one skill one level short, or one missing skill). Comes with an upskilling plan. |
| **Skip for now** | Not a fit. Never suggested, but each one lists the exact reasons. |

## Tech stack
- **Backend:** Python, FastAPI, pdfplumber, python-docx, scikit-learn (TF-IDF)
- **Frontend:** React 18 + Vite
- **Knowledge base:** `backend/app/data/skills.json` (133 skills, aliases, implications) and
  `backend/app/data/roles.json` (39 job roles with must-have skills, minimum levels, minimum experience)

## How the matching works
1. **Parse** — extract text, split into sections (Skills, Experience, Projects, Certifications, …), estimate total experience from date ranges.
2. **Extract skills** — alias matching with longest-match-wins (so "React Native" is not counted as "React"); short ambiguous names (C, R, Go) only count inside the Skills section.
3. **Estimate level (1–4)** — combines the self-rating ("Proficient", "basic", "3 years") with usage evidence (listed only → used in projects → used at work/internship → certified). Evidence beats claims: over-claims are rounded down, and Expert needs an explicit claim. Frameworks imply base skills (Advanced React ⇒ Intermediate JavaScript/HTML/CSS).
4. **Score each role** — `60% must-have fit + 25% good-to-have skills + 15% TF-IDF text similarity`.
5. **Gate** — a high score alone is not enough: a role is recommended only if *every* must-have is met at the required level and experience is enough. This is what stops it suggesting jobs you should not apply for.

## Run it (Windows)
Needs only **Python 3.10+** to run the app (Node.js is needed only if you want to edit the frontend).

**Easiest:** double-click `start.bat`. It starts the backend, which also serves the app, and opens http://127.0.0.1:8001.
The first run installs packages and can take a few minutes; if the page shows an error, wait until the window says
"Application startup complete" and refresh. If the window shows `[ERROR]`, it stays open so you can read it.

**Frontend development (optional, needs Node.js 18+):** run `start_frontend.bat` alongside the backend and open
http://127.0.0.1:5173 for hot reload. After changing the frontend, run `npm run build` in `frontend` so
http://127.0.0.1:8001 serves the new version.

**Manual:**
```bat
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```
In a second terminal:
```bat
cd frontend
npm install
npm run dev
```
API docs (Swagger): http://127.0.0.1:8001/docs

## Tests
```bat
cd backend
pytest -q
```

## Project structure
```
backend/
  app/main.py        FastAPI endpoints
  app/parser.py      text extraction, sections, experience
  app/skills.py      skill extraction + level estimation
  app/matcher.py     scoring + Apply / Almost there / Skip gate
  app/data/          skills.json, roles.json
  tests/             pytest unit + API tests
frontend/src/        React UI (App.jsx, components.jsx, styles.css)
samples/             sample resumes for the demo
```

## Extending
Add a role: append an object to `roles.json` with `title`, `family`, `description`, `min_years`,
`must_have` (each `{skills: [...], min_level: 1-4}`; any one skill in the list satisfies it) and
`good_to_have`. The test `test_roles_reference_known_skills` checks every skill exists in `skills.json`.
