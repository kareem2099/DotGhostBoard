import os
import sys
import logging

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QScrollArea, QLabel, QPushButton,
    QFrame, QSizePolicy, QSystemTrayIcon, QMenu,
    QApplication, QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QFileDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont, QKeyEvent

from core import storage
from core.watcher import ClipboardWatcher
from ui.widgets import ItemCard
from ui.settings import SettingsDialog, load_settings, save_settings

# Debug logger for drag & drop
logger = logging.getLogger(__name__)

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
        self._refresh_sidebar()
        # S003: clean old captures after loading history
        self._clean_captures()

    # ══════════════════════════════════════════
    # Build UI  (W005 — Collections Sidebar)
    # ══════════════════════════════════════════
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        # ── Main Horizontal Layout (Sidebar + Content) ──
        main_hbox = QHBoxLayout(central)
        main_hbox.setContentsMargins(0, 0, 0, 0)
        main_hbox.setSpacing(0)

        # ── W005: Collections Sidebar ──
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(160)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 8)
        sidebar_layout.setSpacing(10)

        sidebar_header = QHBoxLayout()
        coll_label = QLabel("📁 COLLECTIONS")
        coll_label.setStyleSheet("color: #666; font-weight: bold; font-size: 11px; letter-spacing: 1px;")

        add_coll_btn = QPushButton("+")
        add_coll_btn.setObjectName("AddCollBtn")
        add_coll_btn.setFixedSize(24, 24)
        add_coll_btn.setToolTip("New Collection")
        add_coll_btn.clicked.connect(self._create_collection)

        sidebar_header.addWidget(coll_label)
        sidebar_header.addStretch()
        sidebar_header.addWidget(add_coll_btn)

        self.collections_list = QListWidget()
        self.collections_list.setObjectName("CollectionsList")
        self.collections_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.collections_list.customContextMenuRequested.connect(self._on_collection_context_menu)
        self.collections_list.currentItemChanged.connect(self._on_collection_selected)
        self.collections_list.setAcceptDrops(True)
        self.collections_list.setDropIndicatorShown(True)
        self.collections_list.dragEnterEvent = self._sidebar_drag_enter
        self.collections_list.dragMoveEvent = self._sidebar_drag_move
        self.collections_list.dropEvent = self._sidebar_drop_event

        sidebar_layout.addLayout(sidebar_header)
        sidebar_layout.addWidget(self.collections_list)

        main_hbox.addWidget(self.sidebar)

        # ── Main Content Area ──
        main_area = QWidget()
        root = QVBoxLayout(main_area)
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
        self.search_box.setPlaceholderText("🔍  Search… or type #tag to filter by tag")
        self.search_box.textChanged.connect(self._on_search)

        search_layout.addWidget(self.search_box)
        root.addWidget(search_frame)

        # ── W006: Multi-select hint strip (shown once) ──
        self._hint_strip = QFrame()
        self._hint_strip.setObjectName("HintStrip")
        self._hint_strip.setFixedHeight(32)

        hint_layout = QHBoxLayout(self._hint_strip)
        hint_layout.setContentsMargins(12, 0, 8, 0)
        hint_layout.setSpacing(16)

        hint_text = QLabel(
            "💡  Multi-select:  "
            "<span style='color:#00ff41'>Ctrl+Click</span> to select  •  "
            "<span style='color:#00ff41'>Shift+Click</span> to range  •  "
            "<span style='color:#00ff41'>Esc</span> to clear"
        )
        hint_text.setObjectName("HintText")
        hint_text.setTextFormat(Qt.TextFormat.RichText)

        dismiss_btn = QPushButton("✕ got it")
        dismiss_btn.setObjectName("HintDismissBtn")
        dismiss_btn.setFixedHeight(22)
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.clicked.connect(self._dismiss_hint)

        hint_layout.addWidget(hint_text)
        hint_layout.addStretch()
        hint_layout.addWidget(dismiss_btn)

        root.addWidget(self._hint_strip)

        # Hide immediately if already dismissed
        if self._settings.get("multiselect_hint_dismissed", False):
            self._hint_strip.hide()

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

        # ── W007: Bulk Actions Toolbar (hidden by default) ──
        self._bulk_bar = QFrame()
        self._bulk_bar.setObjectName("BulkBar")
        self._bulk_bar.setFixedHeight(52)

        bulk_layout = QHBoxLayout(self._bulk_bar)
        bulk_layout.setContentsMargins(16, 0, 16, 0)
        bulk_layout.setSpacing(8)

        self._bulk_count_lbl = QLabel("0 selected")
        self._bulk_count_lbl.setObjectName("BulkCountLabel")

        btn_pin    = QPushButton("📍 Pin All")
        btn_unpin  = QPushButton("📌 Unpin All")
        btn_delete = QPushButton("✕ Delete All")
        btn_export = QPushButton("📤 Export")
        btn_tag    = QPushButton("🏷 Add Tag")
        btn_cancel = QPushButton("✕ Cancel")

        btn_pin.setObjectName("BulkBtn")
        btn_unpin.setObjectName("BulkBtn")
        btn_export.setObjectName("BulkBtn")
        btn_tag.setObjectName("BulkBtn")
        btn_delete.setObjectName("BulkBtnDanger")
        btn_cancel.setObjectName("BulkBtnCancel")

        btn_pin.clicked.connect(lambda: self._bulk_pin(True))
        btn_unpin.clicked.connect(lambda: self._bulk_pin(False))
        btn_delete.clicked.connect(self._bulk_delete)
        btn_export.clicked.connect(self._bulk_export)
        btn_tag.clicked.connect(self._bulk_add_tag)
        btn_cancel.clicked.connect(self._clear_selection)

        bulk_layout.addWidget(self._bulk_count_lbl)
        bulk_layout.addStretch()
        bulk_layout.addWidget(btn_pin)
        bulk_layout.addWidget(btn_unpin)
        bulk_layout.addWidget(btn_tag)
        bulk_layout.addWidget(btn_export)
        bulk_layout.addWidget(btn_delete)
        bulk_layout.addWidget(btn_cancel)

        root.addWidget(self._bulk_bar)
        self._bulk_bar.hide()   # hidden until 2+ selected

        main_hbox.addWidget(main_area)

        # ── Status bar ──
        self.statusBar().setStyleSheet(
            "background:#111; color:#00ff41; font-size:11px;"
        )
        self.statusBar().showMessage("Watching clipboard…")

        # Allow the scroll area to receive key events via the dashboard
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cards_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # State tracker for collections
        self.active_collection_id = None

        # W006: multi-select state
        self._selected_ids: set[int] = set()
        self._last_clicked_id: int | None = None   # W006: for shift-range
        self._drop_target_card: "ItemCard | None" = None   # drag-over highlight

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
    # W005 — Collections Logic
    # ══════════════════════════════════════════
    def _refresh_sidebar(self):
        """Reload collections from DB and update the sidebar UI."""
        self.collections_list.blockSignals(True)
        self.collections_list.clear()

        # Default item (All items)
        all_item = QListWidgetItem("❖ All Items")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.collections_list.addItem(all_item)

        # Load from DB
        colls = storage.get_collections()
        for c in colls:
            item = QListWidgetItem(f"📁 {c['name']} ({c['item_count']})")
            item.setData(Qt.ItemDataRole.UserRole, c['id'])
            self.collections_list.addItem(item)

            # Keep previous selection active if exists
            if self.active_collection_id == c['id']:
                item.setSelected(True)

        if not self.collections_list.selectedItems():
            all_item.setSelected(True)

        self.collections_list.blockSignals(False)

    def _create_collection(self):
        name, ok = QInputDialog.getText(self, "New Collection", "Collection Name:",
                                        QLineEdit.EchoMode.Normal, "")
        if ok and name.strip():
            storage.create_collection(name.strip())
            self._refresh_sidebar()
            self.statusBar().showMessage(f"Collection '{name}' created")

    def _on_collection_context_menu(self, pos):
        item = self.collections_list.itemAt(pos)
        if not item:
            return
        coll_id = item.data(Qt.ItemDataRole.UserRole)
        if coll_id is None:
            return  # "All Items" — no rename/delete

        menu = QMenu(self)
        rename_action = QAction("✏️ Rename", self)
        delete_action = QAction("🗑️ Delete", self)

        rename_action.triggered.connect(lambda: self._rename_collection(coll_id))
        delete_action.triggered.connect(lambda: self._delete_collection(coll_id))

        menu.addAction(rename_action)
        menu.addAction(delete_action)
        menu.exec(self.collections_list.mapToGlobal(pos))

    def _rename_collection(self, coll_id: int):
        colls = storage.get_collections()
        old_name = next((c["name"] for c in colls if c["id"] == coll_id), "")
        new_name, ok = QInputDialog.getText(self, "Rename Collection", "New Name:",
                                            QLineEdit.EchoMode.Normal, old_name)
        if ok and new_name.strip() and new_name.strip() != old_name:
            storage.rename_collection(coll_id, new_name.strip())
            self._refresh_sidebar()
            self.statusBar().showMessage("Collection renamed ✓")

    def _delete_collection(self, coll_id: int):
        reply = QMessageBox.question(
            self, "Delete Collection",
            "Delete this collection?\n(Items will NOT be deleted, just uncategorized)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            storage.delete_collection(coll_id)
            if self.active_collection_id == coll_id:
                self.active_collection_id = None
            self._refresh_sidebar()
            self._on_collection_selected(self.collections_list.currentItem(), None)
            self.statusBar().showMessage("Collection deleted ✓")

    def _on_collection_selected(self, current, previous):
        if not current:
            return

        self.active_collection_id = current.data(Qt.ItemDataRole.UserRole)

        # Clear current UI cards
        for card in list(self._cards.values()):
            self._remove_card(card.item_id)

        # Fetch items for this collection (or all if None)
        items = storage.get_items_by_collection(self.active_collection_id)
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
        card.sig_tag_added.connect(self._on_tag_added)      # W002
        card.sig_tag_removed.connect(self._on_tag_removed)  # W002
        card.sig_clicked.connect(self._on_card_clicked)     # W006

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
    # W006 — Multi-Select
    # ══════════════════════════════════════════
    def _on_card_clicked(self, item_id: int, modifiers):
        cards = self._visible_cards()
        card_ids = [c.item_id for c in cards]

        # Show hint if still visible (first interaction teaches them)
        if (modifiers & Qt.KeyboardModifier.ControlModifier
                and not self._settings.get("multiselect_hint_dismissed", False)):
            self._hint_strip.show()

        if modifiers & Qt.KeyboardModifier.ShiftModifier and self._last_clicked_id in card_ids:
            # ── Shift+Click: select range ──────────────────────────
            a = card_ids.index(self._last_clicked_id)
            b = card_ids.index(item_id)
            lo, hi = min(a, b), max(a, b)
            for iid in card_ids[lo : hi + 1]:
                self._selected_ids.add(iid)
                self._cards[iid].set_selected(True)

        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            # ── Ctrl+Click: toggle single ──────────────────────────
            if item_id in self._selected_ids:
                self._selected_ids.discard(item_id)
                self._cards[item_id].set_selected(False)
            else:
                self._selected_ids.add(item_id)
                self._cards[item_id].set_selected(True)
            self._last_clicked_id = item_id

        else:
            # ── Plain click: clear selection + move focus ──────────
            self._clear_selection()
            card = self._cards.get(item_id)
            if card in cards:
                self._set_card_focus(cards, cards.index(card))
            self._last_clicked_id = item_id

        self._update_bulk_bar()

        count = len(self._selected_ids)
        if count > 0:
            self.statusBar().showMessage(f"{count} item(s) selected  •  Ctrl+click to add, Shift+click to range")
        else:
            self.statusBar().showMessage("Watching clipboard…")

    def _clear_selection(self):
        for iid in self._selected_ids:
            card = self._cards.get(iid)
            if card:
                card.set_selected(False)
        self._selected_ids.clear()
        self._last_clicked_id = None
        self._update_bulk_bar()

    def _dismiss_hint(self):
        """Hide multi-select hint strip and persist dismissal."""
        self._hint_strip.hide()
        self._settings["multiselect_hint_dismissed"] = True
        save_settings(self._settings)

    # ══════════════════════════════════════════
    # W007 — Bulk Actions
    # ══════════════════════════════════════════
    def _update_bulk_bar(self):
        count = len(self._selected_ids)
        if count >= 2:
            self._bulk_count_lbl.setText(f"{count} selected")
            self._bulk_bar.show()
        else:
            self._bulk_bar.hide()

    def _bulk_pin(self, pin: bool):
        for iid in list(self._selected_ids):
            item = storage.get_item_by_id(iid)
            if item:
                if bool(item.get("is_pinned", 0)) != pin:
                    new_state = storage.toggle_pin(iid)
                    card = self._cards.get(iid)
                    if card:
                        card.update_pin_state(new_state)
        action = "Pinned" if pin else "Unpinned"
        self.statusBar().showMessage(f"{action} {len(self._selected_ids)} items ✓")
        self._refresh_stats()

    def _bulk_delete(self):
        count = len(self._selected_ids)
        reply = QMessageBox.question(
            self, "Delete Selected",
            f"Delete {count} selected item(s)?\nPinned items will be skipped.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        deleted = 0
        for iid in list(self._selected_ids):
            if storage.delete_item(iid):
                self._remove_card(iid)
                deleted += 1
        self._selected_ids.clear()
        self._update_bulk_bar()
        self._refresh_stats()
        self.statusBar().showMessage(f"Deleted {deleted} item(s) ✓")

    def _bulk_export(self):
        if not self._selected_ids:
            return
        fmt, ok = QInputDialog.getItem(
            self, "Export Format", "Choose format:",
            ["txt", "json"], 0, False
        )
        if not ok:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Items",
            f"dotghost_export.{fmt}",
            f"{'Text' if fmt == 'txt' else 'JSON'} Files (*.{fmt})"
        )
        if not path:
            return
        content = storage.export_items(list(self._selected_ids), fmt)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.statusBar().showMessage(f"Exported {len(self._selected_ids)} items → {path} ✓")

    def _bulk_add_tag(self):
        tag, ok = QInputDialog.getText(
            self, "Add Tag", "Tag to add to all selected items:",
            QLineEdit.EchoMode.Normal, "#"
        )
        if not ok or not tag.strip():
            return
        tag = tag.strip().lower()
        tag = tag if tag.startswith("#") else f"#{tag}"
        for iid in list(self._selected_ids):
            updated = storage.add_tag(iid, tag)
            card = self._cards.get(iid)
            if card and tag in updated:
                card.on_tag_added(tag)
        self.statusBar().showMessage(f"Tag {tag} added to {len(self._selected_ids)} items ✓")

    # ══════════════════════════════════════════
    # W002 — Tag slots
    # ══════════════════════════════════════════
    def _on_tag_added(self, item_id: int, tag: str):
        """Write tag to DB, then confirm back to the card's chip row."""
        updated = storage.add_tag(item_id, tag)
        card = self._cards.get(item_id)
        if card and tag in updated:
            card.on_tag_added(tag)
            self.statusBar().showMessage(f"Tag added: {tag}")

    def _on_tag_removed(self, item_id: int, tag: str):
        """Remove tag from DB, then confirm back to the card's chip row."""
        storage.remove_tag(item_id, tag)
        card = self._cards.get(item_id)
        if card:
            card.on_tag_removed(tag)
            self.statusBar().showMessage(f"Tag removed: {tag}")

    # ══════════════════════════════════════════
    # W003 — Search (text + optional #tag filter)
    # ══════════════════════════════════════════
    def _on_search(self, query: str):
        """
        Parse the search box value and apply text + tag filtering.

        Supported formats:
          "python"          → text search only
          "#code"           → tag filter only (show all items with that tag)
          "python #code"    → text search AND tag filter combined
        """
        self._focused_idx = -1
        raw = query.strip()

        if not raw:
            for card in self._cards.values():
                card.setVisible(True)
            return

        # ── split out tag tokens (words starting with #) ──
        tokens = raw.split()
        tag_tokens = [t for t in tokens if t.startswith("#")]
        text_tokens = [t for t in tokens if not t.startswith("#")]

        text_query = " ".join(text_tokens)
        # Support one active tag filter for now (first #tag wins)
        tag_filter = tag_tokens[0] if tag_tokens else None

        if tag_filter and not text_query:
            # Tag-only: use get_items_by_tag for all item types (not just text)
            result_ids = {r["id"] for r in storage.get_items_by_tag(tag_filter)}
        else:
            # Text search (with optional tag filter via search_items)
            result_ids = {
                r["id"] for r in storage.search_items(text_query, tag_filter)
            }

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
            new_idx = 0 if self._focused_idx == -1 else min(self._focused_idx + 1, len(cards) - 1)
            self._set_card_focus(cards, new_idx)

        elif key == Qt.Key.Key_Up:
            new_idx = 0 if self._focused_idx <= 0 else self._focused_idx - 1
            self._set_card_focus(cards, new_idx)

        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if 0 <= self._focused_idx < len(cards):
                self._on_copy(cards[self._focused_idx].item_id)
            else:
                super().keyPressEvent(event)

        elif key == Qt.Key.Key_Escape:
            # Clear focus on Escape
            if 0 <= self._focused_idx < len(cards):
                cards[self._focused_idx].set_focused(False)
            self._focused_idx = -1
            self._clear_selection()

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
    # S006: Drag & Drop
    # ══════════════════════════════════════════
    def _drag_enter(self, event):
        logger.debug(f"[Dashboard] _drag_enter called, hasMimeData={event.mimeData().hasFormat('application/x-dotghost-card-id')}")
        if event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.acceptProposedAction()

    # ══════════════════════════════════════════
    # W005: Drag & Drop to Sidebar Collections
    # ══════════════════════════════════════════
    def _sidebar_drag_enter(self, event):
        if event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.acceptProposedAction()

    def _sidebar_drag_move(self, event):
        if event.mimeData().hasFormat("application/x-dotghost-card-id"):
            item = self.collections_list.itemAt(event.position().toPoint())
            if item:
                self.collections_list.setCurrentItem(item)
            event.acceptProposedAction()

    def _sidebar_drop_event(self, event):
        logger.debug(f"[Dashboard] _sidebar_drop_event called")
        if not event.mimeData().hasFormat("application/x-dotghost-card-id"):
            logger.debug(f"[Dashboard] No mime data format match")
            return

        try:
            dragged_id = int(
                event.mimeData().data("application/x-dotghost-card-id").data().decode()
            )
            logger.debug(f"[Dashboard] Dragged item_id: {dragged_id}")
        except (ValueError, AttributeError) as e:
            logger.debug(f"[Dashboard] Failed to parse dragged_id: {e}")
            return

        item = self.collections_list.itemAt(event.position().toPoint())
        if not item:
            logger.debug(f"[Dashboard] No item at drop position")
            return

        target_coll_id = item.data(Qt.ItemDataRole.UserRole)
        logger.debug(f"[Dashboard] Target collection_id: {target_coll_id}")

        card = self._cards.get(dragged_id)
        if not card:
            logger.debug(f"[Dashboard] Card {dragged_id} not found in _cards")
            return

        storage.move_to_collection(dragged_id, target_coll_id)

        if target_coll_id != self.active_collection_id:
            self._remove_card(dragged_id)

        self._refresh_sidebar()
        self.statusBar().showMessage("Card moved to collection ✓")
        logger.debug(f"[Dashboard] Card {dragged_id} moved to collection {target_coll_id}")

        event.acceptProposedAction()

    def _drag_move(self, event):
        if not event.mimeData().hasFormat("application/x-dotghost-card-id"):
            return

        drop_pos = event.position().toPoint()
        layout   = self.cards_layout
        new_target = None

        for i in range(layout.count() - 1):
            w_item = layout.itemAt(i)
            if w_item and w_item.widget() and w_item.widget().geometry().contains(drop_pos):
                new_target = w_item.widget()
                break

        # Clear old highlight
        if self._drop_target_card and self._drop_target_card is not new_target:
            self._drop_target_card.set_drop_target(False)

        # Apply new highlight
        if new_target:
            new_target.set_drop_target(True)

        self._drop_target_card = new_target
        event.acceptProposedAction()

    def _drop_event(self, event):
        logger.debug(f"[Dashboard] _drop_event called")

        # Clear drop-target highlight
        if self._drop_target_card:
            self._drop_target_card.set_drop_target(False)
            self._drop_target_card = None

        if not event.mimeData().hasFormat("application/x-dotghost-card-id"):
            logger.debug(f"[Dashboard] No mime data format match")
            return
        try:
            dragged_id = int(
                event.mimeData().data("application/x-dotghost-card-id").data().decode()
            )
            logger.debug(f"[Dashboard] Dragged item_id: {dragged_id}")
        except (ValueError, AttributeError) as e:
            logger.debug(f"[Dashboard] Failed to parse dragged_id: {e}")
            return

        # Find which card is at the drop position
        drop_pos = event.position().toPoint()
        logger.debug(f"[Dashboard] Drop position: {drop_pos}")
        target_card = None
        layout = self.cards_layout
        for i in range(layout.count() - 1):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                logger.debug(f"[Dashboard] Checking card {w.item_id} at geometry {w.geometry()}")
                if w.geometry().contains(drop_pos) and w.item_id != dragged_id:
                    target_card = w
                    logger.debug(f"[Dashboard] Found target card: {w.item_id}")
                    break

        if target_card is None:
            logger.debug(f"[Dashboard] No target card at drop position {drop_pos}")
            return

        logger.debug(f"[Dashboard] Target card item_id: {target_card.item_id}")

        # Collect ALL cards in current order (not just pinned ones)
        all_cards = [
            layout.itemAt(i).widget()
            for i in range(layout.count() - 1)
            if layout.itemAt(i) and layout.itemAt(i).widget()
        ]
        logger.debug(f"[Dashboard] All cards: {[c.item_id for c in all_cards]}")

        dragged_card = self._cards.get(dragged_id)
        logger.debug(f"[Dashboard] Dragged card: {dragged_card}, is_pinned={dragged_card.is_pinned if dragged_card else 'N/A'}")
        if dragged_card and dragged_card in all_cards:
            all_cards.remove(dragged_card)
            target_idx = (
                all_cards.index(target_card)
                if target_card in all_cards
                else len(all_cards)
            )
            all_cards.insert(target_idx, dragged_card)
            logger.debug(f"[Dashboard] Reordered all cards: {[c.item_id for c in all_cards]}")

            # Persist new order for all cards
            for order, card in enumerate(all_cards):
                storage.update_sort_order(card.item_id, order)

            # Re-insert cards in new visual order
            for card in all_cards:
                layout.removeWidget(card)
            for order, card in enumerate(all_cards):
                layout.insertWidget(order, card)
        else:
            logger.debug(f"[Dashboard] Dragged card not in all cards, skipping reorder")

        event.acceptProposedAction()
