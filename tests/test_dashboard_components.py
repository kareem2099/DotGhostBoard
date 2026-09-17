"""
tests/test_dashboard_components.py
──────────────────────────────────
Unit tests for isolated Dashboard UI components:
  • SidebarWidget
  • TopBarWidget
  • CardsView
  • BulkToolbar
  • DashboardTrayManager

v2.0.0 Cerberus — Phase 6 Dashboard Decomposition.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget
import pytest

from core.constants import DEVICES_LIST_HEIGHT, SIDEBAR_WIDTH, TOP_BAR_HEIGHT
from ui.components import (
    BulkToolbar,
    CardsView,
    DashboardTrayManager,
    SidebarWidget,
    TopBarWidget,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. SidebarWidget Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_sidebar_dimensions(qapp):
    sidebar = SidebarWidget()
    assert sidebar.width() == SIDEBAR_WIDTH
    assert sidebar.devices_list.height() == DEVICES_LIST_HEIGHT


def test_sidebar_child_widgets(qapp):
    sidebar = SidebarWidget()
    assert sidebar.collections_list.objectName() == "CollectionsList"
    assert sidebar.devices_list.objectName() == "DevicesList"
    assert sidebar.add_coll_btn.objectName() == "AddCollBtn"


def test_sidebar_add_collection_signal(qapp):
    sidebar = SidebarWidget()
    emitted = []
    sidebar.create_collection_requested.connect(lambda: emitted.append(True))

    sidebar.add_coll_btn.click()
    assert len(emitted) == 1


def test_sidebar_collapse(qapp):
    sidebar = SidebarWidget()
    sidebar.show()
    assert sidebar.isVisible()

    sidebar.set_collapsed(True)
    assert not sidebar.isVisible()

    sidebar.set_collapsed(False)
    assert sidebar.isVisible()


# ══════════════════════════════════════════════════════════════════════════════
# 2. TopBarWidget Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_topbar_fixed_height(qapp):
    topbar = TopBarWidget()
    assert topbar.height() == TOP_BAR_HEIGHT


def test_topbar_signals(qapp):
    topbar = TopBarWidget()

    events = []
    topbar.settings_clicked.connect(lambda: events.append("settings"))
    topbar.clear_history_clicked.connect(lambda: events.append("clear"))
    topbar.lock_clicked.connect(lambda: events.append("lock"))
    topbar.update_clicked.connect(lambda: events.append("update"))

    topbar.settings_btn.click()
    topbar.clear_btn.click()
    topbar.lock_btn.click()
    topbar.update_btn.click()

    assert events == ["settings", "clear", "lock", "update"]


def test_topbar_stats_text(qapp):
    topbar = TopBarWidget()
    topbar.set_stats_text("42 clips  •  5 pinned")
    assert topbar.stats_label.text() == "42 clips  •  5 pinned"


def test_topbar_visibility_helpers(qapp):
    topbar = TopBarWidget()
    topbar.show()

    topbar.set_lock_visible(True)
    assert not topbar.lock_btn.isHidden()

    topbar.set_lock_visible(False)
    assert topbar.lock_btn.isHidden()

    topbar.set_update_visible(True)
    assert not topbar.update_btn.isHidden()

    topbar.set_update_visible(False)
    assert topbar.update_btn.isHidden()


def test_topbar_compact_mode(qapp):
    topbar = TopBarWidget()
    topbar.show()

    topbar.set_compact_mode(True)
    assert not topbar.stats_label.isVisible()
    assert topbar.clear_btn.text() == "🗑️"

    topbar.set_compact_mode(False)
    assert topbar.stats_label.isVisible()
    assert topbar.clear_btn.text() == "Clear History"


# ══════════════════════════════════════════════════════════════════════════════
# 3. CardsView Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_cards_view_structure(qapp):
    view = CardsView()
    assert view.widgetResizable()
    assert view.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert view.cards_container is not None
    assert view.cards_layout is not None


def test_cards_view_add_and_remove_card(qapp):
    view = CardsView()
    card1 = QLabel("Card 1")
    card2 = QLabel("Card 2")

    view.add_card_widget(card1, at_top=True)
    view.add_card_widget(card2, at_top=False)

    widgets = view.all_card_widgets()
    assert widgets == [card1, card2]

    view.remove_card_widget(card1)
    assert view.all_card_widgets() == [card2]


def test_cards_view_visible_cards(qapp):
    view = CardsView()
    view.show()
    card1 = QLabel("Visible")
    card2 = QLabel("Hidden")

    view.add_card_widget(card1)
    view.add_card_widget(card2)

    card1.show()
    card2.hide()

    visible = view.visible_cards()
    assert card1 in visible
    assert card2 not in visible


def test_cards_view_replace_card_widget(qapp):
    view = CardsView()
    old_card = QLabel("Old")
    new_card = QLabel("New")

    view.add_card_widget(old_card)
    assert view.all_card_widgets() == [old_card]

    view.replace_card_widget(old_card, new_card)
    assert view.all_card_widgets() == [new_card]


def test_cards_view_reorder_widgets(qapp):
    view = CardsView()
    card_a = QLabel("A")
    card_b = QLabel("B")
    card_c = QLabel("C")

    view.add_card_widget(card_a, at_top=False)
    view.add_card_widget(card_b, at_top=False)
    view.add_card_widget(card_c, at_top=False)

    assert view.all_card_widgets() == [card_a, card_b, card_c]

    view.reorder_widgets([card_c, card_a, card_b])
    assert view.all_card_widgets() == [card_c, card_a, card_b]


def test_cards_view_drop_emits_reordered_signal(qapp):
    from unittest.mock import MagicMock
    from PyQt6.QtCore import QByteArray, QPointF, QMimeData

    view = CardsView()
    view.show()

    card1 = QLabel("Card 1")
    card1.item_id = 101
    card1.setGeometry(0, 0, 200, 50)

    card2 = QLabel("Card 2")
    card2.item_id = 102
    card2.setGeometry(0, 55, 200, 50)

    view.add_card_widget(card1, at_top=False)
    view.add_card_widget(card2, at_top=False)

    reordered_events = []
    view.card_reordered.connect(lambda d, t: reordered_events.append((d, t)))

    event = MagicMock()
    mime = QMimeData()
    mime.setData("application/x-dotghost-card-id", QByteArray(b"101"))
    event.mimeData.return_value = mime
    event.position.return_value = QPointF(50, 75)

    view.handle_drop(event)
    assert reordered_events == [(101, 102)]


# ══════════════════════════════════════════════════════════════════════════════
# 4. BulkToolbar Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_bulk_toolbar_initial_state(qapp):
    toolbar = BulkToolbar()
    assert not toolbar.hint_strip.isHidden()
    assert toolbar.bulk_bar.isHidden()


def test_bulk_toolbar_selection_threshold(qapp):
    toolbar = BulkToolbar()

    toolbar.update_selection_count(1)
    assert toolbar.bulk_bar.isHidden()

    toolbar.update_selection_count(2)
    assert not toolbar.bulk_bar.isHidden()
    assert toolbar.bulk_count_lbl.text() == "2 selected"

    toolbar.update_selection_count(7)
    assert not toolbar.bulk_bar.isHidden()
    assert toolbar.bulk_count_lbl.text() == "7 selected"

    toolbar.update_selection_count(0)
    assert toolbar.bulk_bar.isHidden()


def test_bulk_toolbar_hint_dismiss_signal(qapp):
    toolbar = BulkToolbar()
    emitted = []
    toolbar.hint_dismissed.connect(lambda: emitted.append(True))

    dismiss_btn = toolbar.hint_strip.findChild(QPushButton, "HintDismissBtn")
    assert dismiss_btn is not None
    dismiss_btn.click()

    assert len(emitted) == 1
    assert not toolbar.hint_strip.isVisible()


def test_bulk_toolbar_action_signals(qapp):
    toolbar = BulkToolbar()
    toolbar.update_selection_count(2)

    signals_received = []
    toolbar.pin_all_requested.connect(lambda pin: signals_received.append(f"pin_{pin}"))
    toolbar.delete_all_requested.connect(lambda: signals_received.append("delete"))
    toolbar.export_requested.connect(lambda: signals_received.append("export"))
    toolbar.add_tag_requested.connect(lambda: signals_received.append("tag"))
    toolbar.cancel_requested.connect(lambda: signals_received.append("cancel"))

    buttons = toolbar.bulk_bar.findChildren(QPushButton)
    btn_map = {b.text(): b for b in buttons}

    btn_map["📍 Pin All"].click()
    btn_map["📌 Unpin All"].click()
    btn_map["✕ Delete All"].click()
    btn_map["📤 Export"].click()
    btn_map["🏷 Add Tag"].click()
    btn_map["✕ Cancel"].click()

    assert signals_received == [
        "pin_True",
        "pin_False",
        "delete",
        "export",
        "tag",
        "cancel",
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 5. DashboardTrayManager Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_tray_manager_icon_generation(qapp):
    icon = DashboardTrayManager.make_tray_icon()
    assert not icon.isNull()


def test_tray_manager_setup(qapp):
    manager = DashboardTrayManager()
    manager.setup_tray()
    assert manager.tray is not None


def test_tray_manager_tooltips(qapp):
    manager = DashboardTrayManager()
    manager.setup_tray()

    manager.update_menu_and_tooltip(is_locked=True, is_monitoring_paused=False, has_password=True)
    assert "Locked" in manager.tray.toolTip()

    manager.update_menu_and_tooltip(is_locked=False, is_monitoring_paused=True, has_password=True)
    assert "Monitoring paused" in manager.tray.toolTip()

    manager.update_menu_and_tooltip(is_locked=False, is_monitoring_paused=False, has_password=True)
    assert "Monitoring clipboard" in manager.tray.toolTip()


def test_tray_manager_context_menu_actions(qapp):
    manager = DashboardTrayManager()
    manager.setup_tray()

    # When locked: unlock action should be present, settings should not
    manager.update_menu_and_tooltip(is_locked=True, is_monitoring_paused=False, has_password=True)
    menu = manager.tray.contextMenu()
    action_texts = [a.text() for a in menu.actions() if a.text()]
    assert any("Unlock" in t for t in action_texts)
    assert not any("Settings" in t for t in action_texts)

    # When unlocked: settings & pause monitoring should be present
    manager.update_menu_and_tooltip(is_locked=False, is_monitoring_paused=False, has_password=True)
    menu = manager.tray.contextMenu()
    action_texts = [a.text() for a in menu.actions() if a.text()]
    assert any("Settings" in t for t in action_texts)
    assert any("Pause" in t for t in action_texts)
    assert any("Lock" in t for t in action_texts)
