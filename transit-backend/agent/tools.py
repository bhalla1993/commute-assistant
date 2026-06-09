"""
LLM Tool Definitions
---------------------
Defines the function-calling tools exposed to the OpenAI model.
Each entry maps directly to an engine function.

These are passed as the `tools` argument in every chat completion call.
"""

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "find_nearby_stops",
            "description": (
                "Find Durham Region Transit bus stops near a GPS location. "
                "Use this when the user asks about stops, transit access near them, "
                "or before routing if you only have their coordinates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {
                        "type": "number",
                        "description": "User's latitude in decimal degrees (WGS-84).",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "User's longitude in decimal degrees (WGS-84).",
                    },
                    "radius_m": {
                        "type": "number",
                        "description": "Search radius in metres. Default 500.",
                    },
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_delays_for_stop",
            "description": (
                "Get real-time delay information for all upcoming trips at a specific stop. "
                "Use when the user asks 'is my bus late?', 'when is the next bus at stop X?', "
                "or similar questions about a named stop."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stop_id": {
                        "type": "string",
                        "description": "The GTFS stop_id to check.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Service date in YYYYMMDD format. Use today's date if not specified.",
                    },
                },
                "required": ["stop_id", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_routes_between",
            "description": (
                "Find bus routes that connect an origin stop to a destination stop on a given date. "
                "Returns the next departures with delay information. "
                "Use when the user asks how to get from one place to another."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_stop_id": {
                        "type": "string",
                        "description": "GTFS stop_id of the departure stop.",
                    },
                    "dest_stop_id": {
                        "type": "string",
                        "description": "GTFS stop_id of the destination stop.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Service date in YYYYMMDD format.",
                    },
                },
                "required": ["origin_stop_id", "dest_stop_id", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_alerts",
            "description": (
                "Retrieve active service disruptions and alerts from Durham Region Transit. "
                "Use when the user asks about service disruptions, detours, or cancellations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "route_id": {
                        "type": "string",
                        "description": (
                            "Filter alerts to this GTFS route_id. "
                            "Omit to return all active system-wide alerts."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vehicle_position",
            "description": (
                "Get the current GPS position of a bus for a specific trip. "
                "Use when the user wants to know exactly where their bus is right now."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trip_id": {
                        "type": "string",
                        "description": "The GTFS trip_id of the bus.",
                    },
                },
                "required": ["trip_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trip_delay",
            "description": (
                "Get a stop-by-stop delay breakdown for a specific trip. "
                "Use to give detailed delay info along the full route of a trip."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trip_id": {
                        "type": "string",
                        "description": "The GTFS trip_id.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Service date in YYYYMMDD format.",
                    },
                },
                "required": ["trip_id", "date"],
            },
        },
    },
]
