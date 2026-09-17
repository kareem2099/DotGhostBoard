"""
ui/settings/pages/security.py
──────────────────────────────
Eclipse / Security settings tab + password management helpers.

Extracted from ui/settings.py (v1.6.0 Phantom) in v2.0.0 Cerberus.
Contains:
  - setup_master_password(dialog)   — standalone, was dialog._setup_master_password
  - remove_master_password(dialog)  — standalone, was dialog._remove_master_password
  - refresh_eclipse_pw_ui(dialog)   — standalone, was dialog._refresh_eclipse_pw_ui
  - build_security_tab(dialog) → QWidget

Depends on dialog attributes:
  dialog._section_label(), dialog._hsep(), dialog._settings

All password helpers take `dialog` as their only parameter and access
its owned widgets (dialog._pw_status_lbl, dialog._set_pw_btn, etc.)
which are assigned by build_security_tab before any button is pressed.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QCheckBox, QLabel,
    QPushButton, QFrame, QScrollArea, QWidget,
    QInputDialog, QLineEdit, QMessageBox,
)
from PyQt6.QtCore import Qt

from ui.settings.pages.general import AppFilterEditor

if TYPE_CHECKING:
    from ui.settings.dialog import SettingsDialog


# ══════════════════════════════════════════════════════════════
# Password Management Helpers
# (were SettingsDialog methods; now standalone to keep dialog.py thin)
# ══════════════════════════════════════════════════════════════

def setup_master_password(dialog: "SettingsDialog") -> None:
    """Set or change the master password. Verifies old password first if one exists."""
    from core.crypto import (
        has_master_password,
        save_master_password,
        verify_password,
    )

    had_pw = has_master_password()

    # Verify current password before allowing a change
    if had_pw:
        old_pw, ok = QInputDialog.getText(
            dialog, "Verify Current Password",
            "Enter your current master password:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        if not verify_password(old_pw):
            QMessageBox.warning(
                dialog, "Wrong Password",
                "Current password is incorrect."
            )
            return

    # Get new password
    new_pw, ok = QInputDialog.getText(
        dialog, "Set Master Password",
        "New master password  (minimum 6 characters):",
        QLineEdit.EchoMode.Password,
    )
    if not ok or not new_pw.strip():
        return

    # Confirm
    confirm, ok = QInputDialog.getText(
        dialog, "Confirm Password",
        "Confirm new master password:",
        QLineEdit.EchoMode.Password,
    )
    if not ok:
        return
    if new_pw != confirm:
        QMessageBox.warning(dialog, "Mismatch", "Passwords do not match.")
        return

    try:
        save_master_password(new_pw)
    except ValueError as exc:
        QMessageBox.warning(dialog, "Invalid Password", str(exc))
        return

    QMessageBox.information(
        dialog, "Password Set",
        "Master password set successfully.\n\n"
        "To encrypt an item, right-click its card and choose\n"
        "\U0001f510 Mark as Secret."
    )
    refresh_eclipse_pw_ui(dialog)


def remove_master_password(dialog: "SettingsDialog") -> None:
    """Decrypt all secret items and remove the master password."""
    from core.crypto import verify_password, remove_master_password as _rm, derive_key
    import core.storage as storage

    pw, ok = QInputDialog.getText(
        dialog, "Confirm Removal",
        "Enter your master password to remove it:",
        QLineEdit.EchoMode.Password,
    )
    if not ok or not pw.strip():
        return
    if not verify_password(pw):
        QMessageBox.warning(
            dialog, "Wrong Password", "Master password is incorrect."
        )
        return

    # Decrypt all secret items before removing the key
    key   = derive_key(pw)
    count = storage.decrypt_all_secret_items(key)
    if count == -1:
        QMessageBox.critical(
            dialog, "Decryption Failed",
            "Could not decrypt one or more items.\n"
            "Master password was NOT removed."
        )
        return

    _rm()
    dialog._settings["master_lock_enabled"] = False
    dialog._settings["auto_lock_minutes"]   = 0
    dialog._auto_lock_spin.setValue(0)

    QMessageBox.information(
        dialog, "Password Removed",
        f"Master password removed.\n{count} item(s) decrypted."
    )
    refresh_eclipse_pw_ui(dialog)


def refresh_eclipse_pw_ui(dialog: "SettingsDialog") -> None:
    """Sync password-related widgets to current on-disk state."""
    from core.crypto import has_master_password
    has_pw = has_master_password()
    dialog._pw_status_lbl.setText(
        "\u2705  Master password is SET" if has_pw
        else "\u26aa  No master password configured"
    )
    dialog._pw_status_lbl.setStyleSheet(
        "color:#71c98d;" if has_pw else "color:#555;"
    )
    dialog._set_pw_btn.setText(
        "\U0001f511  Change Password\u2026" if has_pw else "\U0001f511  Set Password\u2026"
    )
    dialog._rm_pw_btn.setEnabled(has_pw)


# ══════════════════════════════════════════════════════════════
# Security Tab Builder
# ══════════════════════════════════════════════════════════════

def build_security_tab(dialog: "SettingsDialog") -> QWidget:
    """
    Build and return the Eclipse/Security settings tab widget.
    Assigns owned widgets to dialog (dialog.X = widget).
    Calls dialog helpers: dialog._section_label(), dialog._hsep(), dialog._settings.
    Password actions are wired to standalone functions in this module.
    """
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

    # \u2500\u2500 Master Password \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    layout.addWidget(dialog._section_label("\U0001f511  Master Password"))

    has_pw = has_master_password()
    dialog._pw_status_lbl = QLabel(
        "\u2705  Master password is SET" if has_pw
        else "\u26aa  No master password configured"
    )
    dialog._pw_status_lbl.setStyleSheet(
        "color:#71c98d;" if has_pw else "color:#555;"
    )
    layout.addWidget(dialog._pw_status_lbl)

    pw_hint = QLabel(
        "When set, the app will show a lock screen on startup and "
        "allow you to lock/unlock from the \U0001f512 button or tray menu."
    )
    pw_hint.setWordWrap(True)
    pw_hint.setStyleSheet("color:#444; font-size:11px;")
    layout.addWidget(pw_hint)

    pw_btn_row = QHBoxLayout()
    pw_btn_row.setSpacing(8)

    dialog._set_pw_btn = QPushButton(
        "\U0001f511  Change Password\u2026" if has_pw else "\U0001f511  Set Password\u2026"
    )
    dialog._set_pw_btn.setObjectName("EclipseBtn")
    dialog._set_pw_btn.clicked.connect(
        lambda: setup_master_password(dialog)
    )

    dialog._rm_pw_btn = QPushButton("\u2715  Remove Password\u2026")
    dialog._rm_pw_btn.setObjectName("EclipseBtnDanger")
    dialog._rm_pw_btn.setToolTip(
        "Remove the master password.\n"
        "\u26a0 All encrypted items will be permanently decrypted first."
    )
    dialog._rm_pw_btn.setEnabled(has_pw)
    dialog._rm_pw_btn.clicked.connect(
        lambda: remove_master_password(dialog)
    )

    pw_btn_row.addWidget(dialog._set_pw_btn)
    pw_btn_row.addWidget(dialog._rm_pw_btn)
    pw_btn_row.addStretch()
    layout.addLayout(pw_btn_row)

    layout.addWidget(dialog._hsep())

    # \u2500\u2500 Auto-lock \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    layout.addWidget(dialog._section_label("\u23f1  Auto-Lock"))

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

    dialog._auto_lock_spin = QSpinBox()
    dialog._auto_lock_spin.setRange(0, 480)
    dialog._auto_lock_spin.setSingleStep(5)
    dialog._auto_lock_spin.setSuffix("  min  (0 = disabled)")
    dialog._auto_lock_spin.setValue(
        dialog._settings.get("auto_lock_minutes", 0)
    )
    lock_form.addRow("Lock after:", dialog._auto_lock_spin)
    layout.addLayout(lock_form)

    layout.addWidget(dialog._hsep())

    # \u2500\u2500 Stealth Mode \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    layout.addWidget(dialog._section_label("\U0001f441  Stealth Mode"))

    dialog._stealth_check = QCheckBox(
        "Hide window from taskbar and Alt+Tab switcher"
    )
    dialog._stealth_check.setChecked(
        bool(dialog._settings.get("stealth_mode", False))
    )
    dialog._stealth_check.setToolTip(
        "Window remains accessible via the tray icon and global hotkey.\n"
        "Uses Qt Tool window flag + _NET_WM_STATE X11 hints."
    )
    layout.addWidget(dialog._stealth_check)

    stealth_warn = QLabel(
        "\u26a0  Changes apply immediately on Save. "
        "If window was already open, it will re-show with new flags."
    )
    stealth_warn.setWordWrap(True)
    stealth_warn.setStyleSheet("color:#555; font-size:11px;")
    layout.addWidget(stealth_warn)

    layout.addWidget(dialog._hsep())

    # \u2500\u2500 App Filter \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    layout.addWidget(dialog._section_label("\U0001f6e1  App Filter"))

    filter_hint = QLabel(
        "Control which applications DotGhostBoard monitors. "
        "Useful to exclude password managers or banking apps."
    )
    filter_hint.setWordWrap(True)
    filter_hint.setStyleSheet("color:#444; font-size:11px;")
    layout.addWidget(filter_hint)

    dialog._app_filter_editor = AppFilterEditor(
        mode=dialog._settings.get("app_filter_mode", "blacklist"),
        app_list=dialog._settings.get("app_filter_list", []),
    )
    layout.addWidget(dialog._app_filter_editor)

    layout.addStretch()
    scroll.setWidget(inner)
    return scroll
