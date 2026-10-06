"""
tests/test_dashboard_coordination.py
───────────────────────────────────
End-to-end and contract tests for Dashboard window coordination across
HistoryController, CollectionController, SecurityController, and SyncController.
"""

from unittest.mock import MagicMock
import pytest

from ui.dashboard import Dashboard


def test_saved_notification_settings_apply_immediately(mock_dashboard, monkeypatch):
    dash = mock_dashboard
    manager = MagicMock()
    dash.tray_manager = manager
    settings = dict(dash._settings, notifications_enabled=False)
    dialog = MagicMock()
    dialog.exec.return_value = True
    monkeypatch.setattr("ui.dashboard.SettingsDialog", lambda parent: dialog)
    monkeypatch.setattr("ui.dashboard.prepare_dialog_for_current_workspace", lambda dlg: None)
    monkeypatch.setattr("ui.dashboard.load_settings", lambda: settings)
    monkeypatch.setattr(dash, "_is_locked", lambda: False)
    dash._open_settings()
    manager.configure_notifications.assert_called_once_with(settings)


@pytest.mark.parametrize("locked", [False, True])
def test_update_notification_opens_details_after_unlock(mock_dashboard, monkeypatch, locked):
    dash = mock_dashboard
    dash.hide()
    dash.tray_manager = MagicMock()
    monkeypatch.setattr(dash, "show_and_raise", MagicMock())
    monkeypatch.setattr(dash, "_show_updater_dialog", MagicMock())
    monkeypatch.setattr(dash, "_is_locked", lambda: locked)
    dash._on_update_found({"tag_name": "v9.0"}, "https://example.test/update")
    request = dash.tray_manager.show_message.call_args.kwargs
    assert request["category"] == "updates"
    request["action_callback"]()
    dash.show_and_raise.assert_called_once()
    assert dash._show_updater_dialog.called is not locked



def test_controllers_attached(mock_dashboard):
    assert hasattr(mock_dashboard, "collection_controller")
    assert hasattr(mock_dashboard, "security_controller")
    assert hasattr(mock_dashboard, "sync_controller")
    assert hasattr(mock_dashboard, "history_controller")


def test_collection_selection_filters_history(mock_dashboard):
    # Emitting collection_selected must update HistoryController's active_collection_id
    mock_dashboard.collection_controller.collection_selected.emit(42)
    assert mock_dashboard.history_controller.active_collection_id == 42


def test_collection_changed_reloads_history(mock_dashboard):
    reloaded = False
    mock_dashboard.history_controller.stats_updated.connect(lambda stats: setattr(mock_dashboard, "_reloaded_flag", True))

    mock_dashboard.collection_controller.collection_changed.emit()
    assert getattr(mock_dashboard, "_reloaded_flag", False) is True


def test_secret_copy_never_bypasses_security_controller(mock_dashboard, monkeypatch):
    # Prevent real modal dialog execution during test
    monkeypatch.setattr(mock_dashboard.security_controller, "prompt_unlock", lambda: False)

    # Lock session so secret copy fails without prompt
    mock_dashboard.security_controller.lock()

    failures = []
    mock_dashboard.security_controller.secret_copy_failed.connect(lambda iid, r: failures.append((iid, r)))

    item = {"id": 99, "content": "secret_data", "is_secret": 1}
    # Simulate user copy of secret item
    mock_dashboard.history_controller.secret_copy_requested.emit(99, item)

    assert len(failures) == 1
    assert failures[0][0] == 99


def test_new_text_capture_updates_history_and_syncs_once(mock_dashboard):
    mock_dashboard.sync_service.push_text = MagicMock()

    mock_dashboard.sync_controller.broadcast_text("captured snippet")
    mock_dashboard.sync_service.push_text.assert_called_once_with("captured snippet")


def test_manual_card_copy_does_not_sync_to_peer(mock_dashboard):
    mock_dashboard.sync_service.push_text = MagicMock()

    # Manual copy of item
    mock_dashboard.history_controller.record_copy_result(1, {"id": 1, "content": "manual copy"})

    # Push to peer must NOT be called on manual copy
    mock_dashboard.sync_service.push_text.assert_not_called()


def test_lock_state_signal_stops_monitoring(mock_dashboard):
    mock_watcher = MagicMock()
    mock_dashboard.watcher = mock_watcher

    # Session locks via SecurityController
    mock_dashboard.security_controller.lock()

    mock_watcher.stop.assert_called_once()
    assert mock_dashboard._auto_lock_timer.isActive() is False
