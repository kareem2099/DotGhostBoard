"""
ui/vault/guide_dialog.py
────────────────────────
Modal dialog displaying comprehensive security instructions, architecture,
and keyboard shortcuts for The Vault in DotGhostBoard.

v2.1.0 Leviathan — Vault Guidance Subsystem.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class VaultGuideDialog(QDialog):
    """
    Dedicated modal displaying security instructions, cryptographic guarantees,
    clipboard scrub policies, version history, and keyboard shortcuts.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("The Vault — Security & User Guide")
        self.setObjectName("VaultGuideDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setFixedWidth(520)
        self.setFixedHeight(620)

        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Header Row
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("🛡️  The Vault Guide")
        title.setObjectName("VaultGuideTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #e6edf3;")

        close_btn = QPushButton("✕")
        close_btn.setObjectName("VaultToolBtn")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        subtitle = QLabel(
            "Security architecture, automatic protections, and tips for DotGhostBoard."
        )
        subtitle.setStyleSheet("color: #8b949e; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(subtitle)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("VaultUnlockDivider")
        layout.addWidget(divider)

        # Scroll Area for guide content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(4, 4, 4, 4)
        c_layout.setSpacing(12)

        # ── Section 1: Quick Shortcuts ──
        c_layout.addWidget(self._make_section_card(
            "⌨️", "Keyboard Shortcuts & Quick Access",
            [
                ("Ctrl+Shift+V", "Toggle the Vault drawer from any window in your system."),
                ("Esc", "Safely close the Vault drawer or dismiss any active dialog."),
                ("Search Box", "Instantly filter secrets by title or category with live debouncing."),
            ]
        ))

        # ── Section 2: Zero-Knowledge Architecture ──
        c_layout.addWidget(self._make_section_card(
            "🔐", "Zero-Knowledge Cryptographic Architecture",
            [
                ("Envelope Encryption",
                 "Secrets are encrypted with a 256-bit DEK, wrapped by a KEK derived from your Master Password."),
                ("AES-256-GCM",
                 "Industry-standard authenticated encryption guarantees confidentiality and tamper detection."),
                ("PBKDF2-HMAC-SHA256",
                 "100,000 hashing rounds protect your Master Password against brute-force attacks."),
                ("Zero Plaintext on Disk",
                 "vault.db stores zero plaintext items. Secrets exist decrypted only in RAM while unlocked."),
            ]
        ))

        # ── Section 3: Ephemeral Security & Auto-Scrubbing ──
        c_layout.addWidget(self._make_section_card(
            "⏱️", "Ephemeral Memory & Auto-Scrubbing",
            [
                ("30-Second Clipboard Wipe",
                 "Any secret copied to your clipboard is automatically zeroed out after 30 seconds to prevent leaks."),
                ("15-Second Reveal Scrub",
                 "Revealing with 👁️ shows plaintext and automatically re-masks it after 15 seconds."),
                ("Immediate Drawer Scrub",
                 "Closing the drawer immediately wipes all revealed plaintexts from memory."),
            ]
        ))

        # ── Section 4: Version History & Rollback ──
        c_layout.addWidget(self._make_section_card(
            "📜", "Password Version History (Rollback)",
            [
                ("Last 3 Versions",
                 "Every time you update a secret, DotGhostBoard retains up to 3 previous encrypted versions."),
                ("One-Click Revert",
                 "Click 📜 on any secret to view timestamps, copy past passwords, or revert back with 1-click."),
            ]
        ))

        # ── Section 5: Expiration Tracking ──
        c_layout.addWidget(self._make_section_card(
            "⏳", "Expiration & Expiry Badges",
            [
                ("API Tokens & Credentials",
                 "Assign expiration dates to temporary keys or access tokens."),
                ("Visual Status Badges",
                 "Cards display 🟢 Active, 🟡 Expiring Soon (< 7 days), or 🔴 Expired badges for proactive rotation."),
            ]
        ))

        # ── Section 6: Encrypted Backups ──
        c_layout.addWidget(self._make_section_card(
            "📦", "Encrypted Backups (.vault)",
            [
                ("Export (📤)",
                 "Exports all secrets into an AES-256-GCM package (.vault) secured with an export passphrase."),
                ("Import (📥)",
                 "Restores secrets from a backup file, decrypts safely, and skips duplicates automatically."),
                ("Zero Plaintext Leakage",
                 "Backup files contain zero unencrypted data and can be safely archived in cold storage."),
            ]
        ))

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Footer Done Button
        footer = QHBoxLayout()
        footer.addStretch()
        done_btn = QPushButton("Got it")
        done_btn.setObjectName("VaultAddBtn")
        done_btn.setFixedHeight(34)
        done_btn.setFixedWidth(100)
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.clicked.connect(self.accept)
        footer.addWidget(done_btn)
        layout.addLayout(footer)

    def _make_section_card(self, icon: str, title: str, items: list[tuple[str, str]]) -> QFrame:
        card = QFrame()
        card.setObjectName("VaultGuideCard")
        c_lay = QVBoxLayout(card)
        c_lay.setContentsMargins(12, 10, 12, 10)
        c_lay.setSpacing(6)

        header = QLabel(f"{icon}  <b>{title}</b>")
        header.setObjectName("VaultGuideCardTitle")
        c_lay.addWidget(header)

        for label, desc in items:
            item_lbl = QLabel(f"• <b>{label}:</b> {desc}")
            item_lbl.setObjectName("VaultGuideCardItem")
            item_lbl.setWordWrap(True)
            c_lay.addWidget(item_lbl)

        return card

    def _apply_style(self) -> None:
        """Apply theme from ui/ghost.qss if not already active on QApplication."""
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
