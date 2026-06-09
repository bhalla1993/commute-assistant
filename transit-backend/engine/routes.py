"""
Route Finder Engine
--------------------
Finds trips that connect an origin stop to a destination stop and returns
the next departures (including real-time delay where available).

Algorithm:
  1. Find all trips that visit *origin_stop_id* (any stop_sequence).
  2. Among those trips, keep only ones that also visit *dest_stop_id*
     at a LATER stop_sequence — i.e. origin appears before destination.
  3. Filter to trips active on *date* via calendar_dates.
  4. Return up to MAX_RESULTS trips ordered by origin departure time.
"""
from datetime import datetime
from typing import TypedDict

from db.database import get_connection

MAX_RESULTS = 5


class RouteOption(TypedDict):
    trip_id: str
    route_id: str
    route_short_name: str
    trip_headsign: str
    origin_stop_id: str
    origin_stop_name: str
    dest_stop_id: str
    dest_stop_name: str
    origin_departure: str      # HH:MM:SS
    dest_arrival: str          # HH:MM:SS
    delay_seconds: int | None  # at origin stop (None if no RT data)
    status: str                # on_time | late | early | no_data | canceled


def find_routes_between(
    origin_stop_id: str,
    dest_stop_id: str,
    date: str,
) -> list[RouteOption]:
    """
    Return up to MAX_RESULTS trips connecting *origin_stop_id* →
    *dest_stop_id* on *date* (YYYYMMDD), ordered by departure time.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            t.trip_id,
            t.route_id,
            r.route_short_name,
            t.trip_headsign,
            orig.stop_id     AS origin_stop_id,
            orig_s.stop_name AS origin_stop_name,
            dest.stop_id     AS dest_stop_id,
            dest_s.stop_name AS dest_stop_name,
            orig.departure_time AS origin_departure,
            dest.arrival_time   AS dest_arrival,
            -- latest RT arrival at origin
            (
                SELECT rtu.arrival_time
                FROM   rt_trip_updates rtu
                WHERE  rtu.trip_id       = t.trip_id
                  AND  rtu.start_date    = :date
                  AND  rtu.stop_sequence = orig.stop_sequence
                ORDER BY rtu.captured_at DESC
                LIMIT 1
            ) AS rt_arrival,
            (
                SELECT rtu.schedule_relationship
                FROM   rt_trip_updates rtu
                WHERE  rtu.trip_id       = t.trip_id
                  AND  rtu.start_date    = :date
                  AND  rtu.stop_sequence = orig.stop_sequence
                ORDER BY rtu.captured_at DESC
                LIMIT 1
            ) AS schedule_relationship
        FROM stop_times orig
        JOIN stop_times dest
             ON  dest.trip_id      = orig.trip_id
             AND dest.stop_id      = :dest_stop_id
             AND dest.stop_sequence > orig.stop_sequence
        JOIN trips  t  ON t.trip_id  = orig.trip_id
        JOIN routes r  ON r.route_id = t.route_id
        JOIN stops  orig_s ON orig_s.stop_id = orig.stop_id
        JOIN stops  dest_s ON dest_s.stop_id = dest.stop_id
        WHERE orig.stop_id = :origin_stop_id
          AND (
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
        ORDER BY orig.departure_time
        LIMIT :limit
        """,
        {
            "origin_stop_id": origin_stop_id,
            "dest_stop_id": dest_stop_id,
            "date": date,
            "limit": MAX_RESULTS,
        },
    ).fetchall()
    conn.close()

    results: list[RouteOption] = []
    for row in rows:
        delay_s, status = _compute_delay(
            date, row["origin_departure"], row["rt_arrival"], row["schedule_relationship"]
        )
        results.append(
            RouteOption(
                trip_id=row["trip_id"],
                route_id=row["route_id"],
                route_short_name=row["route_short_name"] or row["route_id"],
                trip_headsign=row["trip_headsign"] or "",
                origin_stop_id=row["origin_stop_id"],
                origin_stop_name=row["origin_stop_name"],
                dest_stop_id=row["dest_stop_id"],
                dest_stop_name=row["dest_stop_name"],
                origin_departure=row["origin_departure"],
                dest_arrival=row["dest_arrival"],
                delay_seconds=delay_s,
                status=status,
            )
        )
    return results


# --------------------------------------------------------------------------
# Internal helpers (mirrors delays.py logic without the import cycle)
# --------------------------------------------------------------------------

from datetime import timedelta

LATE_THRESHOLD_S = 120
EARLY_THRESHOLD_S = -60


def _gtfs_time_to_unix(date_str: str, time_str: str) -> int:
    base = datetime.strptime(date_str, "%Y%m%d")
    h, m, s = (int(x) for x in time_str.split(":"))
    return int((base + timedelta(hours=h, minutes=m, seconds=s)).timestamp())


def _compute_delay(
    date: str,
    scheduled_time: str | None,
    rt_unix: int | None,
    schedule_relationship: str | None,
) -> tuple[int | None, str]:
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
        return delay_s, "late"
    if delay_s < EARLY_THRESHOLD_S:
        return delay_s, "early"
    return delay_s, "on_time"
