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
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from ui.vault.vault_controller import VaultController

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

        # ── Header Row ──
        header = QHBoxLayout()
        header.setSpacing(6)

        self.title_lbl = QLabel("🛡️ The Vault")
        self.title_lbl.setObjectName("VaultTitle")

        self.badge_lbl = QLabel("🔒 Locked")
        self.badge_lbl.setObjectName("VaultBadge")
        self.badge_lbl.setProperty("unlocked", "false")

        self.lock_toggle_btn = QPushButton("🔓")
        self.lock_toggle_btn.setObjectName("VaultToolBtn")
        self.lock_toggle_btn.setFixedSize(28, 28)
        self.lock_toggle_btn.setToolTip("Lock / Unlock Vault")
        self.lock_toggle_btn.clicked.connect(self._toggle_lock)

        self.add_btn = QPushButton("+ Add")
        self.add_btn.setObjectName("VaultAddBtn")
        self.add_btn.setFixedHeight(28)
        self.add_btn.setToolTip("Add new encrypted secret")
        self.add_btn.clicked.connect(self._prompt_add_secret)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("VaultToolBtn")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("Close Vault Panel")
        self.close_btn.clicked.connect(self.hide_panel)

        header.addWidget(self.title_lbl)
        header.addWidget(self.badge_lbl)
        header.addStretch()
        header.addWidget(self.lock_toggle_btn)
        header.addWidget(self.add_btn)
        header.addWidget(self.close_btn)
        root_layout.addLayout(header)

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
        try:
            if dlg.exec() == SecretDialog.DialogCode.Accepted:
                title, secret_text, category = dlg.get_data()
                if title and secret_text:
                    dup = self._controller.find_duplicate(secret_text)
                    if dup is not None:
                        self._controller.status_message.emit(f"🛡️ Already saved as '{dup.title}'")
                        return dup.id
                    return self._save_with_relock_retry(
                        self._controller.add_secret, title, secret_text, category=category
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
        dlg = SecretDialog(
            title=summary.title,
            category=summary.category,
            item_id=item_id,
            parent=self,
        )
        try:
            if dlg.exec() == SecretDialog.DialogCode.Accepted:
                title, secret_text, category = dlg.get_data()
                self._save_with_relock_retry(
                    self._controller.update_secret,
                    item_id=item_id,
                    title=title,
                    secret_text=secret_text,
                    category=category,
                )
        finally:
            dlg.scrub_inputs()
            dlg.deleteLater()

    def _handle_delete_secret(self, item_id: int) -> None:
        self._guarded(self._controller.delete_secret, item_id)

    def refresh_list(self) -> None:
        """Clear and repopulate secret cards matching current filters."""
        # Clear existing cards
        while self.cards_layout.count() > 1:
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

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

            self.cards_layout.insertWidget(0, empty_frame)
            return

        # ── State 3: Populated Cards ──
        for idx, summary in enumerate(summaries):
            card = SecretCard(summary, self._controller, parent=self.cards_container)
            card.edit_requested.connect(self._prompt_edit_secret)
            card.delete_requested.connect(self._handle_delete_secret)
            self.cards_layout.insertWidget(idx, card)
