import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime

# ── Data Paths ───────────────────────────────────────────────────────────────
_DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".config", "dotghostboard")
_USER_DATA    = os.getenv("DOTGHOST_HOME", _DEFAULT_HOME)
os.makedirs(_USER_DATA, exist_ok=True)

DB_PATH      = os.path.join(_USER_DATA, "ghost.db")
THUMB_DIR    = os.path.join(_USER_DATA, "thumbnails")
CAPTURES_DIR = os.path.join(_USER_DATA, "captures")


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

        # Migration: add tags column for v1.3.0
        try:
            conn.execute("ALTER TABLE clipboard_items ADD COLUMN tags TEXT DEFAULT ''")
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

        # Create trusted_peers table for v1.5.0 (Sycn Phase)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trusted_peers (
                node_id       TEXT PRIMARY KEY,
                device_name   TEXT NOT NULL,
                shared_secret TEXT NOT NULL,
                ip_address    TEXT,
                created_at    TEXT NOT NULL
            )
        """)


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


# ─────────────────────────────────────────────
# TAGS  (W001)
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# COLLECTIONS  (W004)
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# EXPORT  (W008)
# ─────────────────────────────────────────────

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

# ══════════════════════════════════════════
# W008 — Export
# ══════════════════════════════════════════
def export_items(item_ids: list[int], fmt: str) -> str:
    """
    Export items to a formatted string.
    fmt: 'txt' or 'json'
    Returns the formatted string content.
    """
    import json as _json
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


# ─────────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────────
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
        thumb = os.path.join(THUMB_DIR, f"{item_id}.png")
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
        thumb = os.path.join(THUMB_DIR, f"{item_id}.png")
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
        thumb = os.path.join(THUMB_DIR, f"{row['id']}.png")
        if os.path.isfile(thumb):
            try:
                os.remove(thumb)
            except OSError:
                pass

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
# ECLIPSE  (E006) — Encryption helpers
# ─────────────────────────────────────────────

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
    Returns the number of items decrypted, or -1 if key is wrong.
    """
    secrets = get_secret_items()
    if not secrets:
        return 0
    count = 0
    for item in secrets:
        if decrypt_item_permanent(item["id"], key):
            count += 1
        else:
            return -1  # Wrong key — abort
    return count


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


# ─────────────────────────────────────────────
# TRUSTED PEERS (Sync Phase)
# ─────────────────────────────────────────────

def add_trusted_peer(node_id: str, device_name: str, shared_secret: str, ip: str = None) -> None:
    """Store a newly paired peer and its shared encryption key."""
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO trusted_peers (node_id, device_name, shared_secret, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (node_id, device_name, shared_secret, ip, now))


def get_trusted_peer(node_id: str) -> dict | None:
    """Retrieve peer info and shared secret by node_id."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM trusted_peers WHERE node_id = ?", (node_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_trusted_peers() -> list[dict]:
    """Retrieve a list of all paired devices."""
    with _db() as conn:
        cursor = conn.execute("SELECT * FROM trusted_peers ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


def remove_trusted_peer(node_id: str) -> bool:
    """Un-pair a device."""
    with _db() as conn:
        cursor = conn.execute("DELETE FROM trusted_peers WHERE node_id = ?", (node_id,))
        return cursor.rowcount > 0


def is_peer_trusted(node_id: str) -> bool:
    """Fast check for paired status."""
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM trusted_peers WHERE node_id = ? LIMIT 1", (node_id,)
        ).fetchone()
        return bool(row)