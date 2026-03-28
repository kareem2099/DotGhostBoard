"""
ui/settings.py
──────────────
Settings dialog for DotGhostBoard.

v1.1.0  Phantom  — Initial settings panel
v1.3.0  Wraith   — W009: Tag Manager dialog
v1.4.0  Eclipse  — E009: Master password, auto-lock, stealth, app filter
"""

import json
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QCheckBox, QComboBox, QLabel,
    QPushButton, QFrame, QSizePolicy,
    QListWidget, QListWidgetItem, QInputDialog,
    QMessageBox, QAbstractItemView, QLineEdit,
    QTabWidget, QWidget, QScrollArea, QTextEdit,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont

import core.storage as storage

# ── Settings file path ────────────────────────────────────────────────────────
_USER_DATA    = os.path.join(os.path.expanduser("~"), ".config", "dotghostboard")
SETTINGS_PATH = os.path.join(_USER_DATA, "settings.json")

_DEFAULTS: dict = {
    # General
    "max_history":                200,
    "max_captures":               100,
    "theme":                      "dark",
    "clear_on_exit":              False,
    "multiselect_hint_dismissed": False,
    # Eclipse
    "master_lock_enabled":        False,
    "auto_lock_minutes":          0,
    "stealth_mode":               False,
    "app_filter_mode":            "blacklist",
    "app_filter_list":            [],
}


# ── Public helpers ────────────────────────────────────────────────────────────

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
# W009 — Tag Manager Dialog  (unchanged from v1.3.0)
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
            item  = QListWidgetItem(
                f"{tag}   ({count} item{'s' if count != 1 else ''})"
            )
            item.setData(Qt.ItemDataRole.UserRole, tag)
            self._list.addItem(item)

        self._status.setText(
            f"{len(tags)} tag{'s' if len(tags) != 1 else ''} total"
        )

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
            f"✓ Renamed {old_tag} → {new_tag}  "
            f"({updated} item{'s' if updated != 1 else ''} updated)"
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
            f"✓ Deleted {old_tag}  "
            f"({removed} item{'s' if removed != 1 else ''} updated)"
        )
        self._refresh_list()


# ══════════════════════════════════════════════════════════════
# E009 — App Filter Editor  (Eclipse sub-widget)
# ══════════════════════════════════════════════════════════════

class AppFilterEditor(QWidget):
    """
    Inline widget for editing the app whitelist / blacklist.
    Embedded inside the Eclipse tab of SettingsDialog.
    """

    def __init__(self, mode: str, app_list: list[str], parent=None):
        super().__init__(parent)
        self._build_ui(mode, app_list)

    def _build_ui(self, mode: str, app_list: list[str]):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── Mode selector ──
        mode_row = QHBoxLayout()
        mode_lbl = QLabel("Filter mode:")
        mode_lbl.setStyleSheet("color:#888; font-size:12px;")

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(
            [
                "blacklist  (capture all except listed)",
                "whitelist  (capture only listed)",
            ]
        )
        self._mode_combo.setCurrentIndex(0 if mode == "blacklist" else 1)
        self._mode_combo.setToolTip(
            "blacklist: block specific apps from being monitored\n"
            "whitelist: only monitor specific apps"
        )
        mode_row.addWidget(mode_lbl)
        mode_row.addWidget(self._mode_combo, 1)
        layout.addLayout(mode_row)

        # ── App list ──
        list_lbl = QLabel("Application names  (process name or WM_CLASS):")
        list_lbl.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(list_lbl)

        self._app_list = QListWidget()
        self._app_list.setObjectName("AppFilterList")
        self._app_list.setFixedHeight(118)
        self._app_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._app_list.setStyleSheet("""
            QListWidget {
                background: #0f0f0f;
                border: 1px solid #2a2a2a;
                border-radius: 5px;
                font-family: monospace;
                font-size: 12px;
                color: #ccc;
            }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected {
                background: #ff990022;
                color: #ff9900;
            }
        """)
        for app in app_list:
            self._app_list.addItem(QListWidgetItem(app))
        layout.addWidget(self._app_list)

        # ── Add / Remove row ──
        edit_row = QHBoxLayout()
        edit_row.setSpacing(6)

        self._app_input = QLineEdit()
        self._app_input.setPlaceholderText("e.g.  keepassxc   or   gnome-keyring")
        self._app_input.setObjectName("AppFilterInput")
        self._app_input.returnPressed.connect(self._add_app)

        add_btn = QPushButton("＋ Add")
        add_btn.setObjectName("EclipseBtn")
        add_btn.setFixedHeight(30)
        add_btn.clicked.connect(self._add_app)

        rm_btn = QPushButton("✕ Remove")
        rm_btn.setObjectName("EclipseBtnDanger")
        rm_btn.setFixedHeight(30)
        rm_btn.clicked.connect(self._remove_selected)

        edit_row.addWidget(self._app_input, 1)
        edit_row.addWidget(add_btn)
        edit_row.addWidget(rm_btn)
        layout.addLayout(edit_row)

        # ── Detection hint ──
        hint = QLabel(
            "💡  Find your app name:  "
            "<code style='color:#00ff41; font-size:10px;'>"
            "cat /proc/$(xdotool getactivewindow getwindowpid)/comm"
            "</code>"
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#444; font-size:10px; padding-top:4px;")
        layout.addWidget(hint)

    def _add_app(self):
        name = self._app_input.text().strip().lower()
        if not name:
            return
        existing = [
            self._app_list.item(i).text()
            for i in range(self._app_list.count())
        ]
        if name not in existing:
            self._app_list.addItem(QListWidgetItem(name))
        self._app_input.clear()

    def _remove_selected(self):
        row = self._app_list.currentRow()
        if row >= 0:
            self._app_list.takeItem(row)

    def get_mode(self) -> str:
        return (
            "blacklist" if self._mode_combo.currentIndex() == 0
            else "whitelist"
        )

    def get_app_list(self) -> list[str]:
        return [
            self._app_list.item(i).text()
            for i in range(self._app_list.count())
        ]


# ══════════════════════════════════════════════════════════════
# Settings Dialog
# ══════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    """
    Modal settings dialog with two tabs:
      • General  — history limits, theme, clear-on-exit, tag manager
      • Eclipse  — master password, auto-lock, stealth, app filter
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙  DotGhostBoard — Settings")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(560)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )

        self._settings = load_settings()
        self._build_ui()

    # ── Root layout ───────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
        # ── Title ──
        title = QLabel("⚙  Settings")
        title.setStyleSheet(
            "font-size:15px; font-weight:bold; color:#00ff41;"
        )
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#222;")
        root.addWidget(sep)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("SettingsTabs")
        self._tabs.addTab(self._build_general_tab(), "General")
        self._tabs.addTab(self._build_eclipse_tab(), "🔐  Eclipse")
        self._tabs.addTab(self._build_about_tab(),   "👻  About")
        root.addWidget(self._tabs)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("SaveBtn")
        save_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        save_btn.setStyleSheet(
            "QPushButton#SaveBtn { background:#00ff4122; color:#00ff41;"
            " border:1px solid #00ff41; }"
            "QPushButton#SaveBtn:hover { background:#00ff4144; }"
        )
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_and_close)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    # ── General Tab ───────────────────────────────────────────────────────────

    def _build_general_tab(self) -> QWidget:
        tab    = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Max history
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

        # Max captures
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

        # Clear on exit
        self._clear_on_exit = QCheckBox("Clear history when app quits")
        self._clear_on_exit.setChecked(bool(self._settings["clear_on_exit"]))
        self._clear_on_exit.setToolTip(
            "Wipes all unpinned items from the database on exit.\n"
            "Pinned items are always preserved."
        )
        form.addRow("Privacy:", self._clear_on_exit)

        # Theme
        self._theme = QComboBox()
        self._theme.addItems(["Dark Neon", "Light  (coming soon)"])
        self._theme.setCurrentIndex(
            0 if self._settings.get("theme", "dark") == "dark" else 1
        )
        self._theme.model().item(1).setEnabled(False)
        form.addRow("Theme:", self._theme)

        layout.addLayout(form)

        # ── Manage Tags ──
        layout.addWidget(self._hsep())

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
        return tab

    # ── Eclipse Tab ───────────────────────────────────────────────────────────

    def _build_eclipse_tab(self) -> QWidget:
        from core.crypto import has_master_password

        # Wrap in a scroll area so it stays usable on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        inner  = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 16, 12, 20)
        layout.setSpacing(18)

        # ── Master Password ───────────────────────────────────────────────────
        layout.addWidget(self._section_label("🔑  Master Password"))

        has_pw = has_master_password()
        self._pw_status_lbl = QLabel(
            "✅  Master password is SET" if has_pw
            else "⚪  No master password configured"
        )
        self._pw_status_lbl.setStyleSheet(
            "color:#00ff41;" if has_pw else "color:#555;"
        )
        layout.addWidget(self._pw_status_lbl)

        pw_hint = QLabel(
            "When set, the app will show a lock screen on startup and "
            "allow you to lock/unlock from the 🔒 button or tray menu."
        )
        pw_hint.setWordWrap(True)
        pw_hint.setStyleSheet("color:#444; font-size:11px;")
        layout.addWidget(pw_hint)

        pw_btn_row = QHBoxLayout()
        pw_btn_row.setSpacing(8)

        self._set_pw_btn = QPushButton(
            "🔑  Change Password…" if has_pw else "🔑  Set Password…"
        )
        self._set_pw_btn.setObjectName("EclipseBtn")
        self._set_pw_btn.clicked.connect(self._setup_master_password)

        self._rm_pw_btn = QPushButton("✕  Remove Password…")
        self._rm_pw_btn.setObjectName("EclipseBtnDanger")
        self._rm_pw_btn.setToolTip(
            "Remove the master password.\n"
            "⚠ All encrypted items will be permanently decrypted first."
        )
        self._rm_pw_btn.setEnabled(has_pw)
        self._rm_pw_btn.clicked.connect(self._remove_master_password)

        pw_btn_row.addWidget(self._set_pw_btn)
        pw_btn_row.addWidget(self._rm_pw_btn)
        pw_btn_row.addStretch()
        layout.addLayout(pw_btn_row)

        layout.addWidget(self._hsep())

        # ── Auto-lock ─────────────────────────────────────────────────────────
        layout.addWidget(self._section_label("⏱  Auto-Lock"))

        lock_hint = QLabel(
            "Automatically lock the session after N minutes of inactivity. "
            "Set to 0 to disable.  Requires a master password."
        )
        lock_hint.setWordWrap(True)
        lock_hint.setStyleSheet("color:#444; font-size:11px;")
        layout.addWidget(lock_hint)

        lock_form = QFormLayout()
        lock_form.setSpacing(10)
        lock_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._auto_lock_spin = QSpinBox()
        self._auto_lock_spin.setRange(0, 480)
        self._auto_lock_spin.setSingleStep(5)
        self._auto_lock_spin.setSuffix("  min  (0 = disabled)")
        self._auto_lock_spin.setValue(
            self._settings.get("auto_lock_minutes", 0)
        )
        lock_form.addRow("Lock after:", self._auto_lock_spin)
        layout.addLayout(lock_form)

        layout.addWidget(self._hsep())

        # ── Stealth Mode ──────────────────────────────────────────────────────
        layout.addWidget(self._section_label("👁  Stealth Mode"))

        self._stealth_check = QCheckBox(
            "Hide window from taskbar and Alt+Tab switcher"
        )
        self._stealth_check.setChecked(
            bool(self._settings.get("stealth_mode", False))
        )
        self._stealth_check.setToolTip(
            "Window remains accessible via the tray icon and global hotkey.\n"
            "Uses Qt Tool window flag + _NET_WM_STATE X11 hints."
        )
        layout.addWidget(self._stealth_check)

        stealth_warn = QLabel(
            "⚠  Changes apply immediately on Save. "
            "If window was already open, it will re-show with new flags."
        )
        stealth_warn.setWordWrap(True)
        stealth_warn.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(stealth_warn)

        layout.addWidget(self._hsep())

        # ── App Filter ────────────────────────────────────────────────────────
        layout.addWidget(self._section_label("🛡  App Filter"))

        filter_hint = QLabel(
            "Control which applications DotGhostBoard monitors. "
            "Useful to exclude password managers or banking apps."
        )
        filter_hint.setWordWrap(True)
        filter_hint.setStyleSheet("color:#444; font-size:11px;")
        layout.addWidget(filter_hint)

        self._app_filter_editor = AppFilterEditor(
            mode=self._settings.get("app_filter_mode", "blacklist"),
            app_list=self._settings.get("app_filter_list", []),
        )
        layout.addWidget(self._app_filter_editor)

        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ── Eclipse password actions ──────────────────────────────────────────────

    def _setup_master_password(self):
        from core.crypto import (
            has_master_password, save_master_password,
            derive_key, verify_password,
        )

        had_pw = has_master_password()

        # Verify current password before allowing a change
        if had_pw:
            old_pw, ok = QInputDialog.getText(
                self, "Verify Current Password",
                "Enter your current master password:",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return
            if not verify_password(old_pw):
                QMessageBox.warning(
                    self, "Wrong Password",
                    "Current password is incorrect."
                )
                return

        # Get new password
        new_pw, ok = QInputDialog.getText(
            self, "Set Master Password",
            "New master password  (minimum 6 characters):",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not new_pw.strip():
            return

        # Confirm
        confirm, ok = QInputDialog.getText(
            self, "Confirm Password",
            "Confirm new master password:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        if new_pw != confirm:
            QMessageBox.warning(self, "Mismatch", "Passwords do not match.")
            return

        try:
            save_master_password(new_pw)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Password", str(exc))
            return

        # Password saved — items stay unencrypted by default.
        # User marks individual items as secret via right-click on the card.
        QMessageBox.information(
            self, "Password Set",
            "Master password set successfully.\n\n"
            "To encrypt an item, right-click its card and choose\n"
            "🔐 Mark as Secret."
        )

        self._refresh_eclipse_pw_ui()

    def _remove_master_password(self):
        from core.crypto import verify_password, remove_master_password, derive_key

        pw, ok = QInputDialog.getText(
            self, "Confirm Removal",
            "Enter your master password to remove it:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not pw.strip():
            return
        if not verify_password(pw):
            QMessageBox.warning(
                self, "Wrong Password", "Master password is incorrect."
            )
            return

        # Decrypt all secret items before removing the key
        key   = derive_key(pw)
        count = storage.decrypt_all_secret_items(key)
        if count == -1:
            QMessageBox.critical(
                self, "Decryption Failed",
                "Could not decrypt one or more items.\n"
                "Master password was NOT removed."
            )
            return

        remove_master_password()
        self._settings["master_lock_enabled"] = False
        self._settings["auto_lock_minutes"]   = 0
        self._auto_lock_spin.setValue(0)

        QMessageBox.information(
            self, "Password Removed",
            f"Master password removed.\n{count} item(s) decrypted."
        )
        self._refresh_eclipse_pw_ui()

    def _refresh_eclipse_pw_ui(self):
        """Sync password-related widgets to current state."""
        from core.crypto import has_master_password
        has_pw = has_master_password()
        self._pw_status_lbl.setText(
            "✅  Master password is SET" if has_pw
            else "⚪  No master password configured"
        )
        self._pw_status_lbl.setStyleSheet(
            "color:#00ff41;" if has_pw else "color:#555;"
        )
        self._set_pw_btn.setText(
            "🔑  Change Password…" if has_pw else "🔑  Set Password…"
        )
        self._rm_pw_btn.setEnabled(has_pw)

    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#00ff41; font-size:13px; font-weight:bold; "
            "padding-bottom:2px;"
        )
        return lbl

    @staticmethod
    def _hsep() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#1e1e1e; margin: 2px 0;")
        return sep

    def _open_tag_manager(self):
        TagManagerDialog(self).exec()

    # ── About Tab ─────────────────────────────────────────────────────────────

    def _build_about_tab(self) -> QWidget:
        import sys
        import platform
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner  = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)

        # ── Logo + App name ───────────────────────────────────────────────────
        logo_lbl = QLabel("👻")
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_lbl.setStyleSheet("font-size: 48px; padding-bottom: 4px;")
        layout.addWidget(logo_lbl)

        app_name = QLabel("DotGhostBoard")
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_name.setStyleSheet(
            "color: #00ff41; font-size: 22px; font-weight: bold; "
            "font-family: monospace; letter-spacing: 2px;"
        )
        layout.addWidget(app_name)

        version_lbl = QLabel("v1.4.0  ·  Eclipse")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_lbl.setStyleSheet(
            "color: #ff9900; font-size: 13px; "
            "font-family: monospace; padding-bottom: 2px;"
        )
        layout.addWidget(version_lbl)

        suite_lbl = QLabel("Part of the DotSuite toolkit")
        suite_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        suite_lbl.setStyleSheet("color: #444; font-size: 11px; padding-bottom: 16px;")
        layout.addWidget(suite_lbl)

        layout.addWidget(self._hsep())
        layout.addSpacing(14)

        # ── Author ────────────────────────────────────────────────────────────
        layout.addWidget(self._section_label("👤  Author"))
        layout.addSpacing(6)

        author_lbl = QLabel("FreeRave  (kareem)")
        author_lbl.setStyleSheet("color: #ccc; font-size: 13px; padding-left: 4px;")
        layout.addWidget(author_lbl)

        email_lbl = QLabel("kareem209907@gmail.com")
        email_lbl.setStyleSheet("color: #555; font-size: 11px; padding-left: 4px;")
        layout.addWidget(email_lbl)

        layout.addSpacing(14)
        layout.addWidget(self._hsep())
        layout.addSpacing(14)

        # ── License ───────────────────────────────────────────────────────────
        layout.addWidget(self._section_label("📄  License"))
        layout.addSpacing(6)

        lic_box = QFrame()
        lic_box.setStyleSheet(
            "QFrame { background: #0f0f0f; border: 1px solid #1e1e1e; "
            "border-radius: 6px; }"
        )
        lic_layout = QVBoxLayout(lic_box)
        lic_layout.setContentsMargins(12, 10, 12, 10)

        lic_title = QLabel("MIT License")
        lic_title.setStyleSheet("color: #00ff41; font-weight: bold; font-size: 12px;")

        lic_text = QLabel(
            "Copyright © 2026  FreeRave (kareem) — DotSuite\n\n"
            "Permission is hereby granted, free of charge, to any person\n"
            "obtaining a copy of this software to use, copy, modify, merge,\n"
            "publish, distribute, sublicense, and/or sell copies — subject\n"
            "to the MIT License conditions."
        )
        lic_text.setStyleSheet("color: #555; font-size: 11px; line-height: 1.6;")
        lic_text.setWordWrap(True)

        lic_layout.addWidget(lic_title)
        lic_layout.addSpacing(4)
        lic_layout.addWidget(lic_text)
        layout.addWidget(lic_box)

        layout.addSpacing(14)
        layout.addWidget(self._hsep())
        layout.addSpacing(14)

        # ── System info ───────────────────────────────────────────────────────
        layout.addWidget(self._section_label("🖥  System"))
        layout.addSpacing(6)

        sys_grid = QFrame()
        sys_grid.setStyleSheet(
            "QFrame { background: #0a0a0a; border: 1px solid #1a1a1a; "
            "border-radius: 6px; }"
        )
        sys_layout = QFormLayout(sys_grid)
        sys_layout.setContentsMargins(14, 10, 14, 10)
        sys_layout.setSpacing(6)
        sys_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _sys_val(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #00ff41; font-family: monospace; font-size: 11px;")
            return lbl

        def _sys_key(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #444; font-size: 11px;")
            return lbl

        sys_layout.addRow(_sys_key("Python:"),
                          _sys_val(f"{sys.version.split()[0]}"))
        sys_layout.addRow(_sys_key("PyQt6:"),
                          _sys_val(PYQT_VERSION_STR))
        sys_layout.addRow(_sys_key("Qt:"),
                          _sys_val(QT_VERSION_STR))
        sys_layout.addRow(_sys_key("Platform:"),
                          _sys_val(platform.system() + " " + platform.release()))
        sys_layout.addRow(_sys_key("Arch:"),
                          _sys_val(platform.machine()))

        layout.addWidget(sys_grid)

        layout.addSpacing(14)
        layout.addWidget(self._hsep())
        layout.addSpacing(14)

        # ── Links & Social ────────────────────────────────────────────────────
        def _link_btn(label: str, url: str, color: str) -> QPushButton:
            btn = QPushButton(label)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: transparent;"
                f"  color: {color};"
                f"  border: 1px solid {color}55;"
                f"  border-radius: 6px;"
                f"  padding: 6px 12px;"
                f"  font-size: 11px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background: {color}18;"
                f"  border: 1px solid {color};"
                f"}}"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            return btn

        # ── Project ──
        layout.addWidget(self._section_label("📦  Project"))
        layout.addSpacing(4)
        proj_row = QHBoxLayout()
        proj_row.setSpacing(6)
        proj_row.addWidget(_link_btn("⭐  GitHub",
            "https://github.com/kareem2099/DotGhostBoard", "#4a9eff"))
        proj_row.addWidget(_link_btn("🐛  Report a Bug",
            "https://github.com/kareem2099/DotGhostBoard/issues", "#ff6666"))
        proj_row.addStretch()
        layout.addLayout(proj_row)

        layout.addSpacing(10)

        # ── Articles & News ──
        layout.addWidget(self._section_label("📝  Articles & News"))
        layout.addSpacing(4)
        art_row = QHBoxLayout()
        art_row.setSpacing(6)
        art_row.addWidget(_link_btn("dev.to",
            "https://dev.to/freerave", "#a8e6cf"))
        art_row.addWidget(_link_btn("Medium",
            "https://medium.com/@freerave", "#ffcba4"))
        art_row.addWidget(_link_btn("LinkedIn",
            "https://www.linkedin.com/in/freerave/", "#0077b5"))
        art_row.addStretch()
        layout.addLayout(art_row)

        layout.addSpacing(10)

        # ── Social ──
        layout.addWidget(self._section_label("💬  Social"))
        layout.addSpacing(4)
        soc_row = QHBoxLayout()
        soc_row.setSpacing(6)
        soc_row.addWidget(_link_btn("𝕏  Twitter/X",
            "https://x.com/FreeRave2", "#cccccc"))
        soc_row.addWidget(_link_btn("🦋  Bluesky",
            "https://bsky.app/profile/freerave.bsky.social", "#0085ff"))
        soc_row.addStretch()
        layout.addLayout(soc_row)

        layout.addSpacing(10)

        # ── Videos ──
        layout.addWidget(self._section_label("🎬  Videos"))
        layout.addSpacing(4)
        vid_row = QHBoxLayout()
        vid_row.setSpacing(6)
        vid_row.addWidget(_link_btn("▶  YouTube",
            "https://www.youtube.com/@DotFreeRave", "#ff0000"))
        vid_row.addWidget(_link_btn("📸  Instagram",
            "https://www.instagram.com/dotfreerave/", "#e1306c"))
        vid_row.addWidget(_link_btn("🎵  TikTok",
            "https://www.tiktok.com/@dotfreerave", "#69c9d0"))
        vid_row.addStretch()
        layout.addLayout(vid_row)

        layout.addSpacing(10)

        # ── Facebook ──
        layout.addWidget(self._section_label("👥  Facebook"))
        layout.addSpacing(4)
        fb_row = QHBoxLayout()
        fb_row.setSpacing(6)
        fb_row.addWidget(_link_btn("📄  DotSuite Page",
            "https://www.facebook.com/profile.php?id=61582297589938", "#1877f2"))
        fb_row.addWidget(_link_btn("👤  FreeRave",
            "https://www.facebook.com/profile.php?id=61571382752681", "#1877f2"))
        fb_row.addStretch()
        layout.addLayout(fb_row)

        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save_and_close(self):
        # General
        self._settings["max_history"]   = self._max_history.value()
        self._settings["max_captures"]  = self._max_captures.value()
        self._settings["clear_on_exit"] = self._clear_on_exit.isChecked()
        self._settings["theme"]         = "dark"

        # Eclipse
        self._settings["auto_lock_minutes"] = self._auto_lock_spin.value()
        self._settings["stealth_mode"]      = self._stealth_check.isChecked()
        self._settings["app_filter_mode"]   = self._app_filter_editor.get_mode()
        self._settings["app_filter_list"]   = self._app_filter_editor.get_app_list()

        save_settings(self._settings)
        self.accept()

    @property
    def settings(self) -> dict:
        """Returns the last saved settings dict (after accept())."""
        return self._settings