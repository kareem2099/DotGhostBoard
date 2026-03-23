import os
import sys

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QScrollArea, QLabel, QPushButton,
    QFrame, QSizePolicy, QSystemTrayIcon, QMenu,
    QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont

from core import storage
from core.watcher import ClipboardWatcher
from ui.widgets import ItemCard

QSS_PATH = os.path.join(os.path.dirname(__file__), "ghost.qss")


class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DotGhostBoard")
        self.resize(520, 680)
        self.setMinimumWidth(400)

        # ── map of item cards {item_id: ItemCard} ──
        self._cards: dict[int, ItemCard] = {}

        self._load_stylesheet()
        self._build_ui()
        self._setup_tray()
        self._start_watcher()
        self._load_history()

    # ══════════════════════════════════════════
    # Build UI
    # ══════════════════════════════════════════
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top Bar ──
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(56)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 8, 12, 8)

        logo = QLabel("👻 DotGhostBoard")
        logo.setStyleSheet("font-size:15px; font-weight:bold; color:#00ff41;")

        self.stats_label = QLabel("")
        self.stats_label.setObjectName("StatLabel")

        clear_btn = QPushButton("Clear History")
        clear_btn.setFixedHeight(28)
        clear_btn.setToolTip("Delete all un-pinned items")
        clear_btn.clicked.connect(self._clear_history)

        top_layout.addWidget(logo)
        top_layout.addStretch()
        top_layout.addWidget(self.stats_label)
        top_layout.addSpacing(8)
        top_layout.addWidget(clear_btn)
        root.addWidget(top_bar)

        # ── Search ──
        search_frame = QFrame()
        search_frame.setStyleSheet("padding: 8px 12px;")
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(0, 0, 0, 0)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍  Search text items…")
        self.search_box.textChanged.connect(self._on_search)

        search_layout.addWidget(self.search_box)
        root.addWidget(search_frame)

        # ── Scroll Area ──
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(12, 8, 12, 8)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()   # cards are added above this stretch

        self.scroll.setWidget(self.cards_container)
        root.addWidget(self.scroll)

        # ── Status bar ──
        self.statusBar().setStyleSheet(
            "background:#111; color:#333; font-size:11px;"
        )
        self.statusBar().showMessage("Watching clipboard…")

    # ══════════════════════════════════════════
    # Stylesheet
    # ══════════════════════════════════════════
    def _load_stylesheet(self):
        if os.path.exists(QSS_PATH):
            with open(QSS_PATH, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    # ══════════════════════════════════════════
    # System Tray
    # ══════════════════════════════════════════
    @staticmethod
    def _make_tray_icon() -> QIcon:
        """Create a simple green icon programmatically"""
        px = QPixmap(22, 22)
        px.fill(QColor(0, 0, 0, 0))           # transparent
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # green circle
        painter.setBrush(QColor("#00ff41"))
        painter.setPen(QColor("#00cc33"))
        painter.drawEllipse(2, 2, 18, 18)
        # white G letter
        painter.setPen(QColor("#0f0f0f"))
        font = QFont("monospace", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "G")
        painter.end()
        return QIcon(px)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._make_tray_icon())
        self.tray.setToolTip("DotGhostBoard")

        menu = QMenu()
        show_action = QAction("Show", self)
        quit_action = QAction("Quit", self)
        show_action.triggered.connect(self.show_and_raise)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_click)
        self.tray.show()

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_and_raise()

    def show_and_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # ══════════════════════════════════════════
    # Watcher
    # ══════════════════════════════════════════
    def _start_watcher(self):
        self.watcher = ClipboardWatcher()
        self.watcher.new_text_captured.connect(self._on_new_text)
        self.watcher.new_image_captured.connect(self._on_new_image)
        self.watcher.new_video_captured.connect(self._on_new_video)
        self.watcher.start()

    # ══════════════════════════════════════════
    # Load history
    # ══════════════════════════════════════════
    def _load_history(self):
        items = storage.get_all_items()
        for item in reversed(items):   # oldest first so newest appears on top
            self._add_card(item)
        self._refresh_stats()

    # ══════════════════════════════════════════
    # Cards management
    # ══════════════════════════════════════════
    def _add_card(self, item: dict, at_top: bool = True):
        if item["id"] in self._cards:
            return  # already exists

        card = ItemCard(item)
        card.sig_copy.connect(self._on_copy)
        card.sig_pin.connect(self._on_pin)
        card.sig_delete.connect(self._on_delete)

        self._cards[item["id"]] = card
        layout = self.cards_layout
        if at_top:
            layout.insertWidget(0, card)
        else:
            layout.insertWidget(layout.count() - 1, card)

    def _remove_card(self, item_id: int):
        card = self._cards.pop(item_id, None)
        if card:
            card.setParent(None)
            card.deleteLater()

    # ══════════════════════════════════════════
    # Watcher slots
    # ══════════════════════════════════════════
    def _on_new_text(self, item_id: int, text: str):
        item = storage.get_item_by_id(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()
            preview = text[:40] + "…" if len(text) > 40 else text
            self.statusBar().showMessage(f"Text captured: {preview}")

    def _on_new_image(self, item_id: int, file_path: str):
        item = storage.get_item_by_id(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()
            self.statusBar().showMessage("Image captured")

    def _on_new_video(self, item_id: int, video_path: str):
        item = storage.get_item_by_id(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()
            self.statusBar().showMessage(f"Video path captured")

    # ══════════════════════════════════════════
    # Card action slots
    # ══════════════════════════════════════════
    def _on_copy(self, item_id: int):
        item = storage.get_item_by_id(item_id)
        if item:
            # ✅ FIX #1: mark_self_paste to avoid infinite loop
            self.watcher.mark_self_paste()
            self.watcher.paste_item_to_clipboard(item)
            self.statusBar().showMessage("Copied! ⎘")

    def _on_pin(self, item_id: int):
        new_state = storage.toggle_pin(item_id)
        card = self._cards.get(item_id)
        if card:
            card.update_pin_state(new_state)
        self.statusBar().showMessage("Pinned 📍" if new_state else "Unpinned 📌")
        self._refresh_stats()

    def _on_delete(self, item_id: int):
        success = storage.delete_item(item_id)
        if success:
            self._remove_card(item_id)
            self._refresh_stats()
            self.statusBar().showMessage("Deleted ✕")
        else:
            self.statusBar().showMessage("⚠ Pinned items cannot be deleted!")

    # ══════════════════════════════════════════
    # Search
    # ══════════════════════════════════════════
    def _on_search(self, query: str):
        query = query.strip()
        if not query:
            for card in self._cards.values():
                card.setVisible(True)
            return

        result_ids = {r["id"] for r in storage.search_items(query)}
        for item_id, card in self._cards.items():
            card.setVisible(item_id in result_ids)

    # ══════════════════════════════════════════
    # Clear History
    # ══════════════════════════════════════════
    def _clear_history(self):
        storage.delete_unpinned_items()
        to_remove = [iid for iid, card in self._cards.items() if not card.is_pinned]
        for iid in to_remove:
            self._remove_card(iid)
        self._refresh_stats()
        self.statusBar().showMessage("History cleared (pinned items kept)")

    # ══════════════════════════════════════════
    # Stats
    # ══════════════════════════════════════════
    def _refresh_stats(self):
        s = storage.get_stats()
        self.stats_label.setText(
            f"Total: {s['total']}  |  📌 {s['pinned']}  |  "
            f"T: {s['texts']}  I: {s['images']}"
        )

    # ══════════════════════════════════════════
    # ✅ FIX #4: closeEvent to minimize to tray instead of exiting
    # ══════════════════════════════════════════
    def closeEvent(self, event):
        if event.spontaneous():
            # user clicked the window's close button → minimize to tray
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "DotGhostBoard",
                "Running in background. Click tray icon to restore.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            # programmatic close (e.g. from tray menu) → exit app
            self.watcher.stop()   # stop the watcher thread gracefully
            self.tray.hide()
            event.accept()