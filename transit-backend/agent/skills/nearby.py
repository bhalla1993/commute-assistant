"""
Nearby Skill
------------
Answers GPS-based questions directly from the local database, without
calling the LLM.  Handles:

  - "Show stops near me" / "Find stops near me" / "Nearest stops"
  - "What buses are near me?" / "When is my next bus?"
  - "Buses near me" / "What routes serve my area?"

Requires GPS coordinates in context (latitude/longitude).
Returns None when:
  - The message doesn't match the supported patterns.
  - No GPS is provided (the user typed a manual location — let the LLM handle it).
"""
import logging
from datetime import datetime, timezone

from agent.utils import normalize
from db.database import get_connection
from engine.nearby import get_nearby_stops

logger = logging.getLogger(__name__)

# ── Trigger sets ──────────────────────────────────────────────────────────

_STOP_TRIGGERS = {
    "stops near", "show stops", "find stops", "nearest stop",
    "closest stop", "nearby stop", "stop near", "stops around",
    "what stops",
}

_BUS_TRIGGERS = {
    "buses near", "bus near", "next bus", "when is my next",
    "what buses", "buses around", "routes near", "what routes",
    "bus near me", "buses near me",
}

# Calendar day-of-week SQL fragment (SQLite strftime %w: 0=Sunday)
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


def _now_secs() -> int:
    now = datetime.now(tz=timezone.utc)
    return now.hour * 3600 + now.minute * 60 + now.second


def _gtfs_secs(t: str) -> int:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def _get_next_departures(nearby_stop_ids: list[str], date: str) -> list[dict]:
    """
    Return up to 8 upcoming departures across all *nearby_stop_ids*.
    Sorted by scheduled departure time.
    """
    if not nearby_stop_ids:
        return []

    now_secs = _now_secs()
    placeholders = ",".join("?" * len(nearby_stop_ids))

    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT
            r.route_short_name,
            t.trip_headsign,
            st.departure_time,
            s.stop_name,
            st.stop_id,
            (
                SELECT rtu.arrival_time
                FROM   rt_trip_updates rtu
                WHERE  rtu.trip_id       = t.trip_id
                  AND  rtu.start_date    = ?
                  AND  rtu.stop_sequence = st.stop_sequence
                ORDER BY rtu.captured_at DESC
                LIMIT 1
            ) AS rt_arrival,
            (
                SELECT rtu.schedule_relationship
                FROM   rt_trip_updates rtu
                WHERE  rtu.trip_id       = t.trip_id
                  AND  rtu.start_date    = ?
                  AND  rtu.stop_sequence = st.stop_sequence
                ORDER BY rtu.captured_at DESC
                LIMIT 1
            ) AS schedule_relationship
        FROM trips t
        JOIN routes r     ON r.route_id  = t.route_id
        JOIN stop_times st ON st.trip_id  = t.trip_id
        JOIN stops s       ON s.stop_id   = st.stop_id
        WHERE st.stop_id IN ({placeholders})
          AND ({_DOW_SQL})
        ORDER BY st.departure_time
        LIMIT 50
        """,
        [date, date] + nearby_stop_ids + [date],
    ).fetchall()
    conn.close()

    upcoming: list[dict] = []
    seen: set[str] = set()  # deduplicate route+headsign+departure
    for row in rows:
        try:
            dep_secs = _gtfs_secs(row["departure_time"])
        except (ValueError, AttributeError):
            continue
        if dep_secs < now_secs:
            continue
        key = f"{row['route_short_name']}|{row['trip_headsign']}|{row['departure_time']}"
        if key in seen:
            continue
        seen.add(key)

        # Compute delay status
        status = "no_data"
        delay_s = None
        if row["schedule_relationship"] == "CANCELED":
            status = "canceled"
        elif row["rt_arrival"] is not None:
            try:
                # Build the scheduled unix timestamp for comparison
                date_dt = datetime.strptime(date, "%Y%m%d").replace(tzinfo=timezone.utc)
                sched_unix = date_dt.timestamp() + dep_secs
                delay_s = int(row["rt_arrival"]) - int(sched_unix)
                if delay_s > 120:
                    status = "late"
                elif delay_s < -60:
                    status = "early"
                else:
                    status = "on_time"
            except Exception:
                pass

        upcoming.append({
            "route_short_name": row["route_short_name"],
            "trip_headsign": row["trip_headsign"],
            "departure_time": row["departure_time"],
            "stop_name": row["stop_name"],
            "status": status,
            "delay_seconds": delay_s,
        })
        if len(upcoming) >= 8:
            break

    return upcoming


def answer(message: str, context: dict) -> str | None:
    """
    Return a plain-text answer for GPS-based queries; otherwise None.
    """
    norm = normalize(message)
    lat = context.get("latitude")
    lon = context.get("longitude")

    is_stop_query = any(t in norm for t in _STOP_TRIGGERS)
    is_bus_query  = any(t in norm for t in _BUS_TRIGGERS)

    if not (is_stop_query or is_bus_query):
        return None

    # No GPS — can't answer without coordinates
    if lat is None or lon is None:
        return (
            "I don't have your GPS location yet.\n\n"
            "To find nearby stops and buses, either:\n"
            "- Allow location access when your browser asks, or\n"
            "- Type your street or area into the location field below the chat box."
        )

    lat, lon = float(lat), float(lon)

    # Fetch nearby stops (500 m; widen to 1 km if nothing found)
    try:
        stops = get_nearby_stops(lat=lat, lon=lon, radius_m=500.0)
        if not stops:
            stops = get_nearby_stops(lat=lat, lon=lon, radius_m=1000.0)
            radius_label = "1 km"
        else:
            radius_label = "500 m"
    except Exception:
        logger.exception("[nearby_skill] Failed to query nearby stops")
        return None

    if not stops:
        return (
            "No DRT stops found within 1 km of your current location. "
            "You may be outside the Durham Region Transit service area, "
            "or the stop database hasn't been loaded yet."
        )

    # ── Stops-only query ──────────────────────────────────────────────────
    if is_stop_query and not is_bus_query:
        lines = [f"DRT stops near you (within {radius_label}):"]
        for s in stops[:8]:
            dist = int(round(s["distance_m"]))
            lines.append(f"  • Stop {s['stop_id']} — {s['stop_name']} ({dist} m away)")
        if len(stops) > 8:
            lines.append(f"  … and {len(stops) - 8} more stops nearby.")
        lines.append("\nTap a stop number to check arrivals, or ask \"next bus at stop [ID]\".")
        return "\n".join(lines)

    # ── Bus / next departure query ────────────────────────────────────────
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    nearby_stop_ids = [s["stop_id"] for s in stops[:12]]

    try:
        departures = _get_next_departures(nearby_stop_ids, today)
    except Exception:
        logger.exception("[nearby_skill] Failed to query departures")
        departures = []

    if not departures:
        # Fall back to showing stops so the user still gets useful info
        lines = [
            f"No upcoming departures found at the {len(stops)} DRT stop(s) within {radius_label} of you.",
            "Nearby stops:",
        ]
        for s in stops[:5]:
            dist = int(round(s["distance_m"]))
            lines.append(f"  • Stop {s['stop_id']} — {s['stop_name']} ({dist} m)")
        lines.append("\nThis may be because service has ended for the day, or the schedule data isn't loaded yet.")
        return "\n".join(lines)

    lines = [f"Next buses near you (within {radius_label}):"]
    for dep in departures:
        route    = dep["route_short_name"] or "?"
        headsign = dep["trip_headsign"] or ""
        dep_time = dep["departure_time"][:5]   # HH:MM
        stop     = dep["stop_name"] or ""
        status   = dep["status"]
        delay_s  = dep["delay_seconds"]

        if status == "canceled":
            timing = " — CANCELLED"
        elif delay_s is not None and abs(delay_s) >= 60:
            mins = round(delay_s / 60)
            timing = f" — {abs(mins)} min {'late' if mins > 0 else 'early'}"
        elif status == "on_time":
            timing = " — on time"
        else:
            timing = ""

        lines.append(f"  Route {route} → {headsign} at {dep_time} from {stop}{timing}")

    lines.append("\nFor live tracking visit durhamregiontransit.com.")
    return "\n".join(lines)
