"""
Shared SQLite connection helper.
Uses WAL mode for concurrent reads alongside the RT poller writes.
"""
import sqlite3
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "transit.db"))
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory and WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Create all tables and indexes from schema.sql if they don't exist."""
    conn = get_connection()
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    _run_migrations(conn)
    conn.commit()
    conn.close()
    print(f"[db] Initialized database at {DB_PATH}")


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Add new columns to existing tables without dropping data (idempotent)."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    new_columns = [
        ("subscription_tier",        "TEXT NOT NULL DEFAULT 'free'"),
        ("subscription_expires_at",  "INTEGER"),
        ("stripe_customer_id",       "TEXT"),
        ("stripe_subscription_id",   "TEXT"),
    ]
    for col_name, col_def in new_columns:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
    conn.commit()
