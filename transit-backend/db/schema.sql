-- ============================================================
-- DRT AI TRANSIT ASSISTANT — DATABASE SCHEMA
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- STATIC TABLES (loaded once from GTFS zip)
-- ============================================================

CREATE TABLE IF NOT EXISTS stops (
    stop_id   TEXT PRIMARY KEY,
    stop_name TEXT,
    stop_lat  REAL,
    stop_lon  REAL
);

CREATE TABLE IF NOT EXISTS routes (
    route_id         TEXT PRIMARY KEY,
    route_short_name TEXT,
    route_long_name  TEXT,
    route_type       INTEGER
);

CREATE TABLE IF NOT EXISTS trips (
    trip_id       TEXT PRIMARY KEY,
    route_id      TEXT,
    service_id    TEXT,
    trip_headsign TEXT,
    direction_id  INTEGER
);

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id        TEXT,
    stop_sequence  INTEGER,
    stop_id        TEXT,
    arrival_time   TEXT,   -- HH:MM:SS (may exceed 24:00:00 for overnight trips)
    departure_time TEXT,
    PRIMARY KEY (trip_id, stop_sequence)
);

CREATE TABLE IF NOT EXISTS calendar (
    service_id  TEXT PRIMARY KEY,
    monday      INTEGER,
    tuesday     INTEGER,
    wednesday   INTEGER,
    thursday    INTEGER,
    friday      INTEGER,
    saturday    INTEGER,
    sunday      INTEGER,
    start_date  TEXT,  -- YYYYMMDD
    end_date    TEXT   -- YYYYMMDD
);

CREATE TABLE IF NOT EXISTS calendar_dates (
    service_id     TEXT,
    date           TEXT,   -- YYYYMMDD
    exception_type INTEGER -- 1=added, 2=removed
);

-- ============================================================
-- REAL-TIME TABLES (written by poller every 30s)
-- ============================================================

CREATE TABLE IF NOT EXISTS rt_trip_updates (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at           INTEGER DEFAULT (strftime('%s','now')),
    trip_id               TEXT,
    route_id              TEXT,
    start_date            TEXT,
    stop_sequence         INTEGER,
    stop_id               TEXT,
    arrival_time          INTEGER,   -- unix timestamp
    departure_time        INTEGER,   -- unix timestamp
    schedule_relationship TEXT
);

CREATE TABLE IF NOT EXISTS rt_vehicle_positions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at           INTEGER DEFAULT (strftime('%s','now')),
    vehicle_id            TEXT,
    trip_id               TEXT,
    route_id              TEXT,
    latitude              REAL,
    longitude             REAL,
    bearing               REAL,
    speed                 REAL,
    current_stop_sequence INTEGER
);

CREATE TABLE IF NOT EXISTS rt_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at INTEGER DEFAULT (strftime('%s','now')),
    alert_id    TEXT,
    route_id    TEXT,
    stop_id     TEXT,
    header      TEXT,
    description TEXT,
    effect      TEXT
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_rt_trip_updates_trip
    ON rt_trip_updates(trip_id, start_date, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_rt_alerts_route
    ON rt_alerts(route_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_stop_times_stop
    ON stop_times(stop_id);

CREATE INDEX IF NOT EXISTS idx_trips_route
    ON trips(route_id);

CREATE INDEX IF NOT EXISTS idx_rt_vehicle_trip
    ON rt_vehicle_positions(trip_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_stops_location
    ON stops(stop_lat, stop_lon);

-- ============================================================
-- USER AUTH TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id                     TEXT PRIMARY KEY,              -- UUID
    email                  TEXT UNIQUE NOT NULL,
    password_hash          TEXT,                          -- NULL for OAuth-only users
    display_name           TEXT NOT NULL DEFAULT '',
    auth_provider          TEXT NOT NULL DEFAULT 'local', -- 'local' | 'google' | 'facebook'
    provider_id            TEXT,                          -- OAuth provider's user ID
    is_verified            INTEGER NOT NULL DEFAULT 0,
    subscription_tier      TEXT NOT NULL DEFAULT 'free',  -- 'free' | 'premium'
    subscription_expires_at INTEGER,                      -- unix timestamp, NULL = no expiry
    stripe_customer_id     TEXT,
    stripe_subscription_id TEXT,
    created_at             INTEGER DEFAULT (strftime('%s','now')),
    updated_at             INTEGER DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_users_email
    ON users(email);

CREATE INDEX IF NOT EXISTS idx_users_provider
    ON users(auth_provider, provider_id);

CREATE INDEX IF NOT EXISTS idx_reset_token_hash
    ON password_reset_tokens(token_hash);

-- ============================================================
-- CHAT HISTORY TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS chat_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    messages   TEXT NOT NULL,                        -- JSON array of {role, content} objects
    created_at INTEGER DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
    ON chat_sessions(user_id, created_at DESC);

-- Trigger: after inserting a new chat session, delete any rows beyond the 5 most recent for that user.
CREATE TRIGGER IF NOT EXISTS trg_limit_chat_sessions
AFTER INSERT ON chat_sessions
FOR EACH ROW
BEGIN
    DELETE FROM chat_sessions
    WHERE user_id = NEW.user_id
      AND id NOT IN (
          SELECT id FROM chat_sessions
          WHERE user_id = NEW.user_id
          ORDER BY created_at DESC
          LIMIT 5
      );
END;

-- ============================================================
-- MONETIZATION TABLES
-- ============================================================

-- Daily query quota for free-tier users (one row per user per UTC date)
CREATE TABLE IF NOT EXISTS user_daily_quota (
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    quota_date  TEXT NOT NULL,   -- 'YYYY-MM-DD' UTC
    query_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, quota_date)
);

CREATE INDEX IF NOT EXISTS idx_user_daily_quota
    ON user_daily_quota(user_id, quota_date);

-- Single-use ad verification tokens (proves user watched the ad before calling /chat)
CREATE TABLE IF NOT EXISTS ad_tokens (
    id         TEXT PRIMARY KEY,   -- UUID
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER DEFAULT (strftime('%s','now')),
    expires_at INTEGER NOT NULL,   -- created_at + 300 (5-min TTL)
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ad_tokens_user
    ON ad_tokens(user_id, used);
