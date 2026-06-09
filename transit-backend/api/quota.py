"""
Daily quota helpers for free-tier users.

Free users are limited to FREE_DAILY_LIMIT queries per UTC calendar day.
Premium users bypass all quota checks.
"""
import logging
from datetime import datetime, timezone

from db.database import get_connection

logger = logging.getLogger(__name__)

FREE_DAILY_LIMIT = 3   # max AI queries per day for free users
MIN_AD_SECONDS   = 12  # minimum ad watch time enforced server-side


def get_user_tier(user_id: str) -> str:
    """Return 'free' or 'premium' for the given user."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT subscription_tier FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row["subscription_tier"] if row else "free"
    finally:
        conn.close()


def get_daily_query_count(user_id: str) -> int:
    """Return the number of queries the user has made today (UTC)."""
    today = _today_utc()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT query_count FROM user_daily_quota WHERE user_id = ? AND quota_date = ?",
            (user_id, today),
        ).fetchone()
        return row["query_count"] if row else 0
    finally:
        conn.close()


def increment_daily_query(user_id: str) -> None:
    """Atomically increment today's query count for the user (upsert)."""
    today = _today_utc()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO user_daily_quota (user_id, quota_date, query_count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, quota_date) DO UPDATE SET query_count = query_count + 1
            """,
            (user_id, today),
        )
        conn.commit()
    finally:
        conn.close()


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
