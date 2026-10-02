"""
ui/vault/secret_dialog.py
─────────────────────────
Modal dialog to create or edit an encrypted secret item in The Vault.
Includes an auto-generate panel for strong passwords and API tokens.

v2.0.0 Cerberus — Phase 7 Vault UI Subsystem.
"""

from __future__ import annotations

import os
import math
import secrets
import string
import uuid
import base64
from typing import Optional

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ─────────────────────────────────────────────────────────────
#  Generator helpers
# ─────────────────────────────────────────────────────────────

def _generate_password(
    length: int = 20,
    upper: bool = True,
    lower: bool = True,
    digits: bool = True,
    symbols: bool = True,
) -> str:
    """Generate a cryptographically-strong random password."""
    pool = ""
    required: list[str] = []
    if upper:
        pool += string.ascii_uppercase
        required.append(secrets.choice(string.ascii_uppercase))
    if lower:
        pool += string.ascii_lowercase
        required.append(secrets.choice(string.ascii_lowercase))
    if digits:
        pool += string.digits
        required.append(secrets.choice(string.digits))
    if symbols:
        syms = "!@#$%^&*()-_=+[]{}|;:,.<>?"
        pool += syms
        required.append(secrets.choice(syms))

    if not pool:
        pool = string.ascii_letters + string.digits  # safe fallback

    rest_len = max(0, length - len(required))
    rest = [secrets.choice(pool) for _ in range(rest_len)]
    combined = required + rest
    # Shuffle using secrets-based index swap (Fisher-Yates)
    for i in range(len(combined) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        combined[i], combined[j] = combined[j], combined[i]
    return "".join(combined)


def _generate_token(fmt: str, length: int = 32) -> str:
    """Generate a random token in the requested format."""
    if fmt == "hex":
        return secrets.token_hex(length // 2)
    if fmt == "uuid4":
        return str(uuid.uuid4())
    if fmt == "base64":
        return base64.urlsafe_b64encode(secrets.token_bytes(length)).rstrip(b"=").decode()
    if fmt == "bearer":
        return "Bearer " + secrets.token_urlsafe(length)
    return secrets.token_urlsafe(length)


def _entropy_bits(password: str) -> float:
    """Estimate Shannon-style entropy: log2(pool_size) * length."""
    if not password:
        return 0.0
    pool = 0
    has_lower = any(c in string.ascii_lowercase for c in password)
    has_upper = any(c in string.ascii_uppercase for c in password)
    has_digit = any(c in string.digits for c in password)
    has_symbol = any(c not in string.ascii_letters + string.digits for c in password)
    if has_lower:
        pool += 26
    if has_upper:
        pool += 26
    if has_digit:
        pool += 10
    if has_symbol:
        pool += 32
    if pool == 0:
        pool = 26
    return math.log2(pool) * len(password)


class SecretData(tuple):
    """
    Subclass of tuple (title, payload, category) to preserve 3-element unpack
    backward compatibility while providing an .expires_at attribute.
    """

    def __new__(
        cls,
        title: str,
        payload: Optional[str],
        category: str,
        expires_at: Optional[str] = None,
    ):
        return super().__new__(cls, (title, payload, category))

    def __init__(
        self,
        title: str,
        payload: Optional[str],
        category: str,
        expires_at: Optional[str] = None,
    ):
        self.expires_at = expires_at


# ─────────────────────────────────────────────────────────────
#  Dialog
# ─────────────────────────────────────────────────────────────

class SecretDialog(QDialog):
    """
    Dialog for adding or editing a secret item.
    Includes an inline auto-generate panel for passwords and API tokens.
    """

    CATEGORIES = [
        ("generic", "🛡️ Generic"),
        ("password", "🔑 Password"),
        ("token", "🪙 API Token"),
        ("key", "🔐 Private Key"),
        ("note", "📜 Secure Note"),
    ]

    def __init__(
        self,
        title: str = "",
        category: str = "generic",
        item_id: Optional[int] = None,
        secret_payload: str = "",
        expires_at: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._item_id = item_id
        self._is_edit = item_id is not None
        self._initial_expires_at = expires_at

        self.setObjectName("SecretDialog")
        self.setWindowTitle("Edit Secret" if self._is_edit else "Add New Secret")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setMinimumWidth(460)

        self._build_ui(title, category, secret_payload)
        self._apply_style()
        self.adjustSize()

    # ─── UI construction ─────────────────────────────────────

    def _build_ui(self, title: str, category: str, secret_payload: str = "") -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        # Header
        header_text = "✏️  Edit Secret" if self._is_edit else "🛡️  Add New Secret"
        header = QLabel(header_text)
        header.setObjectName("SecretDialogTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("SecretDialogDivider")

        # Title input
        title_label = QLabel("Title")
        title_label.setObjectName("SecretFieldLabel")
        self.title_input = QLineEdit()
        self.title_input.setText(title)
        self.title_input.setPlaceholderText("e.g. AWS Production Token, GitHub Personal Token…")
        self.title_input.setObjectName("SecretInput")
        self.title_input.setFixedHeight(36)

        # Category dropdown
        cat_label = QLabel("Category")
        cat_label.setObjectName("SecretFieldLabel")
        self.cat_combo = QComboBox()
        self.cat_combo.setObjectName("SecretCombo")
        self.cat_combo.setFixedHeight(36)
        for cat_id, cat_name in self.CATEGORIES:
            self.cat_combo.addItem(cat_name, cat_id)
        idx = self.cat_combo.findData(category.lower())
        if idx >= 0:
            self.cat_combo.setCurrentIndex(idx)

        # ── Secret payload row (label + generate toggle) ──
        payload_row = QHBoxLayout()
        payload_row.setContentsMargins(0, 0, 0, 0)
        secret_label = QLabel("Secret Payload (Encrypted)")
        secret_label.setObjectName("SecretFieldLabel")
        payload_row.addWidget(secret_label)
        payload_row.addStretch()

        self._gen_toggle_btn = QPushButton("⚡ Generate")
        self._gen_toggle_btn.setObjectName("GenToggleBtn")
        self._gen_toggle_btn.setFixedHeight(26)
        self._gen_toggle_btn.setCheckable(True)
        self._gen_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gen_toggle_btn.clicked.connect(self._toggle_gen_panel)
        payload_row.addWidget(self._gen_toggle_btn)

        # Secret text area
        self.secret_input = QTextEdit()
        self.secret_input.setObjectName("SecretTextEdit")
        self.secret_input.setMaximumHeight(90)
        if self._is_edit:
            self.secret_input.setPlaceholderText("Leave empty to keep existing secret unchanged…")
        else:
            self.secret_input.setPlaceholderText("Enter sensitive secret text, token, key, or password…")
        if secret_payload:
            self.secret_input.setPlainText(secret_payload)
            self.title_input.setFocus()
        self.secret_input.textChanged.connect(self._update_strength_bar)

        # ── Strength bar & rating ──
        self._strength_bar = QFrame()
        self._strength_bar.setObjectName("StrengthBar")
        self._strength_bar.setFixedHeight(4)
        self._strength_bar.setMaximumWidth(0)
        self._strength_bar.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._strength_lbl = QLabel("")
        self._strength_lbl.setObjectName("SecretStrengthLabel")
        self._strength_lbl.setToolTip("Password entropy score based on length and character space")

        strength_wrap = QFrame()
        strength_wrap.setObjectName("StrengthWrap")
        strength_wrap.setFixedHeight(18)
        sw_lay = QHBoxLayout(strength_wrap)
        sw_lay.setContentsMargins(0, 0, 0, 0)
        sw_lay.setSpacing(8)
        sw_lay.addWidget(self._strength_bar)
        sw_lay.addWidget(self._strength_lbl)
        sw_lay.addStretch()

        # ── Generate panel (hidden by default) ──
        self._gen_panel = QFrame()
        self._gen_panel.setObjectName("GenPanel")
        self._gen_panel.setVisible(False)
        gen_layout = QVBoxLayout(self._gen_panel)
        gen_layout.setContentsMargins(12, 10, 12, 10)
        gen_layout.setSpacing(8)

        # Mode selector: Password vs Token
        mode_row = QHBoxLayout()
        mode_lbl = QLabel("Mode:")
        mode_lbl.setObjectName("GenLabel")
        self._mode_combo = QComboBox()
        self._mode_combo.setObjectName("GenCombo")
        self._mode_combo.setFixedHeight(28)
        self._mode_combo.addItem("🔑 Password", "password")
        self._mode_combo.addItem("🪙 Token / API Key", "token")
        self._mode_combo.setToolTip("Select generator mode: secure password or random cryptographic token")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(mode_lbl)
        mode_row.addWidget(self._mode_combo, 1)
        gen_layout.addLayout(mode_row)

        # ── Password options ──
        self._pw_options = QWidget()
        pw_lay = QVBoxLayout(self._pw_options)
        pw_lay.setContentsMargins(0, 0, 0, 0)
        pw_lay.setSpacing(6)

        # Length slider
        len_row = QHBoxLayout()
        len_lbl = QLabel("Length:")
        len_lbl.setObjectName("GenLabel")
        self._len_slider = QSlider(Qt.Orientation.Horizontal)
        self._len_slider.setMinimum(8)
        self._len_slider.setMaximum(64)
        self._len_slider.setValue(20)
        self._len_slider.setObjectName("GenSlider")
        self._len_slider.setToolTip("Password length (8 to 64 characters)")
        self._len_value_lbl = QLabel("20")
        self._len_value_lbl.setObjectName("GenLabel")
        self._len_value_lbl.setFixedWidth(24)
        self._len_slider.valueChanged.connect(
            lambda v: self._len_value_lbl.setText(str(v))
        )
        len_row.addWidget(len_lbl)
        len_row.addWidget(self._len_slider, 1)
        len_row.addWidget(self._len_value_lbl)
        pw_lay.addLayout(len_row)

        # Charset toggles
        charset_row = QHBoxLayout()
        self._chk_upper = QCheckBox("A–Z")
        self._chk_upper.setToolTip("Include uppercase letters (A–Z)")
        self._chk_lower = QCheckBox("a–z")
        self._chk_lower.setToolTip("Include lowercase letters (a–z)")
        self._chk_digits = QCheckBox("0–9")
        self._chk_digits.setToolTip("Include numeric digits (0–9)")
        self._chk_symbols = QCheckBox("!@#…")
        self._chk_symbols.setToolTip("Include special symbols (!@#$%^&*...)")
        for chk in (self._chk_upper, self._chk_lower, self._chk_digits, self._chk_symbols):
            chk.setChecked(True)
            chk.setObjectName("GenCheck")
            charset_row.addWidget(chk)
        charset_row.addStretch()
        pw_lay.addLayout(charset_row)

        gen_layout.addWidget(self._pw_options)

        # ── Token options ──
        self._tok_options = QWidget()
        self._tok_options.setVisible(False)
        tok_lay = QHBoxLayout(self._tok_options)
        tok_lay.setContentsMargins(0, 0, 0, 0)
        tok_lay.setSpacing(8)
        tok_fmt_lbl = QLabel("Format:")
        tok_fmt_lbl.setObjectName("GenLabel")
        self._tok_combo = QComboBox()
        self._tok_combo.setObjectName("GenCombo")
        self._tok_combo.setFixedHeight(28)
        self._tok_combo.addItem("Hex (64 chars)", "hex")
        self._tok_combo.addItem("UUID v4", "uuid4")
        self._tok_combo.addItem("Base64-URL (43 ch)", "base64")
        self._tok_combo.addItem("Bearer Token", "bearer")
        self._tok_combo.setToolTip("Select format for cryptographic token or API key")
        tok_lay.addWidget(tok_fmt_lbl)
        tok_lay.addWidget(self._tok_combo, 1)
        gen_layout.addWidget(self._tok_options)

        # Generate button
        do_gen_btn = QPushButton("⚡ Generate & Fill")
        do_gen_btn.setObjectName("DoGenBtn")
        do_gen_btn.setFixedHeight(32)
        do_gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        do_gen_btn.setToolTip("Generate cryptographically secure value and insert into secret field")
        do_gen_btn.clicked.connect(self._do_generate)
        gen_layout.addWidget(do_gen_btn)

        # Error label
        self.error_lbl = QLabel("")
        self.error_lbl.setObjectName("SecretDialogError")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecretCancelBtn")
        self.cancel_btn.setFixedHeight(36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setToolTip("Discard changes and close (Esc)")
        self.cancel_btn.clicked.connect(self.reject)

        save_label = "Update Secret" if self._is_edit else "Save to Vault"
        self.save_btn = QPushButton(f"🔐 {save_label}")
        self.save_btn.setObjectName("SecretSaveBtn")
        self.save_btn.setFixedHeight(36)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setToolTip("Encrypt and commit changes to The Vault")
        self.save_btn.clicked.connect(self._on_save)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)

        # ── Expiration Row ──
        exp_row = QHBoxLayout()
        exp_row.setContentsMargins(0, 0, 0, 0)
        exp_row.setSpacing(8)

        self._exp_check = QCheckBox("Set Expiration Date")
        self._exp_check.setObjectName("GenCheck")
        self._exp_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exp_check.setToolTip(
            "Track expiration for temporary API tokens or credentials.\n"
            "Status badges will alert you as the secret nears expiration."
        )
        exp_row.addWidget(self._exp_check)
        exp_row.addStretch()

        self._exp_container = QWidget()
        exp_c_layout = QVBoxLayout(self._exp_container)
        exp_c_layout.setContentsMargins(0, 0, 0, 0)
        exp_c_layout.setSpacing(4)

        inputs_row = QHBoxLayout()
        inputs_row.setContentsMargins(0, 0, 0, 0)
        inputs_row.setSpacing(6)

        self._exp_preset_combo = QComboBox()
        self._exp_preset_combo.setObjectName("GenCombo")
        self._exp_preset_combo.setFixedHeight(28)
        self._exp_preset_combo.addItem("30 Days", 30)
        self._exp_preset_combo.addItem("90 Days", 90)
        self._exp_preset_combo.addItem("180 Days", 180)
        self._exp_preset_combo.addItem("1 Year", 365)
        self._exp_preset_combo.addItem("Custom...", -1)

        self._exp_date_edit = QDateEdit()
        self._exp_date_edit.setObjectName("SecretDateEdit")
        self._exp_date_edit.setFixedHeight(28)
        self._exp_date_edit.setDisplayFormat("dd/MM/yyyy")
        self._exp_date_edit.setCalendarPopup(True)
        self._exp_date_edit.setDate(QDate.currentDate().addDays(30))
        self._exp_date_edit.setMinimumDate(QDate.currentDate())

        inputs_row.addWidget(self._exp_preset_combo)
        inputs_row.addWidget(self._exp_date_edit, 1)
        exp_c_layout.addLayout(inputs_row)

        exp_hint = QLabel("💡 Card status badges will warn you as this secret approaches expiration.")
        exp_hint.setObjectName("SecretExpHint")
        exp_c_layout.addWidget(exp_hint)

        self._exp_container.setVisible(False)
        self._exp_check.toggled.connect(self._exp_container.setVisible)
        self._exp_check.toggled.connect(lambda _: self.adjustSize())
        self._exp_preset_combo.currentIndexChanged.connect(
            self._on_preset_changed
        )
        self._exp_date_edit.dateChanged.connect(self._on_date_changed)

        if self._initial_expires_at:
            try:
                date_part = self._initial_expires_at[:10]
                qdate = QDate.fromString(date_part, "yyyy-MM-dd")
                if qdate.isValid():
                    self._exp_date_edit.setDate(qdate)
                    self._exp_check.setChecked(True)
                    self._exp_container.setVisible(True)
                    self._on_date_changed(qdate)
            except Exception:
                pass

        # Assemble layout
        layout.addWidget(header)
        layout.addWidget(divider)
        layout.addWidget(title_label)
        layout.addWidget(self.title_input)
        layout.addWidget(cat_label)
        layout.addWidget(self.cat_combo)
        layout.addLayout(payload_row)
        layout.addWidget(self.secret_input)
        if self._is_edit:
            hist_hint = QLabel("💡 Changes to this secret will automatically be preserved in Version History.")
            hist_hint.setObjectName("SecretExpHint")
            layout.addWidget(hist_hint)
        layout.addWidget(strength_wrap)
        layout.addWidget(self._gen_panel)
        layout.addLayout(exp_row)
        layout.addWidget(self._exp_container)
        layout.addWidget(self.error_lbl)
        layout.addLayout(btn_layout)

    # ─── Generate panel helpers ───────────────────────────────

    def _toggle_gen_panel(self, checked: bool) -> None:
        self._gen_panel.setVisible(checked)
        self.adjustSize()

    def _on_mode_changed(self, _idx: int) -> None:
        mode = self._mode_combo.currentData()
        self._pw_options.setVisible(mode == "password")
        self._tok_options.setVisible(mode == "token")
        self.adjustSize()

    def _do_generate(self) -> None:
        mode = self._mode_combo.currentData()
        if mode == "password":
            result = _generate_password(
                length=self._len_slider.value(),
                upper=self._chk_upper.isChecked(),
                lower=self._chk_lower.isChecked(),
                digits=self._chk_digits.isChecked(),
                symbols=self._chk_symbols.isChecked(),
            )
        else:
            fmt = self._tok_combo.currentData()
            result = _generate_token(fmt)

        self.secret_input.setPlainText(result)
        # Auto-hint title if still empty
        if not self.title_input.text().strip():
            mode_name = "Password" if mode == "password" else "Token"
            self.title_input.setPlaceholderText(f"Auto-generated {mode_name}")

    def _update_strength_bar(self) -> None:
        text = self.secret_input.toPlainText()
        if not text:
            self._strength_bar.setMaximumWidth(0)
            self._strength_lbl.setText("")
            return

        bits = _entropy_bits(text)
        ratio = min(bits / 128.0, 1.0)

        if bits < 40:
            color = "#e26f6f"   # weak   — red
            label_text = f"Weak (~{int(bits)} bits)"
        elif bits < 80:
            color = "#f0c040"   # fair   — yellow
            label_text = f"Moderate (~{int(bits)} bits)"
        else:
            color = "#2bbf5c"   # strong — green
            label_text = f"Strong (~{int(bits)} bits)"

        self._strength_bar.setStyleSheet(
            f"background: {color}; border-radius: 2px;"
        )
        wrap_w = self._strength_bar.parentWidget().width() or 400
        self._strength_bar.setMaximumWidth(int(wrap_w * ratio))
        self._strength_lbl.setText(label_text)
        self._strength_lbl.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent;")

    def _on_preset_changed(self, _idx: int) -> None:
        days = self._exp_preset_combo.currentData()
        if days is not None and days > 0:
            self._exp_date_edit.blockSignals(True)
            self._exp_date_edit.setDate(QDate.currentDate().addDays(days))
            self._exp_date_edit.blockSignals(False)

    def _on_date_changed(self, date: QDate) -> None:
        today = QDate.currentDate()
        diff = today.daysTo(date)
        match_idx = -1
        for i in range(self._exp_preset_combo.count()):
            if self._exp_preset_combo.itemData(i) == diff:
                match_idx = i
                break
        self._exp_preset_combo.blockSignals(True)
        if match_idx >= 0:
            self._exp_preset_combo.setCurrentIndex(match_idx)
        else:
            custom_idx = self._exp_preset_combo.findData(-1)
            if custom_idx >= 0:
                self._exp_preset_combo.setCurrentIndex(custom_idx)
        self._exp_preset_combo.blockSignals(False)

    # ─── Style ───────────────────────────────────────────────

    def _apply_style(self) -> None:
        """Apply theme from ui/ghost.qss if not already active on the application."""
        app = QApplication.instance()
        if not self.styleSheet() and not (app and app.styleSheet()):
            from core.paths import resource_path
            qss_file = resource_path("ui", "ghost.qss")
            if os.path.exists(qss_file):
                try:
                    with open(qss_file, "r", encoding="utf-8") as f:
                        self.setStyleSheet(f.read())
                except OSError:
                    pass

    # ─── Public API ───────────────────────────────────────────

    def scrub_inputs(self) -> None:
        self.secret_input.clear()
        if self.secret_input.document():
            self.secret_input.document().clearUndoRedoStacks()
        self.title_input.clear()

    def reject(self) -> None:
        self.scrub_inputs()
        super().reject()

    def closeEvent(self, event) -> None:
        self.scrub_inputs()
        super().closeEvent(event)

    def _on_save(self) -> None:
        title = self.title_input.text().strip()
        if not title:
            self.error_lbl.setText("Title cannot be empty.")
            self.title_input.setFocus()
            return

        secret_text = self.secret_input.toPlainText()
        if not self._is_edit and not secret_text:
            self.error_lbl.setText("Secret payload cannot be empty.")
            self.secret_input.setFocus()
            return

        self.accept()

    def get_expires_at(self) -> Optional[str]:
        """Return ISO formatted expiration timestamp or None if unset."""
        if not self._exp_check.isChecked():
            return None
        qdate = self._exp_date_edit.date()
        return f"{qdate.toString('yyyy-MM-dd')}T23:59:59"

    def get_data(self) -> SecretData:
        """
        Returns SecretData(title, secret_text_or_None, category_id,
        expires_at=...) which unpacks as a 3-element tuple for
        backward compatibility:
        title, payload, cat = dlg.get_data()
        """
        title = self.title_input.text().strip()
        secret_text = self.secret_input.toPlainText()
        cat_id = self.cat_combo.currentData() or "generic"
        payload = secret_text if (secret_text or not self._is_edit) else None
        expires_at = self.get_expires_at()
        return SecretData(title, payload, cat_id, expires_at=expires_at)
