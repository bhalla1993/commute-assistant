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

Quickstart (local)
1. Create a virtualenv and install deps
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r transit-backend/requirements.txt
```

2. Copy environment variables
- Create a `.env` file at the repo root. See the `docs/FEATURE_FLAGS.md` and `docs/SUBSCRIPTIONS.md` for required variables.

3. Initialize DB and start server
```bash
cd transit-backend
uvicorn api.main:app --reload --port 8000
```

4. Open the frontend
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
