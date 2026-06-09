"""
Agent Skills Package
---------------------
Each skill module exposes an `answer(message, context) -> str | None`
function that returns a plain-text answer or None if the skill
cannot handle the query.
"""
from agent.skills.alerts import answer as alerts_answer
from agent.skills.faq import answer as faq_answer
from agent.skills.gtfs import answer as gtfs_answer
from agent.skills.nearby import answer as nearby_answer

__all__ = ["faq_answer", "gtfs_answer", "alerts_answer", "nearby_answer"]
