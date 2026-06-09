DRT AI Transit Assistant
========================

Mobile-first web app providing natural-language access to Durham Region Transit (DRT) schedules, live updates, and service alerts using GTFS static data, GTFS-RT feeds, and an AI agent.

Key features
- Nearby stops via browser GPS
- Real-time delays and vehicle positions (GTFS-RT)
- Service alerts awareness
- Natural-language chat powered by a local agent + LLM fallback
- Free tier (limited queries) + optional Stripe subscription for premium access

Tech stack
- Backend: Python 3.12, FastAPI
- Database: SQLite (WAL mode)
- Frontend: Vanilla HTML / CSS / JavaScript (single-page static files)
- Deployment: Docker + Fly.io (recommended)

**Quickstart (local)**

1. Create a virtualenv and install dependencies (from repository root)

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

2. Copy environment variables

- Create a `.env` file at the repo root. See `docs/FEATURE_FLAGS.md` and `docs/SUBSCRIPTIONS.md` for required variables. You can copy the example:

```bash
cp .env.example .env
# then edit .env to set secrets and API keys
```

3. Initialize the (local) SQLite DB (optional)

```bash
mkdir -p transit-backend/data
if [ -f transit-backend/db/schema.sql ]; then
  sqlite3 transit-backend/data/transit.db < transit-backend/db/schema.sql
fi
```

4. Start the development server

From the backend folder:

```bash
cd transit-backend
python -m uvicorn api.main:app --reload --port 8000
```

Or run from the repo root:

```bash
python -m uvicorn transit-backend.api.main:app --reload --port 8000
```

5. Open the frontend

- Visit http://localhost:8000 in your browser to load the UI (served by FastAPI StaticFiles).

Useful commands
- Run tests: `pytest` (from repo root)
- Run formatter: `black .` (if installed)

Repository layout (high level)
- `transit-backend/` — backend Python application
  - `api/` — FastAPI routers and helpers (endpoints, auth, subscription, config)
  - `agent/` — local agent logic and tools for the LLM
  - `engine/` — domain logic (delays, routes, nearby, alerts)
  - `feeds/` — GTFS-RT poller & parser
  - `db/` — schema and SQLite helpers
  - `frontend/` — static files (index.html, app.js, style.css)
- `mvp1-plan.md`, `FEATURE_FLAGS_PLAN.md` — product & implementation plans

Contributing
See `CONTRIBUTING.md` (drafted in `docs/`).

Where to look next
- API reference: `docs/API.md`
- Feature flags & runtime behavior: `docs/FEATURE_FLAGS.md`
- Stripe & subscription setup: `docs/SUBSCRIPTIONS.md`
- Deployment: `docs/DEPLOY.md`

License
- This project does not include a license file. Add one if you plan to publish.
