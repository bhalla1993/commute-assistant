"""
Service Alert Lookup Engine
----------------------------
Retrieves active service disruptions from the rt_alerts table.

"Active" means captured within the last RT_RETENTION_HOURS window —
we rely on the poller's cleanup job and the recency filter to avoid
surfacing stale alerts.

Lookup can be scoped to a specific route_id or returned globally.

Feature flag: SERVICE_ALERTS_ENABLED
  When false (default until Durham Region publishes the alerts feed URL),
  get_active_alerts() returns immediately with an empty list and
  available=False so the API can surface a clean "not available" response
  without touching the database at all.
"""
import os
from typing import TypedDict

from db.database import get_connection

RETENTION_HOURS = int(os.getenv("RT_RETENTION_HOURS", "2"))
ALERTS_ENABLED = os.getenv("SERVICE_ALERTS_ENABLED", "false").strip().lower() == "true"


class Alert(TypedDict):
    alert_id: str
    route_id: str | None
    stop_id: str | None
    header: str | None
    description: str | None
    effect: str


def get_active_alerts(route_id: str | None = None) -> tuple[list[Alert], bool]:
    """
    Return (alerts, available).

    available=False means the alerts feature is disabled (feed URL not yet
    published by Durham Region). Callers should surface a friendly message
    rather than treating this as an error.

    If *route_id* is provided, return alerts for that route plus any
    global alerts (route_id IS NULL).
    If *route_id* is None, return all active alerts.

    Results are deduplicated by alert_id so a single alert affecting
    multiple entities is only returned once.
    """
    if not ALERTS_ENABLED:
        return [], False

    import time
    cutoff = int(time.time()) - RETENTION_HOURS * 3600

    conn = get_connection()

    if route_id:
        rows = conn.execute(
            """
            SELECT DISTINCT alert_id, route_id, stop_id, header, description, effect
            FROM   rt_alerts
            WHERE  captured_at >= ?
              AND  (route_id = ? OR route_id IS NULL)
            ORDER BY captured_at DESC
            """,
            (cutoff, route_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT alert_id, route_id, stop_id, header, description, effect
            FROM   rt_alerts
            WHERE  captured_at >= ?
            ORDER BY captured_at DESC
            """,
            (cutoff,),
        ).fetchall()

    conn.close()

    # Deduplicate by alert_id — keep the first (most recent) occurrence
    seen: set[str] = set()
    results: list[Alert] = []
    for row in rows:
        if row["alert_id"] not in seen:
            seen.add(row["alert_id"])
            results.append(
                Alert(
                    alert_id=row["alert_id"],
                    route_id=row["route_id"],
                    stop_id=row["stop_id"],
                    header=row["header"],
                    description=row["description"],
                    effect=row["effect"],
                )
            )
    return results, True
