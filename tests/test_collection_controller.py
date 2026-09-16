"""
tests/test_collection_controller.py
───────────────────────────────────
Tests for CollectionController behavioral coordinator and signals.
"""

from unittest.mock import MagicMock, patch
import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication, QListWidget

from core.services.collection_service import CollectionService
from ui.controllers.collection_controller import CollectionController


@pytest.fixture
def fake_service():
    service = MagicMock(spec=CollectionService)
    service.get_collections.return_value = [
        {"id": 1, "name": "Work", "item_count": 5},
        {"id": 2, "name": "Personal", "item_count": 3},
    ]
    service.get_collection.side_effect = lambda cid: {
        1: {"id": 1, "name": "Work", "item_count": 5},
        2: {"id": 2, "name": "Personal", "item_count": 3},
    }.get(cid)
    return service


def test_collection_controller_refresh_populates_list(qapp, fake_service):
    list_widget = QListWidget()
    controller = CollectionController(service=fake_service, list_widget=list_widget)

    controller.refresh()

    assert list_widget.count() == 3
    # First item: All Items
    assert list_widget.item(0).text() == "❖ All Items"
    assert list_widget.item(0).data(Qt.ItemDataRole.UserRole) is None

    # Next items
    assert "Work" in list_widget.item(1).text()
    assert list_widget.item(1).data(Qt.ItemDataRole.UserRole) == 1
    assert "Personal" in list_widget.item(2).text()
    assert list_widget.item(2).data(Qt.ItemDataRole.UserRole) == 2


def test_collection_selection_emits_id(qapp, fake_service):
    list_widget = QListWidget()
    controller = CollectionController(service=fake_service, list_widget=list_widget)
    controller.refresh()

    emitted_ids = []
    controller.collection_selected.connect(emitted_ids.append)

    # Select Work (item index 1)
    list_widget.setCurrentItem(list_widget.item(1))
    assert controller.active_collection_id == 1
    assert emitted_ids[-1] == 1

    # Select All Items (item index 0)
    list_widget.setCurrentItem(list_widget.item(0))
    assert controller.active_collection_id is None
    assert emitted_ids[-1] is None


def test_create_collection_updates_and_emits(qapp, fake_service):
    list_widget = QListWidget()
    controller = CollectionController(service=fake_service, list_widget=list_widget)
    controller.refresh()

    changed = False
    def on_change():
        nonlocal changed
        changed = True
    controller.collection_changed.connect(on_change)

    with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Projects", True)):
        controller.prompt_create_collection()

    fake_service.create_collection.assert_called_once_with("Projects")
    assert changed is True


def test_collection_delete_resets_active_filter(qapp, fake_service):
    list_widget = QListWidget()
    controller = CollectionController(service=fake_service, list_widget=list_widget)
    controller.refresh()

    # Set active collection to 1
    list_widget.setCurrentItem(list_widget.item(1))
    assert controller.active_collection_id == 1

    selected_ids = []
    controller.collection_selected.connect(selected_ids.append)

    # Simulate deleting the active collection with user confirmation
    from PyQt6.QtWidgets import QMessageBox
    with patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        controller.prompt_delete_collection(1)

    fake_service.delete_collection.assert_called_once_with(1)
    assert controller.active_collection_id is None
    assert selected_ids[-1] is None


def test_sidebar_drop_moves_item(qapp, fake_service):
    list_widget = QListWidget()
    controller = CollectionController(service=fake_service, list_widget=list_widget)
    controller.refresh()

    moved_events = []
    controller.item_moved_to_collection.connect(lambda i, c: moved_events.append((i, c)))

    # Mock drop event onto item 1 (Work)
    mime = QMimeData()
    mime.setData("application/x-dotghost-card-id", b"42")

    # Mock itemAt to return item 1
    list_widget.itemAt = MagicMock(return_value=list_widget.item(1))

    event = MagicMock(spec=QDropEvent)
    event.mimeData.return_value = mime
    event.position.return_value = QPointF(10, 10)

    controller._sidebar_drop_event(event)

    fake_service.move_item_to_collection.assert_called_once_with(42, 1)
    assert (42, 1) in moved_events
    event.acceptProposedAction.assert_called_once()
