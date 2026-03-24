"""
ui/settings.py
──────────────
Settings dialog for DotGhostBoard v1.1.0 Phantom.

Reads and writes data/settings.json.
Opens via the ⚙ button in the top bar.
"""

import json
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QCheckBox, QComboBox, QLabel,
    QPushButton, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt

# ── Settings file path ────────────────────────────────────────────────────────
_BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH  = os.path.join(_BASE_DIR, "data", "settings.json")

_DEFAULTS: dict = {
    "max_history":  200,
    "max_captures": 100,
    "theme":        "dark",
    "clear_on_exit": False,
}


# ── Public helpers ─────────────────────────────────────────────────────────────

def load_settings() -> dict:
    """Return settings dict. Missing keys fall back to defaults."""
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge with defaults so new keys always exist
            return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save_settings(settings: dict) -> None:
    """Persist settings dict to data/settings.json."""
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


# ── Dialog ─────────────────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    """
    Modal settings dialog.
    Changes are applied to settings.json only on Save.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙  DotGhostBoard — Settings")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMaximumWidth(480)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )

        self._settings = load_settings()
        self._build_ui()

    # ──────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── Title ──
        title = QLabel("Settings")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#00ff41;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#222;")
        layout.addWidget(sep)

        # ── Form ──
        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 1. Max history
        self._max_history = QSpinBox()
        self._max_history.setRange(10, 5000)
        self._max_history.setSingleStep(10)
        self._max_history.setSuffix("  items")
        self._max_history.setValue(self._settings["max_history"])
        self._max_history.setToolTip(
            "Maximum number of clipboard items to keep.\n"
            "Oldest items are trimmed on startup and on capture."
        )
        form.addRow("Max history:", self._max_history)

        # 2. Max captures (S003)
        self._max_captures = QSpinBox()
        self._max_captures.setRange(10, 2000)
        self._max_captures.setSingleStep(10)
        self._max_captures.setSuffix("  files")
        self._max_captures.setValue(self._settings.get("max_captures", 100))
        self._max_captures.setToolTip(
            "Maximum number of saved image/video capture files to keep.\n"
            "Oldest unpinned captures are deleted from disk automatically."
        )
        form.addRow("Max captures:", self._max_captures)

        # 3. Clear on exit
        self._clear_on_exit = QCheckBox("Clear history when app quits")
        self._clear_on_exit.setChecked(bool(self._settings["clear_on_exit"]))
        self._clear_on_exit.setToolTip(
            "Wipes all unpinned items from the database on exit.\n"
            "Pinned items are always preserved."
        )
        form.addRow("Privacy:", self._clear_on_exit)

        # 4. Theme
        self._theme = QComboBox()
        self._theme.addItems(["Dark Neon", "Light  (coming soon)"])
        self._theme.setCurrentIndex(
            0 if self._settings.get("theme", "dark") == "dark" else 1
        )
        self._theme.model().item(1).setEnabled(False)
        form.addRow("Theme:", self._theme)

        layout.addLayout(form)

        # ── Hotkey hint ──
        hint_frame = QFrame()
        hint_frame.setObjectName("HintFrame")
        hint_layout = QVBoxLayout(hint_frame)
        hint_layout.setContentsMargins(10, 8, 10, 8)

        hint_title = QLabel("Global Hotkey")
        hint_title.setStyleSheet("color:#555; font-size:11px;")
        hint_label = QLabel("Ctrl + Alt + V   →   Show / Hide window")
        hint_label.setStyleSheet("color:#00ff41; font-size:12px;")

        hint_layout.addWidget(hint_title)
        hint_layout.addWidget(hint_label)
        layout.addWidget(hint_frame)

        layout.addStretch()

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("SaveBtn")
        save_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        save_btn.setStyleSheet(
            "QPushButton#SaveBtn { background:#00ff4122; color:#00ff41; border:1px solid #00ff41; }"
            "QPushButton#SaveBtn:hover { background:#00ff4144; }"
        )
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_and_close)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    # ──────────────────────────────────────────
    def _save_and_close(self):
        self._settings["max_history"]   = self._max_history.value()
        self._settings["max_captures"]  = self._max_captures.value()
        self._settings["clear_on_exit"] = self._clear_on_exit.isChecked()
        self._settings["theme"]         = "dark"
        save_settings(self._settings)
        self.accept()

    # ──────────────────────────────────────────
    @property
    def settings(self) -> dict:
        """Returns the last saved settings (useful after accept())."""
        return self._settings
