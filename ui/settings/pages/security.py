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
    QComboBox, QCheckBox, QLabel,
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

def _service(dialog):
    parent = dialog.parent() if hasattr(dialog, "parent") else None
    service = getattr(parent, "security_service", None)
    if service is None:
        from core.services import SecurityService
        service = getattr(dialog, "_password_service", None) or SecurityService()
    dialog._password_service = service
    return service


def _password(dialog, title, prompt):
    return QInputDialog.getText(dialog, title, prompt, QLineEdit.EchoMode.Password)


def _sync_session(dialog):
    parent = dialog.parent()
    if parent and hasattr(parent, "security_controller"):
        parent.security_controller.set_active_key(_service(dialog).active_key)
        parent.topbar.set_lock_visible(_service(dialog).has_master_password())
    refresh_eclipse_pw_ui(dialog)
    _refresh_vault_password_ui(dialog)


def setup_master_password(dialog):
    """Route every settings action through the coordinator, never raw verifier writes."""
    service = _service(dialog)
    old_password = None
    if service.has_master_password():
        old_password, ok = _password(dialog, "Current Dashboard Password", "Current Dashboard password:")
        if not ok:
            return
        if not service.verify_master_password(old_password):
            QMessageBox.warning(dialog, "Wrong Password", "Current Dashboard password is incorrect.")
            return
    new_password, ok = _password(dialog, "Dashboard Password", "New Dashboard password (at least 12 characters):")
    if not ok:
        return
    confirm, ok = _password(dialog, "Confirm Password", "Confirm new Dashboard password:")
    if not ok:
        return
    if new_password != confirm:
        QMessageBox.warning(dialog, "Mismatch", "Passwords do not match.")
        return
    try:
        if old_password is None:
            service.setup_master_password(new_password)
        else:
            success, message = service.change_master_password(old_password, new_password)
            if not success:
                raise ValueError(message)
    except Exception as exc:
        QMessageBox.warning(dialog, "Password Not Changed", str(exc))
        return
    _sync_session(dialog)
    QMessageBox.information(dialog, "Password Updated", "Dashboard password updated. Your encrypted data was preserved.")


def remove_master_password(dialog):
    service = _service(dialog)
    password, ok = _password(dialog, "Remove Dashboard Password", "Current Dashboard password:")
    if not ok:
        return
    success, count, message = service.remove_master_password(password)
    if not success:
        QMessageBox.warning(dialog, "Password Not Removed", message)
        return
    dialog._settings["master_lock_enabled"] = False
    dialog._settings["auto_lock_minutes"] = 0
    dialog._auto_lock_combo.setCurrentIndex(dialog._auto_lock_combo.findData(0))
    _sync_session(dialog)
    QMessageBox.information(dialog, "Password Removed", message)


def _refresh_vault_password_ui(dialog):
    independent = _service(dialog).vault.independent_password
    dialog._independent_vault_check.blockSignals(True)
    dialog._independent_vault_check.setChecked(independent)
    dialog._independent_vault_check.blockSignals(False)
    dialog._independent_vault_check.setEnabled(_service(dialog).has_master_password())
    dialog._change_vault_password_btn.setEnabled(independent)


def configure_vault_password(dialog, independent):
    service = _service(dialog)
    try:
        dashboard_password, ok = _password(dialog, "Confirm Dashboard Password", "Current Dashboard password:")
        if not ok:
            return
        if not service.verify_master_password(dashboard_password):
            raise ValueError("Incorrect Dashboard password.")
        current_vault = None
        if service.vault.independent_password:
            current_vault, ok = _password(dialog, "Current Vault Password", "Current independent Vault password:")
            if not ok:
                return
        new_vault = None
        if independent:
            new_vault, ok = _password(dialog, "Independent Vault Password", "New Vault password (at least 12 characters; different from Dashboard):")
            if not ok:
                return
            confirm, ok = _password(dialog, "Confirm Vault Password", "Confirm the new Vault password:")
            if not ok:
                return
            if new_vault != confirm:
                raise ValueError("Vault passwords do not match.")
        service.vault.configure_password(dashboard_password, new_vault, current_vault)
        parent = dialog.parent()
        if parent and hasattr(parent, "vault_controller"):
            parent.vault_controller.on_session_unlocked()
        QMessageBox.information(dialog, "Vault Password Updated", "Vault password settings updated. Your secrets were preserved.")
    except Exception as exc:
        QMessageBox.warning(dialog, "Vault Password Not Changed", str(exc))
    finally:
        parent = dialog.parent()
        if parent and hasattr(parent, "vault_controller") and not service.vault.is_unlocked:
            parent.vault_controller.lock()
        _refresh_vault_password_ui(dialog)


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
        "allow you to lock/unlock from the 🔒 button or tray menu.\n"
        "🛡️ By default, your Master Password also unlocks The Vault. You can choose an independent Vault password below. "
        "You can export an offline encrypted backup (.vault) from The Vault drawer."
    )
    pw_hint.setWordWrap(True)
    pw_hint.setStyleSheet("color:#626a70; font-size:11px;")
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
        "The Vault must be empty. Encrypted Dashboard items will be decrypted first."
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

    layout.addWidget(dialog._section_label("🛡️  Vault Password"))
    dialog._independent_vault_check = QCheckBox("Use a separate password for The Vault")
    dialog._independent_vault_check.setObjectName("IndependentVaultPassword")
    layout.addWidget(dialog._independent_vault_check)
    vault_hint = QLabel(
        "Off by default: Dashboard and Vault share one password. With a separate password, "
        "sign in to Dashboard, then unlock the Vault before capture starts. "
        "Password changes apply immediately; Cancel does not undo them."
    )
    vault_hint.setWordWrap(True)
    vault_hint.setStyleSheet("color:#8a9296; font-size:11px;")
    layout.addWidget(vault_hint)
    dialog._change_vault_password_btn = QPushButton("Change Vault Password…")
    dialog._change_vault_password_btn.setObjectName("EclipseBtn")
    layout.addWidget(dialog._change_vault_password_btn)
    _refresh_vault_password_ui(dialog)
    dialog._independent_vault_check.toggled.connect(lambda enabled: configure_vault_password(dialog, enabled))
    dialog._change_vault_password_btn.clicked.connect(lambda: configure_vault_password(dialog, True))
    layout.addWidget(dialog._hsep())

    # \u2500\u2500 Auto-lock \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    layout.addWidget(dialog._section_label("\u23f1  Dashboard Auto-Lock"))

    lock_hint = QLabel(
        "Disabled by default. Optionally lock the whole app after inactivity. "
        "Requires a Master Password. The Vault keeps its separate idle lock."
    )
    lock_hint.setWordWrap(True)
    lock_hint.setStyleSheet("color:#8a9296; font-size:11px;")
    layout.addWidget(lock_hint)

    lock_form = QFormLayout()
    lock_form.setSpacing(10)
    lock_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    dialog._auto_lock_combo = QComboBox()
    for label, minutes in [("Disabled (default)", 0), ("5 minutes", 5),
                           ("30 minutes", 30), ("1 hour", 60)]:
        dialog._auto_lock_combo.addItem(label, minutes)
    try:
        saved_minutes = max(0, int(dialog._settings.get("auto_lock_minutes", 0)))
    except (TypeError, ValueError):
        saved_minutes = 0
    if dialog._auto_lock_combo.findData(saved_minutes) < 0:
        # Preserve an explicitly chosen timeout from older versions on Save.
        dialog._auto_lock_combo.addItem(f"{saved_minutes} minutes (saved setting)", saved_minutes)
    dialog._auto_lock_combo.setCurrentIndex(dialog._auto_lock_combo.findData(saved_minutes))
    lock_form.addRow("Lock after inactivity:", dialog._auto_lock_combo)
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

    # ── Zero-Log Password Protection ──────────────────────────────────────────────
    layout.addWidget(dialog._section_label("🛡️  Zero-Log Password Protection"))

    dialog._detect_passwords_check = QCheckBox(
        "Intercept passwords & tokens before history (Requires Master Password)"
    )
    dialog._detect_passwords_check.setChecked(
        bool(dialog._settings.get("detect_passwords", True))
    )
    dialog._detect_passwords_check.setToolTip(
        "Automatically detect passwords, API keys, and sensitive tokens.\n"
        "Prevents them from appearing on the public history board,\n"
        "prompting to save to The Vault or keep."
    )
    layout.addWidget(dialog._detect_passwords_check)

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
