"""
ui/vault/backup_dialog.py
─────────────────────────
Modal dialogs for exporting and importing encrypted Vault packages (.vault).
Clearly explains AES-256-GCM authenticated encryption, PBKDF2 100k rounds,
and guarantees zero plaintext leakage.

v2.1.0 Leviathan — Vault Backup & Restore.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.security.vault.backup import MIN_PASSPHRASE_LEN


class VaultBackupDialog(QDialog):
    """
    Dialog for entering encryption passphrase during Vault export or import.
    Presents clear cryptographic guarantees so the user understands the
    underlying AES-256-GCM encryption and zero-plaintext security model.
    """

    def __init__(
        self,
        mode: str = "export",
        file_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._mode = mode  # "export" or "import"
        self._file_path = file_path
        self._passphrase: Optional[str] = None

        is_export = mode == "export"
        title_text = "Export Encrypted Backup (.vault)" if is_export else "Import Encrypted Backup (.vault)"
        self.setWindowTitle(title_text)
        self.setObjectName("VaultBackupDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setFixedWidth(520)

        self._build_ui()
        self._apply_style()
        self.adjustSize()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        is_export = self._mode == "export"

        # ── Header ──
        header_title = QLabel(
            "🛡️  Export Encrypted Vault Backup" if is_export else "📥  Decrypt Vault Backup"
        )
        header_title.setObjectName("SecretDialogTitle")
        header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_title)

        header_sub = QLabel(
            "Your secrets are encrypted into an independent .vault package."
            if is_export
            else f"Decrypt and restore secrets from: {os.path.basename(self._file_path or '')}"
        )
        header_sub.setObjectName("VaultUnlockSubtitle")
        header_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_sub.setWordWrap(True)
        layout.addWidget(header_sub)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("SecretDialogDivider")
        layout.addWidget(divider)

        # ── Cryptographic Security Banner ──
        info_frame = QFrame()
        info_frame.setObjectName("VaultBackupInfoBox")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setSpacing(6)

        info_title = QLabel(
            "🔐 Military-Grade Authenticated Encryption (AES-256-GCM)"
            if is_export
            else "🔒 Authenticated Cryptographic Decryption"
        )
        info_title.setObjectName("VaultBackupInfoTitle")
        info_layout.addWidget(info_title)

        if is_export:
            bullets = [
                ("• All secrets, passwords, history, and expiry are encrypted.", "normal"),
                ("• Key derived via PBKDF2-HMAC-SHA256 (100k rounds) + salt.", "normal"),
                ("• Zero plaintext stored: 100% safe for USB or cloud backup.", "normal"),
                ("⚠️ Remember this passphrase — without it, the backup cannot be opened!", "warn"),
            ]
        else:
            bullets = [
                ("• Enter the exact passphrase chosen when creating this backup.", "normal"),
                ("• The file's integrity and GCM authentication tag will be verified.", "normal"),
                ("• Duplicates already in your Vault will be automatically preserved.", "normal"),
            ]

        for text, kind in bullets:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            if kind == "warn":
                lbl.setObjectName("VaultBackupWarnDesc")
            else:
                lbl.setObjectName("VaultBackupInfoDesc")
            info_layout.addWidget(lbl)

        layout.addWidget(info_frame)

        # ── Password Inputs ──
        pw_label = QLabel("Backup Passphrase:" if not is_export else "Create Backup Passphrase (min 8 chars):")
        pw_label.setObjectName("VaultBackupLabel")
        layout.addWidget(pw_label)

        self._pw_input = QLineEdit()
        self._pw_input.setObjectName("VaultBackupInput")
        self._pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_input.setPlaceholderText("Enter passphrase…")
        self._pw_input.textChanged.connect(self._clear_error)
        layout.addWidget(self._pw_input)

        if is_export:
            confirm_label = QLabel("Confirm Passphrase:")
            confirm_label.setObjectName("VaultBackupLabel")
            layout.addWidget(confirm_label)

            self._confirm_input = QLineEdit()
            self._confirm_input.setObjectName("VaultBackupInput")
            self._confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._confirm_input.setPlaceholderText("Repeat passphrase…")
            self._confirm_input.textChanged.connect(self._clear_error)
            layout.addWidget(self._confirm_input)
        else:
            self._confirm_input = None

        # Show password toggle
        self._show_pw_check = QCheckBox("Show passphrase text")
        self._show_pw_check.setObjectName("VaultBackupCheck")
        self._show_pw_check.toggled.connect(self._on_toggle_show_pw)
        layout.addWidget(self._show_pw_check)

        # Error label
        self._error_lbl = QLabel("")
        self._error_lbl.setObjectName("VaultBackupError")
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._error_lbl)

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("VaultBackupCancelBtn")
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        submit_text = "🔒 Export Encrypted Backup" if is_export else "🔓 Decrypt & Import"
        self._submit_btn = QPushButton(submit_text)
        self._submit_btn.setObjectName("VaultBackupSubmitBtn")
        self._submit_btn.setFixedHeight(34)
        self._submit_btn.clicked.connect(self._on_submit)
        btn_layout.addWidget(self._submit_btn)

        layout.addLayout(btn_layout)

    def _on_toggle_show_pw(self, checked: bool) -> None:
        echo = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self._pw_input.setEchoMode(echo)
        if self._confirm_input:
            self._confirm_input.setEchoMode(echo)

    def _clear_error(self) -> None:
        self._error_lbl.setText("")

    def _on_submit(self) -> None:
        pw = self._pw_input.text().strip()

        if self._mode == "export":
            if len(pw) < MIN_PASSPHRASE_LEN:
                self._error_lbl.setText(f"Passphrase must be at least {MIN_PASSPHRASE_LEN} characters.")
                self._pw_input.setFocus()
                return

            confirm = self._confirm_input.text().strip() if self._confirm_input else ""
            if pw != confirm:
                self._error_lbl.setText("Passphrases do not match. Please re-check.")
                if self._confirm_input:
                    self._confirm_input.setFocus()
                return
        else:
            if not pw:
                self._error_lbl.setText("Passphrase cannot be empty.")
                self._pw_input.setFocus()
                return

        self._passphrase = pw
        self.accept()

    def get_passphrase(self) -> Optional[str]:
        return self._passphrase

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
