"""
App Filter — Eclipse v1.4.0
────────────────────────────
Controls which applications are monitored for clipboard changes.

Two modes:
  blacklist (default) — capture everything EXCEPT listed apps.
  whitelist           — capture ONLY from listed apps.

Detection strategy (Linux/X11):
  1. xdotool getactivewindow → window ID
  2. xdotool getwindowpid    → PID
  3. /proc/<PID>/comm        → process name
  4. xprop WM_CLASS          → window class (fallback / extra match)

xdotool is optional — if unavailable, should_capture() always returns True.
"""

from __future__ import annotations

import os
import re
import subprocess


# ── Low-level X11 helpers ─────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: float = 1.0) -> str | None:
    """Run *cmd* and return stdout stripped, or None on any error."""
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, timeout=timeout
        ).decode().strip()
    except Exception:
        return None


def get_active_window_id() -> str | None:
    return _run(["xdotool", "getactivewindow"])


def get_active_window_pid(window_id: str) -> int | None:
    raw = _run(["xdotool", "getwindowpid", window_id])
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def get_process_name(pid: int) -> str | None:
    """Read process name from /proc/<pid>/comm (Linux only)."""
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip().lower()
    except (OSError, IOError):
        return None


def get_window_class(window_id: str) -> str | None:
    """
    Return the first quoted value from WM_CLASS property.
    e.g. WM_CLASS = "keepassxc", "KeePassXC"  →  "keepassxc"
    """
    raw = _run(["xprop", "-id", window_id, "WM_CLASS"])
    if not raw:
        return None
    match = re.search(r'"([^"]+)"', raw)
    return match.group(1).lower() if match else None


def get_active_app_identifiers() -> set[str]:
    """
    Return a set of lowercase strings identifying the currently focused app.
    May contain: process name, window class, window class instance — whatever
    was detectable.  Empty set if detection is unavailable.
    """
    identifiers: set[str] = set()

    win_id = get_active_window_id()
    if not win_id:
        return identifiers

    pid = get_active_window_pid(win_id)
    if pid:
        proc = get_process_name(pid)
        if proc:
            identifiers.add(proc)

    wm_class = get_window_class(win_id)
    if wm_class:
        identifiers.add(wm_class)

    return identifiers


# ── AppFilter class ───────────────────────────────────────────────────────────

class AppFilter:
    """
    Decides whether the clipboard event from the currently active
    window should be recorded.

    Usage:
        f = AppFilter(mode="blacklist", app_list=["keepassxc", "gnome-keyring"])
        if f.should_capture():
            # record clipboard
    """

    def __init__(
        self,
        mode: str = "blacklist",
        app_list: list[str] | None = None,
    ) -> None:
        self.mode: str       = mode          # 'blacklist' | 'whitelist'
        self.app_list: list[str] = [
            a.strip().lower() for a in (app_list or []) if a.strip()
        ]

    # ── Public API ────────────────────────────────────────────────────────────

    def should_capture(self) -> bool:
        """
        Return True if the clipboard change from the active window
        should be captured, based on the current mode and app list.

        If xdotool is not installed or detection fails, always returns True
        (fail-open — better to over-capture than silently miss items).
        """
        if not self.app_list:
            return True   # No filter configured → capture everything

        identifiers = get_active_app_identifiers()

        if not identifiers:
            return True   # Detection unavailable → fail-open

        matched = self._matches(identifiers)

        if self.mode == "whitelist":
            return matched      # Allow only listed apps
        else:                   # blacklist
            return not matched  # Block listed apps

    def update(self, mode: str, app_list: list[str]) -> None:
        """Hot-reload filter config without restarting the watcher."""
        self.mode     = mode
        self.app_list = [a.strip().lower() for a in app_list if a.strip()]

    # ── Internals ─────────────────────────────────────────────────────────────

    def _matches(self, identifiers: set[str]) -> bool:
        """
        Return True if any identifier contains any app_list entry as a substring.
        Substring matching covers cases like "keepassxc" matching
        "org.keepassxc.keepassxc" WM_CLASS values.
        """
        for app in self.app_list:
            for ident in identifiers:
                if app in ident:
                    return True
        return False

    # ── Repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"AppFilter(mode={self.mode!r}, "
            f"apps={self.app_list!r})"
        )