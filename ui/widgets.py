"""
ui/widgets.py
─────────────
Item card widget for DotGhostBoard.
v1.2.0: lazy image loading (S001), image viewer on click (S004),
        drag handle for pinned reorder (S006).
v1.3.0: tag input + chip display (W002).
"""

import os
import logging
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QSizePolicy, QApplication,
    QLineEdit, QWidget, QCompleter, QGraphicsOpacityEffect
)
from PyQt6.QtGui import QPixmap, QDrag, QImage, QPainter, QPen, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QMimeData, QByteArray, QStringListModel
from datetime import datetime

import core.storage as storage

# Debug logger for drag & drop
logger = logging.getLogger(__name__)


def _format_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d %b, %H:%M")
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────
# TagChip  — a single removable tag pill
# ──────────────────────────────────────────────────────────────
class TagChip(QFrame):
    """Clickable colored chip that emits sig_remove when the × is pressed."""

    sig_remove = pyqtSignal(str)   # emits the tag string e.g. "#code"

    # Rotate through a small palette so different tags get different colors
    _COLORS = [
        ("#1e3a5f", "#4a9eff"),   # blue
        ("#1e3d2f", "#4adf8a"),   # green
        ("#3d1e3f", "#cc66ff"),   # purple
        ("#3d2e1e", "#ffaa44"),   # amber
        ("#3d1e1e", "#ff6666"),   # red
        ("#1e3d3d", "#44ddcc"),   # teal
    ]
    _color_map: dict[str, tuple] = {}
    _color_idx: int = 0

    @classmethod
    def _color_for(cls, tag: str) -> tuple[str, str]:
        if tag not in cls._color_map:
            palette = cls._COLORS[cls._color_idx % len(cls._COLORS)]
            cls._color_map[tag] = palette
            cls._color_idx += 1
        return cls._color_map[tag]

    def __init__(self, tag: str, parent=None):
        super().__init__(parent)
        self.tag = tag
        bg, fg = self._color_for(tag)
        self.setObjectName("TagChip")
        self.setStyleSheet(f"QFrame#TagChip {{ background: {bg}; border: 1px solid {fg}44; }}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(3)

        lbl = QLabel(tag)
        lbl.setObjectName("TagChipLabel")
        lbl.setStyleSheet(f"color: {fg};")

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(14, 14)
        remove_btn.setStyleSheet(f"color: {fg}99; font-size: 13px;")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.sig_remove.emit(self.tag))

        layout.addWidget(lbl)
        layout.addWidget(remove_btn)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


# ──────────────────────────────────────────────────────────────
# TagInputRow  — wrapping chip area + inline text input
# ──────────────────────────────────────────────────────────────
class TagInputRow(QWidget):
    """
    Shows existing tags as chips and provides an inline QLineEdit
    for adding new ones.  Autocompletes from existing DB tags.
    """

    sig_tag_added   = pyqtSignal(str)   # new tag confirmed by user
    sig_tag_removed = pyqtSignal(str)   # chip × clicked

    def __init__(self, item_id: int, tags: list[str], parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.setObjectName("TagInputRow")

        # Outer wrap uses a simple VBox; chips flow in their own HBox row
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 0)
        outer.setSpacing(4)

        # ── chip row ──────────────────────────────
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(4)
        self._chip_row.addStretch()

        chip_wrap = QWidget()
        chip_wrap.setLayout(self._chip_row)
        chip_wrap.setObjectName("ChipWrap")
        outer.addWidget(chip_wrap)

        # ── tag input ─────────────────────────────
        self._input = QLineEdit()
        self._input.setObjectName("TagInput")
        self._input.setPlaceholderText("+ add tag  (#code, #python…)")
        self._input.setFixedHeight(24)
        self._input.returnPressed.connect(self._on_return)
        outer.addWidget(self._input)

        # Autocomplete from DB tags
        self._refresh_completer()

        # Render initial chips
        for tag in tags:
            self._add_chip(tag)

    # ── public ────────────────────────────────────
    def add_tag_chip(self, tag: str):
        """Called externally when a tag was successfully saved to DB."""
        self._add_chip(tag)
        self._refresh_completer()

    def remove_tag_chip(self, tag: str):
        """Remove chip visually (DB update handled by Dashboard)."""
        for i in range(self._chip_row.count()):
            item = self._chip_row.itemAt(i)
            if item and isinstance(item.widget(), TagChip):
                chip: TagChip = item.widget()
                if chip.tag == tag:
                    chip.deleteLater()
                    self._chip_row.removeItem(item)
                    break

    # ── private ───────────────────────────────────
    def _add_chip(self, tag: str):
        chip = TagChip(tag)
        chip.sig_remove.connect(self.sig_tag_removed)
        # Insert before the trailing stretch
        idx = max(0, self._chip_row.count() - 1)
        self._chip_row.insertWidget(idx, chip)

    def _on_return(self):
        raw = self._input.text().strip()
        if not raw:
            return
        tag = raw.lower() if raw.startswith("#") else f"#{raw.lower()}"
        self._input.clear()
        self.sig_tag_added.emit(tag)

    def _refresh_completer(self):
        all_tags = storage.get_all_tags()
        model = QStringListModel(all_tags)
        completer = QCompleter(model, self._input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._input.setCompleter(completer)


# ══════════════════════════════════════════════════════════════
# ItemCard
# ══════════════════════════════════════════════════════════════
class ItemCard(QFrame):
    """
    A single card representing a clipboard item.
    Sends signals to the Dashboard when the user interacts.
    """

    sig_copy   = pyqtSignal(int)   # copy request
    sig_pin    = pyqtSignal(int)   # pin/unpin request
    sig_delete = pyqtSignal(int)   # delete request
    sig_tag_added   = pyqtSignal(int, str)   # W002: (item_id, tag)
    sig_tag_removed = pyqtSignal(int, str)   # W002: (item_id, tag)
    sig_clicked = pyqtSignal(int, object)  # W006: (item_id, modifiers)

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
        self._tag_row:   TagInputRow | None = None

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

        # W006: selection checkbox overlay (hidden by default)
        self._check_overlay = QLabel("✓")
        self._check_overlay.setObjectName("SelectionCheck")
        self._check_overlay.setFixedSize(18, 18)
        self._check_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._check_overlay.setStyleSheet(
            "background: #00ff41; color: #0a0a0a; border-radius: 9px; "
            "font-weight: bold; font-size: 11px;"
        )
        self._check_overlay.hide()
        top_row.addWidget(self._check_overlay)

        # W005: drag handle for all cards (to drag to collections)
        self._drag_handle = QLabel("⠿")
        self._drag_handle.setObjectName("DragHandle")
        self._drag_handle.setFixedWidth(16)
        self._drag_handle.setToolTip("Drag to reorder or move to collection")
        self._drag_handle.setStyleSheet("color:#555; font-size:16px;")
        self._drag_handle.setCursor(Qt.CursorShape.OpenHandCursor)
        top_row.addWidget(self._drag_handle)

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

        # ── W002: Tag input row ──
        current_tags = storage.get_tags(self.item_id)
        self._tag_row = TagInputRow(self.item_id, current_tags)
        self._tag_row.sig_tag_added.connect(
            lambda tag: self.sig_tag_added.emit(self.item_id, tag)
        )
        self._tag_row.sig_tag_removed.connect(
            lambda tag: self.sig_tag_removed.emit(self.item_id, tag)
        )
        main_layout.addWidget(self._tag_row)

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
    # W002: Called by Dashboard after DB confirm
    # ──────────────────────────────────────────────
    def on_tag_added(self, tag: str):
        """Update chip UI after Dashboard confirms DB write."""
        if self._tag_row:
            self._tag_row.add_tag_chip(tag)

    def on_tag_removed(self, tag: str):
        """Remove chip UI after Dashboard confirms DB write."""
        if self._tag_row:
            self._tag_row.remove_tag_chip(tag)

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
    # W005 & W006: Mouse Clicks, Select, & Drag (Fixed)
    # ──────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            child = self.childAt(pos)
            logger.debug(f"[ItemCard {self.item_id}] mousePressEvent at pos={pos}, child={child}")

            # 1. If clicked on DragHandle (⠿)
            if child == self._drag_handle:
                self._is_dragging_handle = True
                self._drag_start_pos = pos
                logger.debug(f"[ItemCard {self.item_id}] Drag handle CLICKED! Setting _is_dragging_handle=True")
                event.accept()
                # Key point: return here to prevent Dashboard from refreshing the card
                # and breaking the Drag before it starts
                return

            # 2. If clicked on buttons (Copy, Pin, Delete), let them work
            if isinstance(child, QPushButton):
                self._is_dragging_handle = False
                super().mousePressEvent(event)
                return

            # 3. Any other area (Multi-select)
            self._is_dragging_handle = False
            logger.debug(f"[ItemCard {self.item_id}] Not on handle, emitting sig_clicked")
            # Only emit signal if not on handle
            self.sig_clicked.emit(self.item_id, QApplication.keyboardModifiers())

        # Pass event to parent so Text Selection keeps working
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Drag only works if we really started from the Handle
        if (event.buttons() == Qt.MouseButton.LeftButton
                and getattr(self, "_is_dragging_handle", False)):

            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            logger.debug(f"[ItemCard {self.item_id}] mouseMoveEvent: dist={dist}, threshold={QApplication.startDragDistance()}")
            if dist > QApplication.startDragDistance():
                logger.debug(f"[ItemCard {self.item_id}] Distance exceeded, calling _do_drag()")
                # Here the magic starts
                self._do_drag()
                self._is_dragging_handle = False
                return  # Exit so it doesn't do Selection while dragging

        super().mouseMoveEvent(event)

    def _do_drag(self):
        logger.debug(f"[ItemCard {self.item_id}] _do_drag() called")
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-dotghost-card-id",
                     QByteArray(str(self.item_id).encode()))
        drag.setMimeData(mime)

        # ── Ghost pixmap: semi-transparent card + neon border ──
        raw = self.grab()
        scaled = raw.scaledToWidth(220, Qt.TransformationMode.SmoothTransformation)

        ghost = QPixmap(scaled.size())
        ghost.fill(Qt.GlobalColor.transparent)
        painter = QPainter(ghost)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(0.72)
        painter.drawPixmap(0, 0, scaled)
        painter.setOpacity(1.0)
        pen = QPen(QColor("#00ff41"), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(1, 1, ghost.width() - 2, ghost.height() - 2, 8, 8)
        painter.end()

        drag.setPixmap(ghost)
        drag.setHotSpot(ghost.rect().center())

        # ── Dim the source card while dragging ──
        _fx = QGraphicsOpacityEffect(self)
        _fx.setOpacity(0.35)
        self.setGraphicsEffect(_fx)

        logger.debug(f"[ItemCard {self.item_id}] Drag started")
        result = drag.exec(Qt.DropAction.MoveAction)
        logger.debug(f"[ItemCard {self.item_id}] Drag done: {result}")

        # ── Restore card ──
        self.setGraphicsEffect(None)
        self._is_dragging_handle = False

    def set_selected(self, selected: bool):
        """W006: Toggle visual selected state"""
        self.setProperty("selected", str(selected).lower())
        self.style().unpolish(self)
        self.style().polish(self)
        # Show/hide the checkmark overlay
        if selected:
            self._check_overlay.show()
        else:
            self._check_overlay.hide()

    def set_drop_target(self, active: bool):
        """W006+: Highlight card as a valid drop position."""
        self.setProperty("droptarget", str(active).lower())
        self.style().unpolish(self)
        self.style().polish(self)

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