"""
core/notifications.py
─────────────────────
Cross-desktop notification dispatcher conforming to the FreeDesktop.org
Desktop Notifications Specification (org.freedesktop.Notifications).

Provides native system notification popups on Linux (GNOME, KDE, XFCE,
Sway, Hyprland, etc.) even when DotGhostBoard is minimized or hidden in the
system tray, with optional click-to-activate action callbacks.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def get_default_icon_path(category: str = "general") -> str:
    """
    Resolve the best icon for the notification.
    Prefers the project high-resolution PNG icon, falling back to stock
    FreeDesktop theme icons.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_icon = os.path.join(base_dir, "data", "icons", "icon_128.png")
    if os.path.exists(app_icon):
        return app_icon

    if category in ("secret", "password", "security"):
        return "dialog-password"
    elif category in ("warning", "alert"):
        return "dialog-warning"
    elif category in ("error", "critical"):
        return "dialog-error"
    return "dialog-information"


try:
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication

    class _NotificationDispatcher(QObject):
        sig_action = pyqtSignal(object)

        def __init__(self):
            super().__init__()
            self.sig_action.connect(self._handle_action)

        def _handle_action(self, fn):
            try:
                fn()
            except Exception as exc:
                logger.debug("Error in notification action callback: %s", exc)

    _dispatcher_instance: Optional[_NotificationDispatcher] = None

    def _get_dispatcher() -> Optional[_NotificationDispatcher]:
        global _dispatcher_instance
        if _dispatcher_instance is None and QApplication.instance():
            _dispatcher_instance = _NotificationDispatcher()
        return _dispatcher_instance

except Exception:
    def _get_dispatcher():
        return None


def _safe_dispatch_callback(callback: Callable[[], None]) -> None:
    """Invoke callback safely on the Qt GUI main thread if QApplication exists."""
    dispatcher = _get_dispatcher()
    if dispatcher is not None:
        dispatcher.sig_action.emit(callback)
        return

    try:
        callback()
    except Exception as exc:
        logger.debug("Error invoking notification action callback: %s", exc)


def send_desktop_notification(
    title: str,
    message: str,
    app_name: str = "DotGhostBoard",
    icon: Optional[str] = None,
    timeout_ms: int = 5000,
    urgency: str = "normal",
    action_label: Optional[str] = None,
    action_callback: Optional[Callable[[], None]] = None,
) -> bool:
    """
    Dispatch a native desktop notification to the operating system.

    Parameters:
        title: Notification summary / heading.
        message: Notification body / text.
        app_name: Name of the originating application (defaults to 'DotGhostBoard').
        icon: Path to image file or stock icon name.
        timeout_ms: Display expiration time in milliseconds (0 for persistent).
        urgency: Notification priority ('low', 'normal', or 'critical').
        action_label: Label for clickable action button (e.g. 'Open DotGhostBoard').
        action_callback: Function called when user clicks the notification / action.

    Returns:
        True if notification was successfully dispatched, False otherwise.
    """
    resolved_icon = icon or get_default_icon_path()

    # 1. Primary path: notify-send (FreeDesktop CLI, available on 99% of Linux desktops)
    notify_send = shutil.which("notify-send")
    if notify_send:
        try:
            cmd = [
                notify_send,
                "-a", app_name,
                "-i", resolved_icon,
                "-t", str(timeout_ms),
                "-u", urgency,
            ]
            if action_callback:
                label = action_label or "Open DotGhostBoard"
                cmd.extend(["-A", f"default={label}"])

            cmd.extend([title, message])

            if action_callback:
                def _wait_action():
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            text=True,
                        )
                        out, _ = proc.communicate(timeout=(timeout_ms / 1000.0) + 3.0)
                        if out and out.strip() == "default":
                            _safe_dispatch_callback(action_callback)
                    except Exception as wait_exc:
                        logger.debug("notify-send action wait finished: %s", wait_exc)

                threading.Thread(target=_wait_action, daemon=True).start()
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            return True
        except Exception as exc:
            logger.debug("notify-send dispatch failed: %s", exc)

    # 2. Secondary path: dbus-python over session bus
    try:
        import dbus
        bus = dbus.SessionBus()
        notify = bus.get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications")
        iface = dbus.Interface(notify, "org.freedesktop.Notifications")
        iface.Notify(
            app_name,
            dbus.UInt32(0),
            resolved_icon,
            title,
            message,
            dbus.Array([], signature="s"),
            dbus.Dictionary({}, signature="sv"),
            dbus.Int32(timeout_ms),
        )
        return True
    except Exception as exc:
        logger.debug("dbus notification dispatch failed: %s", exc)

    return False
