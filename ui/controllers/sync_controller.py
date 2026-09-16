"""
ui/controllers/sync_controller.py
─────────────────────────────────
Controller managing peer synchronization, network discovery UI,
device list state, and pairing flows.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QWidget,
)

from core.services.sync_service import SyncService

logger = logging.getLogger(__name__)


class SyncController(QObject):
    """
    Behavioral controller for peer pairing and synchronization.
    Manages devices_list interactions and coordinates broadcasting.
    """
    peer_paired = pyqtSignal(str)            # node_id
    peer_unpaired = pyqtSignal(str)          # node_id
    peer_discovered = pyqtSignal(dict)       # device data dict
    peer_removed = pyqtSignal(str)           # node_id
    sync_received_signal = pyqtSignal(int, str)  # item_id, text
    status_message = pyqtSignal(str)

    def __init__(
        self,
        service: SyncService,
        devices_list: QListWidget,
        settings: dict,
        parent_window: Optional[QWidget] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._service = service
        self._devices_list = devices_list
        self._settings = settings
        self._parent_window = parent_window

        self._setup_widget()

    @property
    def service(self) -> SyncService:
        return self._service

    def _setup_widget(self):
        self._devices_list.itemDoubleClicked.connect(self._on_item_double_clicked)

    def broadcast_text(self, text: str) -> None:
        """Broadcast text item to connected trusted peers."""
        self._service.push_text(text)

    def add_or_update_device(self, node_id: str, data: dict) -> None:
        """Called when a device is discovered on the local network."""
        for i in range(self._devices_list.count()):
            item = self._devices_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == node_id:
                # Device already in list, update data
                item.setData(Qt.ItemDataRole.UserRole + 1, data)
                item.setToolTip(f"ID: {node_id}\nIP: {data.get('ip')}:{data.get('port')}")
                return

        item = QListWidgetItem(f"📱 {data.get('device_name', 'Device')}")
        item.setData(Qt.ItemDataRole.UserRole, node_id)
        item.setData(Qt.ItemDataRole.UserRole + 1, data)
        item.setToolTip(f"ID: {node_id}\nIP: {data.get('ip')}:{data.get('port')}")

        if self._service.is_peer_trusted(node_id):
            item.setText(f"🔒 {data.get('device_name', 'Device')}")
            item.setForeground(QColor("#00ff41"))
        else:
            item.setForeground(QColor("#cccccc"))

        self._devices_list.addItem(item)
        self.peer_discovered.emit(data)
        self.status_message.emit(f"Discovered peer: {data.get('device_name')}")

    def remove_device(self, node_id: str) -> None:
        """Called when a device disconnects or is removed from discovery."""
        for i in range(self._devices_list.count()):
            item = self._devices_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == node_id:
                self._devices_list.takeItem(i)
                self.peer_removed.emit(node_id)
                break

    def handle_peer_unpaired(self, node_id: str) -> None:
        """Handle peer unpairing notification."""
        for i in range(self._devices_list.count()):
            item = self._devices_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == node_id:
                data = item.data(Qt.ItemDataRole.UserRole + 1) or {}
                name = data.get("device_name", "Device")
                item.setText(f"📱 {name}")
                item.setForeground(QColor("#ccc"))
                self.peer_unpaired.emit(node_id)
                self.status_message.emit(f"Disconnected from {name}")
                break

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Initiate pairing or unpairing when double-clicked."""
        node_id = item.data(Qt.ItemDataRole.UserRole)
        data = item.data(Qt.ItemDataRole.UserRole + 1) or {}
        device_name = data.get("device_name", "Device")
        dlg_parent = self._parent_window or self._devices_list.window()

        if self._service.is_peer_trusted(node_id):
            msg = QMessageBox(dlg_parent)
            msg.setWindowTitle("Device Options")
            msg.setText(f"<b>{device_name}</b> is already paired and trusted.")
            msg.setInformativeText("What would you like to do?")
            msg.setIcon(QMessageBox.Icon.Question)

            reconnect_btn = msg.addButton("🔄 Reconnect", QMessageBox.ButtonRole.AcceptRole)
            reconnect_btn.setObjectName("BulkBtn")

            disconnect_btn = msg.addButton("❌ Disconnect", QMessageBox.ButtonRole.DestructiveRole)
            disconnect_btn.setObjectName("BulkBtnDanger")

            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
            cancel_btn.setObjectName("BulkBtnCancel")

            msg.exec()

            if msg.clickedButton() in (disconnect_btn, reconnect_btn):
                self._service.unpair_peer(node_id, notify=True)
                self.status_message.emit(f"Unpaired with {device_name}")
                item.setText(f"📱 {device_name}")
                item.setForeground(QColor("#ccc"))
                self.peer_unpaired.emit(node_id)

                if msg.clickedButton() == disconnect_btn:
                    return

        # Open pairing dialog
        from ui.pairing_dialog import PairingDialog
        dialog = PairingDialog(
            role="initiator",
            peer_ip=data.get("ip", ""),
            peer_port=data.get("port", 9090),
            peer_node_id=node_id,
            peer_name=device_name,
            parent=dlg_parent,
        )
        if dialog.exec():
            self.status_message.emit(f"Successfully paired with {device_name}!")
            item.setText(f"🔒 {device_name}")
            item.setForeground(QColor("#00ff41"))
            self.peer_paired.emit(node_id)
