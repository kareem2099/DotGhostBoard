"""
core/security/vault/database.py
───────────────────────────────
Isolated SQLite storage for The Vault (vault.db).

Completely separated from ghost.db to guarantee boundary isolation.
Payloads are encrypted using an envelope Data Encryption Key (DEK).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator

_DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".config", "dotghostboard")
_USER_DATA    = os.getenv("DOTGHOST_HOME", _DEFAULT_HOME)
VAULT_DB_PATH = os.path.join(_USER_DATA, "vault.db")

VAULT_SCHEMA_VERSION = 1


def get_vault_db_path() -> str:
    """Return the active vault database path, supporting test monkeypatching."""
    import sys
    vault_db_mod = sys.modules.get("core.security.vault.database")
    if vault_db_mod and hasattr(vault_db_mod, "VAULT_DB_PATH"):
        return vault_db_mod.VAULT_DB_PATH
    return VAULT_DB_PATH


@contextmanager
def _vault_db(path: str | None = None) -> Generator[sqlite3.Cursor, None, None]:
    """
    Context manager for vault.db connections.
    Always uses WAL mode and enforces foreign keys and 0600 file permissions.
    """
    target = path or get_vault_db_path()
    parent = os.path.dirname(os.path.abspath(target))
    os.makedirs(parent, mode=0o700, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass

    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA secure_delete = ON;")

    try:
        os.chmod(target, 0o600)
    except OSError:
        pass

    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_vault_db(path: str | None = None) -> None:
    """
    Initialize schema and versioning for vault.db.
    Guarantees version tracking and downgrade protection.
    """
    with _vault_db(path) as cur:
        cur.execute("PRAGMA user_version;")
        v = cur.fetchone()[0]

        if v > VAULT_SCHEMA_VERSION:
            raise RuntimeError(
                f"Vault database schema version {v} is newer than supported version {VAULT_SCHEMA_VERSION}. "
                "Downgrading is not supported."
            )

        cur.execute("""
            CREATE TABLE IF NOT EXISTS vault_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'generic',
                ciphertext TEXT NOT NULL,
                metadata_encrypted TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vault_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_vault_category ON vault_items(category);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_vault_updated ON vault_items(updated_at DESC);
        """)

        if v < VAULT_SCHEMA_VERSION:
            cur.execute(f"PRAGMA user_version = {VAULT_SCHEMA_VERSION};")
