"""
ui/window_utils.py
──────────────────
UI-level window management helpers for DotGhostBoard.
Orchestrates cross-workspace migration, visibility checks, and focus.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from core.window_manager import (
    get_current_desktop,
    get_window_desktop,
    send_active_window_message,
    send_window_desktop_message,
    set_window_desktop_property,
)


def _is_ewmh_disabled() -> bool:
    """Check if EWMH migration is explicitly disabled by environment flag."""
    return os.environ.get(
        "DOTGHOST_NO_EWMH", ""
    ).strip().lower() in ("1", "true", "yes")


def is_on_current_workspace(widget: QWidget) -> bool:
    """
    Check if widget is located on the user's currently active workspace.
    Returns True on non-xcb platforms, if desktops cannot be queried,
    or if the window's desktop matches current desktop or is sticky.
    """
    if widget is None or _is_ewmh_disabled():
        return True

    if QGuiApplication.platformName() != "xcb":
        return True

    cur = get_current_desktop()
    win = get_window_desktop(int(widget.winId()))

    return cur is None or win is None or win in (cur, 0xFFFFFFFF)


def prepare_dialog_for_current_workspace(dlg: QWidget) -> None:
    """
    Prepare a modal dialog before dlg.exec() by setting desktop property.
    Does NOT call show() to preserve modal state in Qt's exec() loop.
    """
    if dlg is None or _is_ewmh_disabled():
        return

    if QGuiApplication.platformName() != "xcb":
        return

    cur = get_current_desktop()
    if cur is not None:
        set_window_desktop_property(int(dlg.winId()), cur)


def bring_to_current_workspace(widget: QWidget) -> None:
    """
    Bring a widget window to the user's active workspace and focus it.
    - If running under X11 ('xcb'): executes EWMH workspace migration and
      focus activation (bypassing focus-stealing prevention).
    - If not 'xcb' or disabled: relies on standard Qt.
    """
    if widget is None:
        return

    is_xcb = (
        QGuiApplication.platformName() == "xcb"
        and not _is_ewmh_disabled()
    )

    if is_xcb:
        xid = int(widget.winId())
        is_mapped = widget.isVisible()

        cur_desktop = get_current_desktop()
        if cur_desktop is not None:
            if is_mapped:
                send_window_desktop_message(xid, cur_desktop)
            else:
                set_window_desktop_property(xid, cur_desktop)

        widget.show()
        widget.raise_()
        widget.activateWindow()

        # Immediate activation
        send_active_window_message(xid, source=2)

        # Deferred retry for unmapped windows to eliminate WM MapRequest race
        if not is_mapped:
            QTimer.singleShot(
                40, lambda: send_active_window_message(xid, source=2)
            )
    else:
        widget.show()
        widget.raise_()
        widget.activateWindow()
