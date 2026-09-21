"""
ui/controllers/coordination.py
──────────────────────────────
Wires cross-controller signals and UI synchronization for the Dashboard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.dashboard import Dashboard


def wire_dashboard_controllers(dash: Dashboard) -> None:
    """Wire inter-controller and UI signals across controllers and toolbar."""
    bt = dash.bulk_toolbar
    hc = dash.history_controller
    sc = dash.security_controller
    cc = dash.collection_controller

    bt.pin_all_requested.connect(hc.bulk_pin)
    bt.delete_all_requested.connect(lambda: hc.bulk_delete(dash))
    bt.export_requested.connect(lambda: hc.bulk_export(dash))
    bt.add_tag_requested.connect(lambda: hc.bulk_add_tag(dash))
    bt.cancel_requested.connect(hc.clear_selection)
    bt.hint_dismissed.connect(dash._dismiss_hint)
    hc.selection_changed.connect(bt.update_selection_count)
    hc.selection_changed.connect(dash._on_selection_count_changed)

    cc.collection_selected.connect(hc.filter_by_collection)
    cc.collection_changed.connect(hc.reload)
    cc.item_moved_to_collection.connect(dash._on_item_moved_to_collection)

    hc.secret_copy_requested.connect(sc.handle_secret_copy)
    sc.copy_payload_ready.connect(hc.record_copy_result)
    hc.encrypt_requested.connect(lambda iid: sc.encrypt_item(iid, dash))
    hc.decrypt_requested.connect(lambda iid: sc.decrypt_item(iid, confirm=True, parent_widget=dash))
    sc.item_security_changed.connect(hc.refresh_item)
    hc.reveal_requested.connect(dash._on_reveal_requested)
    hc.pin_suggested.connect(dash._on_pin_suggested)
    hc.item_copied_ready.connect(dash._on_item_copied_ready)

    dash.sync_controller.api_text_received.connect(dash._on_sync_item_received)
    dash.sync_controller.sync_received_signal.connect(dash._on_sync_item_received)

    hc.status_message.connect(dash.statusBar().showMessage)
    cc.status_message.connect(dash.statusBar().showMessage)
    dash.sync_controller.status_message.connect(dash.statusBar().showMessage)
