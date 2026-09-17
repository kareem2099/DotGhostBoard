"""
tests/test_history_controller.py
────────────────────────────────
Tests for HistoryController orchestration, card lifecycle, and signals.
"""

from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.services.history_service import HistoryService
from ui.controllers.history_controller import HistoryController


@pytest.fixture
def fake_history_service():
    service = MagicMock(spec=HistoryService)
    sample_items = [
        {"id": 1, "content": "Plain Item 1", "type": "text", "is_secret": 0, "is_pinned": 0, "copy_count": 0, "tags": "[]"},
        {"id": 2, "content": "Plain Item 2", "type": "text", "is_secret": 0, "is_pinned": 0, "copy_count": 0, "tags": "[]"},
        {"id": 3, "content": "Secret Item 3", "type": "text", "is_secret": 1, "is_pinned": 0, "copy_count": 0, "tags": "[]"},
    ]
    service.get_items.return_value = sample_items
    service.get_item.side_effect = lambda iid: next((x for x in sample_items if x["id"] == iid), None)
    service.get_stats.return_value = {"total_items": 3, "total_pinned": 0, "total_secrets": 1, "total_copies": 0}
    service.record_copy.return_value = (1, False, False)
    service.toggle_pin.return_value = True
    return service


def test_load_more_populates_cards_layout(qapp, fake_history_service):
    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)

    controller.load_more(initial=True)

    fake_history_service.get_items.assert_called_once()
    assert len(controller.cards) == 3
    assert 1 in controller.cards
    assert 2 in controller.cards
    assert 3 in controller.cards
    assert layout.count() == 3


def test_copy_non_secret_records_and_emits(qapp, fake_history_service):
    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    ready_copies = []
    controller.item_copied_ready.connect(lambda iid, itm: ready_copies.append((iid, itm)))

    controller.on_copy(1)

    fake_history_service.record_copy.assert_called_once_with(1)
    assert len(ready_copies) == 1
    assert ready_copies[0][0] == 1


def test_copy_secret_emits_secret_copy_requested(qapp, fake_history_service):
    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    secret_requests = []
    ready_copies = []
    controller.secret_copy_requested.connect(lambda iid, itm: secret_requests.append((iid, itm)))
    controller.item_copied_ready.connect(lambda iid, itm: ready_copies.append((iid, itm)))

    # Item 3 is secret
    controller.on_copy(3)

    assert len(secret_requests) == 1
    assert secret_requests[0][0] == 3
    # Should NOT have recorded copy yet until security controller confirms
    fake_history_service.record_copy.assert_not_called()
    assert len(ready_copies) == 0


def test_record_copy_result_handles_pin_suggestion(qapp, fake_history_service):
    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    # Mock service returning should_suggest=True
    fake_history_service.record_copy.return_value = (5, True, False)

    suggestions = []
    controller.pin_suggested.connect(lambda iid, prev: suggestions.append((iid, prev)))

    item = {"id": 1, "content": "Suggested item text"}
    controller.record_copy_result(1, item)

    assert len(suggestions) == 1
    assert suggestions[0][0] == 1
    assert "Suggested item text" in suggestions[0][1]


def test_filter_by_collection_reloads_with_collection_id(qapp, fake_history_service):
    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)

    controller.filter_by_collection(42)

    assert controller.active_collection_id == 42
    fake_history_service.get_items.assert_called_with(
        limit=40,
        offset=0,
        query=None,
        tag=None,
        collection_id=42,
    )


def test_pin_toggle_updates_card_and_stats(qapp, fake_history_service):
    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    controller.on_pin(1)

    fake_history_service.toggle_pin.assert_called_once_with(1)
    card = controller.cards[1]
    assert card.is_pinned is True


def test_delete_removes_card_and_updates_stats(qapp, fake_history_service):
    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    assert 1 in controller.cards

    controller.on_delete(1)

    fake_history_service.delete_item.assert_called_once_with(1)
    assert 1 not in controller.cards
    assert layout.count() == 2


def test_bulk_pin_toggles_selected_items(qapp, fake_history_service):
    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    controller._selected_ids = {1, 2}
    affected = controller.bulk_pin(True)

    assert affected == 2
    assert fake_history_service.toggle_pin.call_count == 2


def test_bulk_delete_with_confirmation(qapp, fake_history_service, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    fake_history_service.delete_item.return_value = True

    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    controller._selected_ids = {1, 2}
    deleted = controller.bulk_delete(parent_widget)

    assert deleted == 2
    assert len(controller.selected_ids) == 0
    assert 1 not in controller.cards
    assert 2 not in controller.cards


def test_bulk_add_tag(qapp, fake_history_service, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("urgent", True))
    fake_history_service.add_tag.return_value = ["#urgent"]

    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    controller._selected_ids = {1, 2}
    tag = controller.bulk_add_tag(parent_widget)

    assert tag == "#urgent"
    assert fake_history_service.add_tag.call_count == 2


def test_clear_selection_emits_signal(qapp, fake_history_service):
    parent_widget = QWidget()
    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    controller._selected_ids = {1, 2}
    emitted = []
    controller.selection_changed.connect(lambda c: emitted.append(c))

    controller.clear_selection()
    assert len(controller.selected_ids) == 0
    assert emitted == [0]


def test_normal_card_click_focuses_without_selection(qapp, fake_history_service):
    parent_widget = QWidget()
    parent_widget.show()

    layout = QVBoxLayout(parent_widget)
    controller = HistoryController(
        service=fake_history_service,
        cards_layout=layout,
    )

    controller.load_more(initial=True)

    # Pre-select item 2 to verify deselecting on normal click emits selection_changed(0) exactly once
    controller._selected_ids = {2}
    emitted = []
    controller.selection_changed.connect(lambda c: emitted.append(c))

    controller.on_card_clicked(1, Qt.KeyboardModifier.NoModifier)

    assert controller.selected_ids == set()
    assert controller._focused_idx == 0
    assert controller._last_clicked_id == 1
    assert emitted == [0]

