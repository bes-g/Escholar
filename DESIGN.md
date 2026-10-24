# E-Scholar design note

## Workflow

1. The student submits a fictitious profile. Field of study, GPA, and country are required. Year of study may be left blank on purpose.
2. FastAPI validates the form. Invalid GPA or year returns a message and the interface keeps the typed values.
3. The model receives the profile and must call tools. It cannot invent a scholarship or an eligibility result.
4. `search_opportunities` reads the five catalog rows from the database and returns each source record.
5. `check_eligibility` runs the written rules in Python. Each row becomes eligible, ineligible, or undetermined. One failed rule makes the row ineligible even when another fact is missing.
6. If anything needed for an undetermined row is absent, the interface asks for that fact and the agent rechecks.
7. When at least one row is eligible and nothing is undetermined, the student sees the plan: deadlines, documents, next actions, and a checklist. Nothing is stored yet.
8. Confirm calls the model again with permission to use `save_application_plan`. The tool refuses if that flag is off. It stores only the eligible rows, using catalog deadlines and documents.
9. Saved plans are read back from the database.

The loop allows at most 5 model rounds and 8 tool calls. A labeled control simulates a model failure for the failure test. Normal checks call the live model.

## Why this shape

A vector database is the wrong store. There are five records, the criteria are explicit, and eligibility must be deterministic. Similarity search would hide the rule that failed. The requirements also put vector databases out of scope.

React plus FastAPI fits the work better than putting the rules in a Worker. The rule engine, the confirmation gate, and the tool log live in one Python service. The built interface is served by that same service so judges open one HTTPS URL.

Local development uses SQLite. Deployment should use Neon Postgres on the free tier so the catalog and plans are in a remote database. The model is Gemini’s free tier through the OpenAI-compatible endpoint (`gemini-3.5-flash-lite`, or `gemini-3.8-flash` if tool calls are unreliable). The API key is an environment variable on the host, never in the frontend or the repository.

## Storage

Each scholarship row holds an id, name, provider, deadline, summary, documents, and the criterion objects. The seed in `catalog.py` is loaded into the database on startup. The checker reads those rows back, so a running agent is not using a hard-coded reply.

A saved plan stores the plan id, fictitious student name, profile summary, opportunities (deadline, documents, next actions, checklist), and a timestamp.

## What is intentionally absent

No accounts, scraping, real applications, document upload, or private plan list. Saved plans on a shared demo are visible to anyone with the link, which is acceptable only because the data is fictitious. Reminders and document-status tracking are optional and not built.

## Team note

Member responsibilities are still to be filled in. The application code in this repository was drafted with Cursor’s coding agent from the customer requirements, then checked with the rule tests in `backend/tests`.
