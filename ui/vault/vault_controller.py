"""
ui/vault/vault_controller.py
────────────────────────────
Behavioral controller managing The Vault cryptographic operations,
in-memory reveals, clipboard copying, self-paste suppression, and auto-scrub.

v2.0.0 Cerberus — Phase 7 Vault UI Subsystem.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from PyQt6.QtCore import QMimeData, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.constants import VAULT_IDLE_TIMEOUT_SECONDS
from core.security.vault import (
    VaultLockedError,
    VaultService,
    VaultSummary,
)

logger = logging.getLogger(__name__)


class VaultController(QObject):
    """
    Controller coordinating between the VaultService backend and the VaultPanel UI.
    Dispatches Qt signals for state changes and enforces secure in-memory handling.
    """

    vault_unlocked = pyqtSignal()
    vault_locked = pyqtSignal()
    secrets_changed = pyqtSignal()
    secret_revealed = pyqtSignal(int)        # item_id (never emit plaintext over signal bus)
    secret_copy_starting = pyqtSignal()     # emitted immediately before clipboard.setText()
    secret_copied = pyqtSignal(int)          # item_id
    status_message = pyqtSignal(str)
    panel_visibility_changed = pyqtSignal(bool)

    def __init__(
        self,
        vault_service: Optional[VaultService] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._service = vault_service if vault_service is not None else VaultService()
        self._pending_clipboard_hash: Optional[str] = None

        self._clipboard_scrub_timer = QTimer(self)
        self._clipboard_scrub_timer.setSingleShot(True)
        self._clipboard_scrub_timer.timeout.connect(self._on_clipboard_scrub_timeout)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self.lock)

    @property
    def service(self) -> VaultService:
        return self._service

    @property
    def is_unlocked(self) -> bool:
        return self._service.is_unlocked

    def touch(self, idle_seconds: int = VAULT_IDLE_TIMEOUT_SECONDS) -> None:
        """Reset the vault idle auto-lock countdown timer if unlocked."""
        if self.is_unlocked:
            self._idle_timer.start(idle_seconds * 1000)

    def unlock(self, password: str) -> bool:
        """
        Authenticate against master password and unwrap the Vault DEK.
        Emits vault_unlocked on success and resets idle timer.
        """
        success = self._service.unlock(password)
        if success:
            self.touch()
            self.vault_unlocked.emit()
            self.status_message.emit("🔓 The Vault unlocked ✓")
        else:
            self.status_message.emit("⚠ Failed to unlock The Vault: Incorrect password.")
        return success

    def lock(self, *, wipe_clipboard: bool = True) -> None:
        """
        Lock the Vault, scrub DEK from memory, purge pending clipboard secret
        (if wipe_clipboard=True), and notify UI.
        """
        self._idle_timer.stop()
        if wipe_clipboard:
            self._clipboard_scrub_timer.stop()
            self._on_clipboard_scrub_timeout()
        self._service.lock()
        self.vault_locked.emit()
        self.status_message.emit("🔒 The Vault locked")

    def add_secret(self, title: str, secret_text: str, category: str = "generic") -> int:
        """
        Encrypt and persist a new secret to vault.db.
        """
        if not self.is_unlocked:
            self.status_message.emit("⚠ Cannot add secret: Vault is locked.")
            raise VaultLockedError("Vault is locked.")

        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Secret title cannot be empty.")
        if not secret_text:
            raise ValueError("Secret content cannot be empty.")

        item_id = self._service.add_secret(clean_title, secret_text, category=category)
        self.secrets_changed.emit()
        self.status_message.emit(f"Secret '{clean_title}' encrypted & saved ✓")
        return item_id

    def update_secret(
        self,
        item_id: int,
        title: Optional[str] = None,
        secret_text: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        """
        Update an existing secret's metadata or payload.
        """
        if not self.is_unlocked:
            self.status_message.emit("⚠ Cannot update secret: Vault is locked.")
            raise VaultLockedError("Vault is locked.")

        clean_title = title.strip() if title is not None else None
        if clean_title == "":
            raise ValueError("Secret title cannot be empty.")

        success = self._service.update_secret(
            item_id=item_id,
            title=clean_title,
            secret_text=secret_text,
            category=category,
        )
        if success:
            self.secrets_changed.emit()
            self.status_message.emit("Secret updated ✓")
        return success

    def delete_secret(self, item_id: int) -> bool:
        """
        Permanently delete a secret from vault.db.
        """
        if not self.is_unlocked:
            self.status_message.emit("⚠ Cannot delete secret: Vault is locked.")
            raise VaultLockedError("Vault is locked.")

        success = self._service.delete_secret(item_id)
        if success:
            self.secrets_changed.emit()
            self.status_message.emit("Secret deleted from Vault")
        return success

    def reveal_secret(self, item_id: int) -> Optional[str]:
        """
        Decrypt and return a secret payload in-memory for ephemeral card display.
        Catches decryption errors gracefully.
        """
        if not self.is_unlocked:
            self.status_message.emit("⚠ Vault is locked — unlock first to reveal.")
            return None

        try:
            plaintext = self._service.get_secret(item_id)
        except Exception as exc:
            logger.error("Failed to decrypt secret id=%s: %s", item_id, exc)
            self.status_message.emit("⚠ Decryption error: Failed to retrieve secret.")
            return None

        if plaintext is not None:
            self.secret_revealed.emit(item_id)
            self.status_message.emit("Secret revealed in-memory (hidden on lock)")
        else:
            self.status_message.emit("⚠ Secret not found or failed to decrypt.")
        return plaintext

    def copy_secret(self, item_id: int, auto_clear_seconds: int = 30) -> bool:
        """
        Decrypt secret in-memory, notify watcher to prevent capture into clips history,
        and schedule auto-scrub of system clipboard.
        """
        if not self.is_unlocked:
            self.status_message.emit("⚠ Vault is locked — unlock first to copy.")
            return False

        try:
            plaintext = self._service.get_secret(item_id)
        except Exception as exc:
            logger.error("Failed to decrypt secret id=%s for copy: %s", item_id, exc)
            self.status_message.emit("⚠ Decryption error: Failed to copy secret.")
            return False

        if plaintext is None:
            self.status_message.emit("⚠ Failed to decrypt secret for copy.")
            return False

        # 1. Announce intent to copy secret so ClipboardWatcher marks self-paste
        self.secret_copy_starting.emit()

        # 2. Put plaintext into clipboard with password manager hint
        clipboard = QApplication.clipboard()
        if clipboard:
            md = QMimeData()
            md.setText(plaintext)
            md.setData("x-kde-passwordManagerHint", b"secret")
            clipboard.setMimeData(md)
            self._schedule_clipboard_auto_clear(plaintext, timeout_ms=auto_clear_seconds * 1000)
            self.secret_copied.emit(item_id)
            self.status_message.emit(f"Secret copied to clipboard (auto-clears in {auto_clear_seconds}s) ✓")
            return True
        return False

    def _schedule_clipboard_auto_clear(self, plaintext: str, timeout_ms: int = 30_000) -> None:
        """Store only SHA-256 digest of copied secret and start auto-clear countdown."""
        expected_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        self._pending_clipboard_hash = expected_hash
        self._clipboard_scrub_timer.start(timeout_ms)

    def _on_clipboard_scrub_timeout(self) -> None:
        """Scrub clipboard only if it still contains the secret (matched via digest)."""
        if not self._pending_clipboard_hash:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            current_text = clipboard.text()
            if current_text:
                cur_hash = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
                if cur_hash == self._pending_clipboard_hash:
                    clipboard.clear()
                    clipboard.setText("")
                    self.status_message.emit("Clipboard cleared")
        self._pending_clipboard_hash = None

    def list_secrets(
        self,
        category: Optional[str] = None,
        search_query: str = "",
    ) -> list[VaultSummary]:
        """
        Retrieve secret metadata summaries with optional category and search filter.
        Safe to call even when locked (metadata remains unencrypted).
        """
        cat = category.strip().lower() if category and category != "all" else None
        summaries = self._service.list_secrets(category=cat)
        if search_query:
            q = search_query.strip().lower()
            summaries = [s for s in summaries if q in s.title.lower()]
        return summaries

    def count(self, category: Optional[str] = None) -> int:
        """Return total secret count for category."""
        cat = category.strip().lower() if category and category != "all" else None
        return self._service.count(category=cat)

    def find_duplicate(self, plaintext: str) -> Optional[VaultSummary]:
        """
        Search in-memory for an existing secret matching plaintext using constant-time comparison.
        Returns VaultSummary if found, None if not found or if Vault is locked.
        Safe against offline brute-force attacks by keeping search in-memory only.
        """
        if not self.is_unlocked:
            return None
        import hmac
        needle = plaintext.encode("utf-8")
        for s in self._service.list_secrets(category=None):
            try:
                other = self._service.get_secret(s.id)
            except Exception:
                continue
            if other is not None and hmac.compare_digest(other.encode("utf-8"), needle):
                return s
        return None
