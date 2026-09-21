"""
ui/vault/unlock_dialog.py
─────────────────────────
Modal dialog to prompt for Master Password and unlock The Vault.

v2.0.0 Cerberus — Phase 7 Vault UI Subsystem.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.crypto import has_master_password
from ui.vault.vault_controller import VaultController


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
        self.setModal(True)
        self.setFixedSize(420, 280)

        self._build_ui()
        self._apply_style()

        QTimer.singleShot(80, self.pw_input.setFocus)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(12)

        # Header
        title = QLabel("🛡️  The Vault")
        title.setObjectName("VaultUnlockTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Enter Master Password to unlock encrypted secrets")
        subtitle.setObjectName("VaultUnlockSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("VaultUnlockDivider")

        # Password Input
        self.pw_input = QLineEdit()
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_input.setPlaceholderText("Master Password…")
        self.pw_input.setObjectName("VaultUnlockInput")
        self.pw_input.setFixedHeight(42)
        self.pw_input.returnPressed.connect(self._on_submit)

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
        self.cancel_btn.clicked.connect(self.reject)

        self.submit_btn = QPushButton("🔓 Unlock Vault")
        self.submit_btn.setObjectName("VaultUnlockSubmitBtn")
        self.submit_btn.setFixedHeight(38)
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.setStyleSheet("""
            QDialog {
                background: #111315;
                border: 1px solid #282c30;
                border-radius: 12px;
            }
            #VaultUnlockTitle {
                color: #00ff41;
                font-size: 18px;
                font-weight: 700;
            }
            #VaultUnlockSubtitle {
                color: #727a80;
                font-size: 12px;
            }
            #VaultUnlockDivider {
                background: #202428;
                max-height: 1px;
                border: none;
            }
            #VaultUnlockInput {
                background: #181b1d;
                color: #e4e7e9;
                border: 1px solid #2f3438;
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 13px;
            }
            #VaultUnlockInput:focus {
                border: 1px solid #2bbf5c;
                background: #1a1d20;
            }
            #VaultUnlockError {
                color: #e26f6f;
                font-size: 11px;
                min-height: 16px;
            }
            #VaultUnlockCancelBtn {
                background: #1a1c1e;
                color: #8c959c;
                border: 1px solid #292d30;
                border-radius: 7px;
                font-size: 12px;
                padding: 0 16px;
            }
            #VaultUnlockCancelBtn:hover {
                background: #222629;
                color: #ffffff;
            }
            #VaultUnlockSubmitBtn {
                background: #2bbf5c;
                color: #08100b;
                border: none;
                border-radius: 7px;
                font-weight: 700;
                font-size: 12px;
                padding: 0 20px;
            }
            #VaultUnlockSubmitBtn:hover {
                background: #35cf68;
            }
            #VaultUnlockSubmitBtn:pressed {
                background: #24a94f;
            }
        """)

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
