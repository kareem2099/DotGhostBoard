"""
core/security/vault/repository.py
─────────────────────────────────
Data access layer for The Vault (vault_items table).

Repository persists encrypted secret payloads.
Non-secret listing metadata such as title/category remains plaintext by design.
"""

from __future__ import annotations

from typing import Optional
from core.security.vault.database import _vault_db, init_vault_db
from core.security.vault.models import VaultItem, VaultSummary


class VaultRepository:
    """Repository handling CRUD operations on vault.db."""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        init_vault_db(self._db_path)

    def add_item(
        self,
        title: str,
        ciphertext: str,
        category: str = "generic",
        metadata_encrypted: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> int:
        """Insert an encrypted vault item and return its id."""
        with _vault_db(self._db_path) as cur:
            cur.execute("""
                INSERT INTO vault_items (title, category, ciphertext, metadata_encrypted, expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (title.strip(), category.strip().lower(), ciphertext, metadata_encrypted, expires_at))
            return cur.lastrowid

    def get_item(self, item_id: int) -> Optional[VaultItem]:
        """Fetch single VaultItem by id."""
        with _vault_db(self._db_path) as cur:
            cur.execute("""
                SELECT id, title, category, ciphertext, metadata_encrypted, expires_at, created_at, updated_at
                FROM vault_items
                WHERE id = ?
            """, (item_id,))
            row = cur.fetchone()
            if not row:
                return None
            return VaultItem(
                id=row["id"],
                title=row["title"],
                category=row["category"],
                ciphertext=row["ciphertext"],
                metadata_encrypted=row["metadata_encrypted"],
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
                expires_at=str(row["expires_at"]) if row["expires_at"] else None,
            )

    def list_items(
        self,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VaultItem]:
        """Fetch page of VaultItem records."""
        with _vault_db(self._db_path) as cur:
            if category:
                cur.execute("""
                    SELECT id, title, category, ciphertext, metadata_encrypted, expires_at, created_at, updated_at
                    FROM vault_items
                    WHERE category = ?
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                """, (category.strip().lower(), limit, offset))
            else:
                cur.execute("""
                    SELECT id, title, category, ciphertext, metadata_encrypted, expires_at, created_at, updated_at
                    FROM vault_items
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))

            items = []
            for row in cur.fetchall():
                items.append(VaultItem(
                    id=row["id"],
                    title=row["title"],
                    category=row["category"],
                    ciphertext=row["ciphertext"],
                    metadata_encrypted=row["metadata_encrypted"],
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                    expires_at=str(row["expires_at"]) if row["expires_at"] else None,
                ))
            return items

    def list_summaries(
        self,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VaultSummary]:
        """Fetch metadata-only summaries for UI presentation."""
        with _vault_db(self._db_path) as cur:
            if category:
                cur.execute("""
                    SELECT id, title, category, expires_at, created_at, updated_at
                    FROM vault_items
                    WHERE category = ?
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                """, (category.strip().lower(), limit, offset))
            else:
                cur.execute("""
                    SELECT id, title, category, expires_at, created_at, updated_at
                    FROM vault_items
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))

            return [
                VaultSummary(
                    id=row["id"],
                    title=row["title"],
                    category=row["category"],
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                    expires_at=str(row["expires_at"]) if row["expires_at"] else None,
                )
                for row in cur.fetchall()
            ]

    def update_item(
        self,
        item_id: int,
        title: Optional[str] = None,
        ciphertext: Optional[str] = None,
        category: Optional[str] = None,
        metadata_encrypted: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Update fields of an existing vault item."""
        updates: list[str] = []
        params: list[object] = []

        if title is not None:
            updates.append("title = ?")
            params.append(title.strip())
        if ciphertext is not None:
            updates.append("ciphertext = ?")
            params.append(ciphertext)
        if category is not None:
            updates.append("category = ?")
            params.append(category.strip().lower())
        if metadata_encrypted is not None:
            updates.append("metadata_encrypted = ?")
            params.append(metadata_encrypted)
        if expires_at is not None:
            updates.append("expires_at = ?")
            params.append(expires_at if expires_at != "" else None)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(item_id)

        with _vault_db(self._db_path) as cur:
            cur.execute(f"""
                UPDATE vault_items
                SET {", ".join(updates)}
                WHERE id = ?
            """, params)
            return cur.rowcount > 0

    def delete_item(self, item_id: int) -> bool:
        """Delete vault item by id along with its history."""
        with _vault_db(self._db_path) as cur:
            cur.execute("DELETE FROM vault_item_history WHERE vault_item_id = ?", (item_id,))
            cur.execute("DELETE FROM vault_items WHERE id = ?", (item_id,))
            return cur.rowcount > 0

    def add_history_entry(
        self,
        vault_item_id: int,
        ciphertext: str,
        max_entries: int = 3,
    ) -> int:
        """Record a previous encrypted ciphertext version, capping at max_entries."""
        with _vault_db(self._db_path) as cur:
            cur.execute("""
                INSERT INTO vault_item_history (vault_item_id, ciphertext, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (vault_item_id, ciphertext))
            entry_id = cur.lastrowid

            # Keep only the newest max_entries
            cur.execute("""
                DELETE FROM vault_item_history
                WHERE vault_item_id = ?
                  AND id NOT IN (
                      SELECT id FROM vault_item_history
                      WHERE vault_item_id = ?
                      ORDER BY created_at DESC, id DESC
                      LIMIT ?
                  )
            """, (vault_item_id, vault_item_id, max_entries))
            return entry_id

    def get_history(self, vault_item_id: int, limit: int = 3) -> list[dict]:
        """Fetch history entries for a vault item ordered newest first."""
        with _vault_db(self._db_path) as cur:
            cur.execute("""
                SELECT id, vault_item_id, ciphertext, created_at
                FROM vault_item_history
                WHERE vault_item_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            """, (vault_item_id, limit))
            return [
                {
                    "id": row["id"],
                    "vault_item_id": row["vault_item_id"],
                    "ciphertext": row["ciphertext"],
                    "created_at": str(row["created_at"]),
                }
                for row in cur.fetchall()
            ]

    def count_history(self, vault_item_id: int) -> int:
        """Return total number of history entries for this vault item."""
        with _vault_db(self._db_path) as cur:
            cur.execute(
                "SELECT COUNT(*) FROM vault_item_history WHERE vault_item_id = ?",
                (vault_item_id,),
            )
            return cur.fetchone()[0]

    def delete_history_entry(self, history_id: int) -> bool:
        """Delete single history entry by id."""
        with _vault_db(self._db_path) as cur:
            cur.execute("DELETE FROM vault_item_history WHERE id = ?", (history_id,))
            return cur.rowcount > 0

    def count_items(self, category: Optional[str] = None) -> int:
        """Return total number of vault items."""
        with _vault_db(self._db_path) as cur:
            if category:
                cur.execute("SELECT COUNT(*) FROM vault_items WHERE category = ?", (category.strip().lower(),))
            else:
                cur.execute("SELECT COUNT(*) FROM vault_items")
            return cur.fetchone()[0]

    def get_metadata(self, key: str) -> Optional[str]:
        """Fetch metadata value by key."""
        with _vault_db(self._db_path) as cur:
            cur.execute("SELECT value FROM vault_metadata WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else None

    def set_metadata(self, key: str, value: str) -> None:
        """Insert or replace metadata KV pair."""
        with _vault_db(self._db_path) as cur:
            cur.execute("""
                INSERT INTO vault_metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, value))

    def delete_metadata(self, key: str) -> bool:
        """Remove metadata entry."""
        with _vault_db(self._db_path) as cur:
            cur.execute("DELETE FROM vault_metadata WHERE key = ?", (key,))
            return cur.rowcount > 0
