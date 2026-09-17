"""
ui/components/sidebar.py
────────────────────────
Collections & Devices sidebar component for DotGhostBoard Dashboard.

v2.0.0 Cerberus — Phase 6 Dashboard Decomposition.
Owns only the UI structure (widgets and layout). Controllers and services
are injected externally from Dashboard.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from core.constants import DEVICES_LIST_HEIGHT, SIDEBAR_WIDTH


class SidebarWidget(QFrame):
    """
    Sidebar panel containing:
      • Collections header with '+' button and collections list.
      • Devices header and LAN sync devices list.
    """

    create_collection_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(10)

        # ── Collections Header & List ──
        coll_header = QHBoxLayout()
        coll_label = QLabel("📁 COLLECTIONS")
        coll_label.setStyleSheet(
            "color: #666; font-weight: bold; font-size: 11px; letter-spacing: 1px;"
        )

        self.add_coll_btn = QPushButton("+")
        self.add_coll_btn.setObjectName("AddCollBtn")
        self.add_coll_btn.setFixedSize(24, 24)
        self.add_coll_btn.setToolTip("New Collection")
        self.add_coll_btn.clicked.connect(self.create_collection_requested.emit)

        coll_header.addWidget(coll_label)
        coll_header.addStretch()
        coll_header.addWidget(self.add_coll_btn)
        layout.addLayout(coll_header)

        self.collections_list = QListWidget()
        self.collections_list.setObjectName("CollectionsList")
        layout.addWidget(self.collections_list)

        # ── Devices Header & List ──
        layout.addSpacing(16)
        dev_header = QHBoxLayout()
        dev_label = QLabel("🌐 DEVICES")
        dev_label.setStyleSheet(
            "color: #666; font-weight: bold; font-size: 11px; letter-spacing: 1px;"
        )
        dev_header.addWidget(dev_label)
        dev_header.addStretch()
        layout.addLayout(dev_header)

        self.devices_list = QListWidget()
        self.devices_list.setObjectName("DevicesList")
        self.devices_list.setFixedHeight(DEVICES_LIST_HEIGHT)
        self.devices_list.setToolTip("Double-click a device to pair")
        layout.addWidget(self.devices_list)

    def set_collapsed(self, collapsed: bool):
        """Collapse or restore the sidebar for responsive view."""
        self.setVisible(not collapsed)
