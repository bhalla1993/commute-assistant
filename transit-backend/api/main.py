"""
FastAPI Application Entry Point
--------------------------------
Starts the app, initialises the database, and launches the RT poller
as a background daemon thread via the lifespan context manager.

Run locally with:
    uvicorn api.main:app --reload --port 8000
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

import uuid
from fastapi import Request
from fastapi.staticfiles import StaticFiles

load_dotenv()  # load .env before any module reads os.environ

from db.database import init_db          # noqa: E402 (must follow load_dotenv)
from feeds.poller import start_poller    # noqa: E402
from api.config import FeatureFlags      # noqa: E402
from api.endpoints import router         # noqa: E402
from api.auth_router import router as auth_router  # noqa: E402
from api.ads_router import router as ads_router            # noqa: E402
from api.subscription_router import router as sub_router   # noqa: E402
from api.config_router import router as config_router      # noqa: E402


# Set log level from env or default to DEBUG for local, INFO otherwise
import os
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if os.getenv("ENV") == "local" else "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("api")


# Middleware for request/response logging
from starlette.middleware.base import BaseHTTPMiddleware

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        logger.info(f"[{request_id}] {request.method} {request.url}")
        if LOG_LEVEL == "DEBUG":
            try:
                body = await request.body()
                logger.debug(f"[{request_id}] Request body: {body.decode(errors='ignore')}")
            except Exception:
                logger.debug(f"[{request_id}] Could not read request body.")
        response = await call_next(request)
        logger.info(f"[{request_id}] Response status: {response.status_code}")
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("[startup] Initialising database…")
    init_db()

    logger.info("[startup] Logging feature flags…")
    FeatureFlags.log_startup()
    if FeatureFlags.validate_config():
        logger.info("[startup] Feature flag configuration valid")
    else:
        logger.error("[startup] Feature flag configuration has errors!")

    logger.info("[startup] Starting GTFS-RT poller…")
    start_poller()

    yield  # app is running

    # ── Shutdown (nothing to tear down for now) ───────────────────────────────
    logger.info("[shutdown] Goodbye.")



app = FastAPI(
    title="DRT AI Transit Assistant",
    description="Natural language transit assistance for Durham Region Transit.",
    version="0.1.0",
    lifespan=lifespan,
)

# Add logging middleware
app.add_middleware(LoggingMiddleware)

app.include_router(config_router)
app.include_router(auth_router)
app.include_router(ads_router)
app.include_router(sub_router)
app.include_router(router)

# Mount the frontend AFTER all API routes so API paths take priority.
_frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
