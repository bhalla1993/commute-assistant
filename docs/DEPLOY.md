Deployment — Docker + Fly.io
=============================

This document covers recommended steps to containerize and deploy the app to Fly.io.

Prerequisites
- Docker installed
- Fly CLI (`flyctl`) installed and logged in
- A Fly.io account

Dockerfile (recommended)
- Base image: `python:3.12-slim`
- Copy project, install `requirements.txt`, expose port 8000, and run `uvicorn api.main:app --host 0.0.0.0 --port 8000`.

Build & run locally
```bash
docker build -t drt-transit .
docker run -p 8000:8000 --env-file .env drt-transit
# then open http://localhost:8000
```

Fly.io quick deploy (first time)
```bash
cd transit-backend
fly launch            # follow prompts (app name, region)
fly volumes create transit_data --region yyz --size 3
# set secrets
fly secrets set OPENAI_API_KEY=<key> STRIPE_SECRET_KEY=<sk> STRIPE_WEBHOOK_SECRET=<whsec> APP_BASE_URL=https://your-app.fly.dev
fly deploy
fly open
```

Persistent storage
- Create a Fly volume and mount it at `/app/data` (the app uses `DB_PATH` which defaults to `data/transit.db`).
- Ensure the Docker image does not bake the DB file; the runtime will use the mounted volume.

Health checks
- Configure Fly to check `GET /health` and consider the app `degraded` if poller or DB fails.

Environment variables & secrets
- Use `fly secrets set` to store sensitive keys.
- Common env vars:
  - `OPENAI_API_KEY` or `OPENAI_BASE_URL` + `OPENAI_MODEL`
  - `DB_PATH` (inside container should be `/app/data/transit.db`)
  - `POLL_INTERVAL_SECONDS` (default 30)
  - `GTFS_RT_*_URL` (trip updates, vehicle positions, alerts)
  - Stripe keys: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PREMIUM_PRICE_ID`, `APP_BASE_URL`
  - Feature flags: see `docs/FEATURE_FLAGS.md`

Rolling restarts & maintenance
- To disable features for maintenance, set `MAINTENANCE_MODE=true` via secrets or env and restart.

Rollback
- Revert to a previous Fly image via `fly deploy --image <image>` or from Fly's dashboard.

