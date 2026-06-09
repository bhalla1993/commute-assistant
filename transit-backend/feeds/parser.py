"""
GTFS-RT Protobuf Parser
-----------------------
Parses raw protobuf bytes from GTFS-RT feeds into plain Python dicts
ready to be written to the rt_* SQLite tables.

Three feed types:
  - Trip Updates   — scheduled vs realtime arrival/departure per stop
  - Vehicle Positions — live lat/lon of each vehicle
  - Service Alerts — active service disruptions
"""
from google.transit import gtfs_realtime_pb2


def parse_trip_updates(pb_bytes: bytes) -> list[dict]:
    """
    Parse a TripUpdates GTFS-RT feed.

    Returns a flat list of stop-time-update rows, one dict per
    (trip, stop_sequence) pair, matching the rt_trip_updates schema.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(pb_bytes)

    rows: list[dict] = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue

        tu = entity.trip_update
        trip = tu.trip
        trip_id = trip.trip_id
        route_id = trip.route_id
        start_date = trip.start_date

        for stu in tu.stop_time_update:
            arrival_time = stu.arrival.time if stu.HasField("arrival") else None
            departure_time = stu.departure.time if stu.HasField("departure") else None
            schedule_rel = _schedule_relationship(stu.schedule_relationship)

            rows.append(
                {
                    "trip_id": trip_id,
                    "route_id": route_id,
                    "start_date": start_date,
                    "stop_sequence": stu.stop_sequence,
                    "stop_id": stu.stop_id or None,
                    "arrival_time": arrival_time,
                    "departure_time": departure_time,
                    "schedule_relationship": schedule_rel,
                }
            )
    return rows


def parse_vehicle_positions(pb_bytes: bytes) -> list[dict]:
    """
    Parse a VehiclePositions GTFS-RT feed.

    Returns one dict per vehicle entity, matching rt_vehicle_positions schema.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(pb_bytes)

    rows: list[dict] = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue

        vp = entity.vehicle
        pos = vp.position
        trip = vp.trip

        rows.append(
            {
                "vehicle_id": vp.vehicle.id or entity.id,
                "trip_id": trip.trip_id,
                "route_id": trip.route_id,
                "latitude": pos.latitude if pos.HasField("latitude") else None,  # type: ignore[attr-defined]
                "longitude": pos.longitude if pos.HasField("longitude") else None,  # type: ignore[attr-defined]
                "bearing": pos.bearing if pos.bearing else None,
                "speed": pos.speed if pos.speed else None,
                "current_stop_sequence": vp.current_stop_sequence or None,
            }
        )
    return rows


def parse_alerts(pb_bytes: bytes) -> list[dict]:
    """
    Parse a ServiceAlerts GTFS-RT feed.

    Returns a flat list — one row per informed entity (route/stop combination),
    matching the rt_alerts schema.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(pb_bytes)

    rows: list[dict] = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue

        alert = entity.alert
        alert_id = entity.id
        header = _first_translation(alert.header_text)
        description = _first_translation(alert.description_text)
        effect = _effect_label(alert.effect)

        informed = alert.informed_entity
        if informed:
            for ie in informed:
                rows.append(
                    {
                        "alert_id": alert_id,
                        "route_id": ie.route_id or None,
                        "stop_id": ie.stop_id or None,
                        "header": header,
                        "description": description,
                        "effect": effect,
                    }
                )
        else:
            # Alert with no specific entity — store without route/stop
            rows.append(
                {
                    "alert_id": alert_id,
                    "route_id": None,
                    "stop_id": None,
                    "header": header,
                    "description": description,
                    "effect": effect,
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _first_translation(translated_string) -> str | None:
    """Return the text of the first available translation, or None."""
    if translated_string and translated_string.translation:
        return translated_string.translation[0].text or None
    return None


def _schedule_relationship(value: int) -> str:
    mapping = {0: "SCHEDULED", 1: "ADDED", 2: "UNSCHEDULED", 3: "CANCELED"}
    return mapping.get(value, "SCHEDULED")


def _effect_label(value: int) -> str:
    mapping = {
        0: "UNKNOWN_EFFECT",
        1: "NO_SERVICE",
        2: "REDUCED_SERVICE",
        3: "SIGNIFICANT_DELAYS",
        4: "DETOUR",
        5: "ADDITIONAL_SERVICE",
        6: "MODIFIED_SERVICE",
        7: "OTHER_EFFECT",
        8: "STOP_MOVED",
    }
    return mapping.get(value, "UNKNOWN_EFFECT")
