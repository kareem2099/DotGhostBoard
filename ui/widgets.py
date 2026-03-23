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
        self.item_id  = item["id"]
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

        # ── Row 1: Badge + Meta + Actions ──
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

        # ─ Action buttons ─
        self.pin_btn = QPushButton("Pin" if not self.is_pinned else "Unpin")
        self.pin_btn.setObjectName("PinBtn")
        self.pin_btn.setProperty("pinned", str(self.is_pinned).lower())
        self.pin_btn.setFixedSize(28, 28)
        self.pin_btn.setToolTip("Pin / Unpin")
        self.pin_btn.clicked.connect(lambda: self.sig_pin.emit(self.item_id))

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("CopyBtn")
        copy_btn.setFixedSize(28, 28)
        copy_btn.setToolTip("Copy to Clipboard")
        copy_btn.clicked.connect(lambda: self.sig_copy.emit(self.item_id))

        del_btn = QPushButton("Delete")
        del_btn.setObjectName("DeleteBtn")
        del_btn.setFixedSize(28, 28)
        del_btn.setToolTip("Delete (pinned items are protected)")
        del_btn.clicked.connect(lambda: self.sig_delete.emit(self.item_id))

        top_row.addWidget(self.pin_btn)
        top_row.addWidget(copy_btn)
        top_row.addWidget(del_btn)

        main_layout.addLayout(top_row)

        # ── Row 2: Content Preview ──
        if item["type"] == "text":
            text = item["content"]
            if len(text) > self.PREVIEW_MAX_LEN:
                text = text[:self.PREVIEW_MAX_LEN] + "…"
            content_label = QLabel(text)
            content_label.setObjectName("ItemText")
            content_label.setWordWrap(True)
            content_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            main_layout.addWidget(content_label)

        elif item["type"] == "image":
            img_label = QLabel()
            pixmap = QPixmap(item["content"])
            if not pixmap.isNull():
                pixmap = pixmap.scaledToWidth(
                    300,
                    Qt.TransformationMode.SmoothTransformation
                )
                img_label.setPixmap(pixmap)
            else:
                img_label.setText("Image file not found")
                img_label.setObjectName("ItemText")
            main_layout.addWidget(img_label)

        elif item["type"] == "video":
            path_label = QLabel(f"Video: {item['content']}")
            path_label.setObjectName("ItemText")
            path_label.setWordWrap(True)
            main_layout.addWidget(path_label)

    # ──────────────────────────────────────────────
    def update_pin_state(self, is_pinned: bool):
        """Update card appearance after toggle"""
        self.is_pinned = is_pinned
        self.setProperty("pinned", str(is_pinned).lower())
        self.pin_btn.setText("Unpin" if is_pinned else "Pin")
        self.pin_btn.setProperty("pinned", str(is_pinned).lower())
        # reapply QSS styling
        self.style().unpolish(self)
        self.style().polish(self)
        self.pin_btn.style().unpolish(self.pin_btn)
        self.pin_btn.style().polish(self.pin_btn)
