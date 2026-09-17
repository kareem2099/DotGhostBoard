"""
ui/settings/pages/about.py
───────────────────────────
About tab — version, author, license, system info, and social links.

Extracted from ui/settings.py (v1.6.0 Phantom) in v2.0.0 Cerberus.
Contains:
  - build_about_tab(dialog) → QWidget

Depends on dialog helpers:
  dialog._section_label(), dialog._hsep()

Code is preserved verbatim; only self.X → dialog.X substitution was applied.
(About tab has no owned state — no dialog.X = widget assignments.)
"""

from __future__ import annotations
import sys
import platform
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QFrame,
    QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt, QUrl, PYQT_VERSION_STR, QT_VERSION_STR
from PyQt6.QtGui import QDesktopServices

if TYPE_CHECKING:
    from ui.settings.dialog import SettingsDialog


def build_about_tab(dialog: "SettingsDialog") -> QWidget:
    """
    Build and return the About tab widget.
    No owned state (no dialog.X = widget assignments).
    Calls dialog helpers: dialog._section_label(), dialog._hsep().
    """
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

    from core.config import APP_VERSION, APP_CODENAME

    version_lbl = QLabel(f"{APP_VERSION}  ·  {APP_CODENAME}")
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

    layout.addWidget(dialog._hsep())
    layout.addSpacing(14)

    # ── Author ────────────────────────────────────────────────────────────
    layout.addWidget(dialog._section_label("👤  Author"))
    layout.addSpacing(6)

    author_lbl = QLabel("FreeRave  (kareem)")
    author_lbl.setStyleSheet("color: #ccc; font-size: 13px; padding-left: 4px;")
    layout.addWidget(author_lbl)

    email_lbl = QLabel("kareem209907@gmail.com")
    email_lbl.setStyleSheet("color: #555; font-size: 11px; padding-left: 4px;")
    layout.addWidget(email_lbl)

    layout.addSpacing(14)
    layout.addWidget(dialog._hsep())
    layout.addSpacing(14)

    # ── License ───────────────────────────────────────────────────────────
    layout.addWidget(dialog._section_label("📄  License"))
    layout.addSpacing(6)

    lic_box = QFrame()
    lic_box.setStyleSheet(
        "QFrame { background: #0f0f0f; border: 1px solid #1e1e1e; "
        "border-radius: 6px; }"
    )
    lic_layout = QVBoxLayout(lic_box)
    lic_layout.setContentsMargins(12, 10, 12, 10)

    lic_title = QLabel("Apache License 2.0")
    lic_title.setStyleSheet("color: #72d991; font-weight: bold; font-size: 12px;")

    lic_text = QLabel(
        "Licensed under the Apache License, Version 2.0 (the \"License\");\n"
        "you may not use this file except in compliance with the License.\n"
        "You may obtain a copy of the License at:\n\n"
        "http://www.apache.org/licenses/LICENSE-2.0"
    )
    lic_text.setStyleSheet("color: #555; font-size: 11px; line-height: 1.6;")
    lic_text.setWordWrap(True)

    lic_layout.addWidget(lic_title)
    lic_layout.addSpacing(4)
    lic_layout.addWidget(lic_text)
    layout.addWidget(lic_box)

    layout.addSpacing(14)
    layout.addWidget(dialog._hsep())
    layout.addSpacing(14)

    # ── System info ───────────────────────────────────────────────────────
    layout.addWidget(dialog._section_label("🖥  System"))
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
        lbl.setStyleSheet("color: #72d991; font-family: monospace; font-size: 11px;")
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
    layout.addWidget(dialog._hsep())
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
    layout.addWidget(dialog._section_label("📦  Project"))
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
    layout.addWidget(dialog._section_label("📝  Articles & News"))
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
    layout.addWidget(dialog._section_label("💬  Social"))
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
    layout.addWidget(dialog._section_label("🎬  Videos"))
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
    layout.addWidget(dialog._section_label("👥  Facebook"))
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
