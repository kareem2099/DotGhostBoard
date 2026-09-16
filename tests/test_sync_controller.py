"""
tests/test_sync_controller.py
─────────────────────────────
Tests for SyncController coordination, broadcast, and devices list state.
"""

from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidget

from core.services.sync_service import SyncService
from ui.controllers.sync_controller import SyncController


@pytest.fixture
def fake_sync_service():
    service = MagicMock(spec=SyncService)
    service.is_peer_trusted.return_value = False
    return service


def test_broadcast_text_calls_service_push(qapp, fake_sync_service):
    list_widget = QListWidget()
    controller = SyncController(
        service=fake_sync_service,
        devices_list=list_widget,
        settings={"node_id": "test_node"},
    )

    controller.broadcast_text("Syncing snippet")
    fake_sync_service.push_text.assert_called_once_with("Syncing snippet")


def test_device_discovered_adds_to_list(qapp, fake_sync_service):
    list_widget = QListWidget()
    controller = SyncController(
        service=fake_sync_service,
        devices_list=list_widget,
        settings={"node_id": "test_node"},
    )

    discovered = []
    controller.peer_discovered.connect(discovered.append)

    dev_data = {"device_name": "Ghost-Laptop", "ip": "192.168.1.50", "port": 9090}
    controller.add_or_update_device("node-123", dev_data)

    assert list_widget.count() == 1
    item = list_widget.item(0)
    assert "Ghost-Laptop" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == "node-123"
    assert len(discovered) == 1
    assert discovered[0]["device_name"] == "Ghost-Laptop"


def test_device_discovered_shows_trusted_icon(qapp, fake_sync_service):
    fake_sync_service.is_peer_trusted.return_value = True
    list_widget = QListWidget()
    controller = SyncController(
        service=fake_sync_service,
        devices_list=list_widget,
        settings={"node_id": "test_node"},
    )

    dev_data = {"device_name": "Trusted-PC", "ip": "192.168.1.60", "port": 9090}
    controller.add_or_update_device("node-trusted", dev_data)

    assert list_widget.count() == 1
    assert "🔒 Trusted-PC" in list_widget.item(0).text()


def test_device_removed_removes_from_list(qapp, fake_sync_service):
    list_widget = QListWidget()
    controller = SyncController(
        service=fake_sync_service,
        devices_list=list_widget,
        settings={"node_id": "test_node"},
    )

    controller.add_or_update_device("node-123", {"device_name": "Dev1"})
    assert list_widget.count() == 1

    removed_nodes = []
    controller.peer_removed.connect(removed_nodes.append)

    controller.remove_device("node-123")
    assert list_widget.count() == 0
    assert removed_nodes == ["node-123"]


def test_handle_peer_unpaired(qapp, fake_sync_service):
    list_widget = QListWidget()
    controller = SyncController(
        service=fake_sync_service,
        devices_list=list_widget,
        settings={"node_id": "test_node"},
    )

    controller.add_or_update_device("node-xyz", {"device_name": "Peer-X"})
    # Pretend it was paired
    list_widget.item(0).setText("🔒 Peer-X")

    unpaired = []
    controller.peer_unpaired.connect(unpaired.append)

    controller.handle_peer_unpaired("node-xyz")
    assert "📱 Peer-X" in list_widget.item(0).text()
    assert unpaired == ["node-xyz"]
