"""
ui/widgets/password_input.py
────────────────────────────
Reusable unified password input component with built-in visibility toggle (👁️ / 🙈).
Shared across all authentication dialogs (LockScreen, VaultUnlockDialog, etc.)
to guarantee 100% UI and UX consistency across DotGhostBoard.

v2.1.0 Leviathan — Design System Unification.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)


class PasswordInputWidget(QWidget):
    """
    Composite password input widget containing a QLineEdit and an eye toggle button.
    Exposes familiar QLineEdit methods so it can be used as a drop-in replacement.
    """

    returnPressed = pyqtSignal()
    textChanged = pyqtSignal(str)

    def __init__(
        self,
        placeholder: str = "Master Password…",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("PasswordInputContainer")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._line_edit = QLineEdit(self)
        self._line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._line_edit.setPlaceholderText(placeholder)
        self._line_edit.setObjectName("PasswordInputField")
        self._line_edit.setFixedHeight(42)
        self._line_edit.returnPressed.connect(self.returnPressed.emit)
        self._line_edit.textChanged.connect(self.textChanged.emit)

        self._eye_btn = QPushButton("👁️", self)
        self._eye_btn.setObjectName("PasswordInputEyeBtn")
        self._eye_btn.setFixedSize(42, 42)
        self._eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eye_btn.setToolTip("Show / Hide password")
        self._eye_btn.clicked.connect(self._toggle_visibility)

        layout.addWidget(self._line_edit, 1)
        layout.addWidget(self._eye_btn)

    @property
    def line_edit(self) -> QLineEdit:
        return self._line_edit

    @property
    def eye_btn(self) -> QPushButton:
        return self._eye_btn

    def text(self) -> str:
        return self._line_edit.text()

    def setText(self, text: str) -> None:
        self._line_edit.setText(text)

    def clear(self) -> None:
        self._line_edit.clear()
        self._line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._eye_btn.setText("👁️")

    def setFocus(self) -> None:
        self._line_edit.setFocus()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._line_edit.setEnabled(enabled)
        self._eye_btn.setEnabled(enabled)

    def setPlaceholderText(self, text: str) -> None:
        self._line_edit.setPlaceholderText(text)

    def echoMode(self) -> QLineEdit.EchoMode:
        return self._line_edit.echoMode()

    def setEchoMode(self, mode: QLineEdit.EchoMode) -> None:
        self._line_edit.setEchoMode(mode)
        if mode == QLineEdit.EchoMode.Password:
            self._eye_btn.setText("👁️")
        else:
            self._eye_btn.setText("🙈")

    def setToolTip(self, text: str) -> None:
        self._line_edit.setToolTip(text)

    def _toggle_visibility(self) -> None:
        if self._line_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._eye_btn.setText("🙈")
        else:
            self._line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._eye_btn.setText("👁️")
