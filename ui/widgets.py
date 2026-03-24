"""
ui/widgets.py
─────────────
Item card widget for DotGhostBoard.
v1.2.0: lazy image loading (S001), image viewer on click (S004),
        drag handle for pinned reorder (S006).
"""

import os
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QSizePolicy, QApplication
)
from PyQt6.QtGui import QPixmap, QDrag, QImage
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QMimeData, QByteArray
from datetime import datetime


def _format_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d %b, %H:%M")
    except Exception:
        return ""


class ItemCard(QFrame):
    """
    A single card representing a clipboard item.
    Sends signals to the Dashboard when the user interacts.
    """

    sig_copy   = pyqtSignal(int)   # copy request
    sig_pin    = pyqtSignal(int)   # pin/unpin request
    sig_delete = pyqtSignal(int)   # delete request

    PREVIEW_MAX_LEN = 120
    THUMB_MAX_W     = 300
    THUMB_MAX_H     = 180

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item_id   = item["id"]
        self.item_type = item.get("type", "text")
        self.is_pinned = bool(item.get("is_pinned", 0))
        self._file_path = item.get("content", "")
        self._preview   = item.get("preview") or self._file_path
        self._img_label: QLabel | None = None

        self.setObjectName("ItemCard")
        self.setProperty("pinned", str(self.is_pinned).lower())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self._build_ui(item)

    # ──────────────────────────────────────────────
    def _build_ui(self, item: dict):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(4)

        # ── Top row: drag handle (pinned only) + badge + meta + buttons ──
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        # S006: drag handle for pinned cards
        if self.is_pinned:
            handle = QLabel("⠿")
            handle.setObjectName("DragHandle")
            handle.setFixedWidth(16)
            handle.setToolTip("Drag to reorder")
            handle.setStyleSheet("color:#555; font-size:16px;")
            handle.setCursor(Qt.CursorShape.OpenHandCursor)
            top_row.addWidget(handle)

        # Type badge
        badge = QLabel(item["type"].upper())
        badge.setObjectName("TypeBadge")
        badge.setProperty("type", item["type"])
        badge.setFixedHeight(18)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.style().unpolish(badge)
        badge.style().polish(badge)

        # Time meta
        meta = QLabel(_format_time(item["created_at"]))
        meta.setObjectName("ItemMeta")

        top_row.addWidget(badge)
        top_row.addWidget(meta)
        top_row.addStretch()

        self.pin_btn = QPushButton("📍" if self.is_pinned else "📌")
        self.pin_btn.setObjectName("PinBtn")
        self.pin_btn.setProperty("pinned", str(self.is_pinned).lower())
        self.pin_btn.setFixedSize(28, 28)
        self.pin_btn.setToolTip("Pin / Unpin")
        self.pin_btn.clicked.connect(lambda: self.sig_pin.emit(self.item_id))

        copy_btn = QPushButton("⎘")
        copy_btn.setObjectName("CopyBtn")
        copy_btn.setFixedSize(28, 28)
        copy_btn.setToolTip("Copy to Clipboard")
        copy_btn.clicked.connect(lambda: self.sig_copy.emit(self.item_id))

        del_btn = QPushButton("✕")
        del_btn.setObjectName("DeleteBtn")
        del_btn.setFixedSize(28, 28)
        del_btn.setToolTip("Delete (pinned items are protected)")
        del_btn.clicked.connect(lambda: self.sig_delete.emit(self.item_id))

        top_row.addWidget(self.pin_btn)
        top_row.addWidget(copy_btn)
        top_row.addWidget(del_btn)
        main_layout.addLayout(top_row)

        # ── Content preview ──
        content_widget = self._build_content(item)
        if content_widget:
            main_layout.addWidget(content_widget)

    # ──────────────────────────────────────────────
    def _build_content(self, item: dict) -> QLabel | None:
        label = QLabel()
        label.setObjectName("ItemText")
        label.setWordWrap(True)

        if item["type"] == "text":
            text = item["content"]
            if len(text) > self.PREVIEW_MAX_LEN:
                text = text[:self.PREVIEW_MAX_LEN] + "…"
            label.setText(text)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            return label

        elif item["type"] == "image":
            if not self._file_path or not os.path.isfile(self._file_path):
                label.setText("⚠ Image file not found")
                label.setStyleSheet("color: #ff4444;")
                return label
            # S001: lazy load — show placeholder, load thumbnail after paint
            self._img_label = QLabel("🖼  Loading…")
            self._img_label.setObjectName("ItemText")
            self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._img_label.setStyleSheet("color:#444; min-height:40px;")
            # Make image label clickable → open viewer (S004)
            self._img_label.mousePressEvent = self._on_image_click
            self._img_label.setCursor(Qt.CursorShape.PointingHandCursor)
            # Defer actual pixel load
            QTimer.singleShot(0, self._load_thumbnail)
            return self._img_label

        elif item["type"] == "video":
            file_path = self._file_path
            if not file_path or not os.path.isfile(file_path):
                label.setText(f"⚠ Video not found:\n{file_path}")
                label.setStyleSheet("color: #ff4444;")
                return label
            # S002: if thumbnail exists show it, else show path text
            preview = item.get("preview")
            if preview and os.path.isfile(preview):
                self._img_label = QLabel("🖼  Loading…")
                self._img_label.setObjectName("ItemText")
                self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._img_label.setStyleSheet("color:#444; min-height:40px;")
                self._preview = preview
                QTimer.singleShot(0, self._load_thumbnail)
                return self._img_label
            label.setText(f"🎬 {file_path}")
            return label

        return label

    # ──────────────────────────────────────────────
    # S001: Lazy thumbnail loader
    # ──────────────────────────────────────────────
    def _load_thumbnail(self):
        """Load thumbnail from disk after card is painted."""
        if not self._img_label:
            return
        path = self._preview or self._file_path
        if not path or not os.path.isfile(path):
            self._img_label.setText("⚠ File not found")
            return
        try:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                self._img_label.setText("⚠ Invalid image")
                return
            # Cap at THUMB_MAX_W × THUMB_MAX_H
            if pixmap.width() > self.THUMB_MAX_W:
                pixmap = pixmap.scaledToWidth(
                    self.THUMB_MAX_W, Qt.TransformationMode.SmoothTransformation
                )
            if pixmap.height() > self.THUMB_MAX_H:
                pixmap = pixmap.scaledToHeight(
                    self.THUMB_MAX_H, Qt.TransformationMode.SmoothTransformation
                )
            self._img_label.setPixmap(pixmap)
            self._img_label.setStyleSheet("")
        except Exception as e:
            self._img_label.setText(f"⚠ {e}")

    # ──────────────────────────────────────────────
    # S004: Open image viewer on thumbnail click
    # ──────────────────────────────────────────────
    def _on_image_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from ui.image_viewer import ImageViewer
            viewer = ImageViewer(self._file_path, self)
            viewer.exec()

    # ──────────────────────────────────────────────
    # S006: Update thumbnail when video thumb is ready
    # ──────────────────────────────────────────────
    def update_video_thumb(self, thumb_path: str):
        """Called by Dashboard when thumb_ready signal fires."""
        self._preview = thumb_path
        if self._img_label is None:
            # Create the image label now
            layout = self.layout()
            self._img_label = QLabel("🖼  Loading…")
            self._img_label.setObjectName("ItemText")
            self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._img_label)
        QTimer.singleShot(0, self._load_thumbnail)

    # ──────────────────────────────────────────────
    # P006: Double-click → copy
    # ──────────────────────────────────────────────
    def mouseDoubleClickEvent(self, event):
        self.sig_copy.emit(self.item_id)

    # P005: Keyboard focus highlight
    def set_focused(self, focused: bool):
        self.setProperty("focused", str(focused).lower())
        self.style().unpolish(self)
        self.style().polish(self)

    # ──────────────────────────────────────────────
    # S006: Drag & drop (pinned cards only)
    # ──────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_pinned:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.is_pinned
                and event.buttons() == Qt.MouseButton.LeftButton
                and hasattr(self, "_drag_start_pos")):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist > QApplication.startDragDistance():
                self._do_drag()
        super().mouseMoveEvent(event)

    def _do_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-dotghost-card-id",
                     QByteArray(str(self.item_id).encode()))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    # ──────────────────────────────────────────────
    def update_pin_state(self, is_pinned: bool):
        self.is_pinned = is_pinned
        self.setProperty("pinned", str(is_pinned).lower())
        self.pin_btn.setText("📍" if is_pinned else "📌")
        self.pin_btn.setProperty("pinned", str(is_pinned).lower())
        self.style().unpolish(self)
        self.style().polish(self)
        self.pin_btn.style().unpolish(self.pin_btn)
        self.pin_btn.style().polish(self.pin_btn)