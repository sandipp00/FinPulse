"""SQLite access shared by the API: connections and the account schema."""
import sqlite3

from backend import config
from src.data.schema import MARKET_PRICES_DDL, MARKET_PRICES_INDEX_DDL

ACCOUNT_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    email_verified_at INTEGER
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);

-- One-time links emailed to users. Only the SHA-256 of a token is stored.
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL CHECK (purpose IN ('verify', 'reset')),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens (user_id, purpose);

-- Networks each account has signed in from (keyed, hashed addresses). During a
-- distributed password-guessing attack these keep the real owner able to sign in.
CREATE TABLE IF NOT EXISTS login_ips (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip_hash TEXT NOT NULL,
    last_seen INTEGER NOT NULL,
    PRIMARY KEY (user_id, ip_hash)
);

-- A random key generated once per installation, used to hash IP addresses.
CREATE TABLE IF NOT EXISTS app_secret (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    value BLOB NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    """A read/write connection with sane defaults (autocommit off, as usual)."""
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Upgrade a database created by an older version of the schema."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "email_verified_at" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified_at INTEGER")


def init_db() -> None:
    """Create everything the API needs. Safe to run on every start.

    WAL mode lets the market-data readers and the account writers work at the
    same time without blocking each other.
    """
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(ACCOUNT_SCHEMA)
        _add_missing_columns(conn)
        conn.execute("INSERT OR IGNORE INTO app_secret (id, value) VALUES (1, randomblob(32))")
        # An empty market_prices table (no historical data loaded yet) should
        # produce empty API responses, not "no such table" errors.
        conn.execute(MARKET_PRICES_DDL)
        conn.execute(MARKET_PRICES_INDEX_DDL)
        conn.commit()
    finally:
        conn.close()
