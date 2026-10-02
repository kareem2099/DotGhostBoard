"""
core/window_manager.py
──────────────────────
X11 EWMH (Extended Window Manager Hints) window manager helper.
Enables cross-workspace window migration, desktop queries, and focus
activation for tiling window managers (such as Qtile on X11).

Pure Python + ctypes (libX11) — zero Qt dependencies in core layer.
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    Union,
    byref,
    c_char_p,
    c_int,
    c_long,
    c_ubyte,
    c_ulong,
    c_void_p,
)
import logging
from typing import Generator, Sequence

logger = logging.getLogger(__name__)

# ── X11 Constants ────────────────────────────────────────────────────────
SUBSTRUCTURE_MASK = (1 << 19) | (1 << 20)  # Notify | Redirect
PROP_MODE_REPLACE = 0
CLIENT_MESSAGE_TYPE = 33

# ── X11 C Structures ─────────────────────────────────────────────────────


class XClientMessageEvent(Structure):
    _fields_ = [
        ("type", c_int),
        ("serial", c_ulong),
        ("send_event", c_int),
        ("display", c_void_p),
        ("window", c_ulong),
        ("message_type", c_ulong),
        ("format", c_int),
        ("data", c_long * 5),
    ]


class XEvent(Union):
    _fields_ = [
        ("type", c_int),
        ("xclient", XClientMessageEvent),
        ("pad", c_long * 24),
    ]


# ── Xlib Dynamic Loader & Error Guard ────────────────────────────────────

_x11_lib = None
_x11_load_attempted = False
_error_handler_ref = None  # Global reference to prevent GC on the C callback


def _py_noop_error_handler(_display: c_void_p, _error_event: c_void_p) -> int:
    """Swallow transient X11 errors (e.g. BadWindow during unmap/race)."""
    return 0


def _get_x11():
    """Lazily load libX11 and initialize custom error handler."""
    global _x11_lib, _x11_load_attempted, _error_handler_ref
    if _x11_load_attempted:
        return _x11_lib

    _x11_load_attempted = True
    try:
        lib = ctypes.cdll.LoadLibrary("libX11.so.6")

        # Function signatures
        lib.XOpenDisplay.restype = c_void_p
        lib.XOpenDisplay.argtypes = [c_char_p]

        lib.XCloseDisplay.restype = c_int
        lib.XCloseDisplay.argtypes = [c_void_p]

        lib.XFlush.restype = c_int
        lib.XFlush.argtypes = [c_void_p]

        lib.XDefaultRootWindow.restype = c_ulong
        lib.XDefaultRootWindow.argtypes = [c_void_p]

        lib.XInternAtom.restype = c_ulong
        lib.XInternAtom.argtypes = [c_void_p, c_char_p, c_int]

        lib.XSendEvent.restype = c_int
        lib.XSendEvent.argtypes = [
            c_void_p,
            c_ulong,
            c_int,
            c_long,
            POINTER(XEvent),
        ]

        lib.XChangeProperty.restype = c_int
        lib.XChangeProperty.argtypes = [
            c_void_p,
            c_ulong,
            c_ulong,
            c_ulong,
            c_int,
            c_int,
            POINTER(c_ubyte),
            c_int,
        ]

        lib.XGetWindowProperty.restype = c_int
        lib.XGetWindowProperty.argtypes = [
            c_void_p,
            c_ulong,
            c_ulong,
            c_long,
            c_long,
            c_int,
            c_ulong,
            POINTER(c_ulong),
            POINTER(c_int),
            POINTER(c_ulong),
            POINTER(c_ulong),
            POINTER(POINTER(c_ubyte)),
        ]

        lib.XFree.restype = c_int
        lib.XFree.argtypes = [c_void_p]

        # Install persistent error handler to prevent fatal exit() on BadWindow
        error_handler_type = CFUNCTYPE(c_int, c_void_p, c_void_p)
        lib.XSetErrorHandler.restype = error_handler_type
        lib.XSetErrorHandler.argtypes = [error_handler_type]

        _error_handler_ref = error_handler_type(_py_noop_error_handler)
        lib.XSetErrorHandler(_error_handler_ref)

        _x11_lib = lib
    except Exception as exc:
        logger.debug("Failed to load libX11: %s", exc)
        _x11_lib = None

    return _x11_lib


@contextmanager
def x11_connection() -> Generator[tuple | None, None, None]:
    """Context manager for single-connection scoped X11 operations."""
    x11 = _get_x11()
    if not x11:
        yield None
        return

    disp = x11.XOpenDisplay(None)
    if not disp:
        yield None
        return

    try:
        root = x11.XDefaultRootWindow(disp)
        yield (x11, disp, root)
    finally:
        try:
            x11.XFlush(disp)
            x11.XCloseDisplay(disp)
        except Exception:
            pass


# ── Pure Message Construction (Testable Unit) ────────────────────────────


def create_client_message_payload(
    window_xid: int,
    message_atom: int,
    data_values: Sequence[int],
) -> dict:
    """Build a pure dictionary representing the ClientMessage payload."""
    data_array = [0, 0, 0, 0, 0]
    for idx, val in enumerate(data_values[:5]):
        data_array[idx] = int(val)
    return {
        "type": CLIENT_MESSAGE_TYPE,
        "window": int(window_xid),
        "message_type": int(message_atom),
        "format": 32,
        "data": data_array,
    }


def _send_root_client_message(
    x11,
    disp: c_void_p,
    root: int,
    window_xid: int,
    message_atom: int,
    data_values: Sequence[int],
) -> bool:
    """Send an EWMH ClientMessage event to the root window."""
    payload = create_client_message_payload(
        window_xid, message_atom, data_values
    )
    ev = XEvent()
    ev.type = payload["type"]
    ev.xclient.type = payload["type"]
    ev.xclient.serial = 0
    ev.xclient.send_event = 1
    ev.xclient.display = disp
    ev.xclient.window = c_ulong(payload["window"])
    ev.xclient.message_type = c_ulong(payload["message_type"])
    ev.xclient.format = payload["format"]
    for i in range(5):
        ev.xclient.data[i] = payload["data"][i]

    ret = x11.XSendEvent(
        disp, root, 0, c_long(SUBSTRUCTURE_MASK), byref(ev)
    )
    return ret != 0


# ── X11 EWMH Operations ──────────────────────────────────────────────────


def _read_cardinal_property(
    x11, disp: c_void_p, target_window: int, atom_name: bytes
) -> int | None:
    """Helper to read a single CARDINAL/32-bit property from a window."""
    atom = x11.XInternAtom(disp, atom_name, 0)
    if not atom:
        return None

    actual_type = c_ulong()
    actual_format = c_int()
    nitems = c_ulong()
    bytes_after = c_ulong()
    prop_return = POINTER(c_ubyte)()

    status = x11.XGetWindowProperty(
        disp,
        c_ulong(target_window),
        atom,
        0,
        1,
        0,
        0,
        byref(actual_type),
        byref(actual_format),
        byref(nitems),
        byref(bytes_after),
        byref(prop_return),
    )

    try:
        if (
            status == 0
            and nitems.value > 0
            and actual_format.value == 32
            and prop_return
        ):
            val = ctypes.cast(prop_return, POINTER(c_ulong)).contents.value
            return int(val)
        return None
    finally:
        if prop_return:
            x11.XFree(prop_return)


def get_current_desktop() -> int | None:
    """
    Read _NET_CURRENT_DESKTOP from the root window.
    Returns the zero-based desktop index, or None if not supported/set.
    """
    with x11_connection() as conn:
        if not conn:
            return None
        x11, disp, root = conn
        try:
            return _read_cardinal_property(
                x11, disp, root, b"_NET_CURRENT_DESKTOP"
            )
        except Exception as exc:
            logger.debug("Error reading _NET_CURRENT_DESKTOP: %s", exc)
            return None


def get_window_desktop(xid: int) -> int | None:
    """
    Read _NET_WM_DESKTOP property directly on the target window.
    Returns desktop index (0-based) or 0xFFFFFFFF (sticky), or None.
    """
    if not xid:
        return None

    with x11_connection() as conn:
        if not conn:
            return None
        x11, disp, _root = conn
        try:
            return _read_cardinal_property(
                x11, disp, xid, b"_NET_WM_DESKTOP"
            )
        except Exception as exc:
            logger.debug("Error reading _NET_WM_DESKTOP on 0x%x: %s", xid, exc)
            return None


def set_window_desktop_property(xid: int, desktop: int) -> bool:
    """
    Set _NET_WM_DESKTOP directly on the window via XChangeProperty.
    Used for unmapped/withdrawn windows before show() to prevent flicker.
    """
    if not xid:
        return False

    with x11_connection() as conn:
        if not conn:
            return False
        x11, disp, _root = conn
        try:
            atom_prop = x11.XInternAtom(disp, b"_NET_WM_DESKTOP", 0)
            atom_card = x11.XInternAtom(disp, b"CARDINAL", 0)
            if not atom_prop or not atom_card:
                return False

            val = (c_long * 1)(int(desktop))
            p_data = ctypes.cast(val, POINTER(c_ubyte))

            ret = x11.XChangeProperty(
                disp,
                c_ulong(xid),
                atom_prop,
                atom_card,
                32,
                PROP_MODE_REPLACE,
                p_data,
                1,
            )
            return ret != 0
        except Exception as exc:
            logger.debug("Error setting _NET_WM_DESKTOP property: %s", exc)
            return False


def send_window_desktop_message(xid: int, desktop: int) -> bool:
    """
    Send _NET_WM_DESKTOP client message to the root window.
    Used for already mapped windows to request desktop migration.
    """
    if not xid:
        return False

    with x11_connection() as conn:
        if not conn:
            return False
        x11, disp, root = conn
        try:
            atom_msg = x11.XInternAtom(disp, b"_NET_WM_DESKTOP", 0)
            if not atom_msg:
                return False
            return _send_root_client_message(
                x11, disp, root, xid, atom_msg, [int(desktop), 2]
            )
        except Exception as exc:
            logger.debug("Error sending _NET_WM_DESKTOP message: %s", exc)
            return False


def send_active_window_message(xid: int, source: int = 2) -> bool:
    """
    Send _NET_ACTIVE_WINDOW client message to the root window.
    source=2 indicates pager/user action to bypass focus stealing.
    """
    if not xid:
        return False

    with x11_connection() as conn:
        if not conn:
            return False
        x11, disp, root = conn
        try:
            atom_msg = x11.XInternAtom(disp, b"_NET_ACTIVE_WINDOW", 0)
            if not atom_msg:
                return False
            return _send_root_client_message(
                x11, disp, root, xid, atom_msg, [int(source), 0, 0, 0, 0]
            )
        except Exception as exc:
            logger.debug("Error sending _NET_ACTIVE_WINDOW message: %s", exc)
            return False
