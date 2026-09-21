"""
ui/vault/secret_card.py
───────────────────────
Visual card component for a single encrypted secret item in The Vault.
Displays masked representation (••••••••) with in-memory reveal and auto-scrub.

v2.0.0 Cerberus — Phase 7 Vault UI Subsystem.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.security.vault import VaultSummary
from ui.vault.vault_controller import VaultController

CATEGORY_ICONS = {
    "password": "🔑",
    "token": "🪙",
    "key": "🔐",
    "note": "📜",
    "generic": "🛡️",
}


class SecretCard(QFrame):
    """
    Card widget representing a single Vault item.
    Enforces security: secrets are masked by default and decrypted in-memory only.
    """

    edit_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(
        self,
        summary: VaultSummary,
        controller: VaultController,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._summary = summary
        self._controller = controller
        self._is_revealed: bool = False
        self._revealed_text: Optional[str] = None

        self.setObjectName("SecretCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._build_ui()
        self._controller.vault_locked.connect(self.scrub_revealed)

    @property
    def summary(self) -> VaultSummary:
        return self._summary

    @property
    def is_revealed(self) -> bool:
        return self._is_revealed

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # ── Top Row: Category Icon, Title, Updated Time ──
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        icon = CATEGORY_ICONS.get(self._summary.category.lower(), "🛡️")
        self.cat_badge = QLabel(f"{icon} {self._summary.category.upper()}")
        self.cat_badge.setObjectName("SecretCategoryBadge")

        self.title_label = QLabel(self._summary.title)
        self.title_label.setObjectName("SecretTitle")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        date_str = self._summary.updated_at[:10] if self._summary.updated_at else ""
        self.date_label = QLabel(date_str)
        self.date_label.setStyleSheet("color: #555d63; font-size: 10px; background: transparent;")

        top_row.addWidget(self.cat_badge)
        top_row.addWidget(self.title_label)
        top_row.addStretch()
        top_row.addWidget(self.date_label)

        # ── Middle Row: Secret Display (Masked by default) ──
        self.payload_label = QLabel("••••••••••••••••")
        self.payload_label.setObjectName("SecretPayloadMasked")
        self.payload_label.setTextFormat(Qt.TextFormat.PlainText)
        self.payload_label.setMaximumHeight(120)
        self.payload_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.payload_label.setWordWrap(True)

        # ── Bottom Row: Actions ──
        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        self.reveal_btn = QPushButton("👁️ Reveal")
        self.reveal_btn.setObjectName("SecretCardActionBtn")
        self.reveal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reveal_btn.clicked.connect(self._toggle_reveal)

        self.copy_btn = QPushButton("📋 Copy")
        self.copy_btn.setObjectName("SecretCardActionBtn")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._on_copy)

        self.edit_btn = QPushButton("✏️ Edit")
        self.edit_btn.setObjectName("SecretCardActionBtn")
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._summary.id))

        self.delete_btn = QPushButton("🗑️")
        self.delete_btn.setObjectName("SecretCardActionBtn")
        self.delete_btn.setToolTip("Delete Secret")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(self._on_delete)

        actions_row.addWidget(self.reveal_btn)
        actions_row.addWidget(self.copy_btn)
        actions_row.addStretch()
        actions_row.addWidget(self.edit_btn)
        actions_row.addWidget(self.delete_btn)

        layout.addLayout(top_row)
        layout.addWidget(self.payload_label)
        layout.addLayout(actions_row)

    def _toggle_reveal(self) -> None:
        if not self._is_revealed:
            plaintext = self._controller.reveal_secret(self._summary.id)
            if plaintext is not None:
                self._revealed_text = plaintext
                self._is_revealed = True
                self.payload_label.setText(plaintext)
                self.payload_label.setObjectName("SecretPayloadRevealed")
                if self.payload_label.style():
                    self.payload_label.style().unpolish(self.payload_label)
                    self.payload_label.style().polish(self.payload_label)
                self.reveal_btn.setText("🙈 Hide")
        else:
            self.scrub_revealed()

    def scrub_revealed(self) -> None:
        """Immediately scrub revealed plaintext and restore masked display."""
        self._revealed_text = None
        self._is_revealed = False
        self.payload_label.setText("••••••••••••••••")
        self.payload_label.setObjectName("SecretPayloadMasked")
        if self.payload_label.style():
            self.payload_label.style().unpolish(self.payload_label)
            self.payload_label.style().polish(self.payload_label)
        self.reveal_btn.setText("👁️ Reveal")

    def _on_copy(self) -> None:
        success = self._controller.copy_secret(self._summary.id)
        if success:
            self.copy_btn.setText("✓ Copied!")
            QTimer.singleShot(1500, lambda: self.copy_btn.setText("📋 Copy"))

    def _on_delete(self) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Secret",
            f"Are you sure you want to permanently delete '{self._summary.title}' from The Vault?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self._summary.id)
