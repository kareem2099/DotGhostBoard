"""
ui/widgets/item_card.py
───────────────────────
ItemCard widget for DotGhostBoard.
"""

import os
import logging
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QSizePolicy, QApplication,
    QGraphicsOpacityEffect, QWidget
)
from PyQt6.QtGui import QPixmap, QDrag, QPainter, QPen, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QMimeData, QByteArray

import core.storage as storage
from core.constants import (
    PREVIEW_MAX_LEN,
    THUMB_MAX_W,
    THUMB_MAX_H,
)
from .helpers import _format_time, _copy_count_badge_state
from .tag_input import TagInputRow

# Debug logger for drag & drop
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# ItemCard
# ══════════════════════════════════════════════════════════════
class ItemCard(QFrame):
    """
    A single card representing a clipboard item.
    Sends signals to the Dashboard when the user interacts.

    Layout (top → bottom):
        _build_top_row()          — drag handle, badges, metadata
        _build_action_buttons()   — pin, copy, delete
        _build_preview()          — text / image / video / secret overlay
        _build_tags()             — tag chips + inline tag input
    """

    sig_copy        = pyqtSignal(int)
    sig_pin         = pyqtSignal(int)
    sig_delete      = pyqtSignal(int)
    sig_tag_added   = pyqtSignal(int, str)
    sig_tag_removed = pyqtSignal(int, str)
    sig_clicked     = pyqtSignal(int, object)
    sig_reset_count = pyqtSignal(int)

    # E003: emitted when the card asks Dashboard for the active key
    sig_reveal_requested = pyqtSignal(int)   # (item_id)

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item_id   = item["id"]
        self.item_type = item.get("type", "text")
        self.is_pinned = bool(item.get("is_pinned", 0))
        self.is_secret = bool(item.get("is_secret", 0))   # E003
        self._copy_count = item.get("copy_count", 0) or 0
        self._created_at_iso = item.get("created_at", "")
        self._time_meta: QLabel | None = None

        self._file_path   = item.get("content", "")
        self._preview     = item.get("preview") or self._file_path
        self._img_label:  QLabel | None        = None
        self._tag_row:    TagInputRow | None   = None
        self._count_badge: QLabel | None       = None   # copy count pill

        # E003: revealed state — True while decrypted content is visible
        self._is_revealed: bool = False

        self.setObjectName("ItemCard")
        self.setProperty("pinned", str(self.is_pinned).lower())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self._build_ui(item)

    # ──────────────────────────────────────────────────────────
    # Build UI — orchestrator (delegates to sub-builders)
    # ──────────────────────────────────────────────────────────
    def _build_ui(self, item: dict):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 10, 14, 10)
        main_layout.setSpacing(7)

        main_layout.addLayout(self._build_top_row(item))
        self._build_preview(item, main_layout)
        self._build_tags(main_layout)

    # ──────────────────────────────────────────────────────────
    # _build_top_row — drag handle + badges + metadata
    # ──────────────────────────────────────────────────────────
    def _build_top_row(self, item: dict) -> QHBoxLayout:
        """Build and return the horizontal top row layout."""
        top_row = QHBoxLayout()
        top_row.setSpacing(7)

        # W006: selection checkmark overlay
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

        # Drag handle (all cards)
        self._drag_handle = QLabel("⠿")
        self._drag_handle.setObjectName("DragHandle")
        self._drag_handle.setFixedWidth(16)
        self._drag_handle.setToolTip("Drag to reorder or move to collection")
        self._drag_handle.setStyleSheet("color:#555; font-size:16px;")
        self._drag_handle.setCursor(Qt.CursorShape.OpenHandCursor)
        top_row.addWidget(self._drag_handle)

        # E003: secret badge (🔐 pill, only for secret items)
        if self.is_secret:
            secret_badge = QLabel("🔐")
            secret_badge.setObjectName("SecretBadge")
            secret_badge.setToolTip("This item is encrypted")
            top_row.addWidget(secret_badge)

        # Type badge
        badge = QLabel(item["type"].upper())
        badge.setObjectName("TypeBadge")
        badge.setProperty("type", item["type"])
        badge.setFixedHeight(18)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.style().unpolish(badge)
        badge.style().polish(badge)
        top_row.addWidget(badge)

        # Time meta
        self._time_meta = QLabel(_format_time(item.get("created_at", "")))
        self._time_meta.setObjectName("ItemMeta")
        top_row.addWidget(self._time_meta)

        # Copy count badge
        self._count_badge = QLabel()
        self._count_badge.setObjectName("CopyCountBadge")
        self._count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_badge.setFixedHeight(18)
        self._count_badge.setToolTip("Click to reset copy count")
        self._count_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._count_badge.mousePressEvent = lambda e: self.sig_reset_count.emit(self.item_id)
        self._apply_count_badge_style(self._copy_count)
        top_row.addWidget(self._count_badge)

        top_row.addStretch()

        # E003: secret toggle button (lock/reveal) — only for secret items
        if self.is_secret:
            self._secret_btn = QPushButton("👁 Reveal")
            self._secret_btn.setObjectName("RevealBtn")
            self._secret_btn.setFixedHeight(24)
            self._secret_btn.setToolTip("Reveal encrypted content")
            self._secret_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._secret_btn.clicked.connect(self._on_secret_btn_clicked)
            top_row.addWidget(self._secret_btn)
        else:
            self._secret_btn = None

        top_row.addLayout(self._build_action_buttons())

        return top_row

    # ──────────────────────────────────────────────────────────
    # _build_action_buttons — pin, copy, delete
    # ──────────────────────────────────────────────────────────
    def _build_action_buttons(self) -> QHBoxLayout:
        """Build and return the Pin, Copy, and Delete action buttons.

        Note: self.pin_btn is stored as an instance attribute because
        update_pin_state() needs to mutate it after construction.
        copy_btn and del_btn are kept as locals (not referenced later).
        """
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)

        self.pin_btn = QPushButton("📍" if self.is_pinned else "📌")
        self.pin_btn.setObjectName("PinBtn")
        self.pin_btn.setProperty("pinned", str(self.is_pinned).lower())
        self.pin_btn.setFixedSize(26, 26)
        self.pin_btn.setToolTip("Pin / Unpin")
        self.pin_btn.clicked.connect(
            lambda: self.sig_pin.emit(self.item_id)
        )

        copy_btn = QPushButton("⎘")
        copy_btn.setObjectName("CopyBtn")
        copy_btn.setFixedSize(26, 26)
        copy_btn.setToolTip("Copy to Clipboard")
        copy_btn.clicked.connect(
            lambda: self.sig_copy.emit(self.item_id)
        )

        del_btn = QPushButton("✕")
        del_btn.setObjectName("DeleteBtn")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Delete (pinned items are protected)")
        del_btn.clicked.connect(
            lambda: self.sig_delete.emit(self.item_id)
        )

        actions.addWidget(self.pin_btn)
        actions.addWidget(copy_btn)
        actions.addWidget(del_btn)

        return actions

    # ──────────────────────────────────────────────────────────
    # _build_preview — text / image / video / secret content
    # ──────────────────────────────────────────────────────────
    def _build_preview(self, item: dict, main_layout: QVBoxLayout) -> None:
        """Add the content preview widget(s) to main_layout in-place."""
        if self.is_secret:
            # E003: two widgets, toggle visibility — no QStackedWidget
            # which causes unpredictable height expansion
            self._overlay_widget = self._build_secret_overlay()
            main_layout.addWidget(self._overlay_widget)

            self._revealed_label = QLabel()
            self._revealed_label.setObjectName("ItemText")
            self._revealed_label.setWordWrap(True)
            self._revealed_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self._revealed_label.hide()
            main_layout.addWidget(self._revealed_label)

            # Keep _content_stack as None — not used in this approach
            self._content_stack = None
        else:
            content_widget = self._build_content(item)
            if content_widget:
                main_layout.addWidget(content_widget)

    # ──────────────────────────────────────────────────────────
    # _build_tags — tag chips + inline tag input
    # ──────────────────────────────────────────────────────────
    def _build_tags(self, main_layout: QVBoxLayout) -> None:
        """Add the W002 tag input row to main_layout in-place."""
        current_tags = storage.get_tags(self.item_id)
        self._tag_row = TagInputRow(self.item_id, current_tags)
        self._tag_row.sig_tag_added.connect(
            lambda tag: self.sig_tag_added.emit(self.item_id, tag)
        )
        self._tag_row.sig_tag_removed.connect(
            lambda tag: self.sig_tag_removed.emit(self.item_id, tag)
        )
        main_layout.addWidget(self._tag_row)

    # ──────────────────────────────────────────────────────────
    # E003 — Secret overlay (locked state)
    # ──────────────────────────────────────────────────────────
    def _build_secret_overlay(self) -> QWidget:
        """
        The 'locked' face of a secret card:
        A blurred/greyed placeholder with 🔒 icon and hint text.
        """
        overlay = QFrame()
        overlay.setObjectName("SecretOverlay")
        overlay.setStyleSheet(
            "QFrame#SecretOverlay {"
            "  background: rgba(255, 153, 0, 0.05);"
            "  border: 1px dashed #ff990055;"
            "  border-radius: 6px;"
            "}"
        )
        overlay.setFixedHeight(56)

        layout = QHBoxLayout(overlay)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        lock_icon = QLabel("🔒")
        lock_icon.setStyleSheet("font-size: 20px;")

        hint = QLabel("Encrypted — click  👁 Reveal  to view")
        hint.setStyleSheet("color: #ff990088; font-size: 12px; font-style: italic;")

        layout.addWidget(lock_icon)
        layout.addWidget(hint)
        layout.addStretch()
        return overlay

    # ──────────────────────────────────────────────────────────
    # E003 — Secret button handler
    # ──────────────────────────────────────────────────────────
    def _on_secret_btn_clicked(self):
        if self._is_revealed:
            self._lock_content()
        else:
            # Ask Dashboard for the active key via signal
            self.sig_reveal_requested.emit(self.item_id)

    def reveal_content(self, plaintext: str):
        """Called by Dashboard after decryption — show plaintext, hide overlay."""
        text = plaintext
        if len(text) > PREVIEW_MAX_LEN:
            text = text[:PREVIEW_MAX_LEN] + "…"
        self._revealed_label.setText(text)
        self._overlay_widget.hide()
        self._revealed_label.show()

        self._is_revealed = True
        if self._secret_btn:
            self._secret_btn.setText("🔒 Lock")
            self._secret_btn.setToolTip("Hide encrypted content")

    def _lock_content(self):
        """Hide plaintext, show overlay again."""
        self._revealed_label.hide()
        self._revealed_label.setText("")   # clear from memory
        self._overlay_widget.show()

        self._is_revealed = False
        if self._secret_btn:
            self._secret_btn.setText("👁 Reveal")
            self._secret_btn.setToolTip("Reveal encrypted content")

    # ──────────────────────────────────────────────────────────
    # E003 — Called by Dashboard on session lock (fixes the crash)
    # ──────────────────────────────────────────────────────────
    def on_session_locked(self):
        """
        Called when the user locks the session (Dashboard._lock()).
        Re-hides any currently revealed secret content so nothing
        leaks in the UI after the key is cleared from memory.
        """
        if self.is_secret and self._is_revealed:
            self._lock_content()

    # ──────────────────────────────────────────────────────────
    # Content builder  (non-secret items)
    # ──────────────────────────────────────────────────────────
    def _build_content(self, item: dict) -> QLabel | None:
        label = QLabel()
        label.setObjectName("ItemText")
        label.setWordWrap(True)

        if item["type"] == "text":
            text = item["content"]
            if len(text) > PREVIEW_MAX_LEN:
                text = text[:PREVIEW_MAX_LEN] + "…"
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

    # ──────────────────────────────────────────────────────────
    # W002: Tag update callbacks (called by Dashboard)
    # ──────────────────────────────────────────────────────────
    def on_tag_added(self, tag: str):
        """Update chip UI after Dashboard confirms DB write."""
        if self._tag_row:
            self._tag_row.add_tag_chip(tag)

    def on_tag_removed(self, tag: str):
        """Remove chip UI after Dashboard confirms DB write."""
        if self._tag_row:
            self._tag_row.remove_tag_chip(tag)

    # ──────────────────────────────────────────────────────────
    # S001: Lazy thumbnail loader
    # ──────────────────────────────────────────────────────────
    def _load_thumbnail(self):
        """S001: Load thumbnail — QImageReader decodes at display size directly."""
        if not self._img_label:
            return
        path = self._preview or self._file_path
        if not path or not os.path.isfile(path):
            self._img_label.setText("⚠ File not found")
            return
        try:
            from PyQt6.QtGui import QImageReader
            from PyQt6.QtCore import QSize

            reader = QImageReader(path)
            reader.setAutoTransform(True)

            orig = reader.size()
            if orig.isValid() and orig.width() > 0 and orig.height() > 0:
                scale = min(
                    THUMB_MAX_W / orig.width(),
                    THUMB_MAX_H / orig.height(),
                )
                if scale < 1.0:
                    reader.setScaledSize(QSize(
                        int(orig.width()  * scale),
                        int(orig.height() * scale),
                    ))

            image = reader.read()
            if image.isNull():
                self._img_label.setText("⚠ Invalid image")
                return

            self._img_label.setPixmap(QPixmap.fromImage(image))
            self._img_label.setStyleSheet("")
        except Exception as e:
            self._img_label.setText(f"⚠ {e}")

    # ──────────────────────────────────────────────────────────
    # S004: Image viewer on click
    # ──────────────────────────────────────────────────────────
    def _on_image_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from ui.image_viewer import ImageViewer
            viewer = ImageViewer(self._file_path, self)
            viewer.exec()

    # ──────────────────────────────────────────────────────────
    # S002: Video thumbnail when ffmpeg finishes
    # ──────────────────────────────────────────────────────────
    def update_video_thumb(self, thumb_path: str):
        """Called by Dashboard when thumb_ready signal fires."""
        self._preview = thumb_path
        if self._img_label is None:
            self._img_label = QLabel("🖼  Loading…")
            self._img_label.setObjectName("ItemText")
            self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout().addWidget(self._img_label)
        QTimer.singleShot(0, self._load_thumbnail)

    # ──────────────────────────────────────────────────────────
    # P006: Double-click → copy
    # ──────────────────────────────────────────────────────────
    def mouseDoubleClickEvent(self, event):
        self.sig_copy.emit(self.item_id)

    # ──────────────────────────────────────────────────────────
    # P005: Keyboard focus
    # ──────────────────────────────────────────────────────────
    def set_focused(self, focused: bool):
        self.setProperty("focused", str(focused).lower())
        self.style().unpolish(self)
        self.style().polish(self)

    # ──────────────────────────────────────────────────────────
    # W005 & W006: Click, select, drag
    # ──────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos   = event.position().toPoint()
            child = self.childAt(pos)
            logger.debug(
                f"[ItemCard {self.item_id}] mousePressEvent pos={pos} child={child}"
            )

            if child == self._drag_handle:
                self._is_dragging_handle = True
                self._drag_start_pos     = pos
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
            self.sig_clicked.emit(self.item_id, QApplication.keyboardModifiers())

        # Pass event to parent so Text Selection keeps working
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            event.buttons() == Qt.MouseButton.LeftButton
            and getattr(self, "_is_dragging_handle", False)
        ):
            dist = (
                event.position().toPoint() - self._drag_start_pos
            ).manhattanLength()
            if dist > QApplication.startDragDistance():
                self._do_drag()
                self._is_dragging_handle = False
                return
        super().mouseMoveEvent(event)

    def _do_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(
            "application/x-dotghost-card-id",
            QByteArray(str(self.item_id).encode()),
        )
        drag.setMimeData(mime)

        raw    = self.grab()
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
        painter.drawRoundedRect(
            1, 1, ghost.width() - 2, ghost.height() - 2, 8, 8
        )
        painter.end()

        drag.setPixmap(ghost)
        drag.setHotSpot(ghost.rect().center())

        # ── Dim the source card while dragging ──
        _fx = QGraphicsOpacityEffect(self)
        _fx.setOpacity(0.35)
        self.setGraphicsEffect(_fx)

        drag.exec(Qt.DropAction.MoveAction)

        self.setGraphicsEffect(None)
        self._is_dragging_handle = False

    # ──────────────────────────────────────────────────────────
    # W006: Selection & drop-target states
    # ──────────────────────────────────────────────────────────
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

    # ──────────────────────────────────────────────────────────
    def update_pin_state(self, is_pinned: bool):
        self.is_pinned = is_pinned
        self.setProperty("pinned", str(is_pinned).lower())
        self.pin_btn.setText("📍" if is_pinned else "📌")
        self.pin_btn.setProperty("pinned", str(is_pinned).lower())
        self.style().unpolish(self)
        self.style().polish(self)
        self.pin_btn.style().unpolish(self.pin_btn)
        self.pin_btn.style().polish(self.pin_btn)

    # ──────────────────────────────────────────────────────────
    # Copy count badge
    # ──────────────────────────────────────────────────────────
    def update_copy_count(self, count: int):
        """Refresh the copy count badge without rebuilding the card."""
        self._copy_count = count
        if self._count_badge:
            self._apply_count_badge_style(count)

    def _apply_count_badge_style(self, count: int) -> None:
        """Apply the current copy-frequency state to the badge widget."""
        text, style = _copy_count_badge_state(count)

        if not text:
            self._count_badge.setText("")
            self._count_badge.setVisible(False)
            return

        self._count_badge.setText(text)
        self._count_badge.setStyleSheet(style)
        self._count_badge.setVisible(True)

    def update_relative_time(self):
        """Refresh timestamp label to latest relative format."""
        if hasattr(self, "_created_at_iso") and self._time_meta and self._created_at_iso:
            self._time_meta.setText(_format_time(self._created_at_iso))
