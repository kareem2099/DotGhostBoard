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
from PyQt6.QtGui import QColor, QFont, QKeyEvent

from core import storage


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

        # 150ms search debounce timer
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._do_search)

        self._build_ui()
        self._center_on_screen()

    def _build_ui(self):
        # Outer container frame with border + glow
        container = QFrame(self)
        container.setObjectName("SpotlightContainer")
        container.setStyleSheet("""
            QFrame#SpotlightContainer {
                background-color: #12121c;
                border: 1.5px solid #00e5ff;
                border-radius: 12px;
            }
        """)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 229, 255, 60))
        shadow.setOffset(0, 4)
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
        self.input_field.setPlaceholderText("Spotlight Search clips… (Up/Down to navigate, Enter to copy)")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: #1a1a28;
                color: #e2e8f0;
                border: 1px solid #2d3748;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
                selection-background-color: #00e5ff;
                selection-color: #0a0a0f;
            }
            QLineEdit:focus {
                border: 1px solid #00e5ff;
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
                background: #161622;
                border: 1px solid #262636;
                border-radius: 8px;
                outline: none;
                padding: 4px;
            }
            QListWidget::item {
                background: transparent;
                color: #cbd5e1;
                border-radius: 6px;
                padding: 8px 12px;
                margin-bottom: 2px;
            }
            QListWidget::item:selected {
                background: #252538;
                color: #00e5ff;
                border: 1px solid #00e5ff;
            }
            QListWidget::item:hover {
                background: #1c1c2e;
            }
        """)
        self.results_list.itemActivated.connect(self._on_item_activated)
        self.results_list.installEventFilter(self)
        inner_layout.addWidget(self.results_list)

        # ── Footer Legend ──────────────────────────────────────
        footer = QHBoxLayout()
        hint = QLabel("⌨ <b>Enter</b> to copy & paste  •  <b>Esc</b> to close  •  <b>Spotlight v1.5.5</b>")
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
            items = storage.get_all_items(limit=15)
        else:
            items = storage.search_items(query, limit=15)

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
            if len(preview) > 60:
                preview = preview[:60] + "…"

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
