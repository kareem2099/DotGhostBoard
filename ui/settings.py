"""
ui/settings.py
──────────────
Settings dialog for DotGhostBoard v1.1.0 Phantom.

Reads and writes data/settings.json.
Opens via the ⚙ button in the top bar.

v1.3.0 (W009): Added "Manage Tags" button + TagManagerDialog.
"""

import json
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QCheckBox, QComboBox, QLabel,
    QPushButton, QFrame, QSizePolicy,
    QListWidget, QListWidgetItem, QInputDialog,
    QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt

import core.storage as storage

# ── Settings file path ────────────────────────────────────────────────────────
_USER_DATA     = os.path.join(os.path.expanduser("~"), ".config", "dotghostboard")
SETTINGS_PATH  = os.path.join(_USER_DATA, "settings.json")

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


# ══════════════════════════════════════════════════════════════
# W009 — Tag Manager Dialog
# ══════════════════════════════════════════════════════════════

class TagManagerDialog(QDialog):
    """
    Global tag manager — rename, delete, or merge tags across all items.
    Opens from the Settings dialog via 'Manage Tags' button.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🏷  Manage Tags")
        self.setModal(True)
        self.setMinimumSize(360, 440)
        self.setMaximumWidth(480)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        self._build_ui()
        self._refresh_list()

    # ──────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Title ──
        title = QLabel("🏷  Tag Manager")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#00ff41;")
        layout.addWidget(title)

        subtitle = QLabel("Rename or delete tags globally across all items.")
        subtitle.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(subtitle)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#222;")
        layout.addWidget(sep)

        # ── Tag list ──
        self._list = QListWidget()
        self._list.setObjectName("TagManagerList")
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setStyleSheet("""
            QListWidget {
                background: #111;
                border: 1px solid #2a2a2a;
                border-radius: 6px;
            }
            QListWidget::item {
                padding: 8px 12px;
                color: #ccc;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: #00ff4122;
                color: #00ff41;
            }
            QListWidget::item:hover:!selected {
                background: #1a1a1a;
            }
        """)
        layout.addWidget(self._list)

        # ── Empty state label (shown when no tags) ──
        self._empty_lbl = QLabel("No tags yet — add some from the cards!")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color:#444; font-size:12px; padding: 20px;")
        self._empty_lbl.hide()
        layout.addWidget(self._empty_lbl)

        # ── Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._rename_btn = QPushButton("✏️  Rename")
        self._rename_btn.setObjectName("TagMgrBtn")
        self._rename_btn.setToolTip("Rename selected tag across all items")
        self._rename_btn.clicked.connect(self._rename_selected)

        self._delete_btn = QPushButton("🗑️  Delete")
        self._delete_btn.setObjectName("TagMgrBtnDanger")
        self._delete_btn.setToolTip("Remove selected tag from all items")
        self._delete_btn.clicked.connect(self._delete_selected)

        self._refresh_btn = QPushButton("↻  Refresh")
        self._refresh_btn.setObjectName("TagMgrBtn")
        self._refresh_btn.setToolTip("Reload tag list from database")
        self._refresh_btn.clicked.connect(self._refresh_list)

        btn_row.addWidget(self._rename_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._refresh_btn)
        layout.addLayout(btn_row)

        # ── Status label ──
        self._status = QLabel("")
        self._status.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(self._status)

        # ── Close button ──
        close_btn = QPushButton("Close")
        close_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
# ── Dialog ─────────────────────────────────────────────────────────────────────

    def _refresh_list(self):
        self._list.clear()
        tags = storage.get_all_tags()

        if not tags:
            self._list.hide()
            self._empty_lbl.show()
            self._rename_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            return

        self._empty_lbl.hide()
        self._list.show()
        self._rename_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)

        for tag in tags:
            # Count how many items use this tag
            count = len(storage.get_items_by_tag(tag))
            item = QListWidgetItem(f"{tag}   ({count} item{'s' if count != 1 else ''})")
            item.setData(Qt.ItemDataRole.UserRole, tag)   # store raw tag string
            self._list.addItem(item)

        self._status.setText(f"{len(tags)} tag{'s' if len(tags) != 1 else ''} total")

    # ──────────────────────────────────────────
    def _selected_tag(self) -> str | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ──────────────────────────────────────────
    def _rename_selected(self):
        old_tag = self._selected_tag()
        if not old_tag:
            self._status.setText("⚠ Select a tag first.")
            return

        new_tag, ok = QInputDialog.getText(
            self, "Rename Tag",
            f"Rename  {old_tag}  to:",
            text=old_tag
        )
        if not ok or not new_tag.strip():
            return

        new_tag = new_tag.strip().lower()
        if not new_tag.startswith("#"):
            new_tag = f"#{new_tag}"

        if new_tag == old_tag:
            self._status.setText("No change.")
            return

        updated = storage.rename_tag(old_tag, new_tag)
        self._status.setText(
            f"✓ Renamed {old_tag} → {new_tag}  ({updated} item{'s' if updated != 1 else ''} updated)"
        )
        self._refresh_list()

    # ──────────────────────────────────────────
    def _delete_selected(self):
        old_tag = self._selected_tag()
        if not old_tag:
            self._status.setText("⚠ Select a tag first.")
            return

        count = len(storage.get_items_by_tag(old_tag))
        reply = QMessageBox.question(
            self, "Delete Tag",
            f"Remove  {old_tag}  from {count} item{'s' if count != 1 else ''}?\n"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        removed = storage.delete_tag(old_tag)
        self._status.setText(
            f"✓ Deleted {old_tag}  ({removed} item{'s' if removed != 1 else ''} updated)"
        )
        self._refresh_list()


# ══════════════════════════════════════════════════════════════
# Settings Dialog
# ══════════════════════════════════════════════════════════════

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

        # ── W009: Manage Tags button ──
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#222;")
        layout.addWidget(sep2)

        tags_row = QHBoxLayout()
        tags_lbl = QLabel("Tags:")
        tags_lbl.setStyleSheet("color:#888;")

        manage_tags_btn = QPushButton("🏷  Manage Tags…")
        manage_tags_btn.setObjectName("ManageTagsBtn")
        manage_tags_btn.setToolTip("Rename, delete, or merge tags globally")
        manage_tags_btn.clicked.connect(self._open_tag_manager)

        tags_row.addWidget(tags_lbl)
        tags_row.addStretch()
        tags_row.addWidget(manage_tags_btn)
        layout.addLayout(tags_row)

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
    def _open_tag_manager(self):
        dlg = TagManagerDialog(self)
        dlg.exec()

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
