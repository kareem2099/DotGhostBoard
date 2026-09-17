"""
ui/settings/pages/api.py
─────────────────────────
API & Sync settings tab.

Extracted from ui/settings.py (v1.6.0 Phantom) in v2.0.0 Cerberus.
Contains:
  - build_api_tab(dialog) → QWidget

Depends on dialog helpers:
  dialog._section_label(), dialog._hsep(), dialog._settings

Code is preserved verbatim; only self.X → dialog.X substitution was applied.
"""

from __future__ import annotations
import socket
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QCheckBox, QLabel,
    QPushButton, QLineEdit, QWidget,
)
from PyQt6.QtCore import Qt

if TYPE_CHECKING:
    from ui.settings.dialog import SettingsDialog


def build_api_tab(dialog: "SettingsDialog") -> QWidget:
    """
    Build and return the API/Sync settings tab widget.
    Assigns owned widgets to dialog (dialog.X = widget).
    Calls dialog helpers: dialog._section_label(), dialog._hsep(), dialog._settings.
    """
    from PyQt6.QtWidgets import QApplication

    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(16, 20, 16, 20)
    layout.setSpacing(18)

    layout.addWidget(dialog._section_label("🔌  Local REST API"))

    api_hint = QLabel(
        "Enable a local background server on 127.0.0.1 to access the clipboard "
        "programmatically via the CLI Companion (<code>dotghost push/pop</code>) "
        "or your own scripts."
    )
    api_hint.setWordWrap(True)
    api_hint.setStyleSheet("color:#444; font-size:11px;")
    layout.addWidget(api_hint)

    dialog._api_check = QCheckBox("Enable API Server")
    dialog._api_check.setChecked(bool(dialog._settings.get("api_enabled", False)))
    layout.addWidget(dialog._api_check)

    warn_lbl = QLabel(
        "⚠ Changes to port or enable toggles require an app restart."
    )
    warn_lbl.setStyleSheet("color:#555; font-size:10px;")
    layout.addWidget(warn_lbl)

    form = QFormLayout()
    form.setSpacing(14)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    dialog._api_port = QSpinBox()
    dialog._api_port.setRange(1024, 65535)
    dialog._api_port.setValue(dialog._settings.get("api_port", 9090))
    form.addRow("API Port:", dialog._api_port)

    token_row = QHBoxLayout()
    dialog._api_token_in = QLineEdit()
    dialog._api_token_in.setText(dialog._settings.get("api_token", ""))
    dialog._api_token_in.setEchoMode(QLineEdit.EchoMode.Password)
    dialog._api_token_in.setReadOnly(True)
    dialog._api_token_in.setStyleSheet("font-family: monospace;")

    copy_btn = QPushButton("Copy")
    copy_btn.clicked.connect(
        lambda: QApplication.clipboard().setText(dialog._api_token_in.text())
    )

    show_btn = QPushButton("👁")
    show_btn.setFixedWidth(30)
    show_btn.setCheckable(True)

    def toggle_pw(checked):
        dialog._api_token_in.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    show_btn.toggled.connect(toggle_pw)

    token_row.addWidget(dialog._api_token_in)
    token_row.addWidget(show_btn)
    token_row.addWidget(copy_btn)
    form.addRow("API Token:", token_row)

    form.addRow(dialog._hsep())

    # Sync / Discovery
    dialog._device_name = QLineEdit()
    dialog._device_name.setText(
        dialog._settings.get("device_name", socket.gethostname())
    )
    dialog._device_name.setPlaceholderText("Name displayed to other devices")
    form.addRow("Device Name:", dialog._device_name)

    node_id_lbl = QLabel(
        f"Node ID:  {dialog._settings.get('node_id', 'unknown')}"
    )
    node_id_lbl.setStyleSheet(
        "color:#444; font-size:10px; font-family:monospace;"
    )
    form.addRow("", node_id_lbl)

    layout.addLayout(form)
    layout.addStretch()
    return tab
