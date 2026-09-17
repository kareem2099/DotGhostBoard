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

from core.api_server import APIServerThread
from core.network_discovery import DotGhostDiscovery
from core.services.sync_service import SyncService
from core.sync_engine import SyncEngine
from ui.pairing_dialog import PairingDialog

logger = logging.getLogger(__name__)


class SyncController(QObject):
    """
    Behavioral controller for peer pairing, network discovery,
    API server lifecycle, and background synchronization.
    """
    peer_paired = pyqtSignal(str)                # node_id
    peer_unpaired = pyqtSignal(str)              # node_id
    peer_discovered = pyqtSignal(dict)           # device data dict
    peer_removed = pyqtSignal(str)               # node_id
    sync_received_signal = pyqtSignal(int, str)  # item_id, text
    api_text_received = pyqtSignal(int, str)     # item_id, text
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

        self._api_thread: Optional[APIServerThread] = None
        self._discovery_thread: Optional[DotGhostDiscovery] = None
        self._sync_engine: Optional[SyncEngine] = None
        self._active_pairing_dialogs: dict[str, PairingDialog] = {}

        self._setup_widget()

    @property
    def service(self) -> SyncService:
        return self._service

    @property
    def api_thread(self) -> Optional[APIServerThread]:
        return self._api_thread

    @property
    def discovery_thread(self) -> Optional[DotGhostDiscovery]:
        return self._discovery_thread

    @property
    def sync_engine(self) -> Optional[SyncEngine]:
        return self._sync_engine

    @property
    def active_pairing_dialogs(self) -> dict[str, PairingDialog]:
        return self._active_pairing_dialogs

    def _setup_widget(self):
        self._devices_list.itemDoubleClicked.connect(self._on_item_double_clicked)

    # ──────────────────────────────────────────
    # Sync Engine Lifecycle
    # ──────────────────────────────────────────
    def init_sync_engine(self, is_locked: bool = False):
        """Configure and initialize SyncEngine if session is unlocked."""
        if is_locked:
            return
        node_id = self._settings.get("node_id", "")
        port = self._settings.get("api_port", 9090)
        self._service.configure(node_id, port)
        self._sync_engine = getattr(self._service, "_sync_engine", None)

    # ──────────────────────────────────────────
    # API Server Lifecycle
    # ──────────────────────────────────────────
    def start_api_server(self, is_locked: bool = False):
        """Start the local API server if enabled and unlocked."""
        if is_locked:
            return
        if not self._settings.get("api_enabled", False):
            return

        port = self._settings.get("api_port", 9090)
        token = self._settings.get("api_token", "")
        node_id = self._settings.get("node_id", "")
        device_name = self._settings.get("device_name", "")
        if not token or not node_id:
            return

        if self._api_thread is not None and self._api_thread.isRunning():
            return

        self._api_thread = APIServerThread(
            port, token, node_id, device_name, parent=self
        )
        self._api_thread.new_text_received.connect(self._on_api_new_text)
        self._api_thread.pairing_requested.connect(self._on_pairing_requested)
        self._api_thread.pairing_completed.connect(self._on_pairing_completed)
        self._api_thread.pairing_failed.connect(self._on_pairing_failed)
        self._api_thread.peer_unpaired.connect(self.handle_peer_unpaired)
        self._api_thread.sync_received.connect(self._on_sync_received)
        self._api_thread.start()

    def stop_api_server(self, timeout_ms: int = 2000):
        """Gracefully stop and wait for the API server thread."""
        if self._api_thread:
            self._api_thread.stop()
            self._api_thread.wait(timeout_ms)
            self._api_thread = None

    # ──────────────────────────────────────────
    # Network Discovery Lifecycle
    # ──────────────────────────────────────────
    def start_discovery(self, is_locked: bool = False):
        """Start UDP broadcast discovery if session is unlocked."""
        if is_locked:
            return

        if self._discovery_thread is not None and self._discovery_thread.isRunning():
            return

        port = self._settings.get("api_port", 9090)
        device_name = self._settings.get("device_name", "Unknown Ghost")
        node_id = self._settings.get("node_id", "ghost_node")

        self._discovery_thread = DotGhostDiscovery(
            port, device_name, node_id, parent=self
        )
        self._discovery_thread.signals.device_discovered.connect(self.add_or_update_device)
        self._discovery_thread.signals.device_removed.connect(self.remove_device)
        self._discovery_thread.start()

    def stop_discovery(self, timeout_ms: int = 2000):
        """Stop and wait for the discovery thread."""
        if self._discovery_thread:
            self._discovery_thread.stop()
            self._discovery_thread.wait(timeout_ms)
            self._discovery_thread = None

    # ──────────────────────────────────────────
    # Bulk Start / Stop
    # ──────────────────────────────────────────
    def start_all(self, is_locked: bool = False):
        """Start all network and sync services."""
        if is_locked:
            return
        self.init_sync_engine(is_locked=False)
        self.start_api_server(is_locked=False)
        self.start_discovery(is_locked=False)

    def stop_all(self, timeout_ms: int = 2000):
        """Stop all background sync and discovery services."""
        self.stop_api_server(timeout_ms)
        self.stop_discovery(timeout_ms)

    # ──────────────────────────────────────────
    # Internal Handlers
    # ──────────────────────────────────────────
    def _on_api_new_text(self, item_id: int, text: str):
        self.broadcast_text(text)
        self.api_text_received.emit(item_id, text)

    def _on_sync_received(self, item_id: int, text: str):
        self.sync_received_signal.emit(item_id, text)
        msg = f"📥 Synced from peer: {text[:40]}..." if len(text) > 40 else f"📥 Synced: {text}"
        self.status_message.emit(msg)

    def _on_pairing_requested(self, node_id: str, device_name: str):
        salt = None
        if self._api_thread:
            salt = self._api_thread.pending_salts.get(node_id)

        dlg_parent = self._parent_window or self._devices_list.window()
        dialog = PairingDialog(
            role="receiver",
            peer_node_id=node_id,
            peer_name=device_name,
            salt=salt,
            parent=dlg_parent,
        )

        self._active_pairing_dialogs[node_id] = dialog

        if self._api_thread:
            self._api_thread.active_pairing_sessions[node_id] = dialog.session

        if dialog.exec():
            pass
        else:
            if self._api_thread:
                self._api_thread.active_pairing_sessions.pop(node_id, None)
                self._api_thread.pending_salts.pop(node_id, None)

        self._active_pairing_dialogs.pop(node_id, None)

    def _on_pairing_completed(self, node_id: str, device_name: str):
        self.status_message.emit(f"Successfully paired with {device_name}!")
        self.add_or_update_device(node_id, {"device_name": device_name, "ip": "paired", "port": 0})
        if node_id in self._active_pairing_dialogs:
            self._active_pairing_dialogs[node_id].mark_completed()
        self.peer_paired.emit(node_id)

    def _on_pairing_failed(self, node_id: str, error_message: str):
        self.status_message.emit(f"Pairing failed: {error_message}")
        if node_id in self._active_pairing_dialogs:
            self._active_pairing_dialogs[node_id].mark_failed(error_message)

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
