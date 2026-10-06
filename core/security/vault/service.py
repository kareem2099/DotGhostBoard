"""
core/security/vault/service.py
──────────────────────────────
High-level service managing The Vault session lifecycle and envelope encryption.
"""

from __future__ import annotations

import os
import base64
import hmac
import threading
from typing import Optional
from core.crypto import (
    derive_vault_key,
    encrypt,
    decrypt,
    verify_password,
    secure_zero,
)
from core.security.vault.repository import VaultRepository
from core.security.vault.models import VaultSummary


class VaultLockedError(RuntimeError):
    """Raised when an operation requires an unlocked Vault session."""
    pass


class VaultService:
    """
    Manages session unlock state, key lifecycle, and encrypted CRUD for The Vault.

    Uses envelope encryption: entries are encrypted with a random Data Encryption Key (DEK),
    which is stored wrapped by a Key Encryption Key (KEK) derived from the Master Password.
    This enables instant, safe password rotation without re-encrypting existing vault entries.
    Provides best-effort scrubbing of mutable in-memory key buffers on lock.
    """

    def __init__(self, repository: Optional[VaultRepository] = None):
        self._repo = repository or VaultRepository()
        self._vault_dek: Optional[bytearray] = None
        self._is_unlocked: bool = False
        # Process-local recognition only: never persist password hashes or retain
        # the DEK for matching after auto-lock. This key cannot decrypt the Vault.
        self._recognition_key = os.urandom(32)
        self._recognition: dict[int, tuple[str, bytes]] = {}
        self._recognition_lock = threading.RLock()

    @property
    def is_unlocked(self) -> bool:
        return self._is_unlocked and self._vault_dek is not None

    def _unwrap_or_create_dek(self, vault_kek: bytes) -> bytes:
        """Unwrap stored DEK or create and wrap a fresh random 256-bit DEK."""
        wrapped = self._repo.get_metadata("wrapped_dek")
        if wrapped is None:
            if self._repo.count_items() > 0:
                raise RuntimeError(
                    "Vault contains encrypted items but wrapped DEK is missing."
                )
            raw_dek = os.urandom(32)
            dek_b64 = base64.urlsafe_b64encode(raw_dek).decode("ascii")
            wrapped = encrypt(dek_b64, vault_kek)
            self._repo.set_metadata("wrapped_dek", wrapped)
            return raw_dek
        else:
            dek_b64 = decrypt(wrapped, vault_kek)
            return base64.urlsafe_b64decode(dek_b64.encode("ascii"))

    def unlock(self, password: str) -> bool:
        """
        Verify master password, derive Vault KEK, and unwrap Vault DEK.
        Returns True if unlocked successfully, False otherwise.
        """
        if not verify_password(password):
            return False

        kek = derive_vault_key(password)
        try:
            dek = self._unwrap_or_create_dek(kek)
            self._vault_dek = bytearray(dek)
            self._is_unlocked = True
            self.match_clipboard_secret("")
            return True
        except Exception:
            self.lock()
            return False

    def unlock_with_key(self, vault_kek: bytes) -> None:
        """Directly unlock with a pre-derived vault KEK (used by SecurityService coordinator)."""
        self.lock()
        dek = self._unwrap_or_create_dek(vault_kek)
        self._vault_dek = bytearray(dek)
        self._is_unlocked = True
        self.match_clipboard_secret("")

    def rewrap_dek(self, old_kek: bytes, new_kek: bytes) -> bool:
        """
        Rotate master password by re-wrapping the Vault DEK with the new KEK.
        Does NOT touch or re-encrypt individual vault items.
        """
        wrapped = self._repo.get_metadata("wrapped_dek")
        if wrapped is None:
            if self._repo.count_items() > 0:
                return False
            return True

        try:
            dek_b64 = decrypt(wrapped, old_kek)
            new_wrapped = encrypt(dek_b64, new_kek)
            self._repo.set_metadata("wrapped_dek", new_wrapped)
            if self._is_unlocked:
                raw_dek = base64.urlsafe_b64decode(dek_b64.encode("ascii"))
                if self._vault_dek is not None:
                    secure_zero(self._vault_dek)
                self._vault_dek = bytearray(raw_dek)
            return True
        except Exception:
            return False

    def reset_empty_envelope(self) -> None:
        """Safely delete wrapped DEK metadata only if vault is completely empty."""
        if self.count() != 0:
            raise RuntimeError("Cannot reset envelope on non-empty Vault.")
        self.lock()
        self._repo.delete_metadata("wrapped_dek")

    def lock(self) -> None:
        """Lock the vault and scrub the DEK buffer from memory."""
        if self._vault_dek is not None:
            secure_zero(self._vault_dek)
            self._vault_dek = None
        self._is_unlocked = False

    def _require_unlocked(self) -> bytes:
        if not self.is_unlocked or self._vault_dek is None:
            raise VaultLockedError("Vault is locked. Unlock before accessing secrets.")
        return bytes(self._vault_dek)

    def add_secret(
        self,
        title: str,
        secret_text: str,
        category: str = "generic",
        expires_at: Optional[str] = None,
    ) -> int:
        """Encrypt and persist secret text to vault.db."""
        key = self._require_unlocked()
        ciphertext = encrypt(secret_text, key)
        item_id = self._repo.add_item(
            title=title,
            ciphertext=ciphertext,
            category=category,
            expires_at=expires_at,
        )
        self._remember_secret(item_id, ciphertext, secret_text)
        return item_id

    def _secret_digest(self, plaintext: str) -> bytes:
        # Clipboard capture normalizes surrounding whitespace in the same way.
        return hmac.digest(self._recognition_key, plaintext.strip().encode("utf-8"), "sha256")

    def _remember_secret(self, item_id: int, ciphertext: str, plaintext: str) -> None:
        with self._recognition_lock:
            self._recognition[item_id] = (ciphertext, self._secret_digest(plaintext))

    def match_clipboard_secret(self, plaintext: str) -> bool | None:
        """True: stored secret; False: checked non-secret; None: unlock required.

        Inspect every page, including changes made through imports/other service
        instances. Cached keyed digests survive auto-lock, but never go to disk.
        A cold locked Vault cannot establish a negative match safely.
        """
        needle = self._secret_digest(plaintext)
        seen = set()
        matched = False
        complete = True
        offset = 0
        with self._recognition_lock:
            while True:
                items = self._repo.list_items(limit=100, offset=offset)
                for item in items:
                    seen.add(item.id)
                    cached = self._recognition.get(item.id)
                    if cached is None or cached[0] != item.ciphertext:
                        self._recognition.pop(item.id, None)
                        if self.is_unlocked:
                            try:
                                value = decrypt(item.ciphertext, self._require_unlocked())
                                self._remember_secret(item.id, item.ciphertext, value)
                            except Exception:
                                complete = False
                        else:
                            complete = False
                        cached = self._recognition.get(item.id)
                    if cached and hmac.compare_digest(cached[1], needle):
                        matched = True
                if len(items) < 100:
                    break
                offset += len(items)
            self._recognition = {
                item_id: value for item_id, value in self._recognition.items() if item_id in seen
            }
        return True if matched else (False if complete else None)

    def find_duplicate(self, plaintext: str) -> Optional[VaultSummary]:
        """Find an exact duplicate across all pages, while unlocked."""
        if not self.is_unlocked:
            return None
        needle = plaintext.encode("utf-8")
        offset = 0
        while True:
            summaries = self._repo.list_summaries(limit=100, offset=offset)
            for summary in summaries:
                try:
                    other = self.get_secret(summary.id)
                except Exception:
                    continue
                if other is not None and hmac.compare_digest(other.encode("utf-8"), needle):
                    return summary
            if len(summaries) < 100:
                return None
            offset += len(summaries)

    def get_secret(self, item_id: int) -> Optional[str]:
        """Fetch and decrypt secret payload."""
        key = self._require_unlocked()
        item = self._repo.get_item(item_id)
        if not item:
            return None
        return decrypt(item.ciphertext, key)

    def update_secret(
        self,
        item_id: int,
        title: Optional[str] = None,
        secret_text: Optional[str] = None,
        category: Optional[str] = None,
        save_history: bool = True,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Update an existing secret, preserving previous ciphertext in history if secret_text changes."""
        key = self._require_unlocked()
        ciphertext = None
        if secret_text is not None:
            if save_history:
                existing_item = self._repo.get_item(item_id)
                if existing_item and existing_item.ciphertext:
                    try:
                        existing_plain = decrypt(existing_item.ciphertext, key)
                        if existing_plain != secret_text:
                            self._repo.add_history_entry(item_id, existing_item.ciphertext, max_entries=3)
                    except Exception:
                        pass
            ciphertext = encrypt(secret_text, key)

        updated = self._repo.update_item(
            item_id=item_id,
            title=title,
            ciphertext=ciphertext,
            category=category,
            expires_at=expires_at,
        )
        if updated and ciphertext is not None:
            self._remember_secret(item_id, ciphertext, secret_text)
        return updated

    def get_secret_history(self, item_id: int, limit: int = 3) -> list[dict]:
        """Fetch and decrypt historical secret versions for an item."""
        key = self._require_unlocked()
        records = self._repo.get_history(item_id, limit=limit)
        results = []
        for r in records:
            try:
                plaintext = decrypt(r["ciphertext"], key)
                results.append({
                    "id": r["id"],
                    "vault_item_id": r["vault_item_id"],
                    "plaintext": plaintext,
                    "created_at": r["created_at"],
                })
            except Exception:
                pass
        return results

    def restore_secret_history(self, item_id: int, history_id: int) -> bool:
        """Restore a historical secret value as the current active secret."""
        key = self._require_unlocked()
        records = self._repo.get_history(item_id, limit=10)
        target = next((r for r in records if r["id"] == history_id), None)
        if not target:
            return False
        plaintext = decrypt(target["ciphertext"], key)
        # Update with save_history=True so the replaced current secret is preserved
        return self.update_secret(item_id, secret_text=plaintext, save_history=True)

    def count_secret_history(self, item_id: int) -> int:
        """Return count of historical versions."""
        return self._repo.count_history(item_id)

    def delete_secret(self, item_id: int) -> bool:
        """Delete secret from vault.db."""
        self._require_unlocked()
        return self._repo.delete_item(item_id)

    def list_secrets(self, category: Optional[str] = None) -> list[VaultSummary]:
        """
        List summaries of stored secrets (metadata: title, category, timestamps).
        Safe to call even while locked to show available entries.
        """
        return self._repo.list_summaries(category=category)

    def count(self, category: Optional[str] = None) -> int:
        """Return total number of items stored in the vault."""
        return self._repo.count_items(category=category)
