"""
Alerts Skill
-------------
Answers questions about active service disruptions directly from the
local database without calling the LLM.

If the alerts feature flag is disabled (SERVICE_ALERTS_ENABLED=false),
returns a friendly "not currently available" message so the user isn't
left in the dark.
"""
import logging

from agent.utils import extract_route_ids, normalize
from engine.alerts import get_active_alerts

logger = logging.getLogger(__name__)

_ALERT_TRIGGERS = {
    "alert", "disruption", "detour", "cancel", "cancellation",
    "service change", "delay", "affected", "issue", "problem",
    "not running", "suspended",
}


def answer(message: str, context: dict) -> str | None:  # noqa: ARG001
    """
    Return a plain-text summary of active alerts if the message asks
    about disruptions.  Returns None if the message is not alert-related.
    """
    norm = normalize(message)
    if not any(t in norm for t in _ALERT_TRIGGERS):
        return None

    route_ids = extract_route_ids(message)
    route_id = route_ids[0] if route_ids else None

    try:
        alerts, available = get_active_alerts(route_id=route_id)
    except Exception:
        logger.exception("[alerts_skill] Failed to fetch alerts")
        return None

    if not available:
        return (
            "Real-time service alerts aren't currently published by Durham Region Transit. "
            "For the latest service updates, visit durhamregiontransit.com or call 1-866-247-0055."
        )

    if not alerts:
        scope = f"route {route_id}" if route_id else "the DRT network"
        return f"No active service alerts for {scope} right now."

    lines = ["Active service alerts:"]
    for alert in alerts[:5]:
        header = alert.get("header") or alert.get("description") or "Service disruption"
        route = alert.get("route_id")
        prefix = f"Route {route}: " if route else ""
        lines.append(f"  • {prefix}{header}")

    return "\n".join(lines)
