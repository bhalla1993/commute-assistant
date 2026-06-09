"""
GTFS-RT Background Poller
--------------------------
Runs as a daemon thread (started once at app startup).
Every POLL_INTERVAL_SECONDS it fetches all three GTFS-RT feeds,
parses them, and writes the results to the rt_* SQLite tables.

After each write cycle it also purges rows older than RT_RETENTION_HOURS
to keep the database from growing unboundedly.

Environment variables used (from .env):
  GTFS_RT_TRIP_UPDATES_URL
  GTFS_RT_VEHICLE_POSITIONS_URL
  GTFS_RT_ALERTS_URL
  POLL_INTERVAL_SECONDS   (default 30)
  RT_RETENTION_HOURS      (default 2)
"""
import logging
import os
import threading
import time

import httpx

from db.database import get_connection
from feeds.parser import parse_alerts, parse_trip_updates, parse_vehicle_positions

logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
RETENTION_HOURS = int(os.getenv("RT_RETENTION_HOURS", "2"))

TRIP_UPDATES_URL = os.getenv("GTFS_RT_TRIP_UPDATES_URL", "")
VEHICLE_POSITIONS_URL = os.getenv("GTFS_RT_VEHICLE_POSITIONS_URL", "")
ALERTS_URL = os.getenv("GTFS_RT_ALERTS_URL", "")

# Feature flag: set SERVICE_ALERTS_ENABLED=true in .env once the feed URL is live.
# When false the poller silently skips alerts — no error logs, no wasted HTTP calls.
ALERTS_ENABLED = os.getenv("SERVICE_ALERTS_ENABLED", "false").strip().lower() == "true"

# Shared health status — exposed via /health endpoint
_status: dict = {
    "last_poll_at": None,
    "last_error": None,
    "trip_updates_count": 0,
    "vehicle_positions_count": 0,
    "alerts_count": 0,
}
_status_lock = threading.Lock()


def get_poller_status() -> dict:
    with _status_lock:
        return dict(_status)


# --------------------------------------------------------------------------
# Public entrypoint
# --------------------------------------------------------------------------

def start_poller() -> threading.Thread:
    """
    Spawn and return the background poller daemon thread.
    Call this once from the FastAPI lifespan startup hook.
    """
    thread = threading.Thread(target=_poll_loop, name="rt-poller", daemon=True)
    thread.start()
    logger.info("[poller] Started (interval=%ds, retention=%dh)", POLL_INTERVAL, RETENTION_HOURS)
    return thread


# --------------------------------------------------------------------------
# Poll loop
# --------------------------------------------------------------------------

def _poll_loop() -> None:
    while True:
        try:
            _run_poll_cycle()
        except Exception as exc:  # noqa: BLE001
            logger.exception("[poller] Unexpected error in poll cycle: %s", exc)
            with _status_lock:
                _status["last_error"] = str(exc)
        time.sleep(POLL_INTERVAL)


def _run_poll_cycle() -> None:
    tu_rows = _fetch_and_parse(TRIP_UPDATES_URL, "trip_updates", parse_trip_updates)
    vp_rows = _fetch_and_parse(VEHICLE_POSITIONS_URL, "vehicle_positions", parse_vehicle_positions)

    # Skip alerts entirely when the feature flag is off — avoids repeated
    # HTTP errors while the Durham Region alerts feed URL is unavailable.
    if ALERTS_ENABLED:
        al_rows = _fetch_and_parse(ALERTS_URL, "alerts", parse_alerts)
    else:
        al_rows = []

    conn = get_connection()
    try:
        with conn:
            _write_trip_updates(conn, tu_rows)
            _write_vehicle_positions(conn, vp_rows)
            _write_alerts(conn, al_rows)
            _purge_old_rows(conn)
    finally:
        conn.close()

    with _status_lock:
        _status["last_poll_at"] = time.time()
        _status["last_error"] = None
        _status["trip_updates_count"] = len(tu_rows)
        _status["vehicle_positions_count"] = len(vp_rows)
        _status["alerts_count"] = len(al_rows)

    logger.debug(
        "[poller] Cycle complete — TU:%d VP:%d AL:%d",
        len(tu_rows), len(vp_rows), len(al_rows),
    )


# --------------------------------------------------------------------------
# Fetch helpers
# --------------------------------------------------------------------------

def _fetch_and_parse(url: str, feed_name: str, parser_fn) -> list[dict]:
    if not url:
        logger.warning("[poller] %s URL not configured — skipping", feed_name)
        return []
    try:
        resp = httpx.get(url, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        return parser_fn(resp.content)
    except Exception as exc:  # noqa: BLE001
        logger.error("[poller] Failed to fetch %s: %s", feed_name, exc)
        return []


# --------------------------------------------------------------------------
# Write helpers
# --------------------------------------------------------------------------

def _write_trip_updates(conn, rows: list[dict]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO rt_trip_updates
            (trip_id, route_id, start_date, stop_sequence, stop_id,
             arrival_time, departure_time, schedule_relationship)
        VALUES
            (:trip_id, :route_id, :start_date, :stop_sequence, :stop_id,
             :arrival_time, :departure_time, :schedule_relationship)
        """,
        rows,
    )


def _write_vehicle_positions(conn, rows: list[dict]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO rt_vehicle_positions
            (vehicle_id, trip_id, route_id, latitude, longitude,
             bearing, speed, current_stop_sequence)
        VALUES
            (:vehicle_id, :trip_id, :route_id, :latitude, :longitude,
             :bearing, :speed, :current_stop_sequence)
        """,
        rows,
    )


def _write_alerts(conn, rows: list[dict]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO rt_alerts
            (alert_id, route_id, stop_id, header, description, effect)
        VALUES
            (:alert_id, :route_id, :stop_id, :header, :description, :effect)
        """,
        rows,
    )


# --------------------------------------------------------------------------
# Cleanup
# --------------------------------------------------------------------------

def _purge_old_rows(conn) -> None:
    cutoff = int(time.time()) - RETENTION_HOURS * 3600
    conn.execute("DELETE FROM rt_trip_updates WHERE captured_at < ?", (cutoff,))
    conn.execute("DELETE FROM rt_vehicle_positions WHERE captured_at < ?", (cutoff,))
    conn.execute("DELETE FROM rt_alerts WHERE captured_at < ?", (cutoff,))
