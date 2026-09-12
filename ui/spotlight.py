"""
ui/spotlight.py — Spotlight Quick Search Overlay for DotGhostBoard
===================================================================
A frameless, floating quick-search dialog accessible anywhere via hotkey.
Offers instant keyboard-driven search (Up/Down/Enter) and direct clipboard pasting.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QHBoxLayout, QFrame,
    QApplication, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QColor, QKeyEvent

from core import storage
from core.config import APP_VERSION
from core.constants import SPOTLIGHT_RESULT_LIMIT, SPOTLIGHT_DEBOUNCE_MS, SPOTLIGHT_PREVIEW_MAX_LEN


class SpotlightSearchDialog(QDialog):
    """
    Spotlight-style floating search overlay.
    - Frameless, stays on top, centered on active monitor.
    - Up / Down / Enter keyboard navigation.
    - Emits sig_item_selected(item) when user picks an item to copy.
    """
    sig_item_selected = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(640)
        self.setFixedHeight(420)

        self._items = []
        self._pending_query = ""

        # Search debounce timer
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SPOTLIGHT_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._do_search)

        self._build_ui()
        self._center_on_screen()

    def _build_ui(self):
        # Outer container frame with border + glow
        container = QFrame(self)
        container.setObjectName("SpotlightContainer")
        container.setStyleSheet("""
            QFrame#SpotlightContainer {
                background-color: #111314;
                border: 1px solid #303438;
                border-radius: 14px;
            }
        """)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 8)
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container)

        inner_layout = QVBoxLayout(container)
        inner_layout.setContentsMargins(16, 16, 16, 16)
        inner_layout.setSpacing(12)

        # ── Header / Search Input ──────────────────────────────
        search_box = QHBoxLayout()
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet("font-size: 16px; background: transparent;")

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Search clipboard history…")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: #181a1c;
                color: #e1e4e6;
                border: 1px solid #2b2f32;
                border-radius: 9px;
                padding: 11px 14px;
                font-size: 14px;
            }

            QLineEdit:focus {
                border: 1px solid #3d7650;
                background: #1a1d1e;
            }
        """)
        self.input_field.textChanged.connect(self._on_search_changed)
        self.input_field.installEventFilter(self)

        search_box.addWidget(search_icon)
        search_box.addWidget(self.input_field)
        inner_layout.addLayout(search_box)

        # ── Results List ──────────────────────────────────────
        self.results_list = QListWidget()
        self.results_list.setStyleSheet("""
            QListWidget {
                background: #141617;
                border: 1px solid #25292c;
                border-radius: 9px;
                outline: none;
                padding: 5px;
            }

            QListWidget::item {
                color: #b9bec1;
                border-radius: 7px;
                padding: 9px 12px;
                margin-bottom: 2px;
            }

            QListWidget::item:selected {
                background: #18251d;
                color: #77dd98;
                border: 1px solid #31513b;
            }

            QListWidget::item:hover:!selected {
                background: #1b1e20;
            }
        """)
        self.results_list.itemActivated.connect(self._on_item_activated)
        self.results_list.installEventFilter(self)
        inner_layout.addWidget(self.results_list)

        # ── Footer Legend ───────────────────────────────────────────────
        footer = QHBoxLayout()
        hint = QLabel(
            f"⌨ <b>Enter</b> to copy &amp; paste  •  "
            f"<b>Esc</b> to close  •  "
            f"<b>Spotlight {APP_VERSION}</b>"
        )
        hint.setStyleSheet("color: #64748b; font-size: 11px; background: transparent;")
        footer.addWidget(hint)
        footer.addStretch()
        inner_layout.addLayout(footer)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 3  # upper 1/3 of screen
            self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_screen()
        self._search_timer.stop()
        self.input_field.clear()
        self.input_field.setFocus()
        self._perform_search("")

    def _on_search_changed(self, text: str):
        self._pending_query = text.strip()
        if not self._pending_query:
            self._search_timer.stop()
            self._perform_search("")
        else:
            self._search_timer.start()

    def _do_search(self):
        self._perform_search(self._pending_query)

    def _perform_search(self, query: str):
        self.results_list.clear()
        if not query:
            items = storage.get_all_items(limit=SPOTLIGHT_RESULT_LIMIT)
        else:
            items = storage.search_items(query, limit=SPOTLIGHT_RESULT_LIMIT)

        self._items = items
        for item in items:
            itype = item.get("type", "text")
            is_sec = bool(item.get("is_secret", 0))

            if is_sec:
                icon = "🔒"
                preview = "Secret Item (Encrypted)"
            else:
                icon = "📝" if itype == "text" else ("📸" if itype == "image" else "🎬")
                preview = item.get("preview") or item.get("content") or ""

            preview = preview.replace("\n", " ").strip()
            if len(preview) > SPOTLIGHT_PREVIEW_MAX_LEN:
                preview = preview[:SPOTLIGHT_PREVIEW_MAX_LEN] + "…"

            copies = item.get("copy_count", 0) or 0
            copy_str = f"  (×{copies})" if copies > 1 else ""

            list_item = QListWidgetItem(f"{icon}  {preview}{copy_str}")
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.results_list.addItem(list_item)

        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)

    def _on_item_activated(self, list_item: QListWidgetItem):
        item = list_item.data(Qt.ItemDataRole.UserRole)
        if item:
            self.sig_item_selected.emit(item)
            self.hide()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key_event: QKeyEvent = event
            key = key_event.key()

            if key == Qt.Key.Key_Escape:
                self.hide()
                return True

            elif key == Qt.Key.Key_Down:
                cur = self.results_list.currentRow()
                if cur < self.results_list.count() - 1:
                    self.results_list.setCurrentRow(cur + 1)
                return True

            elif key == Qt.Key.Key_Up:
                cur = self.results_list.currentRow()
                if cur > 0:
                    self.results_list.setCurrentRow(cur - 1)
                return True

            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                current_item = self.results_list.currentItem()
                if current_item:
                    self._on_item_activated(current_item)
                return True

        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                self.hide()
        super().changeEvent(event)
