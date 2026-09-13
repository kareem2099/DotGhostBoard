"""
core/security/vault/service.py
──────────────────────────────
High-level service managing The Vault session lifecycle and envelope encryption.
"""

from __future__ import annotations

import os
import base64
from typing import Optional
from core.crypto import (
    derive_vault_key,
    encrypt,
    decrypt,
    verify_password,
    secure_zero,
)
from core.security.vault.repository import VaultRepository
from core.security.vault.models import VaultItem, VaultSummary


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

    def add_secret(self, title: str, secret_text: str, category: str = "generic") -> int:
        """Encrypt and persist secret text to vault.db."""
        key = self._require_unlocked()
        ciphertext = encrypt(secret_text, key)
        return self._repo.add_item(title=title, ciphertext=ciphertext, category=category)

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
    ) -> bool:
        """Update an existing secret."""
        key = self._require_unlocked()
        ciphertext = encrypt(secret_text, key) if secret_text is not None else None
        return self._repo.update_item(
            item_id=item_id,
            title=title,
            ciphertext=ciphertext,
            category=category,
        )

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
