"""
ui/vault/secret_dialog.py
─────────────────────────
Modal dialog to create or edit an encrypted secret item in The Vault.

v2.0.0 Cerberus — Phase 7 Vault UI Subsystem.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class SecretDialog(QDialog):
    """
    Dialog for adding or editing a secret item.
    """

    CATEGORIES = [
        ("generic", "🛡️ Generic"),
        ("password", "🔑 Password"),
        ("token", "🪙 API Token"),
        ("key", "🔐 Private Key"),
        ("note", "📜 Secure Note"),
    ]

    def __init__(
        self,
        title: str = "",
        category: str = "generic",
        item_id: Optional[int] = None,
        secret_payload: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._item_id = item_id
        self._is_edit = item_id is not None

        self.setWindowTitle("Edit Secret" if self._is_edit else "Add New Secret")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setFixedSize(440, 420)

        self._build_ui(title, category, secret_payload)
        self._apply_style()

    def _build_ui(self, title: str, category: str, secret_payload: str = "") -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        # Title
        header_text = "✏️  Edit Secret" if self._is_edit else "🛡️  Add New Secret"
        header = QLabel(header_text)
        header.setObjectName("SecretDialogTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("SecretDialogDivider")

        # Title input
        title_label = QLabel("Title")
        title_label.setObjectName("SecretFieldLabel")
        self.title_input = QLineEdit()
        self.title_input.setText(title)
        self.title_input.setPlaceholderText("e.g. AWS Production Token, GitHub Personal Token…")
        self.title_input.setObjectName("SecretInput")
        self.title_input.setFixedHeight(36)

        # Category dropdown
        cat_label = QLabel("Category")
        cat_label.setObjectName("SecretFieldLabel")
        self.cat_combo = QComboBox()
        self.cat_combo.setObjectName("SecretCombo")
        self.cat_combo.setFixedHeight(36)
        for cat_id, cat_name in self.CATEGORIES:
            self.cat_combo.addItem(cat_name, cat_id)

        idx = self.cat_combo.findData(category.lower())
        if idx >= 0:
            self.cat_combo.setCurrentIndex(idx)

        # Secret payload input
        secret_label = QLabel("Secret Payload (Encrypted)")
        secret_label.setObjectName("SecretFieldLabel")
        self.secret_input = QTextEdit()
        self.secret_input.setObjectName("SecretTextEdit")
        if self._is_edit:
            self.secret_input.setPlaceholderText("Leave empty to keep existing secret unchanged…")
        else:
            self.secret_input.setPlaceholderText("Enter sensitive secret text, token, key, or password…")
        if secret_payload:
            self.secret_input.setPlainText(secret_payload)
            self.title_input.setFocus()

        # Error label
        self.error_lbl = QLabel("")
        self.error_lbl.setObjectName("SecretDialogError")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecretCancelBtn")
        self.cancel_btn.setFixedHeight(36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)

        save_label = "Update Secret" if self._is_edit else "Save to Vault"
        self.save_btn = QPushButton(f"🔐 {save_label}")
        self.save_btn.setObjectName("SecretSaveBtn")
        self.save_btn.setFixedHeight(36)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)

        layout.addWidget(header)
        layout.addWidget(divider)
        layout.addWidget(title_label)
        layout.addWidget(self.title_input)
        layout.addWidget(cat_label)
        layout.addWidget(self.cat_combo)
        layout.addWidget(secret_label)
        layout.addWidget(self.secret_input)
        layout.addWidget(self.error_lbl)
        layout.addLayout(btn_layout)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #111315;
                border: 1px solid #282c30;
                border-radius: 12px;
            }
            #SecretDialogTitle {
                color: #00ff41;
                font-size: 16px;
                font-weight: 700;
            }
            #SecretDialogDivider {
                background: #202428;
                max-height: 1px;
                border: none;
            }
            #SecretFieldLabel {
                color: #8c969d;
                font-size: 11px;
                font-weight: 600;
            }
            #SecretInput, #SecretCombo {
                background: #181b1d;
                color: #e4e7e9;
                border: 1px solid #2f3438;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
            }
            #SecretInput:focus, #SecretCombo:focus {
                border: 1px solid #2bbf5c;
                background: #1a1d20;
            }
            #SecretTextEdit {
                background: #181b1d;
                color: #e4e7e9;
                border: 1px solid #2f3438;
                border-radius: 6px;
                padding: 8px;
                font-family: monospace;
                font-size: 12px;
            }
            #SecretTextEdit:focus {
                border: 1px solid #2bbf5c;
                background: #1a1d20;
            }
            #SecretDialogError {
                color: #e26f6f;
                font-size: 11px;
                min-height: 16px;
            }
            #SecretCancelBtn {
                background: #1a1c1e;
                color: #8c959c;
                border: 1px solid #292d30;
                border-radius: 7px;
                font-size: 12px;
                padding: 0 16px;
            }
            #SecretCancelBtn:hover {
                background: #222629;
                color: #ffffff;
            }
            #SecretSaveBtn {
                background: #2bbf5c;
                color: #08100b;
                border: none;
                border-radius: 7px;
                font-weight: 700;
                font-size: 12px;
                padding: 0 20px;
            }
            #SecretSaveBtn:hover {
                background: #35cf68;
            }
            #SecretSaveBtn:pressed {
                background: #24a94f;
            }
        """)

    def scrub_inputs(self) -> None:
        self.secret_input.clear()
        if self.secret_input.document():
            self.secret_input.document().clearUndoRedoStacks()
        self.title_input.clear()

    def reject(self) -> None:
        self.scrub_inputs()
        super().reject()

    def closeEvent(self, event) -> None:
        self.scrub_inputs()
        super().closeEvent(event)

    def _on_save(self) -> None:
        title = self.title_input.text().strip()
        if not title:
            self.error_lbl.setText("Title cannot be empty.")
            self.title_input.setFocus()
            return

        secret_text = self.secret_input.toPlainText()
        if not self._is_edit and not secret_text:
            self.error_lbl.setText("Secret payload cannot be empty.")
            self.secret_input.setFocus()
            return

        self.accept()

    def get_data(self) -> tuple[str, Optional[str], str]:
        """
        Returns (title, secret_text_or_None, category_id).
        """
        title = self.title_input.text().strip()
        secret_text = self.secret_input.toPlainText()
        cat_id = self.cat_combo.currentData() or "generic"
        payload = secret_text if (secret_text or not self._is_edit) else None
        return title, payload, cat_id
