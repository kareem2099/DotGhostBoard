"""
core/storage/database.py
────────────────────────
SQLite connection management and path configuration.
"""

import os
import sqlite3
from contextlib import contextmanager

# ── Data Paths ───────────────────────────────────────────────────────────────
_DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".config", "dotghostboard")
_USER_DATA    = os.getenv("DOTGHOST_HOME", _DEFAULT_HOME)
os.makedirs(_USER_DATA, exist_ok=True)

DB_PATH      = os.path.join(_USER_DATA, "ghost.db")
THUMB_DIR    = os.path.join(_USER_DATA, "thumbnails")
CAPTURES_DIR = os.path.join(_USER_DATA, "captures")


def get_db_path() -> str:
    """
    Return the active database path.
    Checks if core.storage has overridden DB_PATH (e.g. during test fixtures).
    """
    import sys
    storage_mod = sys.modules.get("core.storage")
    if storage_mod and hasattr(storage_mod, "DB_PATH"):
        return storage_mod.DB_PATH
    return DB_PATH


def get_thumb_dir() -> str:
    """
    Return the active thumbnails directory.
    Checks if core.storage has overridden THUMB_DIR.
    """
    import sys
    storage_mod = sys.modules.get("core.storage")
    if storage_mod and hasattr(storage_mod, "THUMB_DIR"):
        return storage_mod.THUMB_DIR
    return THUMB_DIR


def get_captures_dir() -> str:
    """
    Return the active captures directory.
    Checks if core.storage has overridden CAPTURES_DIR.
    """
    import sys
    storage_mod = sys.modules.get("core.storage")
    if storage_mod and hasattr(storage_mod, "CAPTURES_DIR"):
        return storage_mod.CAPTURES_DIR
    return CAPTURES_DIR


@contextmanager
def _db(db_path: str | None = None):
    """
    Context manager for DB connections to ensure proper commit/rollback/cleanup.
    """
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA secure_delete = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
