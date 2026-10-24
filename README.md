# 🎓 E‑Scholar

> **A transparent scholarship adviser for a fictional catalog.**
>
> E‑Scholar helps students discover scholarships, understand exactly why they qualify, and build an application plan — without guessing and without storing real personal data.

<p align="center">
  <strong>React · FastAPI · SQLite/Postgres · Gemini tool calling</strong>
</p>

---

## ✨ What it does

A student enters a profile and E‑Scholar:

1. 🔎 Searches the complete scholarship catalog
2. ✅ Checks every eligibility rule in application code
3. 🧭 Separates results into **eligible**, **ineligible**, and **undetermined**
4. ❓ Asks for missing information when a decision cannot yet be made
5. 📝 Shows deadlines, required documents, and next actions
6. 💾 Saves an application plan only after the student confirms

> ⚠️ **Demo project:** The catalog is fictional. Do not enter real personal or sensitive information.

## 🎯 Design principles

- **Deterministic eligibility** — rules are explicit, repeatable, and evaluated in code.
- **No vector database** — this project uses structured records and rule-based decisions, not similarity guesses.
- **Transparent results** — each decision explains the rule outcome and cites its source record.
- **Confirmation before saving** — plans are never persisted without student confirmation.
- **Bounded agent behavior** — the agent loop is limited to a maximum of eight tool calls.
- **One deployable service** — FastAPI can serve both the API and the built React interface.

## 🧱 Architecture

```text
┌────────────────────┐
│   React + Vite UI  │
└─────────┬──────────┘
          │ JSON / REST
          ▼
┌────────────────────┐
│      FastAPI       │
│                    │
│  Bounded agent     │◄──── Gemini API
│  ├─ search         │
│  ├─ eligibility    │
│  └─ save plan      │
└─────────┬──────────┘
          │ SQL
          ▼
┌────────────────────┐
│ SQLite / Postgres  │
│  Five structured   │
│  fictional records │
└────────────────────┘
```

### Why not a vector database?

The catalog contains structured scholarship records, and eligibility depends on explicit acceptance rules. A vector search could return something that *sounds* similar without satisfying the actual requirements. E‑Scholar therefore uses a normal relational database and makes every eligibility decision in application code.

## 🛠️ Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | React with Vite |
| Backend | FastAPI |
| Local database | SQLite |
| Deployment database | Neon Postgres |
| AI model | Gemini API with tool calling |
| Packaging | Docker |
| Testing | Pytest |

## 🚀 Run locally

### 1. Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your Gemini key to `.env`:

```env
LLM_API_KEY=your-key-here
```

> Never commit `.env` or real API keys.

Start FastAPI:

```bash
uvicorn app.main:app --reload --port 8000
```

### 2. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173**. The Vite development server proxies `/api` requests to FastAPI on port `8000`.

### 3. Serve the production build from FastAPI

```bash
cd frontend
npm run build

cd ../backend
uvicorn app.main:app --port 8000
```

Open **http://127.0.0.1:8000**.

### Run the tests

The eligibility tests do not require a model key:

```bash
cd backend
pytest
```

## ☁️ Deployment

E‑Scholar is designed to run as one Dockerized FastAPI service with the built React application included.

1. Create a Neon Postgres database and copy its connection URL.
2. Create a Gemini API key in Google AI Studio.
3. Build and run the `Dockerfile` on a free Python-compatible host.
4. Configure these environment variables:
   - `DATABASE_URL`
   - `LLM_API_KEY`
   - `LLM_MODEL` — optional
   - `FRONTEND_DIST` — use the value configured by the image
5. If your selected Gemini model does not reliably call tools, configure a compatible tool-calling model through `LLM_MODEL`.

Postgres URLs beginning with `postgresql://` are rewritten to use the psycopg driver when needed.

> Free hosts may sleep when idle, so the first request can take up to a minute.

## 🧠 Agent tools

| Tool | Responsibility | Safety behavior |
| --- | --- | --- |
| `search_opportunities` | Reads every catalog record from the database | Keywords only mark possible matches; they do not decide eligibility |
| `check_eligibility` | Evaluates every rule in application code | A failed rule makes a scholarship ineligible, even if another fact is missing |
| `save_application_plan` | Persists the confirmed plan | Saves eligible scholarships only and refuses to run before confirmation |

Deadlines, documents, and actions come from the catalog. This keeps the saved plan consistent with the preview shown to the student.

## ✅ Acceptance checklist

| Case | Steps | Expected result |
| --- | --- | --- |
| **TC‑1 · Eligible shortlist** | Load the example and select **Check** | `SCH-001`, `SCH-003`, and `SCH-004` are eligible with deadlines, documents, and source IDs |
| **TC‑2 · Ineligible profile** | Load the ineligible example | Every scholarship is ineligible and each card names the failed rule and source record |
| **TC‑3 · Save and reopen** | Confirm and save the TC‑1 results, then open **Saved plans** | The reopened plan has the same deadlines, checklist, and actions |
| **TC‑4 · Missing year** | Load the missing-year example, enter year `3`, and recheck | Initial results are undetermined; after the year is supplied, the profile can be confirmed and saved |
| **TC‑5 · Retry flow** | Simulate a failure | A clear error appears, the form remains filled, and **Retry** works |

## 📁 Project layout

```text
.
├── backend/
│   └── app/
│       ├── agent.py          # Bounded model/tool loop
│       ├── catalog.py        # Five fictional scholarships
│       ├── eligibility.py     # Deterministic rule engine
│       └── main.py            # FastAPI application
├── frontend/
│   └── src/
│       └── App.jsx            # Profile, results, confirmation, logs, saved plans
├── DESIGN.md                 # Design note for the submission
├── Dockerfile
└── README.md
```

## 🔐 Privacy and scope

This is an educational demonstration using fictional scholarship data. Do not use it to process real student records, personally identifiable information, financial information, or other sensitive data.

## 📄 License

This project is a demonstration application. Add the repository's intended license here before distributing it publicly.
