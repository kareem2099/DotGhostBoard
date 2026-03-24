import os
import sys

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QScrollArea, QLabel, QPushButton,
    QFrame, QSizePolicy, QSystemTrayIcon, QMenu,
    QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont, QKeyEvent

from core import storage
from core.watcher import ClipboardWatcher
from ui.widgets import ItemCard
from ui.settings import SettingsDialog, load_settings, save_settings

QSS_PATH = os.path.join(os.path.dirname(__file__), "ghost.qss")

class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DotGhostBoard")
        self.resize(520, 680)
        self.setMinimumWidth(400)
        self.setWindowIcon(self._make_tray_icon())

        # ── map of item cards {item_id: ItemCard} ──
        self._cards: dict[int, ItemCard] = {}

        # ── keyboard nav state ──
        self._focused_idx: int = -1

        # ── settings ──
        self._settings: dict = load_settings()

        self._load_stylesheet()
        self._build_ui()
        self._setup_tray()
        self._start_watcher()
        self._load_history()
        # S003: clean old captures after loading history
        self._clean_captures()

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

        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("SettingsBtn")
        settings_btn.setFixedSize(28, 28)
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self._open_settings)

        clear_btn = QPushButton("Clear History")
        clear_btn.setFixedHeight(28)
        clear_btn.setToolTip("Delete all un-pinned items")
        clear_btn.clicked.connect(self._clear_history)

        top_layout.addWidget(logo)
        top_layout.addStretch()
        top_layout.addWidget(self.stats_label)
        top_layout.addSpacing(8)
        top_layout.addWidget(settings_btn)
        top_layout.addSpacing(4)
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

        # S006: enable drop on the cards container
        self.cards_container.setAcceptDrops(True)
        self.cards_container.dragEnterEvent = self._drag_enter
        self.cards_container.dragMoveEvent  = self._drag_move
        self.cards_container.dropEvent      = self._drop_event

        # ── Status bar ──
        self.statusBar().setStyleSheet(
            "background:#111; color:#00ff41; font-size:11px;"
        )
        self.statusBar().showMessage("Watching clipboard…")

        # Allow the scroll area to receive key events via the dashboard
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cards_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

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
        """Load icon.png if available, else draw a minimal fallback."""
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "icons", "icon.png"
        )
        if os.path.isfile(icon_path):
            return QIcon(icon_path)

        px = QPixmap(22, 22)
        px.fill(QColor(0, 0, 0, 0))
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#00ff41"))
        painter.setPen(QColor("#00cc33"))
        painter.drawEllipse(2, 2, 18, 18)
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
    # Settings
    # ══════════════════════════════════════════
    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            old_limit = self._settings.get("max_history", 200)
            self._settings = dlg.settings
            # If limit tightened, trim excess cards from the UI
            if self._settings["max_history"] < old_limit:
                self._enforce_history_limit()
            # S003: re-run cleanup if max_captures changed
            self._clean_captures()
            self.statusBar().showMessage("Settings saved ✓")

    def _enforce_history_limit(self):
        """Trim unpinned cards if count exceeds max_history."""
        limit = self._settings.get("max_history", 200)
        unpinned = [iid for iid, c in self._cards.items() if not c.is_pinned]
        excess = len(self._cards) - limit
        if excess > 0:
            to_remove = unpinned[-excess:]
            for iid in to_remove:
                storage.delete_item(iid)
                self._remove_card(iid)
            self._refresh_stats()

    # S003: auto-cleanup of old capture files
    def _clean_captures(self):
        keep = self._settings.get("max_captures", 100)
        removed = storage.clean_old_captures(keep)
        if removed:
            current_ids = {r["id"] for r in storage.get_all_items(limit=9999)}
            gone = [iid for iid in list(self._cards) if iid not in current_ids]
            for iid in gone:
                self._remove_card(iid)
            self._refresh_stats()
            print(f"[Dashboard] Auto-cleanup removed {removed} old capture(s)")

    # ══════════════════════════════════════════
    # Watcher
    # ══════════════════════════════════════════
    def _start_watcher(self):
        self.watcher = ClipboardWatcher()
        self.watcher.new_text_captured.connect(self._on_new_text)
        self.watcher.new_image_captured.connect(self._on_new_image)
        self.watcher.new_video_captured.connect(self._on_new_video)
        # S002: when video thumbnail is ready, update the card
        self.watcher.thumb_ready.connect(self._on_thumb_ready)
        self.watcher.start()

    # ══════════════════════════════════════════
    # Load history
    # ══════════════════════════════════════════
    def _load_history(self):
        limit = self._settings.get("max_history", 200)
        items = storage.get_all_items(limit=limit)
        for item in reversed(items):
            self._add_card(item)
        self._refresh_stats()

    # ══════════════════════════════════════════
    # Cards management
    # ══════════════════════════════════════════
    def _add_card(self, item: dict, at_top: bool = True):
        if item["id"] in self._cards:
            return

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

        # Auto-trim if over limit (newest item just added)
        self._enforce_history_limit()

    def _remove_card(self, item_id: int):
        card = self._cards.pop(item_id, None)
        if card:
            # Clear keyboard focus if this card was focused
            if self._focused_idx >= 0:
                self._focused_idx = -1
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
            self.statusBar().showMessage("Image captured 📸")

    def _on_new_video(self, item_id: int, video_path: str):
        item = storage.get_item_by_id(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()
            self.statusBar().showMessage("Video path captured 🎬")

    # S002: update card when video thumbnail is extracted
    def _on_thumb_ready(self, item_id: int, thumb_path: str):
        card = self._cards.get(item_id)
        if card:
            card.update_video_thumb(thumb_path)

    # ══════════════════════════════════════════
    # Card action slots
    # ══════════════════════════════════════════
    def _on_copy(self, item_id: int):
        item = storage.get_item_by_id(item_id)
        if item:
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
        self._focused_idx = -1   # reset keyboard focus on new search
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
        self._focused_idx = -1
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
    # Keyboard Navigation (P005)
    # ══════════════════════════════════════════
    def _visible_cards(self) -> list[ItemCard]:
        """Return ordered list of currently visible ItemCards (top → bottom)."""
        result = []
        layout = self.cards_layout
        for i in range(layout.count() - 1):   # -1 to skip trailing stretch
            item = layout.itemAt(i)
            if item and item.widget() and item.widget().isVisible():
                result.append(item.widget())
        return result

    def _set_card_focus(self, cards: list[ItemCard], new_idx: int):
        """Move keyboard focus to card at new_idx; clear previous focus."""
        # Clear old focus
        if 0 <= self._focused_idx < len(cards):
            cards[self._focused_idx].set_focused(False)

        self._focused_idx = new_idx
        if 0 <= new_idx < len(cards):
            card = cards[new_idx]
            card.set_focused(True)
            # Auto-scroll so the card is visible
            self.scroll.ensureWidgetVisible(card)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        cards = self._visible_cards()

        if not cards:
            super().keyPressEvent(event)
            return

        if key == Qt.Key.Key_Down:
            new_idx = min(self._focused_idx + 1, len(cards) - 1)
            if self._focused_idx == -1:
                new_idx = 0
            self._set_card_focus(cards, new_idx)

        elif key == Qt.Key.Key_Up:
            if self._focused_idx <= 0:
                new_idx = 0
            else:
                new_idx = self._focused_idx - 1
            self._set_card_focus(cards, new_idx)

        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if 0 <= self._focused_idx < len(cards):
                focused_card = cards[self._focused_idx]
                self._on_copy(focused_card.item_id)
            else:
                super().keyPressEvent(event)

        elif key == Qt.Key.Key_Escape:
            # Clear focus on Escape
            if 0 <= self._focused_idx < len(cards):
                cards[self._focused_idx].set_focused(False)
            self._focused_idx = -1

        else:
            super().keyPressEvent(event)

    # ══════════════════════════════════════════
    # Close → minimize to tray / real quit
    # ══════════════════════════════════════════
    def closeEvent(self, event):
        if event.spontaneous():
            # User clicked X → minimize to tray
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "DotGhostBoard",
                "Running in background. Click tray icon to restore.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            # Real quit — check clear_on_exit setting
            if self._settings.get("clear_on_exit", False):
                storage.delete_unpinned_items()
            self.watcher.stop()
            self.tray.hide()
            event.accept()

    # ══════════════════════════════════════════
    # S006: Drag & Drop drop handler
    # ══════════════════════════════════════════
    def _drag_enter(self, event):
        if event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.acceptProposedAction()

    def _drag_move(self, event):
        if event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.acceptProposedAction()

    def _drop_event(self, event):
        if not event.mimeData().hasFormat("application/x-dotghost-card-id"):
            return
        try:
            dragged_id = int(
                event.mimeData().data("application/x-dotghost-card-id").data().decode()
            )
        except (ValueError, AttributeError):
            return

        # Find which card is at the drop position
        drop_pos = event.position().toPoint()
        target_card = None
        layout = self.cards_layout
        for i in range(layout.count() - 1):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.geometry().contains(drop_pos) and w.item_id != dragged_id:
                    target_card = w
                    break

        if target_card is None:
            return

        # Collect pinned cards in current order
        pinned_cards = [
            layout.itemAt(i).widget()
            for i in range(layout.count() - 1)
            if layout.itemAt(i) and layout.itemAt(i).widget()
            and layout.itemAt(i).widget().is_pinned
        ]

        dragged_card = self._cards.get(dragged_id)
        if dragged_card and dragged_card in pinned_cards:
            pinned_cards.remove(dragged_card)
            target_idx = (
                pinned_cards.index(target_card)
                if target_card in pinned_cards
                else len(pinned_cards)
            )
            pinned_cards.insert(target_idx, dragged_card)

            # Persist new order
            for order, card in enumerate(pinned_cards):
                storage.update_sort_order(card.item_id, order)

            # Re-insert cards in new visual order
            for card in pinned_cards:
                layout.removeWidget(card)
            for order, card in enumerate(pinned_cards):
                layout.insertWidget(order, card)

        event.acceptProposedAction()