# E-Scholar

A scholarship adviser for a **fictitious** catalog. A student enters a profile. An agent searches five scholarships, checks eligibility with explicit rules in code, asks for anything missing, and saves an application plan only after the student confirms.

Do not enter real personal data.

## Architecture

Use a normal database, not a vector database.

The catalog has five structured records and the acceptance rules are explicit. Eligibility has to be repeatable and decided in application code. A vector search would guess by similarity, which this project is not allowed to do. The requirements also list vector databases as out of scope.

```text
React (Vite)
    |
    |  JSON
    v
FastAPI
    |-- agent loop (Gemini free tier, tool calling, at most 8 tool calls)
    |     search_opportunities     reads the catalog
    |     check_eligibility        rules in code: eligible / ineligible / undetermined
    |     save_application_plan    refused until the student confirms
    |
    v
SQLite locally, Neon Postgres when deployed
```

One FastAPI process serves the built React app and the API, so judges use a single HTTPS URL. The model key stays in the server environment.

Suggested free services, which the team still has to confirm against current limits:

| Piece | Service |
| --- | --- |
| App | One free Python host (the Dockerfile runs the API and the built interface) |
| Database | [Neon](https://neon.tech) Postgres free tier |
| Model | Gemini API free tier, model `gemini-3.5-flash-lite` |

The first request to a sleeping free host can take up to a minute.

## Run locally

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Put your Gemini key in LLM_API_KEY. Do not commit .env.
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. The dev server proxies `/api` to port 8000.

To serve both from FastAPI:

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000.

`pytest` from `backend/` runs the rule tests without a model key.

## Deploy

1. Create a Neon database and copy its Postgres URL.
2. Create a Gemini API key in Google AI Studio.
3. Build and run the Dockerfile on a free host.
4. Set `DATABASE_URL`, `LLM_API_KEY`, and leave `FRONTEND_DIST` as the image sets it.
5. If `gemini-3.5-flash-lite` skips tool calls, set `LLM_MODEL=gemini-3.8-flash`.

`postgresql://` URLs are rewritten to the psycopg driver.

## Five acceptance cases

Load the matching example, or type the values, then check the tool log.

| Case | What to do | Expected |
| --- | --- | --- |
| TC-1 | Example “eligible shortlist”, then Check | SCH-001, SCH-003, and SCH-004 eligible, with deadlines, documents, and source ids |
| TC-2 | Example “ineligible” | Every scholarship ineligible, each card naming the failed rule and source record |
| TC-3 | From TC-1, Confirm and save, then Saved plans | The reopened plan has the same deadlines, checklist, and actions |
| TC-4 | Example “missing year” | Undetermined results ask for year of study. Enter 3, recheck, then confirm and save |
| TC-5 | Simulate a failure | A clear error, the form still filled, and Retry works |

## Tools

- `search_opportunities` reads every catalog row from the database. Keywords only mark rows.
- `check_eligibility` classifies every row in code. A failed rule makes the row ineligible even if another fact is missing.
- `save_application_plan` stores the eligible rows only, and only after confirmation. Deadlines and the checklist come from the catalog, so the saved plan matches the preview.

## Layout

- `backend/app/eligibility.py` — the rule engine
- `backend/app/catalog.py` — the five fictitious scholarships
- `backend/app/agent.py` — the bounded tool loop
- `frontend/src/App.jsx` — profile, results, confirmation, tool log, saved plans
- `DESIGN.md` — short design note for the submission
