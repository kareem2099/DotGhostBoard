"""
tests/test_window_manager.py
────────────────────────────
Unit tests for core/window_manager.py and ui/window_utils.py.
Validates EWMH C-structure ABI layout, client message payloads,
cross-workspace state checks, property order, and UI coordination.
Includes real live EWMH integration tests against X11 window managers.
"""

import ctypes
from unittest.mock import MagicMock, Mock, patch

from core.window_manager import (
    CLIENT_MESSAGE_TYPE,
    XClientMessageEvent,
    XEvent,
    c_long,
    create_client_message_payload,
    get_current_desktop,
    get_window_desktop,
    send_active_window_message,
    send_window_desktop_message,
    set_window_desktop_property,
)
from ui.window_utils import (
    bring_to_current_workspace,
    is_on_current_workspace,
    prepare_dialog_for_current_workspace,
)


# ── ABI Structure Layout Tests ───────────────────────────────────────────


def test_x11_abi_structure_sizes_and_offsets():
    """Verify that ctypes structures precisely match X11 ABI on any arch."""
    expected_event_size = 24 * ctypes.sizeof(c_long)
    expected_data_offset = 7 * ctypes.sizeof(c_long)
    assert ctypes.sizeof(XEvent) == expected_event_size
    assert XClientMessageEvent.data.offset == expected_data_offset


# ── Pure Function Unit Tests ─────────────────────────────────────────────


def test_create_client_message_payload_basic():
    """Verify that pure client message payload conforms to EWMH format 32."""
    payload = create_client_message_payload(
        window_xid=0x12345,
        message_atom=9999,
        data_values=[2, 1],
    )

    assert payload["type"] == CLIENT_MESSAGE_TYPE
    assert payload["window"] == 0x12345
    assert payload["message_type"] == 9999
    assert payload["format"] == 32
    assert len(payload["data"]) == 5
    assert payload["data"] == [2, 1, 0, 0, 0]


def test_create_client_message_payload_truncation():
    """Verify that data values longer than 5 are cleanly bounded."""
    payload = create_client_message_payload(
        window_xid=100,
        message_atom=200,
        data_values=[1, 2, 3, 4, 5, 6, 7],
    )
    assert payload["data"] == [1, 2, 3, 4, 5]


# ── Headless & Missing Display Fallback Tests ────────────────────────────


def test_get_current_desktop_no_display(monkeypatch):
    """Verify get_current_desktop returns None gracefully if X11 absent."""
    mock_x11 = MagicMock()
    mock_x11.XOpenDisplay.return_value = None
    monkeypatch.setattr("core.window_manager._get_x11", lambda: mock_x11)

    result = get_current_desktop()
    assert result is None


def test_get_window_desktop_no_display(monkeypatch):
    """Verify get_window_desktop returns None gracefully if X11 absent."""
    mock_x11 = MagicMock()
    mock_x11.XOpenDisplay.return_value = None
    monkeypatch.setattr("core.window_manager._get_x11", lambda: mock_x11)

    assert get_window_desktop(0x123) is None
    assert get_window_desktop(0) is None


def test_set_window_desktop_property_no_display(monkeypatch):
    """Verify property setting returns False safely when display is absent."""
    mock_x11 = MagicMock()
    mock_x11.XOpenDisplay.return_value = None
    monkeypatch.setattr("core.window_manager._get_x11", lambda: mock_x11)

    assert set_window_desktop_property(1234, 1) is False
    assert set_window_desktop_property(0, 1) is False


def test_send_window_desktop_message_no_display(monkeypatch):
    """Verify desktop message returns False safely when display is absent."""
    mock_x11 = MagicMock()
    mock_x11.XOpenDisplay.return_value = None
    monkeypatch.setattr("core.window_manager._get_x11", lambda: mock_x11)

    assert send_window_desktop_message(1234, 1) is False
    assert send_window_desktop_message(0, 1) is False


def test_send_active_window_message_no_display(monkeypatch):
    """Verify active window returns False safely when display is absent."""
    mock_x11 = MagicMock()
    mock_x11.XOpenDisplay.return_value = None
    monkeypatch.setattr("core.window_manager._get_x11", lambda: mock_x11)

    assert send_active_window_message(1234) is False
    assert send_active_window_message(0) is False


# ── UI Workspace Detection Tests ──────────────────────────────────────────


def test_is_on_current_workspace_non_xcb():
    """Verify non-xcb platforms always evaluate to True."""
    mock_w = MagicMock()
    with patch(
        "PyQt6.QtGui.QGuiApplication.platformName",
        return_value="wayland",
    ):
        assert is_on_current_workspace(mock_w) is True
    assert is_on_current_workspace(None) is True


def test_is_on_current_workspace_scenarios():
    """Verify workspace detection for same, different, and sticky windows."""
    mock_w = MagicMock()
    mock_w.winId.return_value = 0x9999

    with patch("PyQt6.QtGui.QGuiApplication.platformName", return_value="xcb"):
        # 1. Matching desktop
        with patch(
            "ui.window_utils.get_current_desktop", return_value=2
        ), patch("ui.window_utils.get_window_desktop", return_value=2):
            assert is_on_current_workspace(mock_w) is True

        # 2. Different desktop (e.g. window on 0, user on 1)
        with patch(
            "ui.window_utils.get_current_desktop", return_value=1
        ), patch("ui.window_utils.get_window_desktop", return_value=0):
            assert is_on_current_workspace(mock_w) is False

        # 3. Sticky desktop (0xFFFFFFFF)
        with patch(
            "ui.window_utils.get_current_desktop", return_value=3
        ), patch(
            "ui.window_utils.get_window_desktop", return_value=0xFFFFFFFF
        ):
            assert is_on_current_workspace(mock_w) is True

        # 4. Unknown/None fallback
        with patch(
            "ui.window_utils.get_current_desktop", return_value=None
        ), patch("ui.window_utils.get_window_desktop", return_value=1):
            assert is_on_current_workspace(mock_w) is True


# ── Kill Switch Tests ────────────────────────────────────────────────────


def test_ewmh_kill_switch(monkeypatch):
    """Verify DOTGHOST_NO_EWMH=1 bypasses all EWMH calls."""
    monkeypatch.setenv("DOTGHOST_NO_EWMH", "1")
    mock_w = MagicMock()
    mock_w.winId.return_value = 0x8888

    with patch("PyQt6.QtGui.QGuiApplication.platformName", return_value="xcb"):
        with patch("ui.window_utils.get_current_desktop") as mock_desk:
            assert is_on_current_workspace(mock_w) is True
            bring_to_current_workspace(mock_w)
            prepare_dialog_for_current_workspace(mock_w)

            mock_desk.assert_not_called()
            mock_w.show.assert_called_once()
            mock_w.raise_.assert_called_once()
            mock_w.activateWindow.assert_called_once()


# ── Dialog Preparation Tests ─────────────────────────────────────────────


def test_prepare_dialog_for_current_workspace():
    """Verify dialog preparation sets property without calling show()."""
    mock_dlg = MagicMock()
    mock_dlg.winId.return_value = 0x4321

    prepare_dialog_for_current_workspace(None)

    with patch("PyQt6.QtGui.QGuiApplication.platformName", return_value="xcb"):
        with patch(
            "ui.window_utils.get_current_desktop", return_value=3
        ):
            with patch(
                "ui.window_utils.set_window_desktop_property"
            ) as mock_set:
                prepare_dialog_for_current_workspace(mock_dlg)
                mock_set.assert_called_once_with(0x4321, 3)
                mock_dlg.show.assert_not_called()


# ── UI Layer Integration & Order-of-Operations Tests ─────────────────────


def test_bring_to_current_workspace_none_widget():
    """Verify bring_to_current_workspace handles None without raising."""
    bring_to_current_workspace(None)


def test_bring_to_current_workspace_non_xcb():
    """Verify non-xcb platform (Wayland/offscreen) relies purely on Qt."""
    mock_widget = MagicMock()

    with patch(
        "PyQt6.QtGui.QGuiApplication.platformName",
        return_value="wayland",
    ):
        with patch("ui.window_utils.get_current_desktop") as mock_desk:
            bring_to_current_workspace(mock_widget)
            mock_desk.assert_not_called()
            mock_widget.show.assert_called_once()
            mock_widget.raise_.assert_called_once()
            mock_widget.activateWindow.assert_called_once()


def test_bring_to_current_workspace_xcb_unmapped_strict_order():
    """Verify xcb unmapped window sets property strictly BEFORE show()."""
    mock_widget = MagicMock()
    mock_widget.winId.return_value = 0x5555
    mock_widget.isVisible.return_value = False

    parent_mock = Mock()
    parent_mock.attach_mock(mock_widget.show, "show")

    mock_set_prop = Mock()
    mock_send_active = Mock()
    parent_mock.attach_mock(mock_set_prop, "set_prop")
    parent_mock.attach_mock(mock_send_active, "send_active")

    with patch("PyQt6.QtGui.QGuiApplication.platformName", return_value="xcb"):
        with patch(
            "ui.window_utils.get_current_desktop", return_value=1
        ):
            with patch(
                "ui.window_utils.set_window_desktop_property",
                mock_set_prop,
            ), patch(
                "ui.window_utils.send_active_window_message",
                mock_send_active,
            ), patch(
                "ui.window_utils.QTimer.singleShot"
            ) as mock_timer:
                bring_to_current_workspace(mock_widget)

                # Verify execution order: set_prop -> show -> send_active
                calls = [c[0] for c in parent_mock.mock_calls]
                assert calls.index("set_prop") < calls.index("show")
                assert calls.index("show") < calls.index("send_active")

                # Verify singleShot scheduled to guard against MapRequest race
                mock_timer.assert_called_once()
                assert mock_timer.call_args[0][0] == 40


def test_bring_to_current_workspace_xcb_mapped():
    """Verify xcb mapped window sends client message instead of property."""
    mock_widget = MagicMock()
    mock_widget.winId.return_value = 0x7777
    mock_widget.isVisible.return_value = True

    with patch("PyQt6.QtGui.QGuiApplication.platformName", return_value="xcb"):
        with patch(
            "ui.window_utils.get_current_desktop", return_value=2
        ):
            with patch(
                "ui.window_utils.send_window_desktop_message"
            ) as m_msg, patch(
                "ui.window_utils.set_window_desktop_property"
            ) as m_prop, patch(
                "ui.window_utils.send_active_window_message"
            ) as m_active:
                bring_to_current_workspace(mock_widget)

                m_msg.assert_called_once_with(0x7777, 2)
                m_prop.assert_not_called()
                mock_widget.show.assert_called_once()
                m_active.assert_called_once_with(0x7777, source=2)


def test_dashboard_toggle_cross_workspace_resurfaces():
    """Verify toggle_visibility calls show_and_raise if on other workspace."""
    from ui.dashboard import Dashboard

    dash = MagicMock(spec=Dashboard)
    dash.isVisible.return_value = True

    with patch(
        "ui.dashboard.is_on_current_workspace", return_value=False
    ):
        # Call actual method on mock instance
        Dashboard.toggle_visibility(dash)

        dash.hide.assert_not_called()
        dash.show_and_raise.assert_called_once()


# ── Live WM Integration Tests (Xvfb + Openbox & Qtile) ───────────────────


def test_real_ewmh_integration_with_openbox():
    """Verify real property setting and client message migration on live WM."""
    import os
    import shutil
    import subprocess
    import time
    import pytest

    if not (shutil.which("Xvfb") and shutil.which("openbox")):
        pytest.skip("Xvfb or openbox not installed on system")

    display_num = f":{os.getpid() % 40 + 50}"
    xvfb = subprocess.Popen(
        ["Xvfb", display_num, "-screen", "0", "1024x768x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.4)

    old_display = os.environ.get("DISPLAY")
    os.environ["DISPLAY"] = display_num

    wm = subprocess.Popen(
        ["openbox"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.6)

    try:
        from core.window_manager import _get_x11
        x11 = _get_x11()
        assert x11 is not None

        disp = x11.XOpenDisplay(None)
        assert disp is not None
        root = x11.XDefaultRootWindow(disp)

        # 1. Root active desktop should be present (typically 0)
        cur = get_current_desktop()
        assert cur is not None

        # 2. Create test window
        win = x11.XCreateSimpleWindow(disp, root, 10, 10, 200, 200, 1, 0, 0)
        x11.XFlush(disp)

        # 3. Test unmapped property setting
        set_ok = set_window_desktop_property(win, 2)
        assert set_ok is True
        assert get_window_desktop(win) == 2

        # 4. Map window and test mapped client message migration
        x11.XMapWindow(disp, win)
        x11.XFlush(disp)
        time.sleep(0.3)

        send_ok = send_window_desktop_message(win, 3)
        assert send_ok is True
        time.sleep(0.3)
        assert get_window_desktop(win) == 3

        # 5. Test active window message
        act_ok = send_active_window_message(win, source=2)
        assert act_ok is True

        x11.XCloseDisplay(disp)
    finally:
        wm.terminate()
        xvfb.terminate()
        wm.wait()
        xvfb.wait()
        if old_display is not None:
            os.environ["DISPLAY"] = old_display
        else:
            os.environ.pop("DISPLAY", None)


def test_real_qtile_and_qt_integration():
    """Verify live E2E behavior with Qtile tiling WM and Qt widgets."""
    import os
    import shutil
    import subprocess
    import sys
    import time
    import pytest

    if not (shutil.which("Xvfb") and shutil.which("qtile")):
        pytest.skip("Xvfb or qtile not installed on system")

    display_num = f":{os.getpid() % 40 + 90}"
    socket_path = f"/tmp/qtile_pytest_{os.getpid()}"
    if os.path.exists(socket_path):
        os.remove(socket_path)

    xvfb = subprocess.Popen(
        ["Xvfb", display_num, "-screen", "0", "1024x768x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)

    env = dict(os.environ, DISPLAY=display_num, QT_QPA_PLATFORM="xcb")
    env.pop("WAYLAND_DISPLAY", None)

    config_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "qtile_test_config.py"
    )

    wm = subprocess.Popen(
        [
            "qtile", "start", "-b", "x11",
            "-s", socket_path, "-c", str(config_path),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)

    test_script = (
        "import time, sys, subprocess\n"
        "from PyQt6.QtWidgets import QApplication, QWidget, QDialog\n"
        "from ui.window_utils import (\n"
        "    bring_to_current_workspace, is_on_current_workspace,\n"
        "    prepare_dialog_for_current_workspace,\n"
        ")\n"
        "from core.window_manager import (\n"
        "    get_current_desktop, get_window_desktop\n"
        ")\n"
        "app = QApplication(['test'])\n"
        "widget = QWidget()\n"
        "bring_to_current_workspace(widget)\n"
        "app.processEvents()\n"
        "time.sleep(0.4)\n"
        "app.processEvents()\n"
        "win_id = int(widget.winId())\n"
        "cur_desk = get_current_desktop()\n"
        "win_desk = get_window_desktop(win_id)\n"
        "assert widget.isVisible() is True\n"
        "assert win_desk == cur_desk\n"
        "assert is_on_current_workspace(widget) is True\n"
        "# Switch to group 2\n"
        "subprocess.run([\n"
        f"    'qtile', 'cmd-obj', '-s', '{socket_path}',\n"
        "    '-o', 'group', '2', '-f', 'toscreen'\n"
        "])\n"
        "time.sleep(0.4)\n"
        "app.processEvents()\n"
        "assert get_current_desktop() == 1\n"
        "assert widget.isVisible() is True\n"
        "assert is_on_current_workspace(widget) is False\n"
        "# Bring to group 2\n"
        "bring_to_current_workspace(widget)\n"
        "time.sleep(0.4)\n"
        "app.processEvents()\n"
        "assert get_window_desktop(win_id) == 1\n"
        "assert is_on_current_workspace(widget) is True\n"
        "# Test dialog preparation\n"
        "dlg = QDialog(parent=widget)\n"
        "prepare_dialog_for_current_workspace(dlg)\n"
        "dlg.show()\n"
        "app.processEvents()\n"
        "time.sleep(0.2)\n"
        "assert get_window_desktop(int(dlg.winId())) == 1\n"
        "dlg.close()\n"
        "widget.close()\n"
        "app.processEvents()\n"
        "sys.exit(0)\n"
    )

    try:
        proc = subprocess.run(
            [sys.executable, "-c", test_script],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        msg = f"Qtile sub-process failed: {proc.stderr}"
        assert proc.returncode == 0, msg
    finally:
        wm.terminate()
        xvfb.terminate()
        wm.wait()
        xvfb.wait()
        if os.path.exists(socket_path):
            os.remove(socket_path)
