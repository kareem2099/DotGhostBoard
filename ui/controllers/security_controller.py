"""
ui/controllers/security_controller.py
─────────────────────────────────────
Controller managing session security, lock/unlock lifecycle,
Eclipse encryption/decryption, and secret item resolution.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QDialog, QMessageBox, QWidget

from core.services.security_service import SecurityService
from ui.lock_screen import LockScreen

logger = logging.getLogger(__name__)


class SecurityController(QObject):
    """
    Behavioral controller for session authentication and Eclipse cryptographic actions.
    Communicates via Qt signals without directly coupling to UI presentation widgets.
    """
    lock_state_changed = pyqtSignal(bool)           # is_locked: bool
    item_security_changed = pyqtSignal(int)          # item_id: int
    copy_payload_ready = pyqtSignal(int, dict)       # item_id: int, item_payload: dict
    secret_copy_failed = pyqtSignal(int, str)        # item_id: int, reason: str
    auto_lock_triggered = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(
        self,
        service: SecurityService,
        parent_window: Optional[QWidget] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._service = service
        self._parent_window = parent_window

        self._auto_lock_timer = QTimer(self)
        self._auto_lock_timer.setSingleShot(True)
        self._auto_lock_timer.timeout.connect(self._on_auto_lock_timeout)

    @property
    def auto_lock_timer(self) -> QTimer:
        return self._auto_lock_timer

    def reset_auto_lock(self, minutes: int = 0) -> None:
        """Reset or disable the auto-lock timer based on minutes setting."""
        if minutes > 0 and self.has_master_password and not self.is_locked:
            self._auto_lock_timer.start(minutes * 60 * 1000)
        else:
            self._auto_lock_timer.stop()

    def _on_auto_lock_timeout(self) -> None:
        self.auto_lock_triggered.emit()

    @property
    def service(self) -> SecurityService:
        return self._service

    @property
    def is_locked(self) -> bool:
        return self._service.is_locked

    @property
    def has_master_password(self) -> bool:
        return self._service.has_master_password()

    @property
    def active_key(self) -> Optional[bytes]:
        return self._service.active_key

    def set_active_key(self, key: Optional[bytes]) -> None:
        """Explicitly set or clear the session encryption key."""
        if key is None:
            self._service.lock()
        else:
            self._service.set_session_key(key)

        self.lock_state_changed.emit(self.is_locked)


    def prompt_unlock(self, parent_widget: Optional[QWidget] = None) -> bool:
        """
        Display LockScreen dialog to authenticate user.
        Returns True if authenticated successfully.
        """
        dlg_parent = parent_widget or self._parent_window
        dlg = LockScreen(setup=False, parent=dlg_parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            key = dlg.get_key()
            self.set_active_key(key)
            self.status_message.emit("🔓 Unlocked")
            return True
        return False

    def lock(self) -> None:
        """Lock session and scrub keys."""
        self._auto_lock_timer.stop()
        self._service.lock()
        self.lock_state_changed.emit(True)

    def handle_secret_copy(self, item_id: int, item_data: dict) -> None:
        """
        Resolve a secret item for clipboard copy:
        1. Prompts for unlock if session is locked.
        2. Decrypts content in-memory.
        3. Emits copy_payload_ready(item_id, payload) on success.
        """
        if self.is_locked:
            unlocked = self.prompt_unlock()
            if not unlocked or self.is_locked:
                self.secret_copy_failed.emit(item_id, "Session is locked — unlock to copy secret.")
                self.status_message.emit("⚠ Session is locked — unlock to copy secret.")
                return

        plaintext = self._service.decrypt_clip_for_view(item_id)
        if plaintext is None:
            self.secret_copy_failed.emit(item_id, "Decryption failed — wrong key or corrupted data.")
            self.status_message.emit("⚠ Decryption failed — wrong key or corrupted data.")
            return

        payload = dict(item_data)
        payload["content"] = plaintext
        self.copy_payload_ready.emit(item_id, payload)

    def reveal_secret(self, item_id: int) -> Optional[str]:
        """Decrypt a secret item in-memory for preview on card."""
        if self.is_locked:
            self.status_message.emit("⚠ Session is locked — unlock first to reveal secrets.")
            return None

        plaintext = self._service.decrypt_clip_for_view(item_id)
        if plaintext is None:
            self.status_message.emit("⚠ Decryption failed — wrong key or corrupted data.")
            return None

        self.status_message.emit("🔓 Secret revealed  (visible until locked)")
        return plaintext

    def encrypt_item(self, item_id: int, parent_widget: Optional[QWidget] = None) -> bool:
        """Encrypt an item on demand using the active session key."""
        if self.is_locked:
            dlg_parent = parent_widget or self._parent_window
            QMessageBox.information(
                dlg_parent,
                "Unlock Required",
                "Please unlock the session first.\nUse the 🔒 button in the top bar.",
            )
            return False

        success = self._service.encrypt_clip(item_id)
        if success:
            self.status_message.emit("🔐 Item encrypted ✓")
            self.item_security_changed.emit(item_id)
        else:
            self.status_message.emit("⚠ Could not encrypt item.")
        return success

    def decrypt_item(
        self,
        item_id: int,
        confirm: bool = True,
        parent_widget: Optional[QWidget] = None,
    ) -> bool:
        """Permanently decrypt an item, restoring plaintext storage."""
        dlg_parent = parent_widget or self._parent_window
        if self.is_locked:
            QMessageBox.information(
                dlg_parent,
                "Unlock Required",
                "Please unlock the session first.",
            )
            return False

        if confirm:
            reply = QMessageBox.question(
                dlg_parent,
                "Remove Encryption",
                "Permanently decrypt this item?\nIt will be stored as plain text again.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        success = self._service.decrypt_clip_permanent(item_id)
        if success:
            self.status_message.emit("🔓 Item decrypted ✓")
            self.item_security_changed.emit(item_id)
        else:
            self.status_message.emit("⚠ Decryption failed — wrong key?")
        return success
