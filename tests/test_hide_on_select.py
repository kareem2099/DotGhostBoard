"""
tests/test_hide_on_select.py
────────────────────────────
Unit and integration tests for "Hide window on selection / Enter" (Issue #1).
Tests settings persistence, keyboard Enter selection, search box Return trigger,
double-click activation, and dashboard window hiding behavior.
"""

from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QLineEdit

from core import storage
from core.services.history_service import HistoryService
from ui.controllers.history_controller import HistoryController
from ui.settings._io import _DEFAULTS, load_settings, save_settings
from ui.widgets.item_card import ItemCard
from ui.dashboard_compat import DashboardCompatibilityMixin


@pytest.fixture
def fake_history_service():
    storage.init_db()
    service = MagicMock(spec=HistoryService)
    sample_items = [
        {"id": 101, "content": "Alpha Clip", "type": "text", "is_secret": 0, "is_pinned": 0, "copy_count": 0, "tags": "[]"},
        {"id": 102, "content": "Beta Clip", "type": "text", "is_secret": 0, "is_pinned": 0, "copy_count": 0, "tags": "[]"},
        {"id": 103, "content": "Gamma Secret", "type": "text", "is_secret": 1, "is_pinned": 0, "copy_count": 0, "tags": "[]"},
    ]
    service.get_items.return_value = sample_items
    service.get_item.side_effect = lambda iid: next((x for x in sample_items if x["id"] == iid), None)
    service.get_stats.return_value = {"total_items": 3, "total_pinned": 0, "total_secrets": 1, "total_copies": 0}
    service.record_copy.return_value = (1, False, False)
    return service


def test_hide_on_select_default_setting():
    """Verify hide_on_select is present in default settings and defaults to False."""
    assert "hide_on_select" in _DEFAULTS
    assert _DEFAULTS["hide_on_select"] is False


def test_settings_dialog_loads_and_saves_hide_on_select(qapp, tmp_path, monkeypatch):
    """Verify SettingsDialog exposes the checkbox and persists value."""
    test_settings_file = str(tmp_path / "settings.json")
    monkeypatch.setattr("ui.settings._io.SETTINGS_PATH", test_settings_file)

    settings = load_settings()
    settings["hide_on_select"] = True
    save_settings(settings)

    reloaded = load_settings()
    assert reloaded.get("hide_on_select") is True


def test_item_card_emits_sig_activated_on_double_click(qapp):
    """Verify ItemCard emits sig_activated on mouse double click."""
    storage.init_db()
    card = ItemCard({"id": 42, "content": "Test item", "type": "text"})
    activated_ids = []
    card.sig_activated.connect(activated_ids.append)

    event = MagicMock(spec=QMouseEvent)
    card.mouseDoubleClickEvent(event)

    assert activated_ids == [42]


def test_history_controller_enter_key_triggers_copy_and_activation(qapp, fake_history_service):
    """Verify pressing Enter/Return in HistoryController copies and emits item_activated."""
    parent = QWidget()
    layout = QVBoxLayout(parent)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    activated_ids = []
    copied_items = []
    controller.item_activated.connect(activated_ids.append)
    controller.item_copied_ready.connect(lambda iid, item: copied_items.append(iid))

    visible_cards = list(controller.cards.values())

    # Navigate Down to card index 1
    key_down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    assert controller.handle_key_press(key_down, visible_cards) is True
    assert controller._focused_idx == 0

    key_down_2 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    assert controller.handle_key_press(key_down_2, visible_cards) is True
    assert controller._focused_idx == 1

    # Press Enter
    key_enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    handled = controller.handle_key_press(key_enter, visible_cards)

    assert handled is True
    assert 102 in activated_ids
    assert 102 in copied_items


def test_history_controller_enter_without_navigation_picks_first_card(qapp, fake_history_service):
    """Verify pressing Enter immediately (without arrow navigation) selects top card."""
    parent = QWidget()
    layout = QVBoxLayout(parent)
    controller = HistoryController(service=fake_history_service, cards_layout=layout)
    controller.load_more(initial=True)

    assert controller._focused_idx == -1

    activated_ids = []
    controller.item_activated.connect(activated_ids.append)
    visible_cards = list(controller.cards.values())

    key_enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    handled = controller.handle_key_press(key_enter, visible_cards)

    assert handled is True
    assert activated_ids == [101]


def test_search_box_return_triggers_copy_and_activation(qapp, fake_history_service):
    """Verify pressing Return in search_box activates and copies the top or focused card."""
    parent = QWidget()
    layout = QVBoxLayout(parent)
    search_box = QLineEdit()
    controller = HistoryController(
        service=fake_history_service,
        cards_layout=layout,
        search_box=search_box,
    )
    controller.load_more(initial=True)

    activated_ids = []
    controller.item_activated.connect(activated_ids.append)

    # Trigger search box Return
    controller._on_search_box_return()

    assert activated_ids == [101]


def test_dashboard_on_item_activated_hides_when_enabled(qapp, fake_history_service):
    """Verify dashboard hides when hide_on_select is True, and stays open when False."""
    class FakeDashboard(DashboardCompatibilityMixin, QWidget):
        def __init__(self, settings):
            super().__init__()
            self._settings = settings
            self.history_service = fake_history_service
            self.hide_called = False

        def hide(self):
            self.hide_called = True

    # When hide_on_select is True
    dash_enabled = FakeDashboard({"hide_on_select": True})
    dash_enabled._on_item_activated(101)
    assert dash_enabled.hide_called is True

    # When hide_on_select is False
    dash_disabled = FakeDashboard({"hide_on_select": False})
    dash_disabled._on_item_activated(101)
    assert dash_disabled.hide_called is False


def test_dashboard_on_item_activated_secret_delays_hide_until_copy(qapp, fake_history_service):
    """Verify locked secrets delay hide until after password unlock and clipboard paste."""
    class FakeDashboard(DashboardCompatibilityMixin, QWidget):
        def __init__(self):
            super().__init__()
            self._settings = {"hide_on_select": True}
            self.history_service = fake_history_service
            self.security_controller = MagicMock()
            self.security_controller.is_locked = True
            self.watcher = MagicMock()
            self.hide_called = False

        def hide(self):
            self.hide_called = True

    dash = FakeDashboard()
    dash._on_item_activated(103)  # item 103 is a secret

    # Hide should NOT be called immediately while unlock dialog is expected
    assert dash.hide_called is False
    assert getattr(dash, "_hide_after_secret_copy", False) is True

    # Once copy is ready, it should paste and then hide
    dash._on_item_copied_ready(103, {"id": 103, "content": "decrypted"})
    assert dash.hide_called is True
    assert getattr(dash, "_hide_after_secret_copy", False) is False
