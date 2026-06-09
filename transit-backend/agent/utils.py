"""
Agent Utility Helpers
----------------------
Shared text-normalization and pattern-matching helpers used by the
agent core, skills, and knowledge base.
"""
import re
import unicodedata


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text)
    return text


# --------------------------------------------------------------------------
# Stop / route extraction helpers
# --------------------------------------------------------------------------

_STOP_ID_RE = re.compile(r"\bstop\s+(\d+)\b", re.IGNORECASE)
_ROUTE_ID_RE = re.compile(r"\b(?:route|bus)\s+(\d+[a-z]?)\b", re.IGNORECASE)


def extract_stop_ids(text: str) -> list[str]:
    """Return all stop IDs mentioned in *text* (e.g. 'stop 123' → ['123'])."""
    return _STOP_ID_RE.findall(text)


def extract_route_ids(text: str) -> list[str]:
    """Return all route IDs mentioned in *text* (e.g. 'bus 915' → ['915'])."""
    return _ROUTE_ID_RE.findall(text)


# --------------------------------------------------------------------------
# Transit relevance detection
# --------------------------------------------------------------------------

_TRANSIT_KEYWORDS = {
    "bus", "stop", "route", "schedule", "depart", "departure",
    "arrive", "arrival", "trip", "delay", "late", "early", "on time",
    "ontime", "alert", "detour", "cancel", "cancellation", "service",
    "transit", "drt", "durham", "gtfs", "vehicle", "next bus",
    "when is", "how do i get", "fare", "ticket", "pass",
}

# Patterns that strongly signal a clearly off-topic request.
# Only long messages (>3 words) that contain one of these AND no transit
# keywords are considered off-topic.
_OFF_TOPIC_SIGNALS = {
    "weather", "forecast", "temperature", "rain", "snow",
    "stock", "crypto", "bitcoin", "market", "invest",
    "recipe", "cook", "restaurant", "pizza", "food",
    "code", "python", "javascript", "program", "hack",
    "news", "politics", "election", "president", "sport",
    "netflix", "movie", "film", "youtube", "tiktok",
    "poem", "essay", "story", "novel", "translate",
}


def is_transit_related(text: str) -> bool:
    """
    Return False only when a message is CLEARLY off-topic.

    Logic:
    - Short messages (≤4 words: greetings, ack, thanks) → True (let LLM handle).
    - Any transit keyword present → True.
    - Off-topic signal present AND no transit keyword → False.
    - Anything else ambiguous → True (LLM's system prompt handles staying on topic).
    """
    norm = normalize(text)
    word_count = len(norm.split())

    # Always pass short/conversational messages through
    if word_count <= 4:
        return True

    has_transit = any(kw in norm for kw in _TRANSIT_KEYWORDS)
    if has_transit:
        return True

    has_off_topic = any(sig in norm for sig in _OFF_TOPIC_SIGNALS)
    if has_off_topic:
        return False

    # Ambiguous — let the LLM decide
    return True


# --------------------------------------------------------------------------
# Message compression for LLM
# --------------------------------------------------------------------------

def compress_message(text: str, max_length: int = 500) -> str:
    """
    Trim *text* to *max_length* characters without cutting mid-word,
    appending '…' if truncated.
    """
    text = text.strip()
    if len(text) <= max_length:
        return text
    truncated = text[:max_length].rsplit(" ", 1)[0]
    return truncated + "…"
