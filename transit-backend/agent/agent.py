"""
Agent Orchestration
--------------------
Receives a user message (plus optional GPS context), runs an OpenAI
function-calling loop, dispatches tool calls to the engine layer,
and returns the final text response.

Pipeline (per message):
  1. TransitAgent.is_transit_question() — reject off-topic messages early.
  2. TransitAgent.try_local_answer()    — FAQ / GTFS / alerts / KB skills.
  3. TransitAgent.optimize_request()   — compress the message for the LLM.
  4. LLM tool-calling loop             — up to MAX_TOOL_ROUNDS iterations.
  5. fallback_response()               — if everything fails.

Max iterations: MAX_TOOL_ROUNDS (guards against runaway loops).
"""
import json
import logging
from datetime import datetime, timezone

from openai import APITimeoutError as OpenAITimeoutError

from agent.instructions import FALLBACK_RESPONSE, POLITE_DECLINE, SKILL_ORDER
from agent.knowledge_base import lookup as kb_lookup
from agent.prompt import SYSTEM_PROMPT
from agent.providers import get_completion
from agent.skills import alerts_answer, faq_answer, gtfs_answer, nearby_answer
from agent.tools import TOOLS
from agent.utils import compress_message, is_transit_related
from db.database import get_connection
from engine.alerts import get_active_alerts
from engine.delays import get_delays_for_stop, get_trip_delay, get_vehicle_position
from engine.nearby import get_nearby_stops
from engine.routes import find_routes_between

logger = logging.getLogger(__name__)

_SKILL_MAP = {
    "faq": faq_answer,
    "nearby": nearby_answer,
    "gtfs": gtfs_answer,
    "alerts": alerts_answer,
}

MAX_TOOL_ROUNDS = 5


# --------------------------------------------------------------------------
# TransitAgent — pre-LLM processing layer
# --------------------------------------------------------------------------

class TransitAgent:
    """
    Validates, routes, and locally answers user messages before
    falling back to the LLM.
    """

    def is_transit_question(self, message: str) -> bool:
        """Return True if the message is transit-related."""
        return is_transit_related(message)

    def try_local_answer(self, message: str, context: dict) -> str | None:
        """
        Try each skill in SKILL_ORDER, then the knowledge base.
        Returns the first non-None answer, or None if all fail.
        """
        for skill_name in SKILL_ORDER:
            fn = _SKILL_MAP.get(skill_name)
            if fn is None:
                continue
            try:
                result = fn(message, context)
                if result:
                    logger.debug("[agent] local answer from skill '%s'", skill_name)
                    return result
            except Exception:
                logger.exception("[agent] skill '%s' raised an error", skill_name)

        # Knowledge base fallback
        try:
            kb_answer = kb_lookup(message)
            if kb_answer:
                logger.debug("[agent] local answer from knowledge_base")
                return kb_answer
        except Exception:
            logger.exception("[agent] knowledge_base lookup raised an error")

        return None

    def optimize_request(self, message: str) -> str:
        """Compress/clean the message before sending to the LLM."""
        return compress_message(message)

    def fallback_response(self) -> str:
        return FALLBACK_RESPONSE


_transit_agent = TransitAgent()


# --------------------------------------------------------------------------
# Fallback suggestions — shown when LLM is unavailable
# --------------------------------------------------------------------------

def _gtfs_data_available() -> bool:
    """
    Quick probe: return True if the GTFS trips table has at least one row.
    Used to decide whether to offer schedule-based suggestions.
    """
    try:
        conn = get_connection()
        row = conn.execute("SELECT 1 FROM trips LIMIT 1").fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def _alerts_data_available() -> bool:
    """Return True if there are active service alerts in the DB."""
    try:
        conn = get_connection()
        row = conn.execute("SELECT 1 FROM rt_alerts LIMIT 1").fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def build_suggestions(context: dict) -> list[str]:
    """Public alias for the suggestions builder (used by the /suggestions endpoint)."""
    return _build_suggestions(context)


def _routes_at_stop(stop_id: str, limit: int = 4) -> list[str]:
    """Return up to *limit* distinct route short names that serve *stop_id*."""
    try:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT DISTINCT r.route_short_name
            FROM   stop_times st
            JOIN   trips  t ON t.trip_id  = st.trip_id
            JOIN   routes r ON r.route_id = t.route_id
            WHERE  st.stop_id = ?
            LIMIT  ?
            """,
            [stop_id, limit],
        ).fetchall()
        conn.close()
        return [row["route_short_name"] for row in rows if row["route_short_name"]]
    except Exception:
        return []


def _build_suggestions(context: dict) -> list[str]:
    """
    Build a list of predefined queries the agent can always answer locally,
    tailored to the user's GPS location, nearby stops, and live data availability.

    With GPS:
      - Looks up the 2 closest stops within 500 m (widens to 1 km if empty).
      - Generates chips that reference real stop names and route numbers.
      - Falls back to generic nearby chips if no stops are found.

    Without GPS:
      - Offers generic schedule chips for known destinations.

    Always appends static FAQ chips that work fully offline.
    """
    has_gps = context.get("latitude") is not None and context.get("longitude") is not None
    gtfs_ok = _gtfs_data_available()
    alerts_ok = _alerts_data_available()

    suggestions: list[str] = []

    if has_gps and gtfs_ok:
        lat = float(context["latitude"])
        lon = float(context["longitude"])

        nearby = get_nearby_stops(lat=lat, lon=lon, radius_m=500.0)
        if not nearby:
            nearby = get_nearby_stops(lat=lat, lon=lon, radius_m=1000.0)

        if nearby:
            # --- Chip 1: route-specific departure from the closest stop ---
            closest = nearby[0]
            stop_name = closest["stop_name"]
            routes = _routes_at_stop(closest["stop_id"])
            if routes:
                suggestions.append(
                    f"When is the next Route {routes[0]} from {stop_name}?"
                )
                if len(routes) > 1:
                    # Chip 2: all routes at the same stop
                    route_list = ", ".join(routes[:3])
                    suggestions.append(
                        f"What buses serve {stop_name}? (Routes {route_list})"
                    )
            else:
                suggestions.append(f"Show stops near me")

            # --- Chip 3: second closest stop if distinct enough (> 100 m away) ---
            if len(nearby) > 1 and nearby[1]["distance_m"] > 100:
                second = nearby[1]
                second_routes = _routes_at_stop(second["stop_id"])
                if second_routes:
                    suggestions.append(
                        f"Next bus from {second['stop_name']}?"
                    )

            # --- Chip 4: generic "next bus near me" for broader context ---
            suggestions.append("What buses are near me right now?")

        else:
            # No stops found in 1 km — offer the generic nearby queries
            suggestions.append("Show stops near me")
            suggestions.append("What buses are near me right now?")

    elif gtfs_ok:
        # No GPS — offer useful schedule queries for known DRT destinations
        suggestions.append("When is the next bus to Oshawa GO?")
        suggestions.append("When is the next bus to Ajax GO?")

    if alerts_ok:
        suggestions.append("Are there any service alerts?")

    # Static FAQ chips — only add if the FAQ skill can actually answer them.
    # This self-validates so no chip is ever shown that returns no answer.
    _faq_candidates = [
        "What is the DRT bus fare?",
        "How do I contact DRT customer service?",
        "Is DRT accessible for wheelchairs?",
        "How do I use my PRESTO card on DRT?",
    ]
    for chip in _faq_candidates:
        if faq_answer(chip, {}) is not None:
            suggestions.append(chip)

    return suggestions


def _fallback_with_suggestions(context: dict) -> tuple[str, list[str]]:
    """
    Return (message_text, suggestions_list) for the LLM-unavailable state.
    """
    suggestions = _build_suggestions(context)
    msg = (
        "Real-time AI is currently unavailable. "
        "Here are some things I can help with right now:"
    )
    return msg, suggestions


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

class AgentTimeoutError(Exception):
    """Raised when the OpenAI API call times out."""
    pass


def chat(
    user_message: str,
    conversation_history: list[dict],
    latitude: float | None = None,
    longitude: float | None = None,
) -> tuple[str, list[dict], list[str]]:
    """
    Process one user turn.

    Parameters
    ----------
    user_message:
        The raw text from the user.
    conversation_history:
        Previous messages in OpenAI format (role/content pairs).
        Pass an empty list for a fresh conversation.
    latitude, longitude:
        Optional GPS coordinates sent from the mobile app.

    Returns
    -------
    (reply_text, updated_history, suggestions)
        reply_text         — the assistant's final text answer
        updated_history    — the full message list including this turn
        suggestions        — list of predefined queries for offline fallback
                             (empty list when LLM answered successfully)
    """
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    context = {"date": today, "latitude": latitude, "longitude": longitude}


    # --- Step 1: Try local skills / knowledge base (no LLM needed) ---
    logger.info(f"[agent] Received user message: {user_message}")
    local_answer = _transit_agent.try_local_answer(user_message, context)
    if local_answer:
        logger.info("[agent] Answered locally (no LLM needed)")
        follow_up = _build_suggestions(context)
        return local_answer, list(conversation_history), follow_up

    # --- Step 2: Compress message for LLM ---
    optimized_message = _transit_agent.optimize_request(user_message)
    logger.debug(f"[agent] Optimized message for LLM: {optimized_message}")

    # Build the user turn, injecting GPS context if available
    user_content = optimized_message
    if latitude is not None and longitude is not None:
        user_content = (
            f"[User GPS: lat={latitude}, lon={longitude}]\n"
            f"[Today's date: {today}]\n\n"
            f"{optimized_message}"
        )
    else:
        user_content = f"[Today's date: {today}]\n\n{optimized_message}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *conversation_history,
        {"role": "user", "content": user_content},
    ]

    for _round in range(MAX_TOOL_ROUNDS):
        logger.debug(f"[agent] LLM round {_round+1} - sending messages: {messages[-2:]}")
        try:
            logger.info("[agent] Calling AI provider (LLM)")
            response = get_completion(
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                timeout=30.0,
            )
            logger.debug(f"[agent] LLM response: {response}")
        except OpenAITimeoutError as exc:
            logger.warning("[agent] AI request timed out: %s", exc)
            raise AgentTimeoutError("AI request timed out") from exc
        except Exception as exc:
            logger.exception("[agent] LLM call failed: %s", exc)
            updated_history = _strip_system(messages)
            msg, suggestions = _fallback_with_suggestions(context)
            return msg, updated_history, suggestions

        msg = response.choices[0].message

        # Append the raw assistant message (tool_calls or text)
        messages.append(msg.model_dump(exclude_unset=True))

        # No tool calls — we have the final answer
        if not msg.tool_calls:
            reply = msg.content or ""
            logger.info(f"[agent] LLM reply: {reply}")
            updated_history = _strip_system(messages)
            return reply, updated_history, []

        # Execute each tool call and append results
        for tc in msg.tool_calls:
            logger.info(f"[agent] Executing tool call: {tc.function.name} with args: {tc.function.arguments}")
            try:
                result = _dispatch(tc.function.name, tc.function.arguments)
                logger.debug(f"[agent] Tool call result: {result}")
            except Exception as e:
                logger.error(f"[agent] Tool call {tc.function.name} failed: {e}", exc_info=True)
                result = {"error": str(e)}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                }
            )

    # Safety fallback if loop exhausted or all providers failed.
    logger.warning("[agent] Tool round limit reached for message: %s", user_message[:80])
    updated_history = _strip_system(messages)
    if _transit_agent.is_transit_question(user_message):
        msg, suggestions = _fallback_with_suggestions(context)
        return msg, updated_history, suggestions
    return POLITE_DECLINE, updated_history, []


# --------------------------------------------------------------------------
# Tool dispatcher
# --------------------------------------------------------------------------

def _dispatch(function_name: str, arguments_json: str) -> object:
    """Call the appropriate engine function and return a JSON-serialisable result."""
    try:
        args: dict = json.loads(arguments_json)
    except json.JSONDecodeError:
        return {"error": "invalid arguments"}

    try:
        if function_name == "find_nearby_stops":
            return get_nearby_stops(
                lat=args["latitude"],
                lon=args["longitude"],
                radius_m=args.get("radius_m", 500.0),
            )

        if function_name == "get_delays_for_stop":
            return get_delays_for_stop(
                stop_id=args["stop_id"],
                date=args["date"],
            )

        if function_name == "find_routes_between":
            return find_routes_between(
                origin_stop_id=args["origin_stop_id"],
                dest_stop_id=args["dest_stop_id"],
                date=args["date"],
            )

        if function_name == "get_active_alerts":
            alerts, available = get_active_alerts(route_id=args.get("route_id"))
            if not available:
                return {"alerts": [], "available": False, "message": "Service alerts are not currently available for Durham Region Transit."}
            return {"alerts": alerts, "available": True}

        if function_name == "get_vehicle_position":
            result = get_vehicle_position(trip_id=args["trip_id"])
            return result if result is not None else {"error": "no position data"}

        if function_name == "get_trip_delay":
            return get_trip_delay(
                trip_id=args["trip_id"],
                date=args["date"],
            )

    except Exception as exc:  # noqa: BLE001
        logger.exception("[agent] Tool %s raised: %s", function_name, exc)
        return {"error": str(exc)}

    return {"error": f"unknown tool: {function_name}"}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _strip_system(messages: list[dict]) -> list[dict]:
    """Return messages without the system prompt (not needed in history storage)."""
    return [m for m in messages if m.get("role") != "system"]
