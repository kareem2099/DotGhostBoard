"""
ui/vault/send_to_vault.py
─────────────────────────
Coordinator for moving clipboard items directly into The Vault, and managing
in-memory candidate secret interceptions with non-intrusive masked toasts.

Decoupled from Dashboard to maintain strict line count limits (<= 500 lines).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from core.security.detector import SecretDetector
from core import storage
from ui.widgets.secret_toast import SecretDetectedToast

if TYPE_CHECKING:
    from ui.dashboard import Dashboard

logger = logging.getLogger(__name__)


def attach_send_to_vault(dashboard: Dashboard) -> None:
    """
    Attach 'Send to Vault' item migration and secret interception handlers
    to the Dashboard window.
    """
    import hashlib
    from PyQt6.QtCore import QTimer

    detector = SecretDetector()
    active_toast: list[Optional[SecretDetectedToast]] = [None]
    abs_timer: list[Optional[QTimer]] = [None]
    kept_hashes: set[str] = set()
    handled: dict[str, str] = {}

    def _scrub_candidate():
        if abs_timer[0]:
            try:
                abs_timer[0].stop()
                abs_timer[0].deleteLater()
            except Exception:
                pass
            abs_timer[0] = None

        if active_toast[0]:
            try:
                active_toast[0].scrub()
                active_toast[0].hide()
                active_toast[0].close()
                active_toast[0].deleteLater()
            except Exception:
                pass
            active_toast[0] = None

    def _show_already_saved(where_saved: str) -> None:
        _scrub_candidate()
        toast = SecretDetectedToast("", parent=dashboard, already_saved=where_saved)
        active_toast[0] = toast
        toast.sig_dismissed.connect(_scrub_candidate)

        toast.adjustSize()
        x_pos = max(20, dashboard.width() - toast.width() - 20)
        y_pos = max(20, dashboard.height() - toast.height() - 30)
        toast.move(x_pos, y_pos)
        toast.show()

        if not dashboard.isVisible():
            tray_mgr = getattr(dashboard, "tray_manager", None)
            if tray_mgr and hasattr(tray_mgr, "show_message"):
                tray_mgr.show_message(
                    "DotGhostBoard — Already Secured 🛡️",
                    f"Secret already protected in {where_saved}.",
                    timeout=4000,
                )
        dashboard.statusBar().showMessage(f"🛡️ Secret already protected in {where_saved}")

    def _auto_save_eclipse_fallback(cand: str):
        """Fallback: encrypt into history as an Eclipse card so data is never lost."""
        if not cand:
            return
        cand_h = hashlib.sha256(cand.encode("utf-8")).hexdigest()
        if cand_h in handled:
            return
        sec_ctrl = getattr(dashboard, "security_controller", None)
        if sec_ctrl and not sec_ctrl.is_locked and sec_ctrl.active_key:
            from core.crypto import encrypt
            ct = encrypt(cand, sec_ctrl.active_key)
            storage.add_encrypted_item(ct)
            handled[cand_h] = "history (encrypted)"
            if hasattr(dashboard, "history_controller"):
                dashboard.history_controller.reload()
            dashboard.statusBar().showMessage("Candidate auto-locked to history with Eclipse 🔒")
            if not dashboard.isVisible():
                tray_mgr = getattr(dashboard, "tray_manager", None)
                if tray_mgr and hasattr(tray_mgr, "show_message"):
                    tray_mgr.show_message(
                        "DotGhostBoard — Secret Saved 🔒",
                        "Secret auto-locked to history with Eclipse.",
                        timeout=5000,
                    )
        else:
            dashboard.statusBar().showMessage("Session locked — secret candidate discarded for security")

    def _on_secret_candidate(event) -> None:
        """Handle incoming secret candidate from watcher pipeline."""
        if not dashboard.security_service.has_master_password():
            return
        if not dashboard._settings.get("detect_passwords", True):
            return

        cand_text = str(event.content) if hasattr(event, "content") else str(event)
        if not cand_text:
            return

        # Consecutive duplicate copy while toast is active: do not duplicate toast or fallback
        if active_toast[0] and getattr(active_toast[0], "_candidate_text", "") == cand_text:
            return

        cand_hash = hashlib.sha256(cand_text.encode("utf-8")).hexdigest()
        # If user already chose to keep this false positive during this session, pass through
        if cand_hash in kept_hashes:
            storage.add_item("text", cand_text)
            if hasattr(dashboard, "history_controller"):
                dashboard.history_controller.reload()
            return

        where = handled.get(cand_hash)
        if where is None:
            vault_ctrl = getattr(dashboard, "vault_controller", None)
            if vault_ctrl is not None:
                dup = vault_ctrl.find_duplicate(cand_text)
                if dup is not None:
                    where = f"The Vault ('{dup.title}')"
                    handled[cand_hash] = where
        if where:
            _show_already_saved(where)
            return

        # If previous toast is still active, safely save it via Eclipse before replacing
        if active_toast[0] and getattr(active_toast[0], "_candidate_text", None):
            _auto_save_eclipse_fallback(active_toast[0]._candidate_text)
        _scrub_candidate()

        toast = SecretDetectedToast(cand_text, parent=dashboard)
        active_toast[0] = toast

        def _on_toast_save(cand: str):
            if abs_timer[0]:
                try:
                    abs_timer[0].stop()
                except Exception:
                    pass
            cat = _guess_category(cand)
            added_id = dashboard.vault_panel._prompt_add_secret(
                prefill_secret=cand,
                prefill_category=cat,
            )
            if added_id is not None:
                handled[cand_hash] = "The Vault"
                _scrub_candidate()
                dashboard.statusBar().showMessage("🛡️ Secret saved to Vault ✓")
            else:
                _auto_save_eclipse_fallback(cand)
                _scrub_candidate()

        def _on_toast_keep(cand: str):
            kept_hashes.add(cand_hash)
            _scrub_candidate()
            storage.add_item("text", cand)
            if hasattr(dashboard, "history_controller"):
                dashboard.history_controller.reload()
            dashboard.statusBar().showMessage("Saved to clipboard history ✓")

        def _on_toast_timeout(cand: str):
            _auto_save_eclipse_fallback(cand)
            _scrub_candidate()

        toast.sig_save_to_vault.connect(_on_toast_save)
        toast.sig_keep_in_history.connect(_on_toast_keep)
        toast.sig_timeout.connect(_on_toast_timeout)
        toast.sig_dismissed.connect(_scrub_candidate)

        # Absolute 5-minute coordinator timer cap for hidden tray window
        t = QTimer(dashboard)
        t.setSingleShot(True)
        t.setInterval(300_000)
        t.timeout.connect(lambda: _on_toast_timeout(cand_text))
        t.start()
        abs_timer[0] = t

        # Bottom-right placement so it never overlaps PinSuggestionToast (bottom-left)
        toast.adjustSize()
        x_pos = max(20, dashboard.width() - toast.width() - 20)
        y_pos = max(20, dashboard.height() - toast.height() - 30)
        toast.move(x_pos, y_pos)
        toast.show()

        # Send tray notification if dashboard is currently hidden in tray
        if not dashboard.isVisible():
            tray_mgr = getattr(dashboard, "tray_manager", None)
            if tray_mgr and hasattr(tray_mgr, "show_message"):
                tray_mgr.show_message(
                    "DotGhostBoard — Secret Intercepted 🛡️",
                    "A password or credential was protected from public history. Open to review.",
                    timeout=5000,
                )
        dashboard.statusBar().showMessage("🛡️ Secret / Password detected — not saved to public board")

    def _guess_category(text: str) -> str:
        match = detector.analyze(text)
        if not match:
            return "generic"
        st = match.secret_type
        if "password" in st:
            return "password"
        if "token" in st or "api" in st:
            return "token"
        if "key" in st:
            return "key"
        return "generic"

    def _on_send_to_vault(item_id: int) -> None:
        """Migrate a card item directly into The Vault with physical erasure."""
        if not dashboard.security_service.has_master_password():
            dashboard.statusBar().showMessage("⚠ Please set up a Master Password first to use The Vault.")
            return

        item = storage.get_item_by_id(item_id)
        if not item:
            return
        if item.get("type") != "text":
            dashboard.statusBar().showMessage("⚠ Only text items can be moved to The Vault.")
            return

        # Resolve Eclipse ciphertext if item was marked as secret
        if item.get("is_secret", 0):
            if hasattr(dashboard, "security_controller"):
                plaintext = dashboard.security_controller.reveal_secret(item_id)
                if plaintext is None:
                    return
            else:
                return
        else:
            plaintext = item.get("content", "")

        if not plaintext:
            return

        cat = _guess_category(plaintext)
        added_id = dashboard.vault_panel._prompt_add_secret(
            prefill_secret=plaintext,
            prefill_category=cat,
        )

        if added_id is not None:
            # Physical SQLite erasure from public history
            dashboard.history_controller.on_delete(item_id, secure=True, force=True)
            dashboard.statusBar().showMessage("🛡️ Secret moved to Vault & removed from public history ✓")

    # Wire to history controller
    if hasattr(dashboard, "history_controller"):
        dashboard.history_controller.send_to_vault_requested.connect(_on_send_to_vault)

    # Dynamic pipeline detector: evaluated at runtime per event
    def _is_detection_enabled() -> bool:
        return bool(
            dashboard._settings.get("detect_passwords", True)
            and dashboard.security_service.has_master_password()
        )

    if hasattr(dashboard, "watcher") and dashboard.watcher:
        dashboard.watcher.pipeline.set_secret_detector(
            lambda ev: _is_detection_enabled() and detector.is_secret(ev)
        )
        dashboard.watcher.secret_candidate_detected.connect(_on_secret_candidate)

    # Scrub candidate on session lock
    if hasattr(dashboard, "security_controller"):
        def _on_lock_changed(locked: bool):
            if locked:
                _scrub_candidate()
                handled.clear()

        dashboard.security_controller.lock_state_changed.connect(_on_lock_changed)

    # Expose helper on dashboard
    dashboard._scrub_secret_candidate = _scrub_candidate
    dashboard._on_send_to_vault = _on_send_to_vault
    dashboard._on_secret_candidate = _on_secret_candidate
