import re
# --- Keyword-based intent filter ---
_TRANSIT_KEYWORDS = [
    "bus", "train", "transit", "stop", "station", "route", "schedule", "timetable", "arrival", "departure",
    "delay", "vehicle", "trip", "fare", "ticket", "pass", "map", "service", "alert", "next", "nearby", "location",
    "gps", "time", "connection", "transfer", "platform", "line", "direction", "destination", "origin", "track",
    "real-time", "live", "update", "frequency", "interval", "crowd", "accessibility", "wheelchair", "elevator",
    "bike", "parking", "lost", "found", "contact", "support"
]
_SMALLTALK_KEYWORDS = [
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings", "how are you", "what's up",
    "sup", "yo", "thank you", "thanks", "bye", "goodbye", "see you", "take care", "welcome", "nice to meet you"
]
_TIME_KEYWORDS = [
    "time", "date", "today", "now", "current time", "what time", "what's the time", "day", "month", "year"
]
_HELP_KEYWORDS = [
    "help", "support", "assist", "guide", "info", "information", "instructions", "how to", "usage"
]

def is_allowed_query(text: str) -> bool:
    text = text.lower()
    for kw in _TRANSIT_KEYWORDS + _SMALLTALK_KEYWORDS + _TIME_KEYWORDS + _HELP_KEYWORDS:
        if re.search(rf"\\b{re.escape(kw)}\\b", text):
            return True
    return False
"""
API Endpoints
--------------
All HTTP routes for the DRT AI Transit Assistant.

Routes:
  POST  /chat              — AI agent chat (main mobile endpoint)
  POST  /chat/history      — save a completed chat session
  GET   /chat/history      — retrieve last 5 chat sessions for the user
  GET   /stops/nearby      — nearby stops by GPS
  GET   /delays/{stop_id}  — real-time delays at a stop
  GET   /alerts            — active service alerts
  GET   /vehicle/{trip_id} — live vehicle position
  GET   /health            — poller + DB health check
"""

import asyncio
import json
import time
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError


from agent.agent import AgentTimeoutError, build_suggestions, chat as agent_chat
from api.auth import get_current_user
from api.quota import FREE_DAILY_LIMIT, MIN_AD_SECONDS, get_daily_query_count, get_user_tier, increment_daily_query
from db.database import get_connection
from engine.alerts import get_active_alerts
from engine.delays import get_delays_for_stop, get_vehicle_position
from engine.nearby import get_nearby_stops
from feeds.poller import get_poller_status
from api.rate_limit import InMemoryRateLimiter
_chat_rate_limiter = InMemoryRateLimiter(max_calls=10, window_sec=60)  # 10 calls/minute per user

logger = logging.getLogger("api.endpoints")


router = APIRouter()

# Test-only endpoint to reset the /chat rate limiter
@router.post("/test/reset-rate-limit", include_in_schema=False)
def reset_chat_rate_limit():
    """Test-only endpoint to reset the /chat rate limiter."""
    _chat_rate_limiter.reset()
    return {"reset": True}


# ============================================================
# POST /chat
# ============================================================

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list)
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)


class ChatResponse(BaseModel):
    reply: str
    history: list[dict]
    suggestions: list[str] = Field(default_factory=list)


CHAT_TIMEOUT_SECONDS = 40


@router.post("/chat", response_model=ChatResponse, summary="Chat with the DRT AI assistant")
async def post_chat(
    body: ChatRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
) -> ChatResponse:

    # Rate limit per user (or per IP if user not available)
    key = f"user:{user['id']}" if user and 'id' in user else f"ip:{request.client.host if request and request.client else 'unknown'}"
    _chat_rate_limiter.check(key)

    # ── Monetization gate (free users only) ──────────────────────────────
    if user and 'id' in user:
        tier = get_user_tier(user['id'])
        if tier == 'free':
            # 1. Enforce daily query limit
            count = get_daily_query_count(user['id'])
            if count >= FREE_DAILY_LIMIT:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "reason": "quota_exceeded",
                        "message": (
                            f"You've used your {FREE_DAILY_LIMIT} free queries for today. "
                            "Upgrade to Premium for unlimited access, or come back tomorrow."
                        ),
                    },
                )
            # 2. Require a verified (used) ad token in the X-Ad-Token header
            ad_token_id = request.headers.get("X-Ad-Token") if request else None
            if not ad_token_id:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "reason": "ad_required",
                        "message": "Please complete the ad to continue.",
                    },
                )
            # Validate: token exists, belongs to this user, is marked used, not expired
            import time as _time
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT user_id, used, expires_at FROM ad_tokens WHERE id = ?",
                    (ad_token_id,),
                ).fetchone()
            finally:
                conn.close()
            if not row or row["user_id"] != user['id'] or not row["used"]:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "reason": "ad_required",
                        "message": "Ad verification failed. Please complete the ad and try again.",
                    },
                )
            # 3. Count this query against today's quota
            increment_daily_query(user['id'])
    # ── End monetization gate ─────────────────────────────────────────────

    # Keyword-based filter for allowed queries
    if not is_allowed_query(body.message):
        return ChatResponse(
            reply="Sorry, I can only help with transit information, simple greetings, or time/date queries.",
            history=body.history,
            suggestions=["Try asking about bus times, stops, or say hello!"]
        )
    # Location is optional — GPS-based skills use it when present; FAQ and
    # other local skills work fine without it.  Skills that need GPS (e.g.
    # nearby stops) return a helpful in-chat message if coords are missing.

    loop = asyncio.get_event_loop()
    try:
        reply, updated_history, suggestions = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: agent_chat(
                    user_message=body.message,
                    conversation_history=body.history,
                    latitude=body.latitude,
                    longitude=body.longitude,
                ),
            ),
            timeout=CHAT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="The request took too long to process. Please try again.",
        )
    except AgentTimeoutError:
        raise HTTPException(
            status_code=504,
            detail="The AI service is taking too long to respond. Please try again.",
        )
    return ChatResponse(reply=reply, history=updated_history, suggestions=suggestions)


# ============================================================
# POST /chat/history  — upsert a chat session
# ============================================================


class MessageModel(BaseModel):
    role: str
    content: str

class SaveChatHistoryRequest(BaseModel):
    messages: list[MessageModel] = Field(..., min_length=1)
    session_id: int | None = Field(None, description="Existing session ID to update in-place")


@router.post("/chat/history", status_code=201, summary="Save or update a chat session")
def post_chat_history(
    body: SaveChatHistoryRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    key = f"user:{user['id']}" if user and 'id' in user else f"ip:{request.client.host if request and request.client else 'unknown'}"
    _chat_rate_limiter.check(key)
    """
    Upsert a chat session for the authenticated user.
    - If session_id is provided and belongs to this user, UPDATE it in-place.
    - Otherwise INSERT a new row.
    Returns {session_id} so the client can track the active session.
    The DB trigger automatically deletes sessions beyond the most-recent 5.
    """
    conn = get_connection()
    try:
        # Validate messages structure
        try:
            messages_json = json.dumps([m.model_dump() for m in body.messages])
        except (TypeError, ValidationError) as e:
            logger.warning(f"Invalid chat history messages: {e}")
            raise HTTPException(status_code=422, detail="Invalid message format.")

        if body.session_id is not None:
            # Verify the session belongs to this user before updating
            row = conn.execute(
                "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
                (body.session_id, user["id"]),
            ).fetchone()
            if row:
                try:
                    conn.execute(
                        "UPDATE chat_sessions SET messages = ?, created_at = strftime('%s','now') WHERE id = ?",
                        (messages_json, body.session_id),
                    )
                    conn.commit()
                except Exception as e:
                    logger.error(f"DB error updating chat session: {e}")
                    raise HTTPException(status_code=500, detail="Failed to update chat session.")
                return {"session_id": body.session_id}
            else:
                logger.warning(f"User {user['id']} tried to update session {body.session_id} not owned by them.")

        # INSERT new session (trigger enforces 5-session limit)
        try:
            cursor = conn.execute(
                "INSERT INTO chat_sessions (user_id, messages) VALUES (?, ?)",
                (user["id"], messages_json),
            )
            conn.commit()
            return {"session_id": cursor.lastrowid}
        except Exception as e:
            logger.error(f"DB error inserting chat session: {e}")
            raise HTTPException(status_code=500, detail="Failed to save chat session.")
    finally:
        conn.close()


# ============================================================
# GET /chat/history  — fetch last 5 sessions
# ============================================================

@router.get("/chat/history", summary="Get last 5 chat sessions")
def get_chat_history(
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    key = f"user:{user['id']}" if user and 'id' in user else f"ip:{request.client.host if request and request.client else 'unknown'}"
    _chat_rate_limiter.check(key)
    """Return the last 5 chat sessions for the authenticated user, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, messages, created_at
            FROM chat_sessions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()

    sessions = []
    for row in rows:
        try:
            messages = json.loads(row["messages"])
        except (json.JSONDecodeError, TypeError):
            messages = []
        sessions.append({
            "id": row["id"],
            "messages": messages,
            "created_at": row["created_at"],
        })
    return {"sessions": sessions}


# ============================================================
# GET /stops/nearby
# ============================================================

@router.get("/stops/nearby", summary="Find nearby DRT stops")
def get_stops_nearby(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude"),
    radius: float = Query(500.0, ge=50.0, le=5000.0, description="Search radius in metres"),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    key = f"user:{user['id']}" if user and 'id' in user else f"ip:{request.client.host if request and request.client else 'unknown'}"
    _chat_rate_limiter.check(key)
    try:
        stops = get_nearby_stops(lat=lat, lon=lon, radius_m=radius)
        return {"stops": stops, "count": len(stops)}
    except Exception as e:
        logger.error(f"Failed to get nearby stops: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch nearby stops.")


# ============================================================
# GET /delays/{stop_id}
# ============================================================

@router.get("/delays/{stop_id}", summary="Real-time delays at a stop")
def get_delays(
    stop_id: str,
    date: str = Query(
        default=None,
        description="Service date YYYYMMDD. Defaults to today (UTC).",
        pattern=r"^\d{8}$",
    ),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    key = f"user:{user['id']}" if user and 'id' in user else f"ip:{request.client.host if request and request.client else 'unknown'}"
    _chat_rate_limiter.check(key)
    if not stop_id or not isinstance(stop_id, str) or len(stop_id) > 32:
        logger.warning(f"Invalid stop_id: {stop_id}")
        raise HTTPException(status_code=422, detail="Invalid stop_id format.")
    if date is None:
        date = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    try:
        delays = get_delays_for_stop(stop_id=stop_id, date=date)
    except Exception as e:
        logger.error(f"Failed to get delays for stop {stop_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch delays.")
    if not delays:
        logger.info(f"No trips found for stop {stop_id} on {date}")
        raise HTTPException(status_code=404, detail=f"No trips found for stop '{stop_id}' on {date}")
    return {"stop_id": stop_id, "date": date, "trips": delays}


# ============================================================
# GET /alerts
# ============================================================

@router.get("/alerts", summary="Active service alerts")
def get_alerts(
    route_id: str | None = Query(None, description="Filter by GTFS route_id"),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    key = f"user:{user['id']}" if user and 'id' in user else f"ip:{request.client.host if request and request.client else 'unknown'}"
    _chat_rate_limiter.check(key)
    try:
        alerts, available = get_active_alerts(route_id=route_id)
    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch alerts.")
    if not available:
        logger.warning("Service alerts unavailable for current provider.")
    return {
        "alerts": alerts,
        "count": len(alerts),
        "available": available,
        "unavailable_reason": (
            None if available
            else "Service alerts are not yet available for Durham Region Transit. "
                 "The data provider has not published a feed URL."
        ),
    }


# ============================================================
# GET /vehicle/{trip_id}
# ============================================================

@router.get("/vehicle/{trip_id}", summary="Live vehicle position for a trip")
def get_vehicle(
    trip_id: str,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    key = f"user:{user['id']}" if user and 'id' in user else f"ip:{request.client.host if request and request.client else 'unknown'}"
    _chat_rate_limiter.check(key)
    if not trip_id or not isinstance(trip_id, str) or len(trip_id) > 32:
        logger.warning(f"Invalid trip_id: {trip_id}")
        raise HTTPException(status_code=422, detail="Invalid trip_id format.")
    try:
        position = get_vehicle_position(trip_id=trip_id)
    except Exception as e:
        logger.error(f"Failed to get vehicle position for trip {trip_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch vehicle position.")
    if position is None:
        logger.info(f"No position data found for trip {trip_id}")
        raise HTTPException(
            status_code=404,
            detail=f"No position data found for trip '{trip_id}'",
        )
    return position


# ============================================================
# GET /health
# ============================================================

@router.get("/health", summary="Service health check")

def health():
    status = get_poller_status()
    now = time.time()
    last_poll = status.get("last_poll_at")
    poller_ok = last_poll is not None and (now - last_poll) < 120  # within 2 poll cycles

    # Add DB health check
    db_ok = True
    db_error = None
    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
    except Exception as e:
        db_ok = False
        db_error = str(e)
        logger.error(f"DB health check failed: {e}")

    status_str = "ok" if poller_ok and db_ok else "degraded"
    if status_str == "degraded":
        logger.warning(f"Health degraded: poller_ok={poller_ok}, db_ok={db_ok}")

    return {
        "status": status_str,
        "poller": {
            "ok": poller_ok,
            "last_poll_at": last_poll,
            "last_error": status.get("last_error"),
            "trip_updates_count": status.get("trip_updates_count", 0),
            "vehicle_positions_count": status.get("vehicle_positions_count", 0),
            "alerts_count": status.get("alerts_count", 0),
        },
        "db": {
            "ok": db_ok,
            "error": db_error,
        },
    }


# ============================================================
# GET /ai-status  — lightweight AI provider availability check
# ============================================================

@router.get("/ai-status", summary="Check whether an AI provider is configured")
def get_ai_status():
    """
    Returns quickly (no LLM call) — just checks whether at least one provider
    has a valid API key in the environment.  Used by the frontend to decide
    whether to enable free-text chat.
    """
    from agent.providers import _load_providers  # noqa: PLC0415
    providers = _load_providers()
    available = len(providers) > 0
    return {
        "available": available,
        "provider": providers[0].name if providers else None,
    }


# ============================================================
# GET /suggestions  — context-aware quick-action chip list
# ============================================================

@router.get("/suggestions", summary="Suggestions the app can always answer locally")
def get_suggestions(
    lat: float | None = Query(None, ge=-90.0, le=90.0, description="User latitude"),
    lon: float | None = Query(None, ge=-180.0, le=180.0, description="User longitude"),
    user: dict = Depends(get_current_user),
):
    """
    Returns suggestions tailored to available data (GTFS loaded, alerts live,
    GPS provided).  These are questions the local skills can answer without
    calling the LLM, so they always work even when AI is unavailable.
    """
    context = {"latitude": lat, "longitude": lon}
    return {"suggestions": build_suggestions(context)}
