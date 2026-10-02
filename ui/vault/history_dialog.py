"""
ui/vault/history_dialog.py
──────────────────────────
Modal dialog for viewing, copying, and reverting to historical versions
of a Vault secret (retains last 3 encrypted versions).
Features zero-knowledge AES-256-GCM encrypted version history.

v2.1.0 Leviathan — Vault Password History.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.security.vault import VaultSummary
from ui.vault.vault_controller import VaultController

logger = logging.getLogger(__name__)


class HistoryEntryWidget(QFrame):
    """Row widget representing a single historical password version."""

    def __init__(
        self,
        entry_idx: int,
        entry_data: dict,
        controller: VaultController,
        on_revert_cb,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._entry_idx = entry_idx
        self._data = entry_data
        self._controller = controller
        self._on_revert_cb = on_revert_cb
        self._is_revealed = False
        self._plaintext = entry_data.get("plaintext", "")

        self.setObjectName("HistoryEntryWidget")
        self._build_ui()

    def scrub(self) -> None:
        """Wipe plaintext in memory and mask display."""
        self._plaintext = ""
        self._is_revealed = False
        self._payload_label.setText("••••••••••••••••")
        self._payload_label.setProperty("revealed", "false")
        if self._payload_label.style():
            self._payload_label.style().unpolish(self._payload_label)
            self._payload_label.style().polish(self._payload_label)
        self._reveal_btn.setText("👁️ Reveal")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header: Version # and Timestamp
        header = QHBoxLayout()
        v_label = QLabel(f"Version #{self._entry_idx}")
        v_label.setObjectName("HistoryVersionLabel")

        time_str = self._data.get("created_at", "")[:19]
        time_label = QLabel(time_str)
        time_label.setObjectName("HistoryTimeLabel")

        header.addWidget(v_label)
        header.addStretch()
        header.addWidget(time_label)
        layout.addLayout(header)

        # Secret Payload (masked by default)
        self._payload_label = QLabel("••••••••••••••••")
        self._payload_label.setObjectName("HistoryPayloadLabel")
        self._payload_label.setProperty("revealed", "false")
        self._payload_label.setTextFormat(Qt.TextFormat.PlainText)
        self._payload_label.setWordWrap(True)
        layout.addWidget(self._payload_label)

        # Action Buttons: Reveal, Copy, Revert
        actions = QHBoxLayout()
        actions.setSpacing(6)

        self._reveal_btn = QPushButton("👁️ Reveal")
        self._reveal_btn.setObjectName("HistoryToolBtn")
        self._reveal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reveal_btn.setToolTip("Temporarily reveal this version's plaintext (15s auto-mask)")
        self._reveal_btn.clicked.connect(self._toggle_reveal)

        self._copy_btn = QPushButton("📋 Copy")
        self._copy_btn.setObjectName("HistoryToolBtn")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setToolTip("Copy this version to clipboard (30s auto-wipe)")
        self._copy_btn.clicked.connect(self._on_copy)

        self._revert_btn = QPushButton("↺ Revert to this")
        self._revert_btn.setObjectName("HistoryRevertBtn")
        self._revert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._revert_btn.setToolTip("Roll back secret to this previous version safely")
        self._revert_btn.clicked.connect(self._on_revert)

        actions.addWidget(self._reveal_btn)
        actions.addWidget(self._copy_btn)
        actions.addStretch()
        actions.addWidget(self._revert_btn)
        layout.addLayout(actions)

    def _toggle_reveal(self) -> None:
        if not self._is_revealed:
            self._payload_label.setText(self._plaintext)
            self._payload_label.setProperty("revealed", "true")
            self._reveal_btn.setText("🙈 Hide")
            self._is_revealed = True
        else:
            self._payload_label.setText("••••••••••••••••")
            self._payload_label.setProperty("revealed", "false")
            self._reveal_btn.setText("👁️ Reveal")
            self._is_revealed = False

        if self._payload_label.style():
            self._payload_label.style().unpolish(self._payload_label)
            self._payload_label.style().polish(self._payload_label)

    def _on_copy(self) -> None:
        if self._controller.copy_text(self._plaintext):
            self._copy_btn.setText("✓ Copied!")
            QTimer.singleShot(1500, lambda: self._copy_btn.setText("📋 Copy"))

    def _on_revert(self) -> None:
        self._on_revert_cb(self._data["id"])


class PasswordHistoryDialog(QDialog):
    """Modal dialog displaying password history entries for a secret."""

    def __init__(
        self,
        summary: VaultSummary,
        controller: VaultController,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._summary = summary
        self._controller = controller
        self._entry_widgets: list[HistoryEntryWidget] = []

        self.setWindowTitle(f"Password History — {summary.title}")
        self.setObjectName("PasswordHistoryDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setMinimumWidth(490)
        self.setMaximumWidth(540)
        self.setMinimumHeight(400)

        self._build_ui()
        self._apply_style()
        self._load_history()

        # Scrub and close if vault locks while dialog is open
        self._controller.vault_locked.connect(self.close)

    def _apply_style(self) -> None:
        """Apply theme from ui/ghost.qss if not already active on the application."""
        app = QApplication.instance()
        if not self.styleSheet() and not (app and app.styleSheet()):
            from core.paths import resource_path
            qss_file = resource_path("ui", "ghost.qss")
            if os.path.exists(qss_file):
                try:
                    with open(qss_file, "r", encoding="utf-8") as f:
                        self.setStyleSheet(f.read())
                except OSError:
                    pass

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Header Title
        title_box = QHBoxLayout()
        icon_lbl = QLabel("📜")
        icon_lbl.setStyleSheet("font-size: 20px; background: transparent;")
        heading = QLabel("Password History")
        heading.setObjectName("HistoryHeading")
        title_box.addWidget(icon_lbl)
        title_box.addWidget(heading)
        title_box.addStretch()

        close_x = QPushButton("✕")
        close_x.setObjectName("VaultToolBtn")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setFixedSize(26, 26)
        close_x.setToolTip("Close History Dialog (Esc)")
        close_x.clicked.connect(self.close)
        title_box.addWidget(close_x)
        layout.addLayout(title_box)

        # Subtitle
        sub_lbl = QLabel(f"Secret: <b>{self._summary.title}</b>")
        sub_lbl.setObjectName("HistorySubTitle")
        layout.addWidget(sub_lbl)

        # Security Info Banner
        info_banner = QFrame()
        info_banner.setObjectName("HistoryInfoBanner")
        ib_lay = QHBoxLayout(info_banner)
        ib_lay.setContentsMargins(10, 8, 10, 8)
        ib_lay.setSpacing(8)
        shield_icon = QLabel("🛡️")
        shield_icon.setStyleSheet("font-size: 16px; background: transparent;")
        ib_text = QLabel(
            "Historical versions are encrypted with AES-256-GCM. "
            "Reverting safely saves your current secret to history so nothing is lost."
        )
        ib_text.setObjectName("HistoryInfoBannerText")
        ib_text.setWordWrap(True)
        ib_lay.addWidget(shield_icon)
        ib_lay.addWidget(ib_text, 1)
        layout.addWidget(info_banner)

        desc_lbl = QLabel(
            "DotGhostBoard automatically retains up to 3 previous encrypted versions. "
            "You can reveal, copy, or revert to any past password at any time."
        )
        desc_lbl.setObjectName("HistoryDescLabel")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Scroll Area for history items
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(8)
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, 1)

        # Footer Button
        footer = QHBoxLayout()
        footer.addStretch()
        done_btn = QPushButton("Done")
        done_btn.setObjectName("VaultAddBtn")
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setFixedHeight(34)
        done_btn.setFixedWidth(90)
        done_btn.setToolTip("Done viewing history")
        done_btn.clicked.connect(self.close)
        footer.addWidget(done_btn)
        layout.addLayout(footer)

    def _load_history(self) -> None:
        # Clear existing
        for w in self._entry_widgets:
            w.scrub()
            w.deleteLater()
        self._entry_widgets.clear()

        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        records = self._controller.get_secret_history(self._summary.id)

        if not records:
            empty_lbl = QLabel(
                "No previous password versions recorded for this item yet.\n"
                "Versions are saved automatically whenever you edit or rotate a secret."
            )
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setObjectName("HistoryEmptyLabel")
            self._container_layout.addWidget(empty_lbl)
            return

        for idx, rec in enumerate(records, 1):
            entry_w = HistoryEntryWidget(
                entry_idx=idx,
                entry_data=rec,
                controller=self._controller,
                on_revert_cb=self._on_revert_entry,
                parent=self._container,
            )
            self._entry_widgets.append(entry_w)
            self._container_layout.addWidget(entry_w)

        self._container_layout.addStretch()

    def _on_revert_entry(self, history_id: int) -> None:
        reply = QMessageBox.question(
            self,
            "Revert Password",
            f"Are you sure you want to revert '{self._summary.title}' to this previous version?\n\n"
            "Your current password will be saved into history so you won't lose it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            success = self._controller.restore_secret_history(self._summary.id, history_id)
            if success:
                QMessageBox.information(
                    self,
                    "Reverted Successfully",
                    f"'{self._summary.title}' has been reverted to the selected version.",
                )
                self._load_history()

    def closeEvent(self, event) -> None:
        for w in self._entry_widgets:
            w.scrub()
        super().closeEvent(event)
