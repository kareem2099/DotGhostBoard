import os
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QSizePolicy
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal
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

    PREVIEW_MAX_LEN = 120          # max chars to show in text preview

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item_id   = item["id"]
        self.is_pinned = bool(item.get("is_pinned", 0))
        self.item_type = item.get("type", "text")

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

        # ── Top row: badge + meta + buttons ──
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

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

    def _build_content(self, item: dict) -> QLabel | None:
        """
        FIX #5: return None if content is empty
        """
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

        elif item["type"] == "image":
            file_path = item["content"]
            # FIX #5: handle missing or invalid image files gracefully
            if not file_path or not os.path.isfile(file_path):
                label.setText("⚠ Image file not found")
                label.setStyleSheet("color: #ff4444;")
                return label

            try:
                pixmap = QPixmap(file_path)
                if pixmap.isNull():
                    raise ValueError("Invalid image file")
                pixmap = pixmap.scaledToWidth(
                    300, Qt.TransformationMode.SmoothTransformation
                )
                img_label = QLabel()
                img_label.setPixmap(pixmap)
                return img_label
            except Exception as e:
                label.setText(f"⚠ Failed to load image: {e}")
                label.setStyleSheet("color: #ff4444;")

        elif item["type"] == "video":
            file_path = item["content"]
            # FIX #5: handle missing video files gracefully
            if not file_path or not os.path.isfile(file_path):
                label.setText(f"⚠ Video not found:\n{file_path}")
                label.setStyleSheet("color: #ff4444;")
                return label
            label.setText(f"🎬 {file_path}")

        return label

    def mouseDoubleClickEvent(self, event):
        """P006: Double-click anywhere on the card to copy immediately."""
        self.sig_copy.emit(self.item_id)

    def set_focused(self, focused: bool):
        """P005: Toggle keyboard-nav focus highlight."""
        self.setProperty("focused", str(focused).lower())
        self.style().unpolish(self)
        self.style().polish(self)

    def update_pin_state(self, is_pinned: bool):
        self.is_pinned = is_pinned
        self.setProperty("pinned", str(is_pinned).lower())
        self.pin_btn.setText("📍" if is_pinned else "📌")
        self.pin_btn.setProperty("pinned", str(is_pinned).lower())
        self.style().unpolish(self)
        self.style().polish(self)
        self.pin_btn.style().unpolish(self.pin_btn)
        self.pin_btn.style().polish(self.pin_btn)