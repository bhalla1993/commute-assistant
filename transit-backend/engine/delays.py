"""
Delay Calculation Engine
------------------------
Joins GTFS static schedule times against GTFS-RT trip updates to compute
how many seconds early or late a trip is at each stop.

Key design notes:
  - stop_times.arrival_time is stored as HH:MM:SS and may exceed 24:00:00 for
    overnight trips (e.g. "25:30:00" = 1:30 AM the following day).
  - rt_trip_updates.arrival_time is stored as a unix timestamp (integer).
  - delay_seconds = realtime_unix - scheduled_unix
      > 0  → late
      < 0  → early
  - Thresholds: >120s = late, <-60s = early, else on_time
"""
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from db.database import get_connection

# --------------------------------------------------------------------------
# Public types
# --------------------------------------------------------------------------

class StopDelay(TypedDict):
    trip_id: str
    route_id: str
    route_short_name: str
    trip_headsign: str
    stop_sequence: int
    stop_id: str
    scheduled_arrival: str       # HH:MM:SS original value
    delay_seconds: int | None    # None if no RT data
    status: str                  # "on_time" | "late" | "early" | "no_data" | "canceled"

# --------------------------------------------------------------------------
# Thresholds
# --------------------------------------------------------------------------
LATE_THRESHOLD_S = 120    # > 2 min → late
EARLY_THRESHOLD_S = -60   # < -1 min → early

# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def get_delays_for_stop(stop_id: str, date: str) -> list[StopDelay]:
    """
    Return upcoming trips at *stop_id* for *date* (YYYYMMDD) with delay info.

    Only trips active on *date* (per calendar_dates) are returned.
    Results are sorted by scheduled departure time.
    """
    conn = get_connection()
    with conn:
        rows = conn.execute(
            """
            SELECT
                t.trip_id,
                t.route_id,
                r.route_short_name,
                t.trip_headsign,
                st.stop_sequence,
                st.stop_id,
                st.departure_time AS scheduled_departure,
                st.arrival_time   AS scheduled_arrival,
                -- Latest RT update for this trip+stop
                (
                    SELECT rtu.arrival_time
                    FROM   rt_trip_updates rtu
                    WHERE  rtu.trip_id      = t.trip_id
                      AND  rtu.start_date   = :date
                      AND  rtu.stop_sequence = st.stop_sequence
                    ORDER BY rtu.captured_at DESC
                    LIMIT 1
                ) AS rt_arrival,
                (
                    SELECT rtu.schedule_relationship
                    FROM   rt_trip_updates rtu
                    WHERE  rtu.trip_id      = t.trip_id
                      AND  rtu.start_date   = :date
                      AND  rtu.stop_sequence = st.stop_sequence
                    ORDER BY rtu.captured_at DESC
                    LIMIT 1
                ) AS schedule_relationship
            FROM   stop_times st
            JOIN   trips  t ON t.trip_id  = st.trip_id
            JOIN   routes r ON r.route_id = t.route_id
            WHERE  st.stop_id = :stop_id
              AND  (
                -- Regular recurring service active on this date
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
                    -- But not if there is a removal exception for this date
                    AND NOT EXISTS (
                        SELECT 1 FROM calendar_dates cd2
                        WHERE  cd2.service_id = t.service_id
                          AND  cd2.date = :date
                          AND  cd2.exception_type = 2
                    )
                )
                -- OR an explicit addition exception
                OR EXISTS (
                    SELECT 1 FROM calendar_dates cd
                    WHERE  cd.service_id    = t.service_id
                      AND  cd.date          = :date
                      AND  cd.exception_type = 1
                )
              )
            ORDER BY st.departure_time
            """,
            {"stop_id": stop_id, "date": date},
        ).fetchall()
    conn.close()

    results: list[StopDelay] = []
    for row in rows:
        delay_s, status = _compute_delay(
            date, row["scheduled_arrival"], row["rt_arrival"], row["schedule_relationship"]
        )
        results.append(
            StopDelay(
                trip_id=row["trip_id"],
                route_id=row["route_id"],
                route_short_name=row["route_short_name"] or row["route_id"],
                trip_headsign=row["trip_headsign"] or "",
                stop_sequence=row["stop_sequence"],
                stop_id=row["stop_id"],
                scheduled_arrival=row["scheduled_arrival"],
                delay_seconds=delay_s,
                status=status,
            )
        )
    return results


def get_trip_delay(trip_id: str, date: str) -> list[StopDelay]:
    """
    Return per-stop delay breakdown for a single trip on *date*.
    """
    conn = get_connection()
    with conn:
        rows = conn.execute(
            """
            SELECT
                t.trip_id,
                t.route_id,
                r.route_short_name,
                t.trip_headsign,
                st.stop_sequence,
                st.stop_id,
                st.arrival_time AS scheduled_arrival,
                (
                    SELECT rtu.arrival_time
                    FROM   rt_trip_updates rtu
                    WHERE  rtu.trip_id       = t.trip_id
                      AND  rtu.start_date    = :date
                      AND  rtu.stop_sequence = st.stop_sequence
                    ORDER BY rtu.captured_at DESC
                    LIMIT 1
                ) AS rt_arrival,
                (
                    SELECT rtu.schedule_relationship
                    FROM   rt_trip_updates rtu
                    WHERE  rtu.trip_id       = t.trip_id
                      AND  rtu.start_date    = :date
                      AND  rtu.stop_sequence = st.stop_sequence
                    ORDER BY rtu.captured_at DESC
                    LIMIT 1
                ) AS schedule_relationship
            FROM   stop_times st
            JOIN   trips  t ON t.trip_id  = st.trip_id
            JOIN   routes r ON r.route_id = t.route_id
            WHERE  t.trip_id = :trip_id
            ORDER BY st.stop_sequence
            """,
            {"trip_id": trip_id, "date": date},
        ).fetchall()
    conn.close()

    results: list[StopDelay] = []
    for row in rows:
        delay_s, status = _compute_delay(
            date, row["scheduled_arrival"], row["rt_arrival"], row["schedule_relationship"]
        )
        results.append(
            StopDelay(
                trip_id=row["trip_id"],
                route_id=row["route_id"],
                route_short_name=row["route_short_name"] or row["route_id"],
                trip_headsign=row["trip_headsign"] or "",
                stop_sequence=row["stop_sequence"],
                stop_id=row["stop_id"],
                scheduled_arrival=row["scheduled_arrival"],
                delay_seconds=delay_s,
                status=status,
            )
        )
    return results


def get_vehicle_position(trip_id: str) -> dict | None:
    """Return the most recent vehicle position for *trip_id*, or None."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT vehicle_id, trip_id, route_id, latitude, longitude,
               bearing, speed, current_stop_sequence, captured_at
        FROM   rt_vehicle_positions
        WHERE  trip_id = ?
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        (trip_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------

def _gtfs_time_to_unix(date_str: str, time_str: str) -> int:
    """
    Convert a GTFS date (YYYYMMDD) and time (HH:MM:SS, possibly > 24h) to
    a unix timestamp (UTC-naive, local wall-clock arithmetic).
    """
    base = datetime.strptime(date_str, "%Y%m%d")
    h, m, s = (int(x) for x in time_str.split(":"))
    return int((base + timedelta(hours=h, minutes=m, seconds=s)).timestamp())


def _compute_delay(
    date: str,
    scheduled_time: str | None,
    rt_unix: int | None,
    schedule_relationship: str | None,
) -> tuple[int | None, str]:
    """Return (delay_seconds, status_label)."""
    if schedule_relationship == "CANCELED":
        return None, "canceled"

    if rt_unix is None or scheduled_time is None:
        return None, "no_data"

    try:
        scheduled_unix = _gtfs_time_to_unix(date, scheduled_time)
    except (ValueError, AttributeError):
        return None, "no_data"

    delay_s = rt_unix - scheduled_unix

    if delay_s > LATE_THRESHOLD_S:
        status = "late"
    elif delay_s < EARLY_THRESHOLD_S:
        status = "early"
    else:
        status = "on_time"

    return delay_s, status
