"""
core/storage/repositories/tags.py
─────────────────────────────────
Repository for item tags and tag management.
"""

from datetime import datetime
from ..database import _db


def _parse_tags(raw: str) -> list[str]:
    """Convert stored '#tag1,#tag2' string → clean list, drop empty strings."""
    return [t.strip() for t in raw.split(",") if t.strip()]


def _serialize_tags(tags: list[str]) -> str:
    """Convert list → '#tag1,#tag2' string ready for DB."""
    return ",".join(tags)


def get_tags(item_id: int) -> list[str]:
    """Return the list of tags for a given item. Empty list if item not found."""
    with _db() as conn:
        row = conn.execute(
            "SELECT tags FROM clipboard_items WHERE id = ?", (item_id,)
        ).fetchone()
    if not row:
        return []
    return _parse_tags(row["tags"] or "")


def add_tag(item_id: int, tag: str) -> list[str]:
    """
    Add a tag to an item (idempotent — won't add duplicates).
    Tag is normalised to lowercase and prefixed with '#' if missing.
    Returns the updated tag list.
    """
    tag = tag.strip().lower()
    if not tag.startswith("#"):
        tag = f"#{tag}"

    current = get_tags(item_id)
    if tag in current:
        return current  # already there — nothing to do

    updated = current + [tag]
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET tags = ?, updated_at = ? WHERE id = ?",
            (_serialize_tags(updated), now, item_id),
        )
    return updated


def remove_tag(item_id: int, tag: str) -> list[str]:
    """
    Remove a tag from an item.
    Returns the updated tag list (unchanged if tag wasn't present).
    """
    tag = tag.strip().lower()
    if not tag.startswith("#"):
        tag = f"#{tag}"

    current = get_tags(item_id)
    if tag not in current:
        return current

    updated = [t for t in current if t != tag]
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET tags = ?, updated_at = ? WHERE id = ?",
            (_serialize_tags(updated), now, item_id),
        )
    return updated


def get_items_by_tag(tag: str, limit: int = 200, offset: int = 0) -> list[dict]:
    """
    Return all items that contain the given tag.
    Pinned items first, then descending by date.
    """
    tag = tag.strip().lower()
    if not tag.startswith("#"):
        tag = f"#{tag}"

    # Four LIKE patterns cover every position in the comma-separated string:
    # exact match, tag at start, tag in middle, tag at end.
    with _db() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM clipboard_items
            WHERE tags = ?
               OR tags LIKE ?
               OR tags LIKE ?
               OR tags LIKE ?
            ORDER BY is_pinned DESC, created_at DESC
            LIMIT ? OFFSET ?
            """,
            (tag, f"{tag},%", f"%,{tag},%", f"%,{tag}", limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_all_tags() -> list[str]:
    """Return a deduplicated list of all tags used across all items."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT tags FROM clipboard_items WHERE tags != ''"
        ).fetchall()
    tags = set()
    for row in rows:
        for tag in _parse_tags(row["tags"]):
            tags.add(tag)
    return sorted(tags)


def rename_tag(old_tag: str, new_tag: str) -> int:
    """
    Rename a tag globally across all items.
    Returns the number of items updated.
    """
    old_tag = old_tag.strip().lower()
    new_tag = new_tag.strip().lower()
    if not old_tag.startswith("#"):
        old_tag = f"#{old_tag}"
    if not new_tag.startswith("#"):
        new_tag = f"#{new_tag}"
    if old_tag == new_tag:
        return 0

    updated = 0
    items = get_items_by_tag(old_tag)
    for item in items:
        tags = get_tags(item["id"])
        if old_tag in tags:
            tags = [new_tag if t == old_tag else t for t in tags]
            now = datetime.now().isoformat()
            with _db() as conn:
                conn.execute(
                    "UPDATE clipboard_items SET tags = ?, updated_at = ? WHERE id = ?",
                    (_serialize_tags(tags), now, item["id"]),
                )
            updated += 1
    return updated


def delete_tag(tag: str) -> int:
    """
    Remove a tag globally from all items.
    Returns the number of items updated.
    """
    tag = tag.strip().lower()
    if not tag.startswith("#"):
        tag = f"#{tag}"

    updated = 0
    items = get_items_by_tag(tag)
    for item in items:
        tags = get_tags(item["id"])
        if tag in tags:
            tags = [t for t in tags if t != tag]
            now = datetime.now().isoformat()
            with _db() as conn:
                conn.execute(
                    "UPDATE clipboard_items SET tags = ?, updated_at = ? WHERE id = ?",
                    (_serialize_tags(tags), now, item["id"]),
                )
            updated += 1
    return updated
