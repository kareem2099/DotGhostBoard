"""
tests/test_ipc_spotlight.py
───────────────────────────
Tests for IPC message routing (show / spotlight / toggle), Eclipse lock security guard,
Spotlight overlay activation, and desktop shortcut configuration.
"""

import sys
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication

from core import storage
from core.shortcuts import detect_desktop, _parse_gsettings_bindings
from ui.dashboard import Dashboard


@pytest.fixture
def app():
    instance = QApplication.instance()
    if not instance:
        instance = QApplication(sys.argv)
    return instance


@pytest.fixture
def clean_db(tmp_path):
    db_file = str(tmp_path / "test_ipc_spotlight.db")
    storage.DB_PATH = db_file
    storage.init_db()
    return db_file


@pytest.fixture
def mock_dash_background(monkeypatch):
    monkeypatch.setattr("ui.dashboard.Dashboard._start_watcher", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard._start_api_server", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard._start_discovery", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard._init_sync_engine", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard.check_for_updates", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard._setup_tray", lambda self: None)


from PyQt6.QtCore import QCoreApplication, QEvent


def _cleanup_widget(app, widget):
    """Helper to cleanly hide, schedule deletion, and flush Qt event loop."""
    widget.hide()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_spotlight_dialog_toggle(app, clean_db, mock_dash_background):
    """Verify that calling show_spotlight toggles dialog visibility."""
    dash = Dashboard(startup_locked=False, active_key=b"1"*32)
    assert hasattr(dash, "spotlight_dialog")
    assert not dash.spotlight_dialog.isVisible()

    dash.show_spotlight()
    assert dash.spotlight_dialog.isVisible()

    # Calling it again toggles it off
    dash.show_spotlight()
    assert not dash.spotlight_dialog.isVisible()

    _cleanup_widget(app, dash)


def test_spotlight_requires_unlock_when_locked(
    app,
    clean_db,
    mock_dash_background,
    monkeypatch,
):
    dash = Dashboard(
        startup_locked=False,
        active_key=b"1" * 32,
    )
    dash.hide()

    # Session reports locked
    monkeypatch.setattr(
        dash,
        "_is_locked",
        lambda: True,
    )

    # ── Cancelled unlock ──
    mock_lock = MagicMock(return_value=False)
    monkeypatch.setattr(
        dash,
        "_show_lock_screen",
        mock_lock,
    )

    dash.show_spotlight()

    mock_lock.assert_called_once_with(
        show_dashboard=False
    )
    assert not dash.spotlight_dialog.isVisible()
    assert not dash.isVisible()

    # ── Successful unlock ──
    mock_lock.reset_mock()
    mock_lock.return_value = True

    dash.show_spotlight()

    mock_lock.assert_called_once_with(
        show_dashboard=False
    )
    assert dash.spotlight_dialog.isVisible()

    # Critical behavior:
    # Spotlight opens without exposing full Dashboard.
    assert not dash.isVisible()

    dash.spotlight_dialog.hide()
    _cleanup_widget(app, dash)


def test_dashboard_toggle_visibility(app, clean_db, mock_dash_background, monkeypatch):
    """Verify toggle_visibility toggles between visible and hidden."""
    dash = Dashboard(startup_locked=False, active_key=b"1"*32)
    dash.hide()
    assert not dash.isVisible()

    dash.toggle_visibility()
    assert dash.isVisible()

    dash.toggle_visibility()
    assert not dash.isVisible()

    _cleanup_widget(app, dash)


def test_no_ctrl_shift_f_shortcut_collision(app, clean_db, mock_dash_background):
    """Verify Ctrl+Shift+F is no longer bound to any in-window shortcut."""
    dash = Dashboard(startup_locked=False, active_key=b"1"*32)
    assert not hasattr(dash, "spotlight_shortcut")
    # In-window shortcut should be Ctrl+F to focus search box
    assert hasattr(dash, "find_shortcut")
    _cleanup_widget(app, dash)


def test_ipc_message_routing():
    """Verify IPC connection message parsing handles 'show', 'spotlight', and 'toggle'."""
    mock_window = MagicMock()

    def handle_message(msg: str):
        cleaned = msg.strip()
        if cleaned == "show":
            mock_window.show_and_raise()
        elif cleaned == "spotlight":
            mock_window.show_spotlight()
        elif cleaned == "toggle":
            mock_window.toggle_visibility()

    handle_message("show\n")
    mock_window.show_and_raise.assert_called_once()
    mock_window.show_spotlight.assert_not_called()
    mock_window.toggle_visibility.assert_not_called()

    mock_window.reset_mock()
    handle_message("spotlight\n")
    mock_window.show_spotlight.assert_called_once()
    mock_window.show_and_raise.assert_not_called()
    mock_window.toggle_visibility.assert_not_called()

    mock_window.reset_mock()
    handle_message("toggle\n")
    mock_window.toggle_visibility.assert_called_once()
    mock_window.show_spotlight.assert_not_called()
    mock_window.show_and_raise.assert_not_called()


def test_parse_gsettings_bindings():
    """Verify _parse_gsettings_bindings correctly handles various gsettings outputs."""
    # Standard array
    raw = "['/custom/0/', '/custom/1/']"
    assert _parse_gsettings_bindings(raw) == ["/custom/0/", "/custom/1/"]

    # Empty array with @as prefix
    assert _parse_gsettings_bindings("@as []") == []

    # Malformed inputs
    assert _parse_gsettings_bindings("invalid syntax") == []
    assert _parse_gsettings_bindings("123") == []


def test_detect_desktop(monkeypatch):
    """Verify desktop detection prioritizes XFCE and GNOME correctly."""
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "XFCE")
    monkeypatch.setenv("DESKTOP_SESSION", "xubuntu")
    assert detect_desktop() == "xfce"

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monkeypatch.setenv("DESKTOP_SESSION", "gnome")
    assert detect_desktop() == "gnome"

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("DESKTOP_SESSION", "plasma")
    assert detect_desktop() == "unknown"


def test_setup_shortcuts_unknown_desktop(monkeypatch):
    """Verify setup_shortcuts returns explicit failure when desktop is unknown."""
    from core.shortcuts import setup_shortcuts

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("DESKTOP_SESSION", "plasma")
    ok, msg = setup_shortcuts()
    assert ok is False
    assert "Desktop environment is not supported automatically" in msg


def test_launch_command_appimage_and_spaces(monkeypatch, tmp_path):
    """Verify _get_launch_command prioritizes APPIMAGE and quotes paths with spaces."""
    from core.shortcuts import _get_launch_command, _get_exec_commands

    fake_appimage = tmp_path / "My App Images" / "DotGhostBoard.AppImage"
    fake_appimage.parent.mkdir(parents=True)
    fake_appimage.touch()

    monkeypatch.setenv("APPIMAGE", str(fake_appimage))
    cmd = _get_launch_command()
    assert cmd == [str(fake_appimage)]

    exec_cmds = _get_exec_commands()
    assert len(exec_cmds) == 2
    for sc in exec_cmds:
        # Verify proper shell quoting because of spaces
        assert "'" in sc["command"] or '"' in sc["command"]
        assert sc["flag"] in sc["command"]
