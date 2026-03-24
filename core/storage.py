import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime

DB_PATH    = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ghost.db")
BASE_DIR   = os.path.dirname(os.path.dirname(__file__))
THUMB_DIR  = os.path.join(BASE_DIR, "data", "thumbnails")
CAPTURES_DIR = os.path.join(BASE_DIR, "data", "captures")


# FIX #2: Context manager for DB connections to ensure proper cleanup
@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()   # Ensure connection is always closed


def init_db():
    """Create tables if they don't exist, run any needed migrations."""
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clipboard_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                type        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                preview     TEXT    DEFAULT NULL,
                is_pinned   INTEGER DEFAULT 0,
                sort_order  INTEGER DEFAULT 0,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
        """)
        # Migration: add sort_order to existing databases
        try:
            conn.execute("ALTER TABLE clipboard_items ADD COLUMN sort_order INTEGER DEFAULT 0")
        except Exception:
            pass  # column already exists


# ─────────────────────────────────────────────
# CREATE
# ─────────────────────────────────────────────
def add_item(item_type: str, content: str, preview: str = None) -> int:
    """
    Add a new item to the database.
    Returns the ID of the new item.
    """
    # Check if the item already exists (to prevent duplicates)
    existing = get_item_by_content(content)
    if existing:
        return existing["id"]

    now = datetime.now().isoformat()
    with _db() as conn:
        cursor = conn.execute("""
            INSERT INTO clipboard_items (type, content, preview, is_pinned, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
        """, (item_type, content, preview, now, now))
        return cursor.lastrowid


# ─────────────────────────────────────────────
# READ
# ─────────────────────────────────────────────
def get_all_items(limit: int = 200) -> list:
    """
    Retrieve all items.
    Pinned items first + descending order by date.
    """
    with _db() as conn:
        cursor = conn.execute("""
            SELECT * FROM clipboard_items
            ORDER BY is_pinned DESC, created_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_item_by_content(content: str) -> dict | None:
    """Get item by its content"""
    with _db() as conn:
        cursor = conn.execute(
            "SELECT * FROM clipboard_items WHERE content = ? LIMIT 1", (content,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_item_by_id(item_id: int) -> dict | None:
    """Get item by its ID"""
    with _db() as conn:
        cursor = conn.execute(
            "SELECT * FROM clipboard_items WHERE id = ?", (item_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def search_items(query: str) -> list:
    """Search text items only"""
    with _db() as conn:
        cursor = conn.execute("""
            SELECT * FROM clipboard_items
            WHERE type = 'text' AND content LIKE ?
            ORDER BY is_pinned DESC, created_at DESC
        """, (f"%{query}%",))
        return [dict(row) for row in cursor.fetchall()]


# ─────────────────────────────────────────────
# UPDATE
# ─────────────────────────────────────────────
def toggle_pin(item_id: int) -> bool:
    """
    Toggle pin status.
    Returns the new state (True = pinned).
    """
    item = get_item_by_id(item_id)
    if not item:
        return False

    new_state = 0 if item["is_pinned"] else 1
    now = datetime.now().isoformat()

    with _db() as conn:
        conn.execute("""
            UPDATE clipboard_items
            SET is_pinned = ?, updated_at = ?
            WHERE id = ?
        """, (new_state, now, item_id))
    return bool(new_state)


def update_preview(item_id: int, preview_path: str) -> None:
    """Store a thumbnail / preview path for an item (S002)."""
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET preview = ?, updated_at = ? WHERE id = ?",
            (preview_path, now, item_id)
        )


def update_sort_order(item_id: int, order: int) -> None:
    """Persist drag-and-drop sort order for a pinned card (S006)."""
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET sort_order = ? WHERE id = ?",
            (order, item_id)
        )


# ─────────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────────
def delete_item(item_id: int) -> bool:
    """Delete item — Pinned items are protected and won't be deleted"""
    item = get_item_by_id(item_id)
    if not item:
        return False
    if item["is_pinned"]:
        return False  # ← basic protection for pinned items

    with _db() as conn:
        conn.execute("DELETE FROM clipboard_items WHERE id = ?", (item_id,))
    return True


def delete_unpinned_items():
    """Delete all unpinned items (Clear History)"""
    with _db() as conn:
        conn.execute("DELETE FROM clipboard_items WHERE is_pinned = 0")


def get_stats() -> dict:
    """Quick statistics for the Dashboard"""
    with _db() as conn:
        total  = conn.execute("SELECT COUNT(*) FROM clipboard_items").fetchone()[0]
        pinned = conn.execute("SELECT COUNT(*) FROM clipboard_items WHERE is_pinned = 1").fetchone()[0]
        texts  = conn.execute("SELECT COUNT(*) FROM clipboard_items WHERE type = 'text'").fetchone()[0]
        images = conn.execute("SELECT COUNT(*) FROM clipboard_items WHERE type = 'image'").fetchone()[0]
    return {"total": total, "pinned": pinned, "texts": texts, "images": images}


# ─────────────────────────────────────────────
# CLEANUP (S003)
# ─────────────────────────────────────────────
def clean_old_captures(keep: int = 100) -> int:
    """
    Delete the oldest unpinned image/video items beyond the `keep` limit.
    Also removes their .png files from data/captures/ and data/thumbnails/.
    Returns the number of items deleted.
    """
    with _db() as conn:
        rows = conn.execute("""
            SELECT id, type, content, preview
            FROM clipboard_items
            WHERE is_pinned = 0 AND type IN ('image', 'video')
            ORDER BY created_at DESC
        """).fetchall()

    rows = [dict(r) for r in rows]
    to_delete = rows[keep:]   # everything beyond the keep-th newest

    if not to_delete:
        return 0

    deleted = 0
    for row in to_delete:
        # Remove capture file
        for path in (row["content"], row["preview"]):
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        # Also remove from thumbnails dir by item id
        thumb = os.path.join(THUMB_DIR, f"{row['id']}.png")
        if os.path.isfile(thumb):
            try:
                os.remove(thumb)
            except OSError:
                pass
        # Remove DB row
        with _db() as conn:
            conn.execute("DELETE FROM clipboard_items WHERE id = ?", (row["id"],))
        deleted += 1

    return deleted