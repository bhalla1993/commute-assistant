"""
Nearby Stops Engine
--------------------
Finds transit stops within a given radius of a GPS coordinate using the
Haversine formula (great-circle distance).

All coordinates are in decimal degrees (WGS-84).
"""
import math
from typing import TypedDict

from db.database import get_connection

EARTH_RADIUS_M = 6_371_000  # metres


class NearbyStop(TypedDict):
    stop_id: str
    stop_name: str
    stop_lat: float
    stop_lon: float
    distance_m: float


def get_nearby_stops(lat: float, lon: float, radius_m: float = 500.0) -> list[NearbyStop]:
    """
    Return all stops within *radius_m* metres of (*lat*, *lon*),
    sorted nearest-first.

    Uses a bounding-box pre-filter on the SQL side to avoid a full table scan,
    then applies the exact Haversine check in Python.
    """
    lat_delta = _lat_delta(radius_m)
    lon_delta = _lon_delta(lat, radius_m)

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT stop_id, stop_name, stop_lat, stop_lon
        FROM   stops
        WHERE  stop_lat BETWEEN ? AND ?
          AND  stop_lon BETWEEN ? AND ?
        """,
        (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta),
    ).fetchall()
    conn.close()

    results: list[NearbyStop] = []
    for row in rows:
        dist = haversine(lat, lon, row["stop_lat"], row["stop_lon"])
        if dist <= radius_m:
            results.append(
                NearbyStop(
                    stop_id=row["stop_id"],
                    stop_name=row["stop_name"],
                    stop_lat=row["stop_lat"],
                    stop_lon=row["stop_lon"],
                    distance_m=round(dist, 1),
                )
            )

    results.sort(key=lambda s: s["distance_m"])
    return results


# --------------------------------------------------------------------------
# Haversine formula
# --------------------------------------------------------------------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two WGS-84 coordinates."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------
# Bounding-box helpers
# --------------------------------------------------------------------------

def _lat_delta(radius_m: float) -> float:
    """Degrees of latitude corresponding to *radius_m* metres."""
    return radius_m / EARTH_RADIUS_M * (180.0 / math.pi)


def _lon_delta(lat: float, radius_m: float) -> float:
    """Degrees of longitude at *lat* corresponding to *radius_m* metres."""
    lat_rad = math.radians(lat)
    if math.cos(lat_rad) == 0:
        return 180.0  # pole edge case
    return radius_m / (EARTH_RADIUS_M * math.cos(lat_rad)) * (180.0 / math.pi)
