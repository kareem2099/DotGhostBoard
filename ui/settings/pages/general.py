"""
ui/settings/pages/general.py
─────────────────────────────
General settings tab.

Extracted from ui/settings.py (v1.6.0 Phantom) in v2.0.0 Cerberus.
Contains:
  - AppFilterEditor  (E009 widget — hosted here, imported by security.py)
  - build_general_tab(dialog) → QWidget

Note: AppFilterEditor is rendered in the Eclipse/Security tab;
it is preserved here alongside the settings widgets for Phase 5.

Code is preserved verbatim; only self.X → dialog.X substitution was applied.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import os
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QCheckBox, QComboBox, QLabel,
    QPushButton, QFrame,
    QListWidget, QListWidgetItem, QAbstractItemView, QLineEdit,
    QWidget, QFileDialog, QScrollArea,
)
from PyQt6.QtCore import Qt

if TYPE_CHECKING:
    from ui.settings.dialog import SettingsDialog


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
                background: #211d16;
                color: #d1a85d;
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
            "Find your app name:  "
            "<code style='color:#8dd5a2; font-size:10px;'>"
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
# General Tab
# ══════════════════════════════════════════════════════════════

def build_general_tab(dialog: "SettingsDialog") -> QWidget:
    """
    Build and return the General settings tab widget.
    Assigns owned widgets to dialog (dialog.X = widget).
    Calls dialog helpers: dialog._hsep(), dialog._open_tag_manager(),
    dialog._on_autostart_toggled(), dialog._manual_check_update().
    """
    tab    = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(12, 16, 12, 12)
    layout.setSpacing(14)

    form = QFormLayout()
    form.setSpacing(14)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    # Max history
    dialog._max_history = QSpinBox()
    dialog._max_history.setRange(10, 5000)
    dialog._max_history.setSingleStep(10)
    dialog._max_history.setValue(dialog._settings["max_history"])
    dialog._max_history.setToolTip(
        "Maximum number of clipboard items to keep.\n"
        "Oldest items are trimmed on startup and on capture."
    )
    hist_layout = QHBoxLayout()
    hist_layout.setSpacing(8)
    hist_layout.addWidget(dialog._max_history, stretch=1)
    hist_suffix = QLabel("items")
    hist_suffix.setStyleSheet("color: #8a9296; font-size: 13px;")
    hist_layout.addWidget(hist_suffix)
    form.addRow("Max history:", hist_layout)

    # Max captures
    dialog._max_captures = QSpinBox()
    dialog._max_captures.setRange(10, 2000)
    dialog._max_captures.setSingleStep(10)
    dialog._max_captures.setValue(dialog._settings.get("max_captures", 100))
    dialog._max_captures.setToolTip(
        "Maximum number of saved image/video capture files to keep.\n"
        "Oldest unpinned captures are deleted from disk automatically."
    )
    cap_layout = QHBoxLayout()
    cap_layout.setSpacing(8)
    cap_layout.addWidget(dialog._max_captures, stretch=1)
    cap_suffix = QLabel("files")
    cap_suffix.setStyleSheet("color: #8a9296; font-size: 13px;")
    cap_layout.addWidget(cap_suffix)
    form.addRow("Max captures:", cap_layout)

    # Clear on exit
    dialog._clear_on_exit = QCheckBox("Clear history when app quits")
    dialog._clear_on_exit.setChecked(bool(dialog._settings["clear_on_exit"]))
    dialog._clear_on_exit.setToolTip(
        "Wipes all unpinned items from the database on exit.\n"
        "Pinned items are always preserved."
    )
    form.addRow("Privacy:", dialog._clear_on_exit)

    # Hide window on selection / Enter (Issue #1)
    dialog._hide_on_select = QCheckBox("Hide window on selection / Enter")
    dialog._hide_on_select.setChecked(bool(dialog._settings.get("hide_on_select", False)))
    dialog._hide_on_select.setToolTip(
        "Automatically hides the window back to the background/tray\n"
        "after pressing Enter (or double-clicking) to select/copy a clip.\n"
        "Ideal for keyboard-centric workflows and tiling window managers (i3, Qtile, bspwm)."
    )
    form.addRow("Behavior:", dialog._hide_on_select)

    # Monitor mouse selection (Issue #2)
    dialog._monitor_primary = QCheckBox("Monitor mouse selection (PRIMARY clipboard)")
    dialog._monitor_primary.setChecked(bool(dialog._settings.get("monitor_primary_selection", False)))
    dialog._monitor_primary.setToolTip(
        "Automatically captures text highlighted with the mouse (X11 PRIMARY selection)\n"
        "without needing to press Ctrl+C.\n"
        "Includes smart anti-flood debouncing and drag consolidation."
    )
    form.addRow("Selection:", dialog._monitor_primary)

    # Sync mouse selection to Ctrl+V
    dialog._sync_primary = QCheckBox("Sync mouse selection to Ctrl+V clipboard")
    dialog._sync_primary.setChecked(bool(dialog._settings.get("sync_primary_to_clipboard", True)))
    dialog._sync_primary.setToolTip(
        "Automatically updates the system Ctrl+V clipboard when you select text with the mouse,\n"
        "so pressing Ctrl+V immediately pastes your mouse selection."
    )
    form.addRow("Clipboard:", dialog._sync_primary)

    # Audio feedback
    dialog._custom_sound_path = dialog._settings.get("custom_sound_path", "")
    dialog._capture_sound = QCheckBox("Sound feedback on capture")
    dialog._capture_sound.setChecked(bool(dialog._settings.get("capture_sound_enabled", False)))
    dialog._capture_sound.setToolTip(
        "Plays a quiet, subtle audio pop whenever text or images\n"
        "are captured into the clipboard in the background."
    )

    sound_row = QHBoxLayout()
    sound_row.setSpacing(8)
    form.addRow("Audio:", dialog._capture_sound)

    from core.paths import resource_path
    sound_presets = [
        ("Ghost Pop (Default)", resource_path("data", "assets", "sounds", "ghost_pop.wav")),
        ("Crystal Chime", resource_path("data", "assets", "sounds", "ghost_chime.wav")),
        ("Tactile Click", resource_path("data", "assets", "sounds", "ghost_click.wav")),
        ("Cyber Beam", resource_path("data", "assets", "sounds", "ghost_beam.wav")),
    ]

    sound_combo = QComboBox()
    sound_combo.setFixedHeight(28)
    sound_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    sound_combo.setMinimumContentsLength(18)
    sound_combo.setToolTip("Choose a built-in sound preset or load an external audio file")
    for label, path in sound_presets:
        sound_combo.addItem(f"🎵 {label}", userData=path)
    sound_combo.addItem("📂 Choose Custom File…", userData="__custom__")

    # Match initial selection
    curr_path = dialog._custom_sound_path or resource_path("data", "assets", "sounds", "ghost_pop.wav")
    matched = False
    for i, (_, path) in enumerate(sound_presets):
        if curr_path and os.path.abspath(curr_path) == os.path.abspath(path):
            sound_combo.setCurrentIndex(i)
            matched = True
            break
    if not matched and dialog._custom_sound_path:
        sound_combo.insertItem(len(sound_presets), f"🎵 {os.path.basename(dialog._custom_sound_path)}", userData=dialog._custom_sound_path)
        sound_combo.setCurrentIndex(len(sound_presets))

    def _on_test_sound():
        from core.audio import play_capture_sound
        play_capture_sound(dialog._custom_sound_path or sound_presets[0][1])

    def _restore_sound_selection():
        path = dialog._custom_sound_path or sound_presets[0][1]
        idx = sound_combo.findData(path)
        sound_combo.blockSignals(True)
        sound_combo.setCurrentIndex(idx if idx >= 0 else 0)
        sound_combo.blockSignals(False)

    def _on_sound_combo_changed(idx: int):
        data = sound_combo.itemData(idx)
        if data == "__custom__":
            file_path, _ = QFileDialog.getOpenFileName(
                dialog,
                "Select Capture Sound File",
                "",
                "Audio Files (*.wav *.oga *.ogg *.mp3 *.flac);;All Files (*)",
            )
            if file_path:
                from core.audio import validate_audio_file
                valid, err = validate_audio_file(file_path)
                if not valid:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        dialog,
                        "Invalid Audio File",
                        f"Cannot use this audio file for clipboard feedback:\n\n{err}\n\n"
                        "Please choose a short UI sound effect (under 2 seconds).",
                    )
                    _restore_sound_selection()
                    return

                dialog._custom_sound_path = file_path
                custom_label = f"🎵 {os.path.basename(file_path)}"
                sound_combo.blockSignals(True)
                # Check if custom slot already exists
                if sound_combo.count() > len(sound_presets) + 1:
                    sound_combo.removeItem(len(sound_presets))
                sound_combo.insertItem(len(sound_presets), custom_label, userData=file_path)
                sound_combo.setCurrentIndex(len(sound_presets))
                sound_combo.blockSignals(False)
                _on_test_sound()
            else:
                _restore_sound_selection()
        elif data:
            dialog._custom_sound_path = data
            _on_test_sound()

    sound_combo.currentIndexChanged.connect(_on_sound_combo_changed)

    test_sound_btn = QPushButton("▶ Test")
    test_sound_btn.setFixedHeight(28)
    test_sound_btn.setToolTip("Test play current capture sound")
    test_sound_btn.clicked.connect(_on_test_sound)

    sound_row.addWidget(sound_combo, stretch=1)
    sound_row.addWidget(test_sound_btn)

    form.addRow("Sound:", sound_row)

    # Launch on startup (Autostart)
    from core.autostart import get_autostart_state
    current_autostart = get_autostart_state()
    dialog._autostart_chk = QCheckBox("Launch on system startup (start in tray)")
    dialog._autostart_chk.setChecked(current_autostart.enabled)
    dialog._autostart_chk.setToolTip(
        "Automatically launches DotGhostBoard minimized in the system tray when you log in.\n"
        "Supports all distribution formats (DEB, AppImage, Arch Linux, Portable)."
    )
    dialog._autostart_chk.toggled.connect(dialog._on_autostart_toggled)
    form.addRow("Autostart:", dialog._autostart_chk)

    # Auto Update
    dialog._auto_update = QCheckBox("Check for updates on startup")
    dialog._auto_update.setChecked(bool(dialog._settings.get("auto_update_check", True)))
    dialog._auto_update.setToolTip(
        "Automatically checks GitHub for new releases.\n"
        "If found, a gift icon 🎁 appears in the dashboard."
    )

    # Manual Check for Updates
    dialog._check_update_btn = QPushButton("🔃 Check Now")
    dialog._check_update_btn.setObjectName("CheckUpdateBtn")
    dialog._check_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    dialog._check_update_btn.clicked.connect(dialog._manual_check_update)

    upd_row = QHBoxLayout()
    upd_row.setContentsMargins(0, 0, 0, 0)
    upd_row.addWidget(dialog._auto_update)
    upd_row.addWidget(dialog._check_update_btn)
    upd_row.addStretch()

    form.addRow("Updates:", upd_row)

    # Update Channel selector
    dialog._update_channel = QComboBox()
    dialog._update_channel.setObjectName("UpdateChannelCombo")
    dialog._update_channel.setToolTip(
        "Stable: only tested, production releases.\n"
        "Beta:   includes release candidates and beta builds.\n"
        "Alpha:  includes all pre-release builds (bleeding edge)."
    )
    _channel_items = [
        ("🟢  Stable  (Recommended)", "stable"),
        ("🟡  Beta  (Pre-releases)",  "beta"),
        ("🔴  Alpha  (Bleeding edge)", "alpha"),
    ]
    current_channel = dialog._settings.get("update_channel", "stable")
    for label, value in _channel_items:
        dialog._update_channel.addItem(label, userData=value)
    # Set current index based on stored value
    _channel_values = [v for _, v in _channel_items]
    _channel_idx    = _channel_values.index(current_channel) if current_channel in _channel_values else 0
    dialog._update_channel.setCurrentIndex(_channel_idx)

    form.addRow("Update Channel:", dialog._update_channel)

    dialog._theme = None

    layout.addLayout(form)

    # ── Manage Tags ──
    layout.addWidget(dialog._hsep())

    tags_row = QHBoxLayout()
    tags_lbl = QLabel("Tags:")
    tags_lbl.setStyleSheet("color:#888;")

    manage_tags_btn = QPushButton("🏷  Manage Tags…")
    manage_tags_btn.setObjectName("ManageTagsBtn")
    manage_tags_btn.setToolTip("Rename, delete, or merge tags globally")
    manage_tags_btn.clicked.connect(dialog._open_tag_manager)

    tags_row.addWidget(tags_lbl)
    tags_row.addStretch()
    tags_row.addWidget(manage_tags_btn)
    layout.addLayout(tags_row)

    # ── Hotkey hint & configurator ──
    hint_frame = QFrame()
    hint_frame.setObjectName("HintFrame")
    hint_layout = QVBoxLayout(hint_frame)
    hint_layout.setContentsMargins(12, 10, 12, 10)
    hint_layout.setSpacing(6)

    hint_title = QLabel("Global Hotkeys")
    hint_title.setStyleSheet("color:#6c767d; font-size:11px; font-weight:600;")
    hint_label1 = QLabel("Ctrl + Alt + V       →   Toggle Dashboard (Show/Hide)")
    hint_label1.setStyleSheet("color:#8dd5a2; font-size:12px; font-family:monospace;")
    hint_label2 = QLabel("Ctrl + Alt + Space   →   Spotlight Quick Search")
    hint_label2.setStyleSheet("color:#8dd5a2; font-size:12px; font-family:monospace;")

    btn_row = QHBoxLayout()
    cfg_shortcuts_btn = QPushButton("Configure Global Shortcuts")
    cfg_shortcuts_btn.setObjectName("ConfigShortcutsBtn")
    cfg_shortcuts_btn.setFixedHeight(28)
    cfg_shortcuts_btn.setStyleSheet("""
        QPushButton#ConfigShortcutsBtn {
            background: #18251d;
            color: #77dd98;
            border: 1px solid #31513b;
            border-radius: 6px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton#ConfigShortcutsBtn:hover {
            background: #1f3326;
            color: #92e6ae;
            border: 1px solid #3d694b;
        }
    """)

    shortcut_status = QLabel("")
    shortcut_status.setStyleSheet("color:#8dd5a2; font-size:11px;")

    def _on_configure_shortcuts():
        from core.shortcuts import setup_shortcuts
        ok, msg = setup_shortcuts()
        if ok:
            shortcut_status.setStyleSheet("color:#77dd98; font-size:11px;")
            shortcut_status.setText("✓ Configured")
        else:
            shortcut_status.setStyleSheet("color:#e06c75; font-size:11px;")
            shortcut_status.setText("⚠ Check settings")

    cfg_shortcuts_btn.clicked.connect(_on_configure_shortcuts)
    btn_row.addWidget(cfg_shortcuts_btn)
    btn_row.addWidget(shortcut_status)
    btn_row.addStretch()

    hint_layout.addWidget(hint_title)
    hint_layout.addWidget(hint_label1)
    hint_layout.addWidget(hint_label2)
    hint_layout.addLayout(btn_row)
    layout.addWidget(hint_frame)

    layout.addStretch()
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(tab)
    return scroll
