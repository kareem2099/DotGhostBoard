"""
tests/test_update_controller.py
───────────────────────────────
Unit tests for UpdateController lifecycle and signals.
"""

from unittest.mock import MagicMock, patch
import pytest

from ui.controllers.update_controller import UpdateController, UpdateCheckerThread


def test_update_controller_init(qapp):
    controller = UpdateController()
    assert controller.update_thread is None
    assert controller.pending_update_info is None
    assert controller.pending_asset_url is None


def test_on_update_found_emits_signal(qapp):
    controller = UpdateController()
    found = []
    controller.update_found.connect(lambda info, url: found.append((info, url)))

    fake_info = {"tag_name": "v2.1.0"}
    controller._on_update_found(fake_info, "http://example.com/asset.deb")

    assert controller.pending_update_info == fake_info
    assert controller.pending_asset_url == "http://example.com/asset.deb"
    assert len(found) == 1
    assert found[0] == (fake_info, "http://example.com/asset.deb")


def test_check_for_updates_spawns_thread(qapp):
    controller = UpdateController()
    with patch.object(UpdateCheckerThread, "start") as mock_start:
        controller.check_for_updates()
        assert controller.update_thread is not None
        mock_start.assert_called_once()
        # Second call does not spawn a second thread if running
        with patch.object(controller.update_thread, "isRunning", return_value=True):
            controller.check_for_updates()
            mock_start.assert_called_once()
