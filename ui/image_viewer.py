"""
ui/image_viewer.py
──────────────────
Full-size image viewer popup for DotGhostBoard v1.2.0 Specter.

Opens when user clicks an image thumbnail in a card.
Keyboard: Escape to close, Ctrl+C to copy image.
"""

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea,
    QSizePolicy, QApplication
)
from PyQt6.QtGui import QPixmap, QImage, QKeyEvent, QIcon
from PyQt6.QtCore import Qt


class ImageViewer(QDialog):
    """
    Modal dialog that shows a full-size image.
    Provides Copy Image and Close actions.
    """

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self._file_path = file_path

        self.setWindowTitle("🖼  Image Viewer — DotGhostBoard")
        self.setModal(True)
        self.setMinimumSize(400, 300)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )

        self._build_ui()
        self._load_image()
        self._fit_to_screen()

    # ──────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ── Scrollable image area ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setStyleSheet("background: #0a0a0a; border: none;")

        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._scroll.setWidget(self._img_label)
        layout.addWidget(self._scroll)

        # ── File path hint ──
        self._path_label = QLabel(os.path.basename(self._file_path))
        self._path_label.setStyleSheet("color:#555; font-size:11px;")
        self._path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._path_label)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._copy_btn = QPushButton("⎘  Copy Image")
        self._copy_btn.setObjectName("CopyImageBtn")
        self._copy_btn.setToolTip("Copy full image to clipboard (Ctrl+C)")
        self._copy_btn.setStyleSheet(
            "QPushButton { background:#00ff4122; color:#00ff41; border:1px solid #00ff41;"
            " border-radius:5px; padding:6px 16px; }"
            "QPushButton:hover { background:#00ff4144; }"
        )
        self._copy_btn.clicked.connect(self._copy_image)

        close_btn = QPushButton("Close")
        close_btn.setToolTip("Close viewer (Escape)")
        close_btn.clicked.connect(self.reject)

        btn_row.addWidget(self._copy_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ──────────────────────────────────────────
    def _load_image(self):
        """Load image from disk and display it, scaled to dialog width."""
        if not self._file_path or not os.path.isfile(self._file_path):
            self._img_label.setText("⚠ Image file not found")
            self._img_label.setStyleSheet("color:#ff4444; font-size:14px;")
            self._copy_btn.setEnabled(False)
            return

        pixmap = QPixmap(self._file_path)
        if pixmap.isNull():
            self._img_label.setText("⚠ Failed to load image")
            self._img_label.setStyleSheet("color:#ff4444;")
            self._copy_btn.setEnabled(False)
            return

        self._pixmap = pixmap
        self._update_pixmap()

    def _update_pixmap(self):
        """Scale pixmap to fit current dialog size, preserving aspect ratio."""
        if not hasattr(self, "_pixmap") or self._pixmap.isNull():
            return
        max_w = self._scroll.viewport().width() or 800
        max_h = self._scroll.viewport().height() or 600
        scaled = self._pixmap.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._img_label.setPixmap(scaled)

    def _fit_to_screen(self):
        """Resize dialog to 80% of screen, pixel-aware."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.resize(int(geo.width() * 0.8), int(geo.height() * 0.8))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pixmap()

    # ──────────────────────────────────────────
    def _copy_image(self):
        """Copy the full-resolution image to clipboard as QImage."""
        if not hasattr(self, "_pixmap") or self._pixmap.isNull():
            return
        image = QImage(self._file_path)
        if not image.isNull():
            QApplication.clipboard().setImage(image)
            self._copy_btn.setText("✓  Copied!")
            self._copy_btn.setStyleSheet(
                "QPushButton { background:#00ff4144; color:#00ff41; border:1px solid #00ff41;"
                " border-radius:5px; padding:6px 16px; }"
            )

    # ──────────────────────────────────────────
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        elif event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._copy_image()
        else:
            super().keyPressEvent(event)
