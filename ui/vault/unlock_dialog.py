"""
ui/vault/unlock_dialog.py
─────────────────────────
Modal dialog to prompt for Master Password and unlock The Vault.

v2.0.0 Cerberus — Phase 7 Vault UI Subsystem.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.crypto import has_master_password
from ui.vault.vault_controller import VaultController
from ui.widgets.password_input import PasswordInputWidget


class VaultUnlockDialog(QDialog):
    """
    Dedicated unlock dialog for The Vault.
    Authenticates against Master Password to unwrap the Vault DEK.
    """

    def __init__(
        self,
        controller: VaultController,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._controller = controller
        self._attempts = 0

        self.setWindowTitle("Unlock The Vault")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setObjectName("VaultUnlockDialog")
        self.setModal(True)
        self.setFixedSize(420, 265)

        self._build_ui()
        self._apply_style()

        QTimer.singleShot(80, self.pw_input.setFocus)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 22, 32, 22)
        layout.setSpacing(10)

        # Header
        title = QLabel("🛡️  The Vault")
        title.setObjectName("VaultUnlockTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(
            "Enter Master Password to unlock encrypted secrets.\n"
            "Secrets are protected with AES-256-GCM and zero plaintext."
        )
        subtitle.setObjectName("VaultUnlockSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("VaultUnlockDivider")

        # Password Input Row with Eye Toggle
        self.pw_input = PasswordInputWidget(placeholder="Master Password…", parent=self)
        self.pw_input.returnPressed.connect(self._on_submit)
        self.pw_input.setToolTip("Enter your Master Password (configured in Settings ⚙)")

        # Error label
        self.error_lbl = QLabel("")
        self.error_lbl.setObjectName("VaultUnlockError")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_lbl.setWordWrap(True)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("VaultUnlockCancelBtn")
        self.cancel_btn.setFixedHeight(38)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setToolTip("Cancel and keep Vault locked (Esc)")
        self.cancel_btn.clicked.connect(self.reject)

        self.submit_btn = QPushButton("🔓 Unlock Vault")
        self.submit_btn.setObjectName("VaultUnlockSubmitBtn")
        self.submit_btn.setFixedHeight(38)
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.setToolTip("Verify Master Password and decrypt Vault (Enter)")
        self.submit_btn.clicked.connect(self._on_submit)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.submit_btn)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(divider)
        layout.addWidget(self.pw_input)
        layout.addWidget(self.error_lbl)
        layout.addStretch()
        layout.addLayout(btn_layout)

        if not has_master_password():
            self.pw_input.setEnabled(False)
            self.submit_btn.setEnabled(False)
            self.error_lbl.setText("No Master Password configured. Set one in Settings (⚙) first.")

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

    def accept(self) -> None:
        self._scrub_inputs()
        super().accept()

    def reject(self) -> None:
        self._scrub_inputs()
        super().reject()

    def closeEvent(self, event) -> None:
        self._scrub_inputs()
        super().closeEvent(event)

    def _scrub_inputs(self) -> None:
        self.pw_input.clear()

    def _on_submit(self) -> None:
        password = self.pw_input.text()
        if not password:
            self.error_lbl.setText("Password cannot be empty.")
            return

        if self._controller.unlock(password):
            self.accept()
        else:
            self._attempts += 1
            self.pw_input.clear()
            self.pw_input.setFocus()
            msg = "Incorrect Master Password."
            if self._attempts >= 3:
                msg += f" ({self._attempts} failed attempts)"
            self.error_lbl.setText(msg)
