"""
Knowledge Base
---------------
Stores and retrieves Q&A pairs learned from admin curation or
common user corrections.  Backed by the SQLite database so entries
survive process restarts.

Schema (created on first use):
  kb_entries(id INTEGER PK, question TEXT, answer TEXT, hits INTEGER,
             created_at INTEGER, updated_at INTEGER)

Lookup is keyword-overlap similarity: the entry whose normalised
question shares the most tokens with the incoming message is returned,
provided its score meets SIMILARITY_THRESHOLD.
"""
import logging
import time
from typing import TypedDict

from agent.utils import normalize
from db.database import get_connection

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.5  # fraction of query tokens that must match


# --------------------------------------------------------------------------
# DB bootstrap
# --------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT    NOT NULL,
    answer     TEXT    NOT NULL,
    hits       INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS kb_entries_question ON kb_entries(question);
"""


def _ensure_table() -> None:
    conn = get_connection()
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

class KBEntry(TypedDict):
    id: int
    question: str
    answer: str
    hits: int


def lookup(message: str) -> str | None:
    """
    Return the best-matching KB answer for *message*, or None if no
    entry meets SIMILARITY_THRESHOLD.
    """
    try:
        _ensure_table()
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, question, answer FROM kb_entries ORDER BY hits DESC"
        ).fetchall()
        conn.close()
    except Exception:
        logger.exception("[knowledge_base] lookup failed")
        return None

    if not rows:
        return None

    query_tokens = set(normalize(message).split())
    if not query_tokens:
        return None

    best_score = 0.0
    best_id: int | None = None
    best_answer: str | None = None

    for row in rows:
        entry_tokens = set(normalize(row["question"]).split())
        if not entry_tokens:
            continue
        overlap = len(query_tokens & entry_tokens) / len(query_tokens)
        if overlap > best_score:
            best_score = overlap
            best_id = row["id"]
            best_answer = row["answer"]

    if best_score >= SIMILARITY_THRESHOLD and best_answer:
        _increment_hits(best_id)
        return best_answer

    return None


def add_entry(question: str, answer: str) -> int:
    """
    Insert a new Q&A pair.  Returns the new row id.
    Raises ValueError if question or answer is empty.
    """
    question = question.strip()
    answer = answer.strip()
    if not question or not answer:
        raise ValueError("question and answer must not be empty")

    _ensure_table()
    now = int(time.time())
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO kb_entries (question, answer, hits, created_at, updated_at) VALUES (?,?,0,?,?)",
        (question, answer, now, now),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    logger.info("[knowledge_base] added entry id=%s", row_id)
    return row_id


def delete_entry(entry_id: int) -> bool:
    """Delete a KB entry by id. Returns True if a row was deleted."""
    _ensure_table()
    conn = get_connection()
    cur = conn.execute("DELETE FROM kb_entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def list_entries() -> list[KBEntry]:
    """Return all KB entries ordered by hit count descending."""
    try:
        _ensure_table()
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, question, answer, hits FROM kb_entries ORDER BY hits DESC"
        ).fetchall()
        conn.close()
        return [KBEntry(id=r["id"], question=r["question"], answer=r["answer"], hits=r["hits"]) for r in rows]
    except Exception:
        logger.exception("[knowledge_base] list_entries failed")
        return []


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------

def _increment_hits(entry_id: int | None) -> None:
    if entry_id is None:
        return
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE kb_entries SET hits = hits + 1, updated_at = ? WHERE id = ?",
            (int(time.time()), entry_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.warning("[knowledge_base] failed to increment hits for id=%s", entry_id)
