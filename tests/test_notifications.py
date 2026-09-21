"""
tests/test_notifications.py
────────────────────────────
Unit tests for core.notifications and desktop notification dispatching.
Covers:
- notify-send command formatting and argument passing.
- Interactive action callback dispatch.
- Fallback to dbus when notify-send is absent.
- Graceful error handling (no unhandled exceptions).
- Integration with DashboardTrayManager.show_message.
- Default icon resolution for categories.
"""

from unittest.mock import MagicMock, patch

from core.notifications import (
    get_default_icon_path,
    send_desktop_notification,
)
from ui.components.tray_manager import DashboardTrayManager


def test_get_default_icon_path():
    """Verify icon resolution returns valid existing path or freedesktop stock name."""
    icon_general = get_default_icon_path("general")
    assert isinstance(icon_general, str) and len(icon_general) > 0

    with patch("os.path.exists", return_value=False):
        assert get_default_icon_path("secret") == "dialog-password"
        assert get_default_icon_path("warning") == "dialog-warning"
        assert get_default_icon_path("error") == "dialog-error"
        assert get_default_icon_path("other") == "dialog-information"


def test_send_desktop_notification_notify_send_success(monkeypatch):
    """Verify send_desktop_notification constructs expected notify-send command."""
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/notify-send" if cmd == "notify-send" else None)

    spawned_cmds = []

    def fake_popen(cmd, *args, **kwargs):
        spawned_cmds.append(cmd)
        mock_proc = MagicMock()
        return mock_proc

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    res = send_desktop_notification(
        title="Test Title",
        message="Test Body",
        app_name="DotGhostBoard",
        icon="dialog-password",
        timeout_ms=3000,
        urgency="critical",
    )

    assert res is True
    assert len(spawned_cmds) == 1
    cmd = spawned_cmds[0]
    assert cmd[0] == "/usr/bin/notify-send"
    assert "-a" in cmd and cmd[cmd.index("-a") + 1] == "DotGhostBoard"
    assert "-i" in cmd and cmd[cmd.index("-i") + 1] == "dialog-password"
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "3000"
    assert "-u" in cmd and cmd[cmd.index("-u") + 1] == "critical"
    assert cmd[-2] == "Test Title"
    assert cmd[-1] == "Test Body"


def test_send_desktop_notification_with_action_callback(monkeypatch, qapp):
    """Verify that clicking action triggers action_callback safely."""
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/notify-send" if cmd == "notify-send" else None)

    callback_called = []

    def on_click():
        callback_called.append(True)

    class FakeProc:
        def communicate(self, timeout=None):
            return ("default\n", "")

    def fake_popen(cmd, *args, **kwargs):
        assert "-A" in cmd
        assert "default=Open App" in cmd
        return FakeProc()

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    res = send_desktop_notification(
        title="Secret Intercepted",
        message="Click to open",
        action_label="Open App",
        action_callback=on_click,
    )
    assert res is True

    # Process any Qt events if callback was scheduled via QTimer
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()

    # The background thread runs communicate and invokes callback
    import time
    for _ in range(20):
        QApplication.processEvents()
        if callback_called:
            break
        time.sleep(0.05)

    assert len(callback_called) == 1


def test_send_desktop_notification_dbus_fallback(monkeypatch):
    """Verify fallback to dbus-python when notify-send is absent."""
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    mock_dbus = MagicMock()
    mock_session_bus = MagicMock()
    mock_dbus.SessionBus.return_value = mock_session_bus
    mock_notify_obj = MagicMock()
    mock_session_bus.get_object.return_value = mock_notify_obj
    mock_iface = MagicMock()
    mock_dbus.Interface.return_value = mock_iface

    monkeypatch.setitem(__import__("sys").modules, "dbus", mock_dbus)

    res = send_desktop_notification(
        title="Dbus Title",
        message="Dbus Message",
        timeout_ms=4000,
    )

    assert res is True
    assert mock_iface.Notify.called


def test_send_desktop_notification_all_fail_graceful(monkeypatch):
    """Verify that if both notify-send and dbus fail, function returns False without exception."""
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    monkeypatch.setitem(__import__("sys").modules, "dbus", None)

    res = send_desktop_notification(title="Fail", message="Fail")
    assert res is False


def test_tray_manager_show_message_integration(qapp, monkeypatch):
    """Verify DashboardTrayManager.show_message invokes send_desktop_notification."""
    tray_mgr = DashboardTrayManager()

    dispatched = []

    def fake_send(title, message, **kwargs):
        dispatched.append((title, message, kwargs))
        return True

    monkeypatch.setattr("core.notifications.send_desktop_notification", fake_send)

    tray_mgr.show_message("Secret Title", "Secret Body", timeout=4500)

    assert len(dispatched) == 1
    assert dispatched[0][0] == "Secret Title"
    assert dispatched[0][1] == "Secret Body"
    assert dispatched[0][2]["timeout_ms"] == 4500
    assert callable(dispatched[0][2]["action_callback"])


def test_tray_manager_show_message_fallback_to_tray(qapp, monkeypatch):
    """Verify that if send_desktop_notification returns False, tray.showMessage is called."""
    tray_mgr = DashboardTrayManager()
    tray_mgr.tray = MagicMock()
    tray_mgr.tray.isVisible.return_value = True

    # Simulate native notification failure
    monkeypatch.setattr("core.notifications.send_desktop_notification", lambda *a, **k: False)

    tray_mgr.show_message("Fallback Title", "Fallback Body", timeout=2500)

    assert tray_mgr.tray.showMessage.called
    args = tray_mgr.tray.showMessage.call_args[0]
    assert args[0] == "Fallback Title"
    assert args[1] == "Fallback Body"
    assert args[3] == 2500
