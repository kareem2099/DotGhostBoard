"""
ui/settings/dialog.py
──────────────────────
SettingsDialog orchestrator shell.

v2.0.0 Cerberus — Phase 5 Settings Decomposition.

All tab-building logic lives in ui/settings/pages/*.
All I/O logic lives in ui/settings/_io.py.
Password management lives in ui/settings/pages/security.py.

This file wires the package together and owns only:
  - __init__ + _build_ui
  - shared widget helpers (_section_label, _hsep, _open_tag_manager)
  - general helpers (_manual_check_update, _on_autostart_toggled)
  - _save_and_close + settings property
"""

import socket

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSizePolicy,
    QTabWidget, QMessageBox,
)
from PyQt6.QtCore import Qt

from ui.settings._io import load_settings, save_settings
from ui.settings.pages.general import build_general_tab
from ui.settings.pages.security import build_security_tab
from ui.settings.pages.api import build_api_tab
from ui.settings.pages.about import build_about_tab


class SettingsDialog(QDialog):
    """
    Modal settings dialog with four tabs:
      • General  — history limits, theme, autostart, updates, tag manager
      • Eclipse  — master password, auto-lock, stealth, app filter
      • API      — local REST API and device identity
      • About    — app, author, license, system and project information
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
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

        title = QLabel("⚙  Settings")
        title.setObjectName("SettingsTitle")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#e2e5e6;")
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#222;")
        root.addWidget(sep)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("SettingsTabs")
        self._tabs.addTab(build_general_tab(self),  "General")
        self._tabs.addTab(build_security_tab(self), "🔐  Eclipse")
        self._tabs.addTab(build_api_tab(self),      "🌐  API")
        self._tabs.addTab(build_about_tab(self),    "👻  About")
        root.addWidget(self._tabs)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SettingsCancelBtn")
        cancel_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("SettingsSaveBtn")
        save_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_and_close)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    # ── Shared widget helpers (called by page builders via dialog._X()) ───────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#72d991; font-size:13px; font-weight:bold; padding-bottom:2px;"
        )
        return lbl

    @staticmethod
    def _hsep() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#1e1e1e; margin: 2px 0;")
        return sep

    def _open_tag_manager(self):
        from ui.tag_manager import TagManagerDialog
        TagManagerDialog(self).exec()

    # ── General-tab helpers (called via dialog._X() from general.py) ─────────

    def _manual_check_update(self):
        from PyQt6.QtWidgets import QApplication
        main_dashboard = QApplication.instance().property("main_dashboard")
        if main_dashboard:
            main_dashboard.check_for_updates()
            QMessageBox.information(
                self, "Update Check",
                "Checking for updates in the background...\n"
                "If an update is found, a gift icon 🎁 will appear in the dashboard top bar."
            )

    def _on_autostart_toggled(self, checked: bool):
        from core.autostart import enable_autostart, disable_autostart
        res = enable_autostart() if checked else disable_autostart()

        if checked and not res.enabled:
            QMessageBox.warning(
                self, "Autostart Error",
                f"Could not enable autostart:\n{res.message}"
            )
            self._autostart_chk.blockSignals(True)
            self._autostart_chk.setChecked(False)
            self._autostart_chk.blockSignals(False)
        elif not checked and res.enabled:
            QMessageBox.warning(
                self, "Autostart Error",
                f"Could not disable autostart:\n{res.message}"
            )
            self._autostart_chk.blockSignals(True)
            self._autostart_chk.setChecked(True)
            self._autostart_chk.blockSignals(False)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save_and_close(self):
        # General
        self._settings["max_history"]       = self._max_history.value()
        self._settings["max_captures"]      = self._max_captures.value()
        self._settings["clear_on_exit"]     = self._clear_on_exit.isChecked()
        self._settings["theme"]             = "dark"
        self._settings["auto_update_check"] = self._auto_update.isChecked()
        self._settings["update_channel"]    = self._update_channel.currentData()

        # Eclipse
        self._settings["auto_lock_minutes"] = self._auto_lock_spin.value()
        self._settings["stealth_mode"]      = self._stealth_check.isChecked()
        self._settings["app_filter_mode"]   = self._app_filter_editor.get_mode()
        self._settings["app_filter_list"]   = self._app_filter_editor.get_app_list()

        # API / Network
        self._settings["api_enabled"]  = self._api_check.isChecked()
        self._settings["api_port"]     = self._api_port.value()
        self._settings["device_name"]  = (
            self._device_name.text().strip() or socket.gethostname()
        )

        save_settings(self._settings)
        self.accept()

    @property
    def settings(self) -> dict:
        """Returns the last saved settings dict (after accept())."""
        return self._settings
