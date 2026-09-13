"""
core/storage/migrations.py
──────────────────────────
Database initialization, legacy schema adoption, and versioned migrations.
"""

import sqlite3
from .database import _db

CURRENT_SCHEMA_VERSION = 1


def _looks_like_legacy_database(conn: sqlite3.Connection) -> bool:
    """Check if the database has tables from earlier DotGhostBoard v1.x before init_db runs."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='clipboard_items';"
    )
    return cursor.fetchone() is not None


def _ensure_base_schema(conn: sqlite3.Connection) -> None:
    """Ensure all core tables and columns exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clipboard_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            preview     TEXT    DEFAULT NULL,
            is_pinned   INTEGER DEFAULT 0,
            sort_order  INTEGER DEFAULT 0,
            copy_count  INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        )
    """)

    # Migration: add sort_order to existing databases
    try:
        conn.execute("ALTER TABLE clipboard_items ADD COLUMN sort_order INTEGER DEFAULT 0")
    except Exception:
        pass  # column already exists

    # Migration: add tags column for v1.3.0
    try:
        conn.execute("ALTER TABLE clipboard_items ADD COLUMN tags TEXT DEFAULT ''")
    except Exception:
        pass  # column already exists

    # Migration: add copy_count for v1.5.x
    try:
        conn.execute("ALTER TABLE clipboard_items ADD COLUMN copy_count INTEGER DEFAULT 0")
    except Exception:
        pass  # column already exists

    # Create collections table for v1.3.0
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        )
    """)

    # Migration: add collection_id to existing databases
    try:
        conn.execute("ALTER TABLE clipboard_items ADD COLUMN collection_id INTEGER DEFAULT NULL REFERENCES collections(id)")
    except Exception:
        pass  # column already exists

    # Migration: add is_secret for Eclipse v1.4.0
    try:
        conn.execute(
            "ALTER TABLE clipboard_items ADD COLUMN is_secret INTEGER DEFAULT 0"
        )
    except Exception:
        pass  # column already exists

    # trusted_peers table for v1.5.0 (Sync Phase)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trusted_peers (
            node_id       TEXT PRIMARY KEY,
            device_name   TEXT NOT NULL,
            shared_secret TEXT NOT NULL,
            ip_address    TEXT,
            created_at    TEXT NOT NULL
        )
    """)


def _adopt_legacy_schema(conn: sqlite3.Connection) -> None:
    """Stamp a legacy v1.x database to CURRENT_SCHEMA_VERSION."""
    print("[Migration] Legacy v1.x database detected. Adopting current schema...")
    try:
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")
        print(f"[Migration] Successfully migrated legacy database to schema v{CURRENT_SCHEMA_VERSION}.")
    except Exception as exc:
        print(f"[Migration] FATAL ERROR during legacy adoption: {exc}")
        raise


def _initialize_fresh_schema(conn: sqlite3.Connection) -> None:
    """Stamp a newly created database with CURRENT_SCHEMA_VERSION."""
    conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")


def init_db(db_path: str | None = None) -> None:
    """
    Create tables if they don't exist, run migrations, and adopt legacy databases.
    Idempotent and safe across fresh and legacy instances.
    """
    with _db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        row = cursor.fetchone()
        current_version = row[0] if row else 0

        if current_version > CURRENT_SCHEMA_VERSION:
            raise RuntimeError(
                "Database schema is newer than this DotGhostBoard build "
                f"(database={current_version}, supported={CURRENT_SCHEMA_VERSION})."
            )

        # Critical: detect legacy BEFORE creating tables!
        was_legacy = (current_version == 0) and _looks_like_legacy_database(conn)

        _ensure_base_schema(conn)

        if current_version == 0:
            if was_legacy:
                _adopt_legacy_schema(conn)
            else:
                _initialize_fresh_schema(conn)
        elif current_version < CURRENT_SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")
