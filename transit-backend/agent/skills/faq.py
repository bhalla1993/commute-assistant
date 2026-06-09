"""
FAQ Skill
----------
Answers common Durham Region Transit questions from a static Q&A list.
New entries can be added to FAQ_ENTRIES below or loaded from the
knowledge base at runtime.

Matching is keyword-based (normalised text). The first entry whose
keywords all appear in the message is returned.
"""
from agent.utils import normalize

# Each entry: (keywords_required, answer_text)
# All keywords must appear in the normalised user message.
FAQ_ENTRIES: list[tuple[tuple[str, ...], str]] = [
    (
        ("fare",),
        "Adult cash fare on DRT is $3.75 per trip. Day passes and PRESTO card discounts are available. "
        "Visit durhamregiontransit.com/fares for full details.",
    ),
    (
        ("presto",),
        "You can load your PRESTO card online at prestocard.ca, at select GO stations, "
        "or at Shoppers Drug Mart locations. Tap on when boarding DRT buses.",
    ),
    (
        ("accessible", "accessibility", "wheelchair"),
        "All DRT buses are accessible. Wheelchair spaces and kneeling buses are available on every route. "
        "Paratransit (Specialized Transit) is also available — call 905-686-7380 to book.",
    ),
    (
        ("lost", "lost and found"),
        "For lost items on DRT buses, call customer service at 1-866-247-0055 or visit the Durham Region Transit website.",
    ),
    (
        ("contact",),
        "DRT customer service: 1-866-247-0055 (Mon–Fri 7 am–9 pm, Sat–Sun 8 am–6 pm). "
        "You can also use the online contact form at durhamregiontransit.com.",
    ),
    (
        ("trip planner", "plan my trip", "plan a trip"),
        "You can plan your DRT trip using the online trip planner at durhamregiontransit.com/trip-planner "
        "or ask me — just tell me where you're starting from and where you'd like to go.",
    ),
    (
        ("holiday", "stat", "statutory"),
        "DRT runs a modified schedule on statutory holidays. Check durhamregiontransit.com/schedules "
        "for the holiday schedule closest to your travel date.",
    ),
    (
        ("route map", "system map"),
        "The full DRT route map is available at durhamregiontransit.com/routes.",
    ),
]


def answer(message: str, context: dict) -> str | None:  # noqa: ARG001
    """Return an FAQ answer if a matching entry is found, otherwise None."""
    norm = normalize(message)
    for keywords, response in FAQ_ENTRIES:
        if all(kw in norm for kw in keywords):
            return response
    return None
