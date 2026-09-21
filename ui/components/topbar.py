"""
ui/components/topbar.py
───────────────────────
Top bar header component for DotGhostBoard Dashboard.

v2.0.0 Cerberus — Phase 6 Dashboard Decomposition.
Owns logo, update indicator, stats label, session lock button,
settings button, and clear history button.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from core.constants import TOP_BAR_HEIGHT


class TopBarWidget(QFrame):
    """
    Header bar containing:
      • Branding logo.
      • New update notification button (hidden until update is available).
      • Real-time stats label (e.g. item and pinned counts).
      • Eclipse session lock button ('🔒').
      • Settings button ('⚙').
      • Clear history button ('Clear History' / '🗑️').
    """

    settings_clicked = pyqtSignal()
    clear_history_clicked = pyqtSignal()
    lock_clicked = pyqtSignal()
    update_clicked = pyqtSignal()
    vault_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(TOP_BAR_HEIGHT)
        self._build_ui()

    def _build_ui(self):
        top_layout = QHBoxLayout(self)
        top_layout.setContentsMargins(12, 8, 12, 8)

        logo = QLabel("👻 DotGhostBoard")
        logo.setStyleSheet("font-size:15px; font-weight:bold; color:#00ff41;")

        self.stats_label = QLabel("")
        self.stats_label.setObjectName("StatLabel")

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("SettingsBtn")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self.settings_clicked.emit)

        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.setObjectName("ClearHistoryBtn")
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.setToolTip("Delete all un-pinned items")
        self.clear_btn.clicked.connect(self.clear_history_clicked.emit)

        self.vault_btn = QPushButton("🛡️")
        self.vault_btn.setObjectName("TopBarVaultBtn")
        self.vault_btn.setFixedSize(28, 28)
        self.vault_btn.setToolTip("The Vault (Ctrl+Shift+V)")
        self.vault_btn.clicked.connect(self.vault_clicked.emit)

        self.lock_btn = QPushButton("🔒")
        self.lock_btn.setObjectName("SessionLockBtn")
        self.lock_btn.setFixedSize(28, 28)
        self.lock_btn.setToolTip("Lock session (Eclipse)")
        self.lock_btn.clicked.connect(self.lock_clicked.emit)
        self.lock_btn.hide()

        self.update_btn = QPushButton("🎁 New Update!")
        self.update_btn.setStyleSheet("""
            background: #18251d;
            color: #77dd98;
            border: 1px solid #31513b;
            padding: 0 10px;
            border-radius: 5px;
            font-weight: 600;
        """)
        self.update_btn.setFixedHeight(28)
        self.update_btn.clicked.connect(self.update_clicked.emit)
        self.update_btn.hide()

        top_layout.addWidget(logo)
        top_layout.addStretch()
        top_layout.addWidget(self.update_btn)
        top_layout.addSpacing(8)
        top_layout.addWidget(self.stats_label)
        top_layout.addSpacing(8)
        top_layout.addWidget(self.vault_btn)
        top_layout.addSpacing(4)
        top_layout.addWidget(self.lock_btn)
        top_layout.addSpacing(4)
        top_layout.addWidget(self.settings_btn)
        top_layout.addSpacing(4)
        top_layout.addWidget(self.clear_btn)

    def set_stats_text(self, text: str):
        self.stats_label.setText(text)

    def set_lock_visible(self, visible: bool):
        self.lock_btn.setVisible(visible)

    def set_update_visible(self, visible: bool):
        self.update_btn.setVisible(visible)

    def set_compact_mode(self, compact: bool):
        """Toggle compact layout when window is resized below breakpoint."""
        if compact:
            self.stats_label.hide()
            self.clear_btn.setText("🗑️")
            self.clear_btn.setFixedSize(28, 28)
        else:
            self.stats_label.show()
            self.clear_btn.setText("Clear History")
            self.clear_btn.setMinimumWidth(90)
            self.clear_btn.setMaximumWidth(150)
