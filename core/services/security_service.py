"""
core/services/security_service.py
─────────────────────────────────
Session security orchestrator, auto-lock manager, and encryption coordinator.
"""

from __future__ import annotations

import time
from typing import Optional
from core import crypto, storage
from core.crypto import secure_zero
from core.security.vault import VaultService


class SecurityService:
    """
    Coordinates session lock state, master password lifecycle, Eclipse item encryption,
    and ties into VaultService with domain-separated keys and envelope encryption.
    """

    def __init__(
        self,
        crypto_mod=None,
        storage_mod=None,
        vault_service: Optional[VaultService] = None,
    ):
        self._crypto = crypto_mod or crypto
        self._storage = storage_mod or storage
        self._vault = vault_service or VaultService()

        self._active_key: Optional[bytearray] = None
        self._is_locked: bool = True
        self._last_activity: float = time.time()

    # ── Master Password Lifecycle ─────────────────────────────────────────────

    def has_master_password(self) -> bool:
        """Check if master password has been configured."""
        return self._crypto.has_master_password()

    def setup_master_password(self, password: str) -> None:
        """Configure master password and unlock session immediately."""
        if self.has_master_password():
            raise RuntimeError(
                "Master password already exists; use change_master_password()."
            )
        self._crypto.save_master_password(password)
        if not self.unlock(password):
            raise RuntimeError("Failed to unlock session after password setup.")

    def verify_master_password(self, password: str) -> bool:
        """Check if password matches stored master password."""
        return self._crypto.verify_password(password)

    def change_master_password(self, old_password: str, new_password: str) -> tuple[bool, str]:
        """
        Safely rotate master password:
        1. Verifies old password.
        2. Validates new password length.
        3. Atomically re-encrypts all Eclipse items in ghost.db.
        4. Re-wraps the Vault DEK with the new KEK (zero re-encryption of vault items).
        5. Updates master password verifier on disk.
        """
        if not self.verify_master_password(old_password):
            return False, "Current master password is incorrect."

        new_password = new_password.strip()
        if len(new_password) < 6:
            return False, "New master password must be at least 6 characters."

        old_eclipse_key = self._crypto.derive_key(old_password)
        new_eclipse_key = self._crypto.derive_key(new_password)

        old_vault_kek = self._crypto.derive_vault_key(old_password)
        new_vault_kek = self._crypto.derive_vault_key(new_password)

        # 1. Re-encrypt Eclipse secret items in ghost.db
        reencrypted_count = self._storage.reencrypt_all_secret_items(old_eclipse_key, new_eclipse_key)
        if reencrypted_count == -1:
            return False, "Failed to re-encrypt existing Eclipse secret items. Password change aborted."

        # 2. Re-wrap Vault DEK
        if not self._vault.rewrap_dek(old_vault_kek, new_vault_kek):
            # Rollback Eclipse items
            self._storage.reencrypt_all_secret_items(new_eclipse_key, old_eclipse_key)
            return False, "Failed to re-wrap Vault key. Password change aborted."

        # 3. Save new master password verifier
        self._crypto.save_master_password(new_password)

        # 4. Update in-memory session if unlocked
        if not self.is_locked:
            if self._active_key is not None:
                secure_zero(self._active_key)
            self._active_key = bytearray(new_eclipse_key)

        self.touch()
        return True, "Master password changed successfully."

    def remove_master_password(self, password: str) -> tuple[bool, int, str]:
        """
        Safely remove master password:
        1. Verifies password.
        2. Checks that Vault contains 0 items (prevents accidental unrecoverable loss of vault secrets).
        3. Permanently decrypts all secret items in ghost.db.
        4. Removes verifier and salt from disk and locks session.
        """
        if not self.verify_master_password(password):
            return False, 0, "Master password is incorrect."

        vault_count = self._vault.count()
        if vault_count > 0:
            return (
                False,
                0,
                f"Cannot remove master password: Vault contains {vault_count} item(s). "
                "Please export or delete all vault items first.",
            )

        eclipse_key = self._crypto.derive_key(password)
        count = self._storage.decrypt_all_secret_items(eclipse_key)
        if count == -1:
            return False, 0, "Could not decrypt one or more items. Master password was NOT removed."

        # Remove verifier and salt, and reset empty vault envelope
        self.lock()
        self._crypto.remove_master_password()
        self._vault.reset_empty_envelope()

        return True, count, f"Master password removed. {count} item(s) decrypted."

    # ── Session Lifecycle ─────────────────────────────────────────────────────

    @property
    def is_locked(self) -> bool:
        """Return True if session is locked or if master password is set and unauthenticated."""
        if not self.has_master_password():
            return False
        return self._is_locked or self._active_key is None

    @property
    def active_key(self) -> Optional[bytes]:
        """Return current in-memory Eclipse key or None if locked."""
        if self._active_key is None or self._is_locked:
            return None
        return bytes(self._active_key)

    @property
    def vault(self) -> VaultService:
        """Access the attached VaultService."""
        return self._vault

    def unlock(self, password: str) -> bool:
        """
        Authenticate against master password.
        Derives Eclipse key and Vault key with independent domain separation.
        """
        if not self._crypto.verify_password(password):
            return False

        # 1. Derive and store Eclipse key
        eclipse_key = self._crypto.derive_key(password)
        self._active_key = bytearray(eclipse_key)

        # 2. Derive domain-separated Vault KEK and unlock Vault DEK
        vault_kek = self._crypto.derive_vault_key(password)
        self._vault.unlock_with_key(vault_kek)

        self._is_locked = False
        self.touch()
        return True

    def set_session_key(self, key: bytes) -> None:
        """
        Set an externally-derived Eclipse key and mark the session as unlocked.
        Used by SecurityController when a key is obtained outside the normal
        password-unlock flow (e.g., restored from LockScreen dialog).

        Caller is responsible for ensuring `key` is a valid AES-256 key (32 bytes).
        """
        if self._active_key is not None:
            secure_zero(self._active_key)
        self._active_key = bytearray(key)
        self._is_locked = False
        self.touch()

    def lock(self) -> None:
        """Lock session, scrub keys in-memory, and lock Vault."""
        if self._active_key is not None:
            secure_zero(self._active_key)
            self._active_key = None
        self._is_locked = True
        self._vault.lock()

    def touch(self) -> None:
        """Record user activity to reset auto-lock countdown."""
        self._last_activity = time.time()

    def is_auto_lock_expired(self, timeout_seconds: int) -> bool:
        """
        Check if inactivity exceeds timeout_seconds.
        timeout_seconds <= 0 disables auto-lock.
        """
        if timeout_seconds <= 0 or self.is_locked:
            return False
        return (time.time() - self._last_activity) >= timeout_seconds

    # ── Clip Encryption Operations (Eclipse in ghost.db) ─────────────────────

    def encrypt_clip(self, item_id: int) -> bool:
        """Encrypt a clip in ghost.db using active key."""
        key = self.active_key
        if key is None:
            return False
        return self._storage.encrypt_item(item_id, key)

    def decrypt_clip_for_view(self, item_id: int) -> Optional[str]:
        """Decrypt a clip in-memory for preview/copying. Does not alter DB."""
        key = self.active_key
        if key is None:
            return None
        return self._storage.decrypt_item(item_id, key)

    def decrypt_clip_permanent(self, item_id: int) -> bool:
        """Permanently remove encryption from a clip in ghost.db."""
        key = self.active_key
        if key is None:
            return False
        return self._storage.decrypt_item_permanent(item_id, key)
