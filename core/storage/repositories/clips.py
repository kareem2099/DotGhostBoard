"""
core/storage/repositories/clips.py
──────────────────────────────────
Repository for clipboard items (text, image, video), encryption, search, and cleanup.
"""

import os
import json as _json
import hashlib
from datetime import datetime
from ..database import _db, get_thumb_dir
from .tags import get_tags


def _get_file_hash(filepath: str) -> str | None:
    """Calculate SHA-256 hash of a file for image duplicate detection."""
    if not filepath or not os.path.isfile(filepath):
        return None
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, PermissionError):
        return None


def add_item(item_type: str, content: str, preview: str = None) -> int:
    """
    Add a new item to the database.
    If the item already exists (by content or image hash), bump its updated_at
    (move to top) and increment its copy_count, then return the existing ID
    so the watcher can refresh the UI.
    """
    # 1. Direct content match (text string, video path, or identical image path)
    existing = get_item_by_content(content)
    if existing:
        now = datetime.now().isoformat()
        with _db() as conn:
            conn.execute(
                "UPDATE clipboard_items SET updated_at = ?, copy_count = copy_count + 1 WHERE id = ?",
                (now, existing["id"]),
            )
        return existing["id"]

    # 2. Image content hash match (detect duplicate screenshots / image pixel data)
    if item_type == "image" and os.path.isfile(content):
        new_hash = _get_file_hash(content)
        if new_hash:
            new_size = os.path.getsize(content)
            with _db() as conn:
                rows = conn.execute(
                    "SELECT id, content FROM clipboard_items WHERE type = 'image' ORDER BY updated_at DESC LIMIT 100"
                ).fetchall()

            for row in rows:
                existing_path = row["content"]
                if existing_path and os.path.isfile(existing_path):
                    if os.path.getsize(existing_path) == new_size:
                        if _get_file_hash(existing_path) == new_hash:
                            # Duplicate image detected! Remove temporary newly created file
                            try:
                                os.remove(content)
                            except OSError:
                                pass

                            now = datetime.now().isoformat()
                            with _db() as conn:
                                conn.execute(
                                    "UPDATE clipboard_items SET updated_at = ?, copy_count = copy_count + 1 WHERE id = ?",
                                    (now, row["id"]),
                                )
                            return row["id"]

    # 3. New item insertion
    now = datetime.now().isoformat()
    with _db() as conn:
        cursor = conn.execute("""
            INSERT INTO clipboard_items (type, content, preview, is_pinned, copy_count, created_at, updated_at)
            VALUES (?, ?, ?, 0, 1, ?, ?)
        """, (item_type, content, preview, now, now))
        return cursor.lastrowid


def increment_copy_count(item_id: int) -> int:
    """
    Increment the copy_count for an item (called when user presses the copy button).
    Returns the new copy_count value.
    """
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET copy_count = copy_count + 1 WHERE id = ?",
            (item_id,)
        )
        cursor = conn.execute(
            "SELECT copy_count FROM clipboard_items WHERE id = ?",
            (item_id,)
        )
        row = cursor.fetchone()
        return row["copy_count"] if row else 0


def reset_copy_count(item_id: int) -> bool:
    """Reset the copy_count for an item to 0. Returns True if updated, False if item not found."""
    with _db() as conn:
        cursor = conn.execute(
            "UPDATE clipboard_items SET copy_count = 0 WHERE id = ?",
            (item_id,)
        )
        return cursor.rowcount > 0


def get_all_items(limit: int = 200, offset: int = 0) -> list:
    """
    Retrieve all items.
    Pinned items first + descending order by date.
    """
    with _db() as conn:
        cursor = conn.execute("""
            SELECT * FROM clipboard_items
            ORDER BY is_pinned DESC, created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
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


def search_items(query: str, tag_filter: str | None = None, limit: int = 200, offset: int = 0) -> list[dict]:
    """
    Search text items by content.

    Args:
        query:      Free-text search (empty string → all text items).
        tag_filter: Optional tag string like '#code'. When provided, only
                    items that carry that tag are returned.

    Combines results as:  content LIKE query  AND  tag_filter (if set).
    """
    if tag_filter:
        tag = tag_filter.strip().lower()
        if not tag.startswith("#"):
            tag = f"#{tag}"

        sql = """
            SELECT * FROM clipboard_items
            WHERE type = 'text' AND content LIKE :query
              AND (
                  tags = :tag
                  OR tags LIKE :tag_start
                  OR tags LIKE :tag_mid
                  OR tags LIKE :tag_end
              )
            ORDER BY is_pinned DESC, created_at DESC
            LIMIT :limit OFFSET :offset
        """
        params = {
            "query":     f"%{query}%",
            "tag":       tag,
            "tag_start": f"{tag},%",
            "tag_mid":   f"%,{tag},%",
            "tag_end":   f"%,{tag}",
            "limit":     limit,
            "offset":    offset,
        }
        with _db() as conn:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    # ── simple path (no tag filter) — same behaviour as before ──
    with _db() as conn:
        cursor = conn.execute("""
            SELECT * FROM clipboard_items
            WHERE type = 'text' AND content LIKE ?
            ORDER BY is_pinned DESC, created_at DESC
            LIMIT ? OFFSET ?
        """, (f"%{query}%", limit, offset))
        return [dict(row) for row in cursor.fetchall()]


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


def update_item_field(item_id: int, field: str, value: any) -> None:
    """Update a specific field for an item with whitelist protection."""
    ALLOWED = {"is_secret", "is_pinned", "sort_order", "collection_id"}
    if field not in ALLOWED:
        raise ValueError(f"Field '{field}' is not whitelisted for direct update")
        
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            f"UPDATE clipboard_items SET {field} = ?, updated_at = ? WHERE id = ?",
            (value, now, item_id)
        )


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


def export_items_txt(item_ids: list[int]) -> str:
    """Export items as plain text. One block per item."""
    lines = []
    for iid in item_ids:
        item = get_item_by_id(iid)
        if not item:
            continue
        lines.append(f"[{item['type'].upper()}] {item['created_at']}")
        if item["type"] == "text":
            lines.append(item["content"])
        else:
            lines.append(item["content"])
        if item.get("tags"):
            lines.append(f"Tags: {item['tags']}")
        lines.append("")  # blank separator
    return "\n".join(lines)


def export_items_json(item_ids: list[int]) -> list[dict]:
    """Export items as a JSON-serializable list of dicts."""
    result = []
    for iid in item_ids:
        item = get_item_by_id(iid)
        if item:
            result.append({
                "id": item["id"],
                "type": item["type"],
                "content": item["content"],
                "tags": item.get("tags", ""),
                "is_pinned": item["is_pinned"],
                "created_at": item["created_at"],
            })
    return result


def export_items(item_ids: list[int], fmt: str) -> str:
    """
    Export items to a formatted string.
    fmt: 'txt' or 'json'
    Returns the formatted string content.
    """
    from datetime import datetime as _dt

    if fmt == "json":
        rows = []
        for iid in item_ids:
            item = get_item_by_id(iid)
            if item:
                rows.append({
                    "id":         item["id"],
                    "type":       item["type"],
                    "content":    item["content"],
                    "created_at": item["created_at"],
                    "tags":       get_tags(item["id"]),
                })
        return _json.dumps(rows, indent=2, ensure_ascii=False)

    else:  # txt
        lines = []
        for iid in item_ids:
            item = get_item_by_id(iid)
            if not item:
                continue
            ts = item.get("created_at", "")
            try:
                ts = _dt.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
            lines.append(f"[{ts}] ({item['type'].upper()})")
            lines.append(item["content"])
            tags = get_tags(item["id"])
            if tags:
                lines.append("Tags: " + ", ".join(tags))
            lines.append("─" * 48)
        return "\n".join(lines)


def delete_item(item_id: int, secure: bool = False) -> bool:
    """
    Delete item — pinned items are protected and won't be deleted.

    Args:
        item_id: ID of the item to delete.
        secure:  If True, overwrite file bytes before deletion (Eclipse).
                 Only applies to image/video items with a file on disk.
    """
    item = get_item_by_id(item_id)
    if not item:
        return False
    if item["is_pinned"]:
        return False  # ← basic protection for pinned items

    # Secure-delete file-based items if requested
    if secure and item["type"] in ("image", "video"):
        from core.secure_delete import secure_delete
        for path in (item["content"], item.get("preview")):
            if path and os.path.isfile(path):
                secure_delete(path)
        # Also secure-delete thumbnail
        thumb = os.path.join(get_thumb_dir(), f"{item_id}.png")
        if os.path.isfile(thumb):
            secure_delete(thumb)
    else:
        # Original cleanup: plain os.remove
        for path in (item["content"], item.get("preview")):
            if (
                path
                and item["type"] in ("image", "video")
                and os.path.isfile(path)
            ):
                try:
                    os.remove(path)
                except OSError:
                    pass
        # Also remove thumbnail if not secure
        thumb = os.path.join(get_thumb_dir(), f"{item_id}.png")
        if os.path.isfile(thumb):
            try:
                os.remove(thumb)
            except OSError:
                pass

    with _db() as conn:
        conn.execute("DELETE FROM clipboard_items WHERE id = ?", (item_id,))
    return True


def delete_unpinned_items():
    """Delete all unpinned items (Clear History) and their files"""
    with _db() as conn:
        rows = conn.execute("""
            SELECT id, type, content, preview
            FROM clipboard_items
            WHERE is_pinned = 0 AND type IN ('image', 'video')
        """).fetchall()

    for row in rows:
        # Remove original and preview files
        for path in (row["content"], row["preview"]):
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        # Remove auto-generated thumbnail
        thumb = os.path.join(get_thumb_dir(), f"{row['id']}.png")
        if os.path.isfile(thumb):
            try:
                os.remove(thumb)
            except OSError:
                pass

    with _db() as conn:
        conn.execute("DELETE FROM clipboard_items WHERE is_pinned = 0")


def mark_secret(item_id: int, secret: bool) -> None:
    """
    Toggle the is_secret flag on an item.

    NOTE: This only sets the flag — it does NOT encrypt/decrypt the content.
    Use encrypt_item() / decrypt_item() for that.
    """
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET is_secret = ?, updated_at = ? WHERE id = ?",
            (1 if secret else 0, now, item_id),
        )


def encrypt_item(item_id: int, key: bytes) -> bool:
    """
    Encrypt an item's content in-place using AES-256-GCM.
    Sets is_secret = 1 after encryption.

    Returns False if:
      - Item not found
      - Item is already encrypted (is_secret = 1)
      - Item type is not 'text' (binary items are referenced by path, not stored inline)
    """
    from core.crypto import encrypt as _encrypt
    item = get_item_by_id(item_id)
    if not item:
        return False
    if item.get("is_secret"):
        return False   # Already encrypted
    if item["type"] != "text":
        return False   # File paths are not encrypted — only text content

    ciphertext = _encrypt(item["content"], key)
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET content = ?, is_secret = 1, updated_at = ? WHERE id = ?",
            (ciphertext, now, item_id),
        )
    return True


def decrypt_item(item_id: int, key: bytes) -> str | None:
    """
    Decrypt and return the plaintext content of a secret item.
    Does NOT modify the database — returns plaintext for in-memory use only.

    Returns:
        Plaintext string  — if decryption succeeded.
        Plain content     — if item is not secret (pass-through).
        None              — if item not found or decryption fails.
    """
    from core.crypto import decrypt as _decrypt
    item = get_item_by_id(item_id)
    if not item:
        return None
    if not item.get("is_secret"):
        return item["content"]   # Not encrypted — return as-is
    try:
        return _decrypt(item["content"], key)
    except ValueError:
        return None   # Wrong key or corrupted data


def decrypt_item_permanent(item_id: int, key: bytes) -> bool:
    """
    Decrypt an item and store the plaintext back in the DB (un-secret it).
    Sets is_secret = 0 after decryption.

    Returns True on success, False if item not found / wrong key.
    """
    plaintext = decrypt_item(item_id, key)
    if plaintext is None:
        return False
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET content = ?, is_secret = 0, updated_at = ? WHERE id = ?",
            (plaintext, now, item_id),
        )
    return True


def get_secret_items() -> list[dict]:
    """Return all items marked as secret (is_secret = 1)."""
    with _db() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM clipboard_items
            WHERE is_secret = 1
            ORDER BY is_pinned DESC, created_at DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def encrypt_all_text_items(key: bytes) -> int:
    """
    Encrypt ALL unencrypted text items in one call.
    Useful when the user enables master password on an existing database.
    Returns the number of items encrypted.
    """
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id FROM clipboard_items
            WHERE type = 'text' AND is_secret = 0
            """
        ).fetchall()
    count = 0
    for row in rows:
        if encrypt_item(row["id"], key):
            count += 1
    return count


def decrypt_all_secret_items(key: bytes) -> int:
    """
    Permanently decrypt ALL secret items.
    Used when the user removes their master password.
    Two-phase atomic approach: verifies all items decrypt in-memory before mutating DB.
    Returns the number of items decrypted, or -1 if key is wrong or any item is corrupted.
    """
    secrets = get_secret_items()
    if not secrets:
        return 0

    decrypted: dict[int, str] = {}

    # Phase 1: verify everything before mutating DB
    for item in secrets:
        plain = decrypt_item(item["id"], key)
        if plain is None:
            return -1  # Wrong key or corrupted item — abort without DB mutation
        decrypted[item["id"]] = plain

    # Phase 2: commit all changes atomically under one transaction
    now = datetime.now().isoformat()
    with _db() as conn:
        for item_id, plain in decrypted.items():
            conn.execute(
                """
                UPDATE clipboard_items
                SET content = ?, is_secret = 0, updated_at = ?
                WHERE id = ?
                """,
                (plain, now, item_id),
            )

    return len(decrypted)


def reencrypt_all_secret_items(old_key: bytes, new_key: bytes) -> int:
    """
    Re-encrypt all secret items from old_key to new_key.
    Returns the count of re-encrypted items, or -1 if any item fails decryption.
    """
    from core.crypto import encrypt as _encrypt
    secrets = get_secret_items()
    if not secrets:
        return 0

    decrypted_map: dict[int, str] = {}
    for item in secrets:
        plain = decrypt_item(item["id"], old_key)
        if plain is None:
            return -1  # Abort on decryption failure
        decrypted_map[item["id"]] = plain

    now = datetime.now().isoformat()
    with _db() as conn:
        for item_id, plain in decrypted_map.items():
            new_ciphertext = _encrypt(plain, new_key)
            conn.execute(
                "UPDATE clipboard_items SET content = ?, updated_at = ? WHERE id = ?",
                (new_ciphertext, now, item_id),
            )
    return len(decrypted_map)


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
        thumb = os.path.join(get_thumb_dir(), f"{row['id']}.png")
        if os.path.isfile(thumb):
            try:
                os.remove(thumb)
            except OSError:
                pass
        deleted += 1

    # Bulk-delete all rows in a single transaction
    if to_delete:
        ids = [row["id"] for row in to_delete]
        placeholders = ",".join("?" * len(ids))
        with _db() as conn:
            conn.execute(
                f"DELETE FROM clipboard_items WHERE id IN ({placeholders})", ids
            )

    return deleted
