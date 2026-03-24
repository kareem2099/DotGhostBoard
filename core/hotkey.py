"""
core/hotkey.py
──────────────
Global hotkey listener — runs in a daemon thread.
Listens for Ctrl+Shift+V anywhere on the system and
emits a Qt signal to show the DotGhostBoard window.

Uses pynput (no root required on X11/Wayland).
"""

from pynput import keyboard
from PyQt6.QtCore import QObject, pyqtSignal


# Keys we're watching
_COMBO = {keyboard.Key.ctrl_l, keyboard.Key.shift, keyboard.KeyCode.from_char('v')}
# Also handle right-ctrl variant
_COMBO_R = {keyboard.Key.ctrl_r, keyboard.Key.shift, keyboard.KeyCode.from_char('v')}


class HotkeyListener(QObject):
    """
    Daemon thread that listens for Ctrl+Shift+V globally.
    Emits `triggered` signal → connect to Dashboard.show_and_raise()
    """

    triggered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pressed: set = set()
        self._listener: keyboard.Listener | None = None

    # ──────────────────────────────────────────
    def start(self):
        """Start listening in a background daemon thread."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self._listener.daemon = True
        self._listener.start()
        print("[Hotkey] Listening for Ctrl+Shift+V")

    def stop(self):
        """Stop the listener cleanly."""
        if self._listener:
            self._listener.stop()
            self._listener = None
            print("[Hotkey] Stopped")

    # ──────────────────────────────────────────
    def _normalize(self, key) -> keyboard.KeyCode | keyboard.Key | None:
        """Normalize left/right Ctrl & Shift to a single value."""
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            return keyboard.Key.ctrl_l
        if key in (keyboard.Key.shift, keyboard.Key.shift_r):
            return keyboard.Key.shift
        return key

    def _on_press(self, key):
        normalized = self._normalize(key)
        if normalized:
            self._pressed.add(normalized)
        self._check_combo()

    def _on_release(self, key):
        normalized = self._normalize(key)
        self._pressed.discard(normalized)

    def _check_combo(self):
        """Fire if Ctrl + Shift + V are all held."""
        if _COMBO.issubset(self._pressed):
            self._pressed.clear()   # Prevent multiple triggers if keys are held down
            self.triggered.emit()