"""
Lock Screen — Eclipse v1.4.0
──────────────────────────────
Modal, frameless, always-on-top dialog that blocks all dashboard
interaction until the correct master password is entered.

Two modes:
  setup=False (default) — unlock: verifies against stored verifier.
  setup=True            — first-time: creates new master password.
"""

from __future__ import annotations

import os
from PyQt6.QtWidgets import (
    QApplication,
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent

from core.crypto import (
    derive_key, verify_password,
    save_master_password,
)
from ui.widgets.password_input import PasswordInputWidget


class LockScreen(QDialog):
    """
    Full-window lock dialog.

    After exec() returns Accepted, call get_key() to obtain the
    derived AES key for this session.
    """

    MAX_ATTEMPTS = 5   # Log warning after this many failures (no hard lockout)

    def __init__(self, parent=None, *, setup: bool = False) -> None:
        super().__init__(parent)
        self._setup = setup
        self._key: bytes | None = None
        self._attempts = 0

        self.setWindowTitle("DotGhostBoard — Locked")
        self.setObjectName("LockScreen")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setFixedSize(420, 290 if setup else 235)

        self._build_ui()
        self._apply_style()

        # Auto-focus password field after widget is shown
        QTimer.singleShot(80, self.pw_input.setFocus)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 22, 32, 22)
        root.setSpacing(10)

        # ── Header ──
        title = QLabel("👻  DotGhostBoard")
        title.setObjectName("LockTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle_text = "Set Master Password" if self._setup else "🔒  Session Locked"
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("LockSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("LockDivider")

        # ── Password input ──
        self.pw_input = PasswordInputWidget(placeholder="Enter master password…", parent=self)
        self.pw_input.returnPressed.connect(self._on_submit)

        # ── Confirm input (setup only) ──
        self.confirm_input = PasswordInputWidget(placeholder="Confirm password…", parent=self)
        self.confirm_input.returnPressed.connect(self._on_submit)
        self.confirm_input.setVisible(self._setup)

        # ── Error label ──
        self.error_lbl = QLabel("")
        self.error_lbl.setObjectName("LockError")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_lbl.setWordWrap(True)

        # ── Submit button ──
        btn_label = "🔐  Set Password" if self._setup else "🔓  Unlock"
        self.submit_btn = QPushButton(btn_label)
        self.submit_btn.setObjectName("LockBtn")
        self.submit_btn.setFixedHeight(38)
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.clicked.connect(self._on_submit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.submit_btn)
        btn_row.addStretch()

        # ── Assemble ──
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(divider)
        root.addWidget(self.pw_input)
        root.addWidget(self.confirm_input)
        root.addWidget(self.error_lbl)
        root.addStretch()
        root.addLayout(btn_row)

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

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _on_submit(self) -> None:
        password = self.pw_input.text()

        if not password:
            self._show_error("Password cannot be empty.")
            return

        if self._setup:
            self._handle_setup(password)
        else:
            self._handle_unlock(password)

    def _handle_setup(self, password: str) -> None:
        if len(password) < 6:
            self._show_error("Password must be at least 6 characters.")
            return

        confirm = self.confirm_input.text()
        if password != confirm:
            self._show_error("Passwords do not match.")
            self.confirm_input.clear()
            self.pw_input.clear()
            self.pw_input.setFocus()
            return

        try:
            save_master_password(password)
            self._key = derive_key(password)
            self.accept()
        except ValueError as e:
            self._show_error(str(e))

    def _handle_unlock(self, password: str) -> None:
        if verify_password(password):
            self._key = derive_key(password)
            self.accept()
        else:
            self._attempts += 1
            self.pw_input.clear()
            self.pw_input.setFocus()

            msg = "Incorrect password."
            if self._attempts >= 3:
                msg += f"  ({self._attempts} failed attempt{'s' if self._attempts > 1 else ''})"
            self._show_error(msg)

            if self._attempts >= self.MAX_ATTEMPTS:
                import logging
                logging.getLogger(__name__).warning(
                    "[LockScreen] %d failed unlock attempts", self._attempts
                )

    def _show_error(self, msg: str) -> None:
        self.error_lbl.setText(msg)

    # ── Public helpers ────────────────────────────────────────────────────────

    def get_key(self) -> bytes | None:
        """
        Returns the derived AES-256 key if unlock/setup succeeded.
        None if dialog was cancelled or not yet accepted.
        """
        return self._key

    # ── Escape cannot close a lock screen ────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() != Qt.Key.Key_Escape:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:   # type: ignore[override]
        # Prevent closing via window manager if no key was obtained
        if self._key is None:
            event.ignore()
        else:
            super().closeEvent(event)
