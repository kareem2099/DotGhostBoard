"""
ui/vault/vault_panel.py
───────────────────────
The Vault drawer / slide-in panel widget for DotGhostBoard.
Features debounced filtering, category pills, locked/unlocked state transitions,
ephemeral secret reveal scrubbing, and guarded mutation slots.

v2.0.0 Cerberus — Phase 7 Vault UI Subsystem.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.constants import (
    SEARCH_DEBOUNCE_MS,
    VAULT_CATEGORIES,
    VAULT_DRAWER_WIDTH,
)
from core.security.vault import VaultLockedError
from ui.vault.secret_card import SecretCard
from ui.vault.secret_dialog import SecretDialog
from ui.vault.unlock_dialog import VaultUnlockDialog
from ui.vault.backup_dialog import VaultBackupDialog
from ui.vault.guide_dialog import VaultGuideDialog
from ui.vault.vault_controller import VaultController
from ui.window_utils import prepare_dialog_for_current_workspace

logger = logging.getLogger(__name__)


class VaultPanel(QFrame):
    """
    Drawer panel providing full UI interaction with The Vault subsystem.
    Can be shown/hidden via sidebar action or Ctrl+Shift+V shortcut.
    """

    close_requested = pyqtSignal()

    def __init__(
        self,
        controller: VaultController,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._controller = controller
        self._active_category = "all"
        self._search_query = ""

        self.setObjectName("VaultPanel")
        self.setFixedWidth(VAULT_DRAWER_WIDTH)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._apply_debounced_search)

        self._build_ui()
        self._sync_lock_ui()
        self._wire_signals()
        self.refresh_list()

    @property
    def controller(self) -> VaultController:
        return self._controller

    def _belongs_to_panel(self, obj) -> bool:
        if not isinstance(obj, QWidget):
            return False
        if obj is self or self.isAncestorOf(obj):
            return True
        owner = obj.window().parentWidget()
        return owner is not None and (owner is self or self.isAncestorOf(owner))

    def eventFilter(self, obj, ev):
        if (
            ev.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress)
            and self._belongs_to_panel(obj)
        ):
            self._controller.touch()
            main_win = self.window()
            if hasattr(main_win, "_reset_auto_lock"):
                main_win._reset_auto_lock()
        return False

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        # ── Header Row 1: Title + Badge + Close ──
        header = QHBoxLayout()
        header.setSpacing(8)

        self.title_lbl = QLabel("🛡️ The Vault")
        self.title_lbl.setObjectName("VaultTitle")

        self.badge_lbl = QLabel("🔒 Locked")
        self.badge_lbl.setObjectName("VaultBadge")
        self.badge_lbl.setProperty("unlocked", "false")

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("VaultToolBtn")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setToolTip("Close Vault Panel")
        self.close_btn.clicked.connect(self.hide_panel)

        header.addWidget(self.title_lbl)
        header.addWidget(self.badge_lbl)
        header.addStretch()
        header.addWidget(self.close_btn)
        root_layout.addLayout(header)

        # ── Toolbar Row 2: Add Secret + Utility Tools ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.add_btn = QPushButton("+ Add Secret")
        self.add_btn.setObjectName("VaultAddBtn")
        self.add_btn.setFixedHeight(28)
        self.add_btn.setToolTip("Add new encrypted secret")
        self.add_btn.clicked.connect(self._prompt_add_secret)

        self.lock_toggle_btn = QPushButton("🔓")
        self.lock_toggle_btn.setObjectName("VaultToolBtn")
        self.lock_toggle_btn.setFixedSize(28, 28)
        self.lock_toggle_btn.setToolTip("Lock / Unlock Vault")
        self.lock_toggle_btn.clicked.connect(self._toggle_lock)

        self.export_btn = QPushButton("📤")
        self.export_btn.setObjectName("VaultToolBtn")
        self.export_btn.setFixedSize(28, 28)
        self.export_btn.setToolTip("Export Encrypted Vault Backup (.vault)")
        self.export_btn.clicked.connect(self._on_export_vault)

        self.import_btn = QPushButton("📥")
        self.import_btn.setObjectName("VaultToolBtn")
        self.import_btn.setFixedSize(28, 28)
        self.import_btn.setToolTip("Import Encrypted Vault Backup (.vault)")
        self.import_btn.clicked.connect(self._on_import_vault)

        self.help_btn = QPushButton("❓")
        self.help_btn.setObjectName("VaultToolBtn")
        self.help_btn.setFixedSize(28, 28)
        self.help_btn.setToolTip("The Vault Security & Shortcuts Guide (❓)")
        self.help_btn.clicked.connect(self._show_guide)

        toolbar.addWidget(self.add_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.lock_toggle_btn)
        toolbar.addWidget(self.export_btn)
        toolbar.addWidget(self.import_btn)
        toolbar.addWidget(self.help_btn)
        root_layout.addLayout(toolbar)

        # ── Search Box ──
        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setFixedHeight(34)
        self.search_box.setPlaceholderText("Search secrets…")
        self.search_box.textChanged.connect(self._on_search_changed)
        root_layout.addWidget(self.search_box)

        # ── Category Pills Bar ──
        self.cat_btn_group = QButtonGroup(self)
        self.cat_btn_group.setExclusive(True)
        cats_layout = QHBoxLayout()
        cats_layout.setSpacing(4)

        CAT_LABELS = {
            "all": "All",
            "password": "Pass",
            "token": "Token",
            "key": "Key",
            "note": "Note",
            "generic": "Gen",
        }
        for cat in VAULT_CATEGORIES:
            btn = QPushButton(CAT_LABELS.get(cat, cat.capitalize()))
            btn.setObjectName("VaultCategoryBtn")
            btn.setToolTip(f"{cat.capitalize()} secrets")
            btn.setCheckable(True)
            if cat == "all":
                btn.setChecked(True)
            self.cat_btn_group.addButton(btn)
            cats_layout.addWidget(btn)
            btn.clicked.connect(lambda checked, c=cat: self._on_category_selected(c))

        cats_layout.addStretch()
        root_layout.addLayout(cats_layout)

        # ── Scroll Area for Secret Cards ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(2, 2, 2, 2)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        root_layout.addWidget(self.scroll_area)

    def _sync_lock_ui(self) -> None:
        """Synchronize badge and lock button to current controller state."""
        is_unlocked = self._controller.is_unlocked
        self.badge_lbl.setText("🔓 Unlocked" if is_unlocked else "🔒 Locked")
        self.badge_lbl.setProperty("unlocked", "true" if is_unlocked else "false")
        if self.badge_lbl.style():
            self.badge_lbl.style().unpolish(self.badge_lbl)
            self.badge_lbl.style().polish(self.badge_lbl)
        self.lock_toggle_btn.setText("🔒" if is_unlocked else "🔓")
        self.lock_toggle_btn.setToolTip("Lock Vault" if is_unlocked else "Unlock Vault")

    def _wire_signals(self) -> None:
        self._controller.vault_unlocked.connect(self._on_vault_unlocked)
        self._controller.vault_locked.connect(self._on_vault_locked)
        self._controller.secrets_changed.connect(self.refresh_list)

    def showEvent(self, event) -> None:
        """Ensure global event filter is attached whenever panel becomes visible."""
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        """Ensure global event filter is detached whenever panel is hidden."""
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
        super().hideEvent(event)

    def show_panel(self) -> None:
        """Display the drawer panel and notify."""
        self.show()
        self.refresh_list()
        self._controller.panel_visibility_changed.emit(True)

    def hide_panel(self) -> None:
        """Hide the drawer panel, scrub revealed plaintexts, and notify."""
        self.scrub_all_revealed()
        self.hide()
        self.close_requested.emit()
        self._controller.panel_visibility_changed.emit(False)

    def scrub_all_revealed(self) -> None:
        """Immediately purge revealed plaintext across all rendered cards."""
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), SecretCard):
                item.widget().scrub_revealed()

    def toggle_panel(self) -> None:
        """Toggle panel visibility safely based on hidden state."""
        if not self.isHidden():
            self.hide_panel()
        else:
            self.show_panel()

    def _on_search_changed(self, text: str) -> None:
        self._search_query = text
        self._search_timer.start()

    def _apply_debounced_search(self) -> None:
        self.refresh_list()

    def _on_category_selected(self, category: str) -> None:
        self._active_category = category
        self.refresh_list()

    def _toggle_lock(self) -> None:
        if self._controller.is_unlocked:
            self._controller.lock()
        else:
            self._prompt_unlock()

    def _on_vault_unlocked(self) -> None:
        self._sync_lock_ui()
        self.refresh_list()

    def _on_vault_locked(self) -> None:
        self.scrub_all_revealed()
        self._sync_lock_ui()
        self.refresh_list()

    def _guarded(self, fn: Callable, *args, **kwargs):
        """Execute a controller mutation safely, catching any domain exceptions at UI boundary."""
        try:
            return fn(*args, **kwargs)
        except (VaultLockedError, ValueError) as exc:
            self._controller.status_message.emit(f"⚠ {exc}")
            return None

    def _save_with_relock_retry(self, fn: Callable, *args, **kwargs):
        """Execute mutation; if failed because vault locked in background, prompt unlock and retry."""
        res = self._guarded(fn, *args, **kwargs)
        if res is None and not self._controller.is_unlocked and self._prompt_unlock():
            res = self._guarded(fn, *args, **kwargs)
        return res

    def _prompt_unlock(self) -> bool:
        dlg = VaultUnlockDialog(self._controller, parent=self)
        prepare_dialog_for_current_workspace(dlg)
        try:
            return dlg.exec() == VaultUnlockDialog.DialogCode.Accepted
        finally:
            dlg.deleteLater()

    def _prompt_add_secret(
        self,
        prefill_secret: str = "",
        prefill_title: str = "",
        prefill_category: str = "generic",
    ) -> Optional[int]:
        if not self._controller.is_unlocked:
            if not self._prompt_unlock():
                return None

        dlg = SecretDialog(
            title=prefill_title,
            category=prefill_category,
            secret_payload=prefill_secret,
            parent=self,
        )
        prepare_dialog_for_current_workspace(dlg)
        try:
            if dlg.exec() == SecretDialog.DialogCode.Accepted:
                data = dlg.get_data()
                title, secret_text, category = data
                expires_at = data.expires_at
                if title and secret_text:
                    dup = self._controller.find_duplicate(secret_text)
                    if dup is not None:
                        self._controller.status_message.emit(f"🛡️ Already saved as '{dup.title}'")
                        return dup.id
                    return self._save_with_relock_retry(
                        self._controller.add_secret,
                        title,
                        secret_text,
                        category=category,
                        expires_at=expires_at,
                    )
            return None
        finally:
            dlg.scrub_inputs()
            dlg.deleteLater()

    def _prompt_edit_secret(self, item_id: int) -> None:
        if not self._controller.is_unlocked:
            if not self._prompt_unlock():
                return

        summaries = self._controller.list_secrets()
        matching = [s for s in summaries if s.id == item_id]
        if not matching:
            return

        summary = matching[0]

        # Pre-fill current secret so user can see and edit it (not type from scratch)
        current_secret = ""
        try:
            current_secret = self._controller.reveal_secret(item_id) or ""
        except Exception:
            pass

        dlg = SecretDialog(
            title=summary.title,
            category=summary.category,
            item_id=item_id,
            secret_payload=current_secret,
            expires_at=summary.expires_at,
            parent=self,
        )
        prepare_dialog_for_current_workspace(dlg)
        try:
            if dlg.exec() == SecretDialog.DialogCode.Accepted:
                data = dlg.get_data()
                title, secret_text, category = data
                expires_at = data.expires_at
                self._save_with_relock_retry(
                    self._controller.update_secret,
                    item_id=item_id,
                    title=title,
                    secret_text=secret_text,
                    category=category,
                    expires_at=expires_at,
                )
        finally:
            dlg.scrub_inputs()
            dlg.deleteLater()

    def _on_export_vault(self) -> None:
        if not self._controller.is_unlocked:
            if not self._prompt_unlock():
                return

        dlg = VaultBackupDialog(mode="export", parent=self)
        prepare_dialog_for_current_workspace(dlg)
        if dlg.exec() != VaultBackupDialog.DialogCode.Accepted:
            return
        passphrase = dlg.get_passphrase()
        if not passphrase:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Encrypted Vault Backup",
            "dotghost_vault_backup.vault",
            "Vault Backup (*.vault);;All Files (*)",
        )
        if not file_path:
            return

        try:
            count = self._controller.export_vault(passphrase, file_path)
            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {count} secret(s) to:\n{file_path}\n\n"
                f"🔒 Package is fully encrypted with AES-256-GCM.\n"
                f"Keep your export passphrase safe to restore it later.",
            )
            self._controller.status_message.emit(f"📦 Exported {count} encrypted secrets")
        except Exception as exc:
            logger.error("Failed to export vault backup: %s", exc)
            QMessageBox.critical(self, "Export Failed", f"Failed to export vault: {exc}")

    def _on_import_vault(self) -> None:
        if not self._controller.is_unlocked:
            if not self._prompt_unlock():
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Encrypted Vault Backup to Import",
            "",
            "Vault Backup (*.vault);;All Files (*)",
        )
        if not file_path:
            return

        dlg = VaultBackupDialog(mode="import", file_path=file_path, parent=self)
        prepare_dialog_for_current_workspace(dlg)
        if dlg.exec() != VaultBackupDialog.DialogCode.Accepted:
            return
        passphrase = dlg.get_passphrase()
        if not passphrase:
            return

        try:
            result = self._controller.import_vault(passphrase, file_path)
            imported = result.get("imported_count", 0)
            skipped = result.get("skipped_count", 0)
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully verified and imported {imported} secret(s).\n"
                f"{skipped} duplicate(s) skipped.",
            )
            self._controller.status_message.emit(
                f"📥 Imported {imported} secrets ({skipped} skipped)"
            )
            self.refresh_list()
        except Exception as exc:
            logger.error("Failed to import vault backup: %s", exc)
            QMessageBox.critical(self, "Import Failed", f"Failed to import vault: {exc}")

    def _handle_delete_secret(self, item_id: int) -> None:
        self._guarded(self._controller.delete_secret, item_id)

    def _prompt_history_secret(self, item_id: int) -> None:
        if not self._controller.is_unlocked:
            if not self._prompt_unlock():
                return

        summaries = self._controller.list_secrets()
        matching = [s for s in summaries if s.id == item_id]
        if not matching:
            return

        from ui.vault.history_dialog import PasswordHistoryDialog
        dlg = PasswordHistoryDialog(matching[0], self._controller, parent=self)
        prepare_dialog_for_current_workspace(dlg)
        try:
            dlg.exec()
        finally:
            dlg.deleteLater()

    def _show_guide(self) -> None:
        """Display the comprehensive Vault security, architecture, and shortcuts guide."""
        dlg = VaultGuideDialog(parent=self)
        prepare_dialog_for_current_workspace(dlg)
        try:
            dlg.exec()
        finally:
            dlg.deleteLater()

    def refresh_list(self) -> None:
        """Clear and repopulate secret cards matching current filters."""
        # Clear existing cards and disconnect signals to avoid calling scrub on deleted widgets
        while self.cards_layout.count() > 1:
            child = self.cards_layout.takeAt(0)
            widget = child.widget() if child else None
            if widget and isinstance(widget, SecretCard):
                try:
                    self._controller.vault_locked.disconnect(widget.scrub_revealed)
                except (TypeError, RuntimeError):
                    pass
            if widget:
                widget.deleteLater()

        summaries = self._controller.list_secrets(
            category=self._active_category,
            search_query=self._search_query,
        )

        # ── State 1: Locked Banner if locked ──
        if not self._controller.is_unlocked:
            banner = QFrame()
            banner.setObjectName("SecretCard")
            b_layout = QVBoxLayout(banner)
            b_layout.setContentsMargins(16, 20, 16, 20)
            b_layout.setSpacing(10)

            lock_icon = QLabel("🔒")
            lock_icon.setStyleSheet("font-size: 28px; background: transparent;")
            lock_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

            msg = QLabel("The Vault is Locked\nUnlock to view and manage encrypted secrets.")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setStyleSheet("color: #8c969d; font-size: 12px; background: transparent;")

            unlock_btn = QPushButton("🔓 Unlock Vault")
            unlock_btn.setObjectName("VaultAddBtn")
            unlock_btn.setFixedHeight(34)
            unlock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            unlock_btn.clicked.connect(self._prompt_unlock)

            b_layout.addWidget(lock_icon)
            b_layout.addWidget(msg)
            b_layout.addWidget(unlock_btn)

            self.cards_layout.insertWidget(0, banner)
            return

        # ── State 2: Empty State if 0 items ──
        if not summaries:
            empty_frame = QFrame()
            e_layout = QVBoxLayout(empty_frame)
            e_layout.setContentsMargins(16, 28, 16, 28)
            e_layout.setSpacing(8)

            icon_lbl = QLabel("🛡️")
            icon_lbl.setStyleSheet("font-size: 28px; background: transparent;")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            text_lbl = QLabel("No secrets stored in The Vault.")
            text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text_lbl.setStyleSheet("color: #6d767c; font-size: 12px; background: transparent;")

            add_first_btn = QPushButton("+ Add First Secret")
            add_first_btn.setObjectName("VaultAddBtn")
            add_first_btn.setFixedHeight(32)
            add_first_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            add_first_btn.clicked.connect(self._prompt_add_secret)

            e_layout.addWidget(icon_lbl)
            e_layout.addWidget(text_lbl)
            e_layout.addWidget(add_first_btn)

            # Quick Security Guide Card
            guide_card = QFrame()
            guide_card.setObjectName("VaultEmptyGuideCard")
            g_layout = QVBoxLayout(guide_card)
            g_layout.setContentsMargins(12, 12, 12, 12)
            g_layout.setSpacing(6)

            g_title = QLabel("💡 Quick Security Guide")
            g_title.setObjectName("VaultEmptyGuideTitle")
            g_layout.addWidget(g_title)

            tips = [
                ("⌨️", "Toggle Vault", "Press <b>Ctrl+Shift+V</b> anytime to summon or close this drawer."),
                ("⏱️", "Auto-Scrub", "Copied secrets auto-clear from clipboard after 30 seconds."),
                ("📜", "Version History", "Retains last 3 encrypted versions for single-click rollback."),
                ("⏳", "Expiration", "Set expiration dates to track temporary tokens with status badges."),
                ("📦", "Encrypted Backups", "Click <b>📤</b> in the top bar to export an AES-256-GCM (.vault) package."),
            ]

            for icon, label, text in tips:
                tip_lbl = QLabel(f"{icon} <b>{label}:</b> {text}")
                tip_lbl.setObjectName("VaultEmptyGuideItem")
                tip_lbl.setWordWrap(True)
                g_layout.addWidget(tip_lbl)

            e_layout.addWidget(guide_card)

            self.cards_layout.insertWidget(0, empty_frame)
            return

        # ── State 3: Populated Cards ──
        for idx, summary in enumerate(summaries):
            card = SecretCard(summary, self._controller, parent=self.cards_container)
            card.edit_requested.connect(self._prompt_edit_secret)
            card.delete_requested.connect(self._handle_delete_secret)
            card.history_requested.connect(self._prompt_history_secret)
            self.cards_layout.insertWidget(idx, card)
