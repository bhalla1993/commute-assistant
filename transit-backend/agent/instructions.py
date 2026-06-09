"""
Agent Routing Instructions
---------------------------
Defines the rules used by TransitAgent to decide how to handle each
incoming message:

  RELEVANCE_THRESHOLD — minimum keyword hit count to treat a message as
      transit-related.
  POLITE_DECLINE      — response when the message is clearly off-topic.
  FALLBACK_RESPONSE   — response when all local skills AND the LLM fail.
  SKILL_ORDER         — ordered list of skill names to try for local answers.
"""

# How many transit keywords must appear for the message to be routed
# through the full pipeline. Messages below this threshold receive
# POLITE_DECLINE immediately.
RELEVANCE_THRESHOLD: int = 1

# Sent to the user when the message is not transit-related
POLITE_DECLINE: str = (
    "I'm here to help with Durham Region Transit questions — routes, schedules, "
    "delays, and service alerts. Is there anything transit-related I can help with?"
)

# Sent when every skill and the LLM all fail or are unavailable
FALLBACK_RESPONSE: str = (
    "Sorry, I'm having trouble fetching that information right now. "
    "You can also check real-time updates at durhamregiontransit.com or call 1-866-247-0055."
)

# Skills are tried in this order; the first non-None answer wins
# 'nearby' runs before 'gtfs' so GPS-based queries resolve locally without LLM
SKILL_ORDER: list[str] = ["faq", "nearby", "gtfs", "alerts"]
