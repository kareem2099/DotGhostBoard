"""
ui/widgets/pin_toast.py
───────────────────────
A non-blocking toast shown at the bottom-left of the Dashboard
suggesting the user to pin a frequently-copied item.
Disappears after PIN_TOAST_DURATION_MS or when the user clicks Pin/Dismiss.
"""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core.constants import PIN_SUGGESTION_THRESHOLD, PIN_TOAST_DURATION_MS


class PinSuggestionToast(QFrame):
    """
    A non-blocking toast shown at the bottom-left of the Dashboard
    suggesting the user to pin a frequently-copied item.
    Disappears after PIN_TOAST_DURATION_MS or when the user clicks Pin/Dismiss.
    """
    sig_pin = pyqtSignal(int)  # item_id
    sig_close = pyqtSignal()

    def __init__(self, item_id: int, preview: str, parent=None):
        super().__init__(parent)
        self._item_id = item_id
        self.setObjectName("PinToast")
        self.setFixedWidth(340)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QFrame#PinToast {
                background: #151b17;
                border: 1px solid #31513b;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # Header
        header = QLabel(f"📌 You've copied this {PIN_SUGGESTION_THRESHOLD} times — Pin it?")
        header.setStyleSheet("color:#77dd98; font-weight:600; font-size:12px;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Preview snippet
        snippet = QLabel(f"\"{preview}\"")
        snippet.setStyleSheet("color:#888; font-size:11px;")
        snippet.setWordWrap(True)
        snippet.setMaximumWidth(310)
        layout.addWidget(snippet)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setFixedHeight(26)
        dismiss_btn.setStyleSheet(
            "QPushButton { background:#1a1c1e; color:#7e868a; border:1px solid #292d30;"
            "border-radius:5px; padding:0 12px; font-size:11px; }"
            "QPushButton:hover { color:#d2d6d8; border-color:#363b3f; background:#222528; }"
        )
        dismiss_btn.clicked.connect(self._dismiss)
        btn_row.addWidget(dismiss_btn)

        pin_btn = QPushButton("📌  Pin It")
        pin_btn.setFixedHeight(26)
        pin_btn.setStyleSheet("""
            QPushButton {
                background:#2bbf5c;
                color:#08100b;
                border:none;
                border-radius:5px;
                padding:0 14px;
                font-size:11px;
                font-weight:700;
            }
            QPushButton:hover {
                background:#35cf68;
            }
        """)
        pin_btn.clicked.connect(self._on_pin)
        btn_row.addWidget(pin_btn)

        layout.addLayout(btn_row)
        self.adjustSize()

        # Auto-dismiss after PIN_TOAST_DURATION_MS
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PIN_TOAST_DURATION_MS)
        self._timer.timeout.connect(self._dismiss)
        self._timer.start()

    def _on_pin(self):
        self._timer.stop()
        self.sig_pin.emit(self._item_id)
        self._dismiss()

    def _dismiss(self):
        self._timer.stop()
        self.sig_close.emit()
        self.deleteLater()
