import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ghost.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # convert rows to dict-like objects
    return conn


def init_db():
    """Create tables if they don't exist"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clipboard_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT    NOT NULL,          -- 'text' | 'image' | 'video'
            content     TEXT    NOT NULL,          -- text or file path
            preview     TEXT    DEFAULT NULL,      -- preview image path (for images/videos)
            is_pinned   INTEGER DEFAULT 0,         -- 0 = normal | 1 = pinned
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


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
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clipboard_items (type, content, preview, is_pinned, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
        """, (item_type, content, preview, now, now))
        conn.commit()
        new_id = cursor.lastrowid
        return new_id
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[Storage] Error adding item: {e}")
        raise
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────
# READ
# ─────────────────────────────────────────────
def get_all_items(limit: int = 200) -> list:
    """
    Retrieve all items.
    Pinned items first + descending order by date.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM clipboard_items
        ORDER BY is_pinned DESC, created_at DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_item_by_content(content: str) -> dict:
    """Get item by its content"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clipboard_items WHERE content = ? LIMIT 1", (content,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_item_by_id(item_id: int) -> dict:
    """Get item by its ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clipboard_items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def search_items(query: str) -> list:
    """Search text items only"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM clipboard_items
        WHERE type = 'text' AND content LIKE ?
        ORDER BY is_pinned DESC, created_at DESC
    """, (f"%{query}%",))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


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

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE clipboard_items
        SET is_pinned = ?, updated_at = ?
        WHERE id = ?
    """, (new_state, now, item_id))
    conn.commit()
    conn.close()
    return bool(new_state)


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

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clipboard_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return True


def delete_unpinned_items():
    """Delete all unpinned items (Clear History)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clipboard_items WHERE is_pinned = 0")
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Quick statistics for the Dashboard"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM clipboard_items")
    total = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as pinned FROM clipboard_items WHERE is_pinned = 1")
    pinned = cursor.fetchone()["pinned"]
    cursor.execute("SELECT COUNT(*) as texts FROM clipboard_items WHERE type = 'text'")
    texts = cursor.fetchone()["texts"]
    cursor.execute("SELECT COUNT(*) as images FROM clipboard_items WHERE type = 'image'")
    images = cursor.fetchone()["images"]
    conn.close()
    return {"total": total, "pinned": pinned, "texts": texts, "images": images}
