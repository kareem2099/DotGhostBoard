"""
ui/widgets/secret_toast.py
──────────────────────────
A non-blocking toast displayed when a password or secret candidate is detected.
Allows the user to save to Vault directly, keep in normal history (false positive),
or dismiss. Holds candidate text in memory only with a 60-second TTL.
"""

from typing import Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class SecretDetectedToast(QFrame):
    """
    Non-blocking toast for secret candidates:
    - In-memory retention with 60s TTL.
    - 3 options: Save to Vault, Keep in History, Dismiss.
    - Plaintext is always masked in preview.
    - Supports already_saved variant for pre-secured secrets.
    """

    sig_save_to_vault = pyqtSignal(str)    # (candidate_text)
    sig_keep_in_history = pyqtSignal(str)  # (candidate_text)
    sig_timeout = pyqtSignal(str)          # (candidate_text)
    sig_dismissed = pyqtSignal()

    def __init__(self, candidate_text: str, parent=None, already_saved: Optional[str] = None):
        super().__init__(parent)
        self._candidate_text: str = "" if already_saved else candidate_text
        self._already_saved: Optional[str] = already_saved

        self.setObjectName("SecretDetectedToast")
        self.setFixedWidth(380)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QFrame#SecretDetectedToast {
                background: #16181b;
                border: 1px solid #36413a;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        if already_saved:
            # Header with icon
            header = QLabel("✅ Already Secured")
            header.setStyleSheet("color: #44ec85; font-weight: 700; font-size: 12px;")
            layout.addWidget(header)

            subtext = QLabel(f"Found in {already_saved} — nothing to do.")
            subtext.setStyleSheet("color: #8c959c; font-size: 10px;")
            subtext.setWordWrap(True)
            layout.addWidget(subtext)
        else:
            # Header with icon
            header = QLabel("🛡️ Secret / Password Detected")
            header.setStyleSheet("color: #00ff41; font-weight: 700; font-size: 12px;")
            layout.addWidget(header)

            # Subtext explaining zero-log behavior
            subtext = QLabel("Prevented from saving to public board. What would you like to do?")
            subtext.setStyleSheet("color: #8c959c; font-size: 10px;")
            subtext.setWordWrap(True)
            layout.addWidget(subtext)

        # Masked preview (fixed-length mask, zero revealed characters)
        preview_lbl = QLabel("••••••••••••")
        preview_lbl.setStyleSheet(
            "background: #101214; color: #00ff41; padding: 4px 8px; "
            "border-radius: 4px; font-family: monospace; font-size: 13px; letter-spacing: 2px;"
        )
        layout.addWidget(preview_lbl)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        dismiss_btn = QPushButton("✕ Dismiss")
        dismiss_btn.setFixedHeight(26)
        dismiss_btn.setStyleSheet("""
            QPushButton {
                background: #1c1f22;
                color: #7b8388;
                border: 1px solid #282c30;
                border-radius: 5px;
                padding: 0 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #ffffff;
                background: #252a2e;
            }
        """)
        dismiss_btn.clicked.connect(self._on_dismiss)
        btn_row.addWidget(dismiss_btn)

        if not already_saved:
            keep_btn = QPushButton("📋 Keep")
            keep_btn.setFixedHeight(26)
            keep_btn.setToolTip("False positive? Save to normal clipboard history")
            keep_btn.setStyleSheet("""
                QPushButton {
                    background: #1c1f22;
                    color: #a0a6ac;
                    border: 1px solid #363d42;
                    border-radius: 5px;
                    padding: 0 10px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    color: #ffffff;
                    background: #2b3237;
                }
            """)
            keep_btn.clicked.connect(self._on_keep_in_history)
            btn_row.addWidget(keep_btn)

            btn_row.addStretch()

            save_btn = QPushButton("🛡️ Save to Vault")
            save_btn.setFixedHeight(26)
            save_btn.setStyleSheet("""
                QPushButton {
                    background: #2bbf5c;
                    color: #08100b;
                    border: none;
                    border-radius: 5px;
                    padding: 0 12px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background: #35cf68;
                }
            """)
            save_btn.clicked.connect(self._on_save_to_vault)
            btn_row.addWidget(save_btn)
        else:
            btn_row.addStretch()

        layout.addLayout(btn_row)
        self.adjustSize()

        if already_saved:
            QTimer.singleShot(4000, self._on_dismiss)
        else:
            # 60s TTL timer — started in showEvent so it only ticks when toast is visible
            self._ttl_timer = QTimer(self)
            self._ttl_timer.setSingleShot(True)
            self._ttl_timer.setInterval(60_000)
            self._ttl_timer.timeout.connect(self._on_timeout)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "_ttl_timer") and not self._ttl_timer.isActive():
            self._ttl_timer.start()

    def scrub(self):
        """Zero out the candidate text in memory immediately."""
        self._candidate_text = ""

    def _on_save_to_vault(self):
        if hasattr(self, "_ttl_timer"):
            self._ttl_timer.stop()
        candidate = self._candidate_text
        self.scrub()
        self.sig_save_to_vault.emit(candidate)

    def _on_keep_in_history(self):
        if hasattr(self, "_ttl_timer"):
            self._ttl_timer.stop()
        candidate = self._candidate_text
        self.scrub()
        self.sig_keep_in_history.emit(candidate)

    def _on_dismiss(self):
        if hasattr(self, "_ttl_timer"):
            self._ttl_timer.stop()
        self.scrub()
        self.sig_dismissed.emit()

    def _on_timeout(self):
        if hasattr(self, "_ttl_timer"):
            self._ttl_timer.stop()
        candidate = self._candidate_text
        self.scrub()
        self.sig_timeout.emit(candidate)
