"""
GTFS Skill
-----------
Answers questions about upcoming departures and route delays directly
from the local GTFS database, without calling the LLM.

Handles patterns like:
  - "When is the next bus at stop 1234?"
  - "Is route 915 delayed?"
  - "Next departures at stop 42"
  - "When is the next bus to Oshawa GO?"
  - "Next bus towards Whitby"
"""
import logging
import re
from datetime import datetime, timezone

from agent.utils import extract_route_ids, extract_stop_ids, normalize
from db.database import get_connection
from engine.delays import get_delays_for_stop
from engine.nearby import get_nearby_stops

logger = logging.getLogger(__name__)

_DEPARTURE_TRIGGERS = {
    "next bus", "next departure", "next trip",
    "when is the", "when does", "what time",
    "departures", "schedule at",
}

_DELAY_TRIGGERS = {
    "delay", "late", "early", "on time", "ontime", "delayed",
}

# Extracts destination keyword from "to X", "towards X", "going to X", etc.
_DEST_RE = re.compile(
    r"\b(?:to|towards?|going\s+to|heading\s+to|bound\s+for|direction\s+of?)\s+"
    r"([a-z][a-z0-9 ]{1,40})",
    re.IGNORECASE,
)

# Trailing noise words that should be stripped from extracted destination
_DEST_NOISE_RE = re.compile(
    r"\b(?:bus|please|today|now|soon|route|transit|stop)\s*$",
    re.IGNORECASE,
)

# Reusable day-of-week SQL fragment (SQLite strftime %w: 0=Sunday)
_DOW_SQL = """
    EXISTS (
        SELECT 1 FROM calendar c
        WHERE  c.service_id = t.service_id
          AND  :date BETWEEN c.start_date AND c.end_date
          AND  (
                (CAST(strftime('%w', substr(:date,1,4)||'-'||substr(:date,5,2)||'-'||substr(:date,7,2)) AS INTEGER) = 0 AND c.sunday    = 1)
             OR (CAST(strftime('%w', substr(:date,1,4)||'-'||substr(:date,5,2)||'-'||substr(:date,7,2)) AS INTEGER) = 1 AND c.monday    = 1)
             OR (CAST(strftime('%w', substr(:date,1,4)||'-'||substr(:date,5,2)||'-'||substr(:date,7,2)) AS INTEGER) = 2 AND c.tuesday   = 1)
             OR (CAST(strftime('%w', substr(:date,1,4)||'-'||substr(:date,5,2)||'-'||substr(:date,7,2)) AS INTEGER) = 3 AND c.wednesday = 1)
             OR (CAST(strftime('%w', substr(:date,1,4)||'-'||substr(:date,5,2)||'-'||substr(:date,7,2)) AS INTEGER) = 4 AND c.thursday  = 1)
             OR (CAST(strftime('%w', substr(:date,1,4)||'-'||substr(:date,5,2)||'-'||substr(:date,7,2)) AS INTEGER) = 5 AND c.friday    = 1)
             OR (CAST(strftime('%w', substr(:date,1,4)||'-'||substr(:date,5,2)||'-'||substr(:date,7,2)) AS INTEGER) = 6 AND c.saturday  = 1)
          )
          AND NOT EXISTS (
              SELECT 1 FROM calendar_dates cd2
              WHERE  cd2.service_id = t.service_id
                AND  cd2.date = :date
                AND  cd2.exception_type = 2
          )
    )
    OR EXISTS (
        SELECT 1 FROM calendar_dates cd
        WHERE  cd.service_id    = t.service_id
          AND  cd.date          = :date
          AND  cd.exception_type = 1
    )
"""


def _gtfs_secs(t: str) -> int:
    """Convert a GTFS HH:MM:SS time string (may exceed 24:00:00) to seconds since midnight."""
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def _now_secs() -> int:
    """Current time as seconds since midnight (local clock approximated via UTC)."""
    now = datetime.now(tz=timezone.utc)
    return now.hour * 3600 + now.minute * 60 + now.second


def _extract_destination(text: str) -> str | None:
    """
    Extract a destination keyword from phrases like 'next bus to Oshawa GO'.
    Returns None if no destination phrase is found.
    """
    m = _DEST_RE.search(text)
    if not m:
        return None
    dest = _DEST_NOISE_RE.sub("", m.group(1)).strip()
    return dest if len(dest) >= 3 else None


def _trips_to_destination(
    destination: str,
    date: str,
    nearby_stop_ids: list[str],
) -> list[dict]:
    """
    Return up to 5 upcoming departures for trips whose headsign contains
    *destination*, optionally filtered to *nearby_stop_ids* (user's nearby stops).
    Falls back to system-wide results when no GPS stops are provided.
    """
    conn = get_connection()
    now_secs = _now_secs()
    dest_pattern = f"%{destination}%"

    select_cols = """
        SELECT
            r.route_short_name,
            t.trip_headsign,
            st.departure_time,
            s.stop_name,
            st.stop_id
        FROM trips t
        JOIN routes r  ON r.route_id  = t.route_id
        JOIN stop_times st ON st.trip_id = t.trip_id
        JOIN stops s   ON s.stop_id   = st.stop_id
    """

    if nearby_stop_ids:
        placeholders = ",".join("?" * len(nearby_stop_ids))
        rows = conn.execute(
            f"""
            {select_cols}
            WHERE t.trip_headsign LIKE ?
              AND st.stop_id IN ({placeholders})
              AND ({_DOW_SQL})
            ORDER BY st.departure_time
            LIMIT 20
            """,
            [dest_pattern] + nearby_stop_ids + [date, date],
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            {select_cols}
            WHERE t.trip_headsign LIKE :dest
              AND ({_DOW_SQL})
            ORDER BY st.departure_time
            LIMIT 20
            """,
            {"dest": dest_pattern, "date": date},
        ).fetchall()

    conn.close()

    # Filter to upcoming times only
    upcoming: list[dict] = []
    for row in rows:
        try:
            dep_secs = _gtfs_secs(row["departure_time"])
        except (ValueError, AttributeError):
            continue
        if dep_secs >= now_secs:
            upcoming.append(dict(row))
        if len(upcoming) >= 5:
            break
    return upcoming


def answer(message: str, context: dict) -> str | None:
    """
    Return a plain-text answer about departures/delays if the message
    matches a supported pattern; otherwise None.

    Supported patterns:
      1. Numeric stop ID: "next bus at stop 1234", "is stop 42 delayed"
      2. Destination name: "next bus to Oshawa GO", "when does bus go to Whitby"
      3. Route number: "any delays on route 110", "is route 215 delayed"
    """
    norm = normalize(message)
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    date = context.get("date", today)

    stop_ids = extract_stop_ids(message)
    route_ids = extract_route_ids(message)
    is_departure_query = any(t in norm for t in _DEPARTURE_TRIGGERS)
    is_delay_query = any(t in norm for t in _DELAY_TRIGGERS)

    # ------------------------------------------------------------------ #
    # Path 1: Numeric stop-ID query (original behaviour)                  #
    # ------------------------------------------------------------------ #
    if stop_ids and (is_departure_query or is_delay_query):
        stop_id = stop_ids[0]
        try:
            results = get_delays_for_stop(stop_id=stop_id, date=date)
        except Exception:
            logger.exception("[gtfs_skill] Failed to query stop %s", stop_id)
            return None

        if not results:
            return None

        lines = [f"Upcoming trips at stop {stop_id}:"]
        for row in results[:3]:
            route = row.get("route_short_name", row.get("route_id", "?"))
            headsign = row.get("trip_headsign", "")
            scheduled = row.get("scheduled_arrival", "")
            delay_s = row.get("delay_seconds")
            status = row.get("status", "no_data")

            if status == "canceled":
                lines.append(f"  Route {route} {headsign} at {scheduled} — CANCELLED")
            elif delay_s is not None and abs(delay_s) >= 60:
                mins = round(delay_s / 60)
                direction = "late" if mins > 0 else "early"
                lines.append(
                    f"  Route {route} {headsign} at {scheduled} — about {abs(mins)} min {direction}"
                )
            else:
                lines.append(f"  Route {route} {headsign} at {scheduled} — on time")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Path 3: Route-number delay query (e.g. "any delays on route 110")   #
    # ------------------------------------------------------------------ #
    is_delay_query = any(t in norm for t in _DELAY_TRIGGERS)
    if route_ids and is_delay_query and not stop_ids:
        route_short = route_ids[0]
        try:
            conn = get_connection()
            rows = conn.execute(
                """
                SELECT DISTINCT
                    rtu.trip_id,
                    r.route_short_name,
                    t.trip_headsign,
                    rtu.stop_sequence,
                    rtu.arrival_time      AS rt_arrival,
                    rtu.schedule_relationship
                FROM rt_trip_updates rtu
                JOIN trips  t ON t.trip_id  = rtu.trip_id
                JOIN routes r ON r.route_id = t.route_id
                WHERE r.route_short_name = ?
                  AND rtu.start_date = ?
                ORDER BY rtu.captured_at DESC
                LIMIT 20
                """,
                [route_short, date],
            ).fetchall()
            conn.close()
        except Exception:
            logger.exception("[gtfs_skill] Route delay query failed for route %s", route_short)
            return None

        if not rows:
            return (
                f"No real-time data found for Route {route_short} today. "
                "Either there's no live feed active or the route isn't running right now. "
                "Check durhamregiontransit.com for scheduled times."
            )

        canceled = [r for r in rows if r["schedule_relationship"] == "CANCELED"]
        delayed  = []
        for r in rows:
            if r["schedule_relationship"] == "CANCELED":
                continue
            if r["rt_arrival"] is not None:
                try:
                    # We don't have the scheduled time here, so just flag as having RT data
                    delayed.append(r)
                except Exception:
                    pass

        lines = [f"Real-time status for Route {route_short}:"]
        if canceled:
            trips_seen: set[str] = set()
            for r in canceled:
                if r["trip_id"] not in trips_seen:
                    trips_seen.add(r["trip_id"])
                    lines.append(f"  • Trip {r['trip_id']} ({r['trip_headsign']}) — CANCELLED")
        if delayed:
            lines.append(f"  • {len(delayed)} trip update(s) with live tracking active.")
            lines.append("  Tap a stop below to see exact delays:")
            # Show up to 3 distinct trip headsigns
            seen_headsigns: set[str] = set()
            for r in delayed:
                hs = r["trip_headsign"] or r["trip_id"]
                if hs not in seen_headsigns:
                    seen_headsigns.add(hs)
                    lines.append(f"    Route {r['route_short_name']} → {hs}")
                if len(seen_headsigns) >= 3:
                    break
        if not canceled and not delayed:
            lines.append(f"  No delays or cancellations reported for Route {route_short} right now.")

        lines.append("\nFor live tracking visit durhamregiontransit.com.")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Path 2: Destination-name query (e.g. "next bus to Oshawa GO")       #
    # ------------------------------------------------------------------ #
    if not is_departure_query:
        return None

    destination = _extract_destination(message)
    if not destination:
        return None

    # Try nearby stops first (GPS from context), then system-wide fallback
    nearby_stop_ids: list[str] = []
    lat = context.get("latitude")
    lon = context.get("longitude")
    if lat is not None and lon is not None:
        try:
            nearby = get_nearby_stops(lat=float(lat), lon=float(lon), radius_m=750.0)
            nearby_stop_ids = [s["stop_id"] for s in nearby]
        except Exception:
            logger.exception("[gtfs_skill] Could not fetch nearby stops")

    try:
        trips = _trips_to_destination(destination, date, nearby_stop_ids)
    except Exception:
        logger.exception("[gtfs_skill] Failed destination query for '%s'", destination)
        return None

    # If GPS-based search found nothing, widen to system-wide
    if not trips and nearby_stop_ids:
        try:
            trips = _trips_to_destination(destination, date, [])
        except Exception:
            logger.exception("[gtfs_skill] Fallback destination query failed for '%s'", destination)
            return None

    dest_title = destination.title()

    if not trips:
        return None

    location_hint = "near your location" if nearby_stop_ids else "on the network"
    lines = [f"Next buses to {dest_title} ({location_hint}):"]
    for trip in trips:
        route = trip.get("route_short_name", "?")
        dep = trip.get("departure_time", "")[:5]   # HH:MM
        stop_name = trip.get("stop_name", "unknown stop")
        lines.append(f"  Route {route} — {dep} from {stop_name}")

    lines.append("\nFor real-time tracking visit durhamregiontransit.com.")
    return "\n".join(lines)
