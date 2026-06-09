DRT AI TRANSIT ASSISTANT — PLAN (Web App Edition)
==================================================
Last updated: 2026-04-26
Status: Weeks 1–3 backend complete. Week 4 (Web UI + Deployment) in progress.

VISION
------
A mobile-responsive web app where a user asks natural language questions about
Durham Region Transit (DRT). An AI agent uses real-time and scheduled transit
data to suggest the best route options, flag delays, and surface service alerts.
Runs in any phone or desktop browser — no app install required.

SCOPE — IN
----------
- Durham Region Transit only
- Trip delay detection and alternative route suggestions
- User GPS-based nearby stop discovery (browser geolocation API)
- Manual location text input fallback when GPS is denied
- Service alert awareness
- Natural language Q&A via web chat interface (mobile-responsive)
- Chat history saved in browser localStorage (persists across page refreshes, per device)
- One saved "regular route" per device with auto-check on page load
- Works in phone browser (375px+) and on desktop

SCOPE — OUT
-----------
- GO Transit, TTC, or other agency integration
- Trip booking or fare payment
- User accounts or server-side saved routes (no login system)
- Cross-device history or route sync
- Historical delay trend analysis
- Push notifications
- Native iOS or Android app (deferred — web app covers phone browsers first)

DATA SOURCES
------------
All from: https://opendata.durham.ca/search?tags=Durham%2520Transit

1. GTFS Static Schedule     — .zip (CSV files)   — load once, reload on timetable changes
2. GTFS-RT Trip Updates     — .pb (protobuf)      — poll every 30 seconds
3. GTFS-RT Vehicle Positions — .pb (protobuf)     — poll every 30 seconds
4. GTFS-RT Service Alerts   — .pb (protobuf)      — poll every 30 seconds

TECH STACK
----------
Backend:     Python + FastAPI
Database:    SQLite (WAL mode) — on Fly.io persistent volume
AI (dev):    Groq free tier — llama-3.3-70b-versatile (OpenAI-compatible API, $0)
AI (prod):   OpenAI GPT-4o or Gemini Flash (pay-as-you-go, ~$1–5/month at MVP volume)
Frontend:    Vanilla HTML + CSS + JavaScript — served by FastAPI StaticFiles, no build tools
Deployment:  Fly.io — single container, free 3GB persistent volume for SQLite
Packages:    gtfs-realtime-bindings, protobuf, fastapi, uvicorn, openai, python-multipart

PROJECT STRUCTURE
-----------------
transit-backend/
  frontend/
    index.html             <- single-page web app shell (status card + chat + input bar)
    style.css              <- mobile-first responsive styles (375px to 1280px)
    app.js                 <- all UI logic: chat, GPS, localStorage, saved route
  data/
    gtfs/                  <- unzipped GTFS static files go here
    TripUpdates            <- sample .pb file (already have this)
  db/
    schema.sql             <- all table definitions
    load_gtfs.py           <- one-time static data loader
    database.py            <- shared SQLite connection helper
  feeds/
    poller.py              <- background thread, fetches all 3 RT feeds every 30s
    parser.py              <- parses .pb bytes to Python dicts
  engine/
    delays.py              <- scheduled vs realtime delay calculation
    routes.py              <- find routes between two stops
    nearby.py              <- haversine-based stop proximity from GPS
    alerts.py              <- active service alert lookup
  agent/
    tools.py               <- LLM tool definitions (function calling)
    prompt.py              <- system prompt for AI agent
    agent.py               <- agent orchestration logic
  api/
    main.py                <- FastAPI app entry point + StaticFiles mount for frontend/
    endpoints.py           <- /chat, /stops/nearby, /delays, /alerts
  Dockerfile               <- builds single container (FastAPI + frontend + SQLite + poller)
  fly.toml                 <- Fly.io deploy config with persistent volume mount
  requirements.txt
  .env                     <- API keys (never commit this)

DATABASE SCHEMA (SQLite)
------------------------

-- STATIC TABLES (loaded once from GTFS zip)

CREATE TABLE stops (
    stop_id TEXT PRIMARY KEY,
    stop_name TEXT,
    stop_lat REAL,
    stop_lon REAL
);

CREATE TABLE routes (
    route_id TEXT PRIMARY KEY,
    route_short_name TEXT,
    route_long_name TEXT,
    route_type INTEGER
);

CREATE TABLE trips (
    trip_id TEXT PRIMARY KEY,
    route_id TEXT,
    service_id TEXT,
    trip_headsign TEXT,
    direction_id INTEGER
);

CREATE TABLE stop_times (
    trip_id TEXT,
    stop_sequence INTEGER,
    stop_id TEXT,
    arrival_time TEXT,
    departure_time TEXT,
    PRIMARY KEY (trip_id, stop_sequence)
);

CREATE TABLE calendar_dates (
    service_id TEXT,
    date TEXT,
    exception_type INTEGER
);

-- REAL-TIME TABLES (written by poller every 30s)

CREATE TABLE rt_trip_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at INTEGER DEFAULT (strftime('%s','now')),
    trip_id TEXT,
    route_id TEXT,
    start_date TEXT,
    stop_sequence INTEGER,
    stop_id TEXT,
    arrival_time INTEGER,
    departure_time INTEGER,
    schedule_relationship TEXT
);

CREATE TABLE rt_vehicle_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at INTEGER DEFAULT (strftime('%s','now')),
    vehicle_id TEXT,
    trip_id TEXT,
    route_id TEXT,
    latitude REAL,
    longitude REAL,
    bearing REAL,
    speed REAL,
    current_stop_sequence INTEGER
);

CREATE TABLE rt_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at INTEGER DEFAULT (strftime('%s','now')),
    alert_id TEXT,
    route_id TEXT,
    stop_id TEXT,
    header TEXT,
    description TEXT,
    effect TEXT
);

CREATE INDEX idx_rt_trip_updates_trip ON rt_trip_updates(trip_id, start_date, captured_at DESC);
CREATE INDEX idx_rt_alerts_route ON rt_alerts(route_id, captured_at DESC);

CORE ENGINE FUNCTIONS
---------------------
get_nearby_stops(lat, lon, radius_m)      -> stops sorted by distance (haversine)
get_delays_for_stop(stop_id, date)        -> upcoming trips at stop with delay seconds
get_trip_delay(trip_id, date)             -> per-stop delay breakdown
find_routes_between(origin_stop, dest)    -> matching trips with next departures
get_active_alerts(route_id)               -> active service disruptions
get_vehicle_position(trip_id)             -> current lat/lon of bus

DELAY CALCULATION LOGIC
-----------------------
Join stop_times (scheduled arrival_time as HH:MM:SS) with rt_trip_updates
(arrival_time as unix timestamp) on trip_id + stop_sequence.
delay_seconds = realtime_unix - scheduled_unix
positive = late, negative = early
threshold: >120s = late, <-60s = early, else on_time
Note: stop_times arrival_time can exceed 24:00:00 for overnight trips.

AI AGENT DESIGN
---------------
Model: OpenAI GPT-4o or Claude 3.5 Sonnet (function calling / tool use)

Tools registered:
  - find_nearby_stops
  - get_delays_for_stop
  - find_routes_between
  - get_active_alerts
  - get_vehicle_position
  - get_trip_delay

System prompt rules:
  - Only covers DRT routes in Durham Region, Ontario
  - Always calls tools for route/stop/timing data, never guesses
  - Formats answers in plain conversational English
  - Includes delay in minutes (not seconds) in responses
  - Suggests alternatives when delay > 3 minutes

API ENDPOINTS
-------------
POST  /chat              <- user message + GPS coords -> AI response
GET   /stops/nearby      <- ?lat=&lon=&radius=        -> nearby stops list
GET   /delays/:stop_id   <- real-time delays at a stop
GET   /alerts            <- ?route_id=                -> active alerts
GET   /vehicle/:trip_id  <- live bus position
GET   /health            <- poller status + DB check

WEB UI LAYOUT (mobile-first, works 375px to 1280px)
----------------------------------------------------
On page load:
  1. If saved route exists in localStorage → auto-call /delays/{stop_id} + /alerts
     → show route status card at top ("Route 110 — on time" / "5 min delay")
  2. Load chat history from localStorage and render previous messages

Page sections (top to bottom):
  1. Route status card  — saved route delay/alert summary; Edit + Remove buttons
                          Hidden if no route saved yet
  2. Chat area          — scrollable conversation bubbles, newest at bottom
                          User messages right-aligned, assistant messages left-aligned
  3. Input bar (sticky) — text field + Send button + location icon
                          On first Send: request GPS via navigator.geolocation
                          If GPS denied: show inline text field "Enter your area (e.g. Whitby, ON)"

Save route flow:
  - After agent returns a find_routes_between result in chat, show inline
    "Save as my regular route" button in the assistant bubble
  - Clicking it calls saveRoute() and shows the status card going forward

ENVIRONMENT VARIABLES (.env)
-----------------------------
OPENAI_API_KEY=                  # Groq key for dev; OpenAI key for prod
OPENAI_BASE_URL=https://api.groq.com/openai/v1  # remove this line when using OpenAI prod
OPENAI_MODEL=llama-3.3-70b-versatile            # or gpt-4o for prod
GTFS_RT_TRIP_UPDATES_URL=
GTFS_RT_VEHICLE_POSITIONS_URL=
GTFS_RT_ALERTS_URL=
SQLITE_DB_PATH=data/transit.db
POLL_INTERVAL_SECONDS=30
RT_RETENTION_HOURS=2

Groq free account: https://console.groq.com — 14,400 requests/day, no credit card needed.
Swap to OpenAI for prod by removing OPENAI_BASE_URL and changing OPENAI_MODEL to gpt-4o.

BUILD SEQUENCE
--------------
Week 1 — Data Foundation
  - Project structure + SQLite schema (schema.sql)
  - GTFS static loader (load_gtfs.py)
  - TripUpdates .pb parser (parser.py)
  - Delay calculation engine (delays.py)
  - Verify delay output against known trips

Week 2 — Live Feeds + Engine
  - GTFS-RT poller for all 3 feeds (poller.py)
  - Nearby stops with haversine (nearby.py)
  - Route finder between two stops (routes.py)
  - Service alert lookup (alerts.py)
  - Old RT data cleanup job (keep last 2 hours only)

Week 3 — AI Agent + Backend API
  - FastAPI app and all endpoints (main.py, endpoints.py)
  - Register engine functions as LLM tools (tools.py)
  - System prompt tuning (prompt.py)
  - Agent orchestration (agent.py)
  - End-to-end test: natural language -> tool calls -> response

Week 4 — Web Frontend + Deployment
  Step 4.1 — Mount frontend/ as FastAPI StaticFiles at "/" in api/main.py
  Step 4.2 — Create frontend/index.html + frontend/style.css
             (route status card, chat area, sticky input bar, mobile-first CSS)
  Step 4.3 — Create frontend/app.js
             (sendMessage, getLocation with GPS+fallback, saveHistory/loadHistory,
              clearChat — all using localStorage key "drt_chat_history")
  Step 4.4 — Add saved route to frontend/app.js
             (saveRoute, checkSavedRoute on load, inline "Save" button after route results,
              Edit/Remove on status card — localStorage key "drt_saved_route")
  Step 4.5 — Create Dockerfile
             (python:3.12-slim, install requirements, COPY frontend/, uvicorn on port 8000)
  Step 4.6 — Create fly.toml
             (port 8000, persistent volume "transit_data" at /app/data, health check /health)
  Step 4.7 — Write test_e2e.py end-to-end smoke test using httpx
  Step 4.8 — Deploy to Fly.io and verify on phone browser

DEPLOYMENT
----------
Platform:   Fly.io (free tier)
Container:  Single Docker container — FastAPI + frontend/ + SQLite + poller background thread
DB:         SQLite file on Fly.io persistent volume (3GB free, survives redeploys)
Volume:     Named "transit_data", mounted at /app/data inside the container
Cost:       $0/month (shared-cpu-1x + 256MB RAM is within free allowance)
Worst case: $3/month if extra RAM needed
Scale path: Migrate SQLite -> PostgreSQL + PostGIS only when user base grows

Deploy command (after fly launch on first setup):
  fly deploy

SUCCESS CRITERIA
----------------
- "Is my bus late?" returns correct answer within 3 seconds
- Nearby stops found within 500m of GPS or manual location input
- At least 2 alternative routes surfaced when primary trip delayed >3 minutes
- Service alerts surfaced in conversation when relevant to user's query
- Chat history survives page refresh on phone browser
- Saved route status card loads automatically on next page open
- App is fully usable on a 375px phone screen in any mobile browser
- Deployed on Fly.io and accessible via public HTTPS URL

KEY TECHNICAL NOTES
-------------------
- GTFS trip_id format in DRT feed: "2663__461029_Timetable_-_2026-04"
- GTFS-RT is ephemeral — only current state, not history
- trip_id in GTFS-RT must match trip_id in GTFS static exactly (use as join key)
- SQLite WAL mode: PRAGMA journal_mode=WAL; — enables concurrent reads during writes
- Haversine formula handles stop proximity without PostGIS
- LLM must never guess stop IDs, route numbers, or times — always call tools
- Groq uses same OpenAI Python SDK — set OPENAI_BASE_URL env var, no code changes needed
- localStorage keys: "drt_chat_history" (array of message objects), "drt_saved_route" (object)
- localStorage is per-device and per-browser — not synced across devices (by design for MVP)
- navigator.geolocation only works on HTTPS in production — Fly.io provides free TLS
- FastAPI StaticFiles must be mounted AFTER all API routes to avoid route conflicts

HOW TO USE THIS PLAN IN A NEW CHAT
-----------------------------------
Attach this file using #file:mvp1-plan.md at the start of a new Copilot Agent Mode chat.
Then paste the relevant prompt from agent-prompts.md for the step you want to build.

Weeks 1–3 are complete. Start new chats at Week 4 steps.
Example: "#file:mvp1-plan.md — Step 4.1: mount frontend/ as StaticFiles in api/main.py"

See agent-prompts.md for the exact copy-paste prompt for each step.

COST SUMMARY
------------
Dev/local:    $0 (Groq free tier + local uvicorn)
Production:   $0–3/month Fly.io + $1–5/month AI at MVP volume = ~$1–8/month total