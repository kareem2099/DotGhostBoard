"""
core/storage/repositories/collections.py
────────────────────────────────────────
Repository for collections and item organization.
"""

from datetime import datetime
from ..database import _db


def create_collection(name: str) -> int:
    """Create a new collection. Returns its ID. Ignores duplicate names."""
    name = name.strip()
    if not name:
        raise ValueError("Collection name cannot be empty")
    now = datetime.now().isoformat()
    with _db() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO collections (name, created_at, updated_at) VALUES (?, ?, ?)",
            (name, now, now),
        )
        if cursor.lastrowid:
            return cursor.lastrowid
        # Already exists — return existing ID
        row = conn.execute(
            "SELECT id FROM collections WHERE name = ?", (name,)
        ).fetchone()
        return row["id"] if row else 0


def delete_collection(collection_id: int) -> bool:
    """Delete a collection. Items in it become uncategorized (collection_id = NULL)."""
    with _db() as conn:
        # Unlink items first
        conn.execute(
            "UPDATE clipboard_items SET collection_id = NULL WHERE collection_id = ?",
            (collection_id,),
        )
        conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
    return True


def get_collections() -> list[dict]:
    """Return all collections with item counts."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT c.id, c.name, c.created_at,
                   COUNT(ci.id) AS item_count
            FROM collections c
            LEFT JOIN clipboard_items ci ON ci.collection_id = c.id
            GROUP BY c.id
            ORDER BY c.name
        """).fetchall()
        return [dict(r) for r in rows]


def get_collection_by_id(collection_id: int) -> dict | None:
    """Get a single collection by ID."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM collections WHERE id = ?", (collection_id,)
        ).fetchone()
        return dict(row) if row else None


def rename_collection(collection_id: int, new_name: str) -> bool:
    """Rename an existing collection."""
    new_name = new_name.strip()
    if not new_name:
        return False
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "UPDATE collections SET name = ?, updated_at = ? WHERE id = ?",
            (new_name, now, collection_id),
        )
    return True


def move_to_collection(item_id: int, collection_id: int | None) -> None:
    """Move an item to a collection (or uncategorized if collection_id is None)."""
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET collection_id = ?, updated_at = ? WHERE id = ?",
            (collection_id, now, item_id),
        )


def get_items_by_collection(collection_id: int | None, limit: int = 200, offset: int = 0) -> list[dict]:
    """
    Return items in a specific collection.
    If collection_id is None, return uncategorized items.
    """
    with _db() as conn:
        if collection_id is None:
            cursor = conn.execute("""
                SELECT * FROM clipboard_items
                WHERE collection_id IS NULL
                ORDER BY is_pinned DESC, created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
        else:
            cursor = conn.execute("""
                SELECT * FROM clipboard_items
                WHERE collection_id = ?
                ORDER BY is_pinned DESC, created_at DESC
                LIMIT ? OFFSET ?
            """, (collection_id, limit, offset))
        return [dict(row) for row in cursor.fetchall()]
