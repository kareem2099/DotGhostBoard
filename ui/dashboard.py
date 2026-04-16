import os
import sys
import logging

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QScrollArea, QLabel, QPushButton,
    QFrame, QSystemTrayIcon, QMenu,
    QApplication, QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont, QKeyEvent

from core import storage
from core.watcher import ClipboardWatcher
from core.crypto     import has_master_password
from core.app_filter import AppFilter
from core.sync_engine import SyncEngine
from ui.widgets import ItemCard
from ui.settings import SettingsDialog, load_settings, save_settings
from ui.lock_screen  import LockScreen
from core.network_discovery import DotGhostDiscovery

# Debug logger for drag & drop
logger = logging.getLogger(__name__)

QSS_PATH = os.path.join(os.path.dirname(__file__), "ghost.qss")

_PAGE_SIZE = 20   # Cards loaded per page

class UpdateCheckerThread(QThread):
    update_found = pyqtSignal(dict, str) # update_info, asset_url
    
    def run(self):
        from core.updater import check_for_updates, identify_platform_asset
        from core.config import APP_VERSION
        
        update_info = check_for_updates(APP_VERSION)
        if update_info:
            asset_url = identify_platform_asset(update_info["assets"])
            if asset_url:
                self.update_found.emit(update_info, asset_url)

class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DotGhostBoard")
        self.resize(520, 680)
        self.setMinimumWidth(400)
        self.setWindowIcon(self._make_tray_icon())

        # ── map of item cards {item_id: ItemCard} ──
        self._cards: dict[int, ItemCard] = {}
        self._history_offset: int  = 0
        self._history_exhausted: bool = False
        self._is_loading: bool = False
        self._current_view_mode: str = "history"  # "history", "collection", "search", "tag"
        self._current_search_query: str = ""
        self._current_tag_filter: str | None = None
        self._update_thread = None
        self._pending_update_info: dict | None = None
        self._pending_asset_url: str | None = None

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

        # ── API Server ──
        self._api_thread = None
        self._start_api_server()

        # ── Network Discovery ──
        self._discovery_thread = None
        self._start_discovery()

        # ── Sync Engine ──
        self._sync_engine: SyncEngine | None = None
        self._init_sync_engine()

        # ── Pairing State ──
        self._active_pairing_dialogs = {}

        # ── Eclipse state ──
        self._active_key: bytes | None = None  # set after successful unlock
        self._auto_lock_timer = QTimer(self)
        self._auto_lock_timer.setSingleShot(True)
        self._auto_lock_timer.timeout.connect(self._lock)
        
        # Connect signal so SettingsDialog can trigger check
        QApplication.instance().setProperty("main_dashboard", self)

        if self._settings.get("auto_update_check", True):
            self.check_for_updates()
            
        self._reset_auto_lock()  # start timer if configured

        # App filter (updated from settings)
        self._app_filter = AppFilter(
            mode=self._settings.get("app_filter_mode", "blacklist"),
            app_list=self._settings.get("app_filter_list", []),
        )

        # Apply stealth mode if it was saved
        if self._settings.get("stealth_mode", False):
            self._set_stealth(True)

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
        self.collections_list.dragMoveEvent  = self._sidebar_drag_move
        self.collections_list.dropEvent      = self._sidebar_drop_event

        sidebar_layout.addLayout(sidebar_header)
        sidebar_layout.addWidget(self.collections_list)

        # ── W005: Devices List (Sync Phase) ──
        sidebar_layout.addSpacing(16)
        dev_header = QHBoxLayout()
        dev_label = QLabel("🌐 DEVICES")
        dev_label.setStyleSheet("color: #666; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
        dev_header.addWidget(dev_label)
        dev_header.addStretch()
        sidebar_layout.addLayout(dev_header)

        self.devices_list = QListWidget()
        self.devices_list.setObjectName("DevicesList")
        self.devices_list.setFixedHeight(140)
        self.devices_list.setToolTip("Double-click a device to pair")
        self.devices_list.itemDoubleClicked.connect(self._on_device_double_clicked)
        sidebar_layout.addWidget(self.devices_list)

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

        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.setToolTip("Delete all un-pinned items")
        self.clear_btn.clicked.connect(self._clear_history)

        self.lock_btn = QPushButton("🔒")
        self.lock_btn.setObjectName("LockBtn")
        self.lock_btn.setFixedSize(28, 28)
        self.lock_btn.setToolTip("Lock session  (Eclipse)")
        self.lock_btn.clicked.connect(self._lock)
        # Only visible if master password is configured
        self.lock_btn.setVisible(has_master_password())

        self.update_btn = QPushButton("🎁 New Update!")
        self.update_btn.setStyleSheet(
            "background: #00ff4122; color: #00ff41; border: 1px solid #00ff41; padding: 0 10px; border-radius: 4px; font-weight: bold;"
        )
        self.update_btn.setFixedHeight(28)
        self.update_btn.clicked.connect(self._show_updater_dialog)
        self.update_btn.hide()

        top_layout.addWidget(logo)
        top_layout.addStretch()
        top_layout.addWidget(self.update_btn)
        top_layout.addSpacing(8)
        top_layout.addWidget(self.stats_label)
        top_layout.addSpacing(8)
        top_layout.addWidget(self.lock_btn)
        top_layout.addSpacing(4)
        top_layout.addWidget(settings_btn)
        top_layout.addSpacing(4)
        top_layout.addWidget(self.clear_btn)
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

        # Lazy loading: load more cards when user scrolls near bottom
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

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
        lock_action = QAction("🔒 Lock", self)
        lock_action.triggered.connect(self._lock)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(lock_action)
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
            # Eclipse: update app filter
            self._app_filter.update(
                self._settings.get("app_filter_mode", "blacklist"),
                self._settings.get("app_filter_list", []),
            )
            # Eclipse: update stealth mode
            self._set_stealth(self._settings.get("stealth_mode", False))
            # Eclipse: update lock button visibility
            self.lock_btn.setVisible(has_master_password())
            # Eclipse: restart auto-lock timer with new timeout
            self._reset_auto_lock()
            self.statusBar().showMessage("Settings saved ✓")

    def _enforce_history_limit(self):
        """Trim unpinned cards if count exceeds max_history."""
        limit = self._settings.get("max_history", 200)
        unpinned = [iid for iid, c in self._cards.items() if not c.is_pinned]
        excess   = len(self._cards) - limit
        if excess > 0:
            for iid in unpinned[-excess:]:
                storage.delete_item(iid)
                self._remove_card(iid)
            self._refresh_stats()

    # S003: auto-cleanup of old capture files
    def _clean_captures(self):
        keep    = self._settings.get("max_captures", 100)
        removed = storage.clean_old_captures(keep)
        if removed:
            for iid in list(self._cards):
                if storage.get_item_by_id(iid) is None:
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
        # Eclipse: pass app filter to watcher
        # (requires watcher.py to accept an optional app_filter argument)
        # self.watcher.set_app_filter(self._app_filter)
        # See watcher_eclipse_patch for ClipboardWatcher changes.
        self.watcher.start()

    # ══════════════════════════════════════════
    # Sync Engine
    # ══════════════════════════════════════════
    def _init_sync_engine(self):
        node_id = self._settings.get("node_id", "")
        port    = self._settings.get("api_port", 9090)
        if node_id:
            self._sync_engine = SyncEngine(local_node_id=node_id, api_port=port)

    # ══════════════════════════════════════════
    # API Server
    # ══════════════════════════════════════════
    def _start_api_server(self):
        if self._settings.get("api_enabled", False):
            port = self._settings.get("api_port", 9090)
            token = self._settings.get("api_token", "")
            node_id = self._settings.get("node_id", "")
            device_name = self._settings.get("device_name", "")
            if not token or not node_id:
                return
            from core.api_server import APIServerThread
            self._api_thread = APIServerThread(port, token, node_id, device_name, parent=self)
            self._api_thread.new_text_received.connect(self._on_api_new_text)
            self._api_thread.pairing_requested.connect(self._on_pairing_requested)
            self._api_thread.pairing_completed.connect(self._on_pairing_completed)
            self._api_thread.pairing_failed.connect(self._on_pairing_failed)
            self._api_thread.peer_unpaired.connect(self._on_peer_unpaired)
            self._api_thread.sync_received.connect(self._on_sync_received)
            self._api_thread.start()

    def _on_api_new_text(self, item_id: int, text: str):
        item = storage.get_item_by_id(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()
            # Push to peers
            if self._sync_engine:
                self._sync_engine.push("text", text)

    def _on_peer_unpaired(self, node_id: str):
        """Handle peer unpairing request"""
        for i in range(self.devices_list.count()):
            item = self.devices_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == node_id:
                data = item.data(Qt.ItemDataRole.UserRole + 1)
                item.setText(f"📱 {data['device_name']}")
                item.setForeground(QColor("#ccc"))
                self.statusBar().showMessage(f"Disconnected from {data['device_name']}")
                break

    def _on_sync_received(self, item_id: int, text: str):
        """Called when a trusted peer pushes a clipboard item to us."""
        item = storage.get_item_by_id(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()
            self.statusBar().showMessage(f"📥 Synced from peer: {text[:40]}..." if len(text) > 40 else f"📥 Synced: {text}")

    # ══════════════════════════════════════════
    # Network Discovery
    # ══════════════════════════════════════════
    def _start_discovery(self):
        port = self._settings.get("api_port", 9090)
        device_name = self._settings.get("device_name", "Unknown Ghost")
        node_id = self._settings.get("node_id", "ghost_node")
        
        self._discovery_thread = DotGhostDiscovery(port, device_name, node_id, parent=self)
        self._discovery_thread.signals.device_discovered.connect(self._on_device_discovered)
        self._discovery_thread.signals.device_removed.connect(self._on_device_removed)
        self._discovery_thread.start()

    def _on_device_discovered(self, node_id, data):
        # Prevent duplicates
        for i in range(self.devices_list.count()):
            if self.devices_list.item(i).data(Qt.ItemDataRole.UserRole) == node_id:
                return
        
        item = QListWidgetItem(f"📱 {data['device_name']}")
        item.setData(Qt.ItemDataRole.UserRole, node_id)
        # Store full data for pairing info (IP, Port, etc.)
        item.setData(Qt.ItemDataRole.UserRole + 1, data)
        item.setToolTip(f"ID: {node_id}\nIP: {data['ip']}:{data['port']}")
        if storage.is_peer_trusted(node_id):
            item.setText(f"🔒 {data['device_name']}")
            item.setForeground(QColor("#00ff41"))
            
        self.devices_list.addItem(item)
        self.statusBar().showMessage(f"Discovered peer: {data['device_name']}")

    def _on_device_double_clicked(self, item):
        """Initiate pairing when a device is double-clicked (Role: Initiator)."""
        node_id = item.data(Qt.ItemDataRole.UserRole)
        data = item.data(Qt.ItemDataRole.UserRole + 1)
        
        if storage.is_peer_trusted(node_id):
            msg = QMessageBox(self)
            msg.setWindowTitle("Device Options")
            msg.setText(f"<b>{data['device_name']}</b> is already paired and trusted.")
            msg.setInformativeText("What would you like to do?")
            msg.setIcon(QMessageBox.Icon.Question)
            
            reconnect_btn = msg.addButton("🔄 Reconnect", QMessageBox.ButtonRole.AcceptRole)
            reconnect_btn.setObjectName("BulkBtn")
            
            disconnect_btn = msg.addButton("❌ Disconnect", QMessageBox.ButtonRole.DestructiveRole)
            disconnect_btn.setObjectName("BulkBtnDanger")
            
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
            cancel_btn.setObjectName("BulkBtnCancel")
            
            msg.exec()
            
            if msg.clickedButton() == disconnect_btn or msg.clickedButton() == reconnect_btn:
                # Tell the peer to unpair us as well
                import threading
                def notify_peer_unpair():
                    try:
                        import requests
                        from core.sync_engine import _encrypt_for_peer
                        peer_info = storage.get_trusted_peer(node_id)
                        if peer_info:
                            shared_secret = peer_info.get("shared_secret")
                            peer_url = peer_info.get("ip_address")
                            local_node_id = self._settings.get("node_id")
                            payload = _encrypt_for_peer("unpair", shared_secret)
                            requests.post(f"{peer_url}/api/pair/unpair", json={"node_id": local_node_id, "payload": payload}, timeout=3)
                    except Exception as e:
                        print(f"Failed to notify peer about unpair: {e}")
                
                threading.Thread(target=notify_peer_unpair, daemon=True).start()
                
                storage.remove_trusted_peer(node_id)
                self.statusBar().showMessage(f"Unpaired with {data['device_name']}")
                item.setText(f"📱 {data['device_name']}")
                item.setForeground(QColor("#ccc"))
                
                if msg.clickedButton() == disconnect_btn:
                    return
                # If reconnect_btn, fall through to pairing below

        from ui.pairing_dialog import PairingDialog
        dialog = PairingDialog(
            role="initiator",
            peer_ip=data['ip'],
            peer_port=data['port'],
            peer_node_id=node_id,
            peer_name=data['device_name'],
            parent=self
        )
        if dialog.exec():
            # Successfully paired
            self.statusBar().showMessage(f"Successfully paired with {data['device_name']}!")
            # Update the list item to show paired status icon
            item.setText(f"🔒 {data['device_name']}")
            item.setForeground(QColor("#00ff41"))


    def _on_device_removed(self, node_id):
        for i in range(self.devices_list.count()):
            item = self.devices_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == node_id:
                self.devices_list.takeItem(i)
                break

    def _on_pairing_requested(self, node_id, device_name):
        """
        Called when another device initiates a pairing request (Role: Receiver).
        We show a dialog with a generated PIN.
        """
        # Get the salt that the server generated for this node
        salt = None
        if self._api_thread:
            salt = self._api_thread.pending_salts.get(node_id)
            
        from ui.pairing_dialog import PairingDialog
        dialog = PairingDialog(role="receiver", peer_node_id=node_id, 
                               peer_name=device_name, salt=salt, parent=self)
        
        self._active_pairing_dialogs[node_id] = dialog
        
        # Give the session to the server thread so it can complete the handshake
        if self._api_thread:
            self._api_thread.active_pairing_sessions[node_id] = dialog.session
            
        if dialog.exec():
            # Pairing accepted and completed via API
            pass
        else:
            # Denied or timed out - clean up session
            if self._api_thread:
                self._api_thread.active_pairing_sessions.pop(node_id, None)
                self._api_thread.pending_salts.pop(node_id, None)
        
        self._active_pairing_dialogs.pop(node_id, None)

    def _on_pairing_completed(self, node_id, device_name):
        self.statusBar().showMessage(f"Successfully paired with {device_name}!")
        self._on_device_discovered(node_id, {"device_name": device_name, "ip": "paired", "port": 0})
        
        # Close the dialog if it's still open
        if node_id in self._active_pairing_dialogs:
            self._active_pairing_dialogs[node_id].mark_completed()

    def _on_pairing_failed(self, node_id, error_message):
        self.statusBar().showMessage(f"Pairing failed: {error_message}", 5000)
        if node_id in self._active_pairing_dialogs:
            self._active_pairing_dialogs[node_id].mark_failed(error_message)


    # ══════════════════════════════════════════
    # Load history
    # ══════════════════════════════════════════
    def _load_history(self):
        self._current_view_mode  = "history"
        self._history_offset     = 0
        self._history_exhausted  = False
        self._load_more_history(initial=True)
        self._refresh_stats()

    def _load_more_history(self, initial: bool = False):
        """Load next PAGE_SIZE items from DB — called on init and on scroll."""
        if self._history_exhausted or getattr(self, '_is_loading', False):
            return

        self._is_loading = True
        try:
            limit  = self._settings.get("max_history", 200)

            # For history view, ensure we dont exceed max history.
            if self._current_view_mode == "history":
                remaining = limit - len(self._cards)
                if remaining <= 0:
                    self._history_exhausted = True
                    return
            else:
                remaining = 999999

            batch_size = min(_PAGE_SIZE, remaining)

            if self._current_view_mode == "collection":
                items = storage.get_items_by_collection(self.active_collection_id, limit=batch_size, offset=self._history_offset)
            elif self._current_view_mode == "search":
                items = storage.search_items(self._current_search_query, self._current_tag_filter, limit=batch_size, offset=self._history_offset)
            elif self._current_view_mode == "tag":
                items = storage.get_items_by_tag(self._current_tag_filter, limit=batch_size, offset=self._history_offset)
            else:
                items = storage.get_all_items(limit=batch_size, offset=self._history_offset)

            if not items:
                self._history_exhausted = True
                return

            if initial:
                # First page: newest items — insert oldest-first at top so newest ends on top
                for item in reversed(items):
                    self._add_card(item, at_top=True)
            else:
                # Subsequent pages: older items — append at bottom in storage order
                for item in items:
                    self._add_card(item, at_top=False)

            self._history_offset += len(items)

            if len(items) < batch_size:
                self._history_exhausted = True
        finally:
            self._is_loading = False

    def _on_scroll(self, value: int):
        """Load more history when user scrolls near the bottom."""
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() > 0 and value >= bar.maximum() * 0.85:
            self._load_more_history()

    # ══════════════════════════════════════════
    # Update Mechanisms
    # ══════════════════════════════════════════
    def check_for_updates(self):
        if self._update_thread and self._update_thread.isRunning():
            return  # Prevent spamming multiple threads
        self._update_thread = UpdateCheckerThread(self)
        self._update_thread.update_found.connect(self._on_update_found)
        self._update_thread.finished.connect(lambda: setattr(self, '_update_thread', None))
        self._update_thread.finished.connect(self._update_thread.deleteLater)
        self._update_thread.start()
        
    def _on_update_found(self, update_info: dict, asset_url: str):
        self._pending_update_info = update_info
        self._pending_asset_url = asset_url
        self.update_btn.show()

    def _show_updater_dialog(self):
        if not self._pending_update_info or not self._pending_asset_url:
            return
        from ui.updater_dialog import UpdaterDialog
        dialog = UpdaterDialog(self._pending_update_info, self._pending_asset_url, self)
        if dialog.exec():
            # Update was applied and sys.exit() or os.exec() was called.
            pass

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

        for c in storage.get_collections():
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
        menu.addAction(QAction("✏️ Rename", self,
                               triggered=lambda: self._rename_collection(coll_id)))
        menu.addAction(QAction("🗑️ Delete", self,
                               triggered=lambda: self._delete_collection(coll_id)))
        menu.exec(self.collections_list.mapToGlobal(pos))

    def _rename_collection(self, coll_id: int):
        old_name = next((c["name"] for c in storage.get_collections()
                         if c["id"] == coll_id), "")
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

        if self.active_collection_id is None:
            self._current_view_mode = "history"
        else:
            self._current_view_mode = "collection"

        # Clear current UI cards
        for card in list(self._cards.values()):
            self._remove_card(card.item_id)

        self._history_offset = 0
        self._history_exhausted = False
        self._load_more_history(initial=True)

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
        card.sig_tag_added.connect(self._on_tag_added)
        card.sig_tag_removed.connect(self._on_tag_removed)
        card.sig_clicked.connect(self._on_card_clicked)
        card.sig_reveal_requested.connect(self._on_reveal_requested)  # E003

        # E003: right-click → mark/unmark as secret
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card: self._on_card_context_menu(pos, c)
        )

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
    # E003 — Card right-click context menu
    # ══════════════════════════════════════════
    def _on_card_context_menu(self, pos, card: ItemCard):
        """
        Right-click menu on a card.
        Only shows encryption options if a master password is configured.
        """
        menu = QMenu(self)

        # ── Always-available actions ──
        copy_action = QAction("⎘  Copy", self)
        copy_action.triggered.connect(lambda: self._on_copy(card.item_id))
        menu.addAction(copy_action)

        pin_label = "📌  Unpin" if card.is_pinned else "📍  Pin"
        pin_action = QAction(pin_label, self)
        pin_action.triggered.connect(lambda: self._on_pin(card.item_id))
        menu.addAction(pin_action)

        # ── Eclipse: encryption (only if master password is set) ──
        if has_master_password() and card.item_type == "text":
            menu.addSeparator()

            if card.is_secret:
                # Already encrypted → offer to decrypt
                decrypt_action = QAction("🔓  Remove Encryption", self)
                decrypt_action.triggered.connect(
                    lambda: self._decrypt_card(card.item_id)
                )
                menu.addAction(decrypt_action)
            else:
                # Plain item → offer to encrypt
                encrypt_action = QAction("🔐  Mark as Secret", self)
                encrypt_action.triggered.connect(
                    lambda: self._encrypt_card(card.item_id)
                )
                menu.addAction(encrypt_action)

        menu.addSeparator()

        del_action = QAction("✕  Delete", self)
        del_action.triggered.connect(lambda: self._on_delete(card.item_id))
        menu.addAction(del_action)

        menu.exec(card.mapToGlobal(pos))

    def _rebuild_card_in_place(self, item_id: int) -> None:
        """
        Remove a card and re-insert it at the exact same position.
        Prevents the card from jumping to top or bottom after a rebuild.
        """
        # Remember current index in the layout before removing
        layout = self.cards_layout
        old_idx = -1
        for i in range(layout.count()):
            w = layout.itemAt(i)
            if w and w.widget() and getattr(w.widget(), "item_id", None) == item_id:
                old_idx = i
                break

        self._remove_card(item_id)

        item = storage.get_item_by_id(item_id)
        if not item:
            return

        card = ItemCard(item)
        card.sig_copy.connect(self._on_copy)
        card.sig_pin.connect(self._on_pin)
        card.sig_delete.connect(self._on_delete)
        card.sig_tag_added.connect(self._on_tag_added)
        card.sig_tag_removed.connect(self._on_tag_removed)
        card.sig_clicked.connect(self._on_card_clicked)
        card.sig_reveal_requested.connect(self._on_reveal_requested)
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card: self._on_card_context_menu(pos, c)
        )

        self._cards[item_id] = card

        # Re-insert at saved position (clamp to valid range)
        insert_at = old_idx if old_idx >= 0 else 0
        layout.insertWidget(insert_at, card)

    def _encrypt_card(self, item_id: int):
        """E003: Encrypt a single card's content on demand."""
        if self._active_key is None:
            # No active key → ask user to unlock first
            QMessageBox.information(
                self, "Unlock Required",
                "Please unlock the session first.\n"
                "Use the 🔒 button in the top bar."
            )
            return

        if storage.encrypt_item(item_id, self._active_key):
            self._rebuild_card_in_place(item_id)
            self.statusBar().showMessage("🔐 Item encrypted ✓")
        else:
            self.statusBar().showMessage("⚠ Could not encrypt item.")

    def _decrypt_card(self, item_id: int):
        """E003: Permanently decrypt a card (remove encryption)."""
        if self._active_key is None:
            QMessageBox.information(
                self, "Unlock Required",
                "Please unlock the session first."
            )
            return

        reply = QMessageBox.question(
            self, "Remove Encryption",
            "Permanently decrypt this item?\n"
            "It will be stored as plain text again.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if storage.decrypt_item_permanent(item_id, self._active_key):
            self._rebuild_card_in_place(item_id)
            self.statusBar().showMessage("🔓 Item decrypted ✓")
        else:
            self.statusBar().showMessage("⚠ Decryption failed — wrong key?")

    # ══════════════════════════════════════════
    # Watcher slots
    # ══════════════════════════════════════════
    def _on_new_text(self, item_id: int, text: str):
        item = storage.get_item_by_id(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()
            # Push to peers
            if self._sync_engine:
                self._sync_engine.push("text", text)
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
        cards    = self._visible_cards()
        card_ids = [c.item_id for c in cards]

        # Show hint if still visible (first interaction teaches them)
        if (modifiers & Qt.KeyboardModifier.ControlModifier
                and not self._settings.get("multiselect_hint_dismissed", False)):
            self._hint_strip.show()

        if modifiers & Qt.KeyboardModifier.ShiftModifier and self._last_clicked_id in card_ids:
            a, b = card_ids.index(self._last_clicked_id), card_ids.index(item_id)
            for iid in card_ids[min(a, b): max(a, b) + 1]:
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
            self.statusBar().showMessage(
                f"{count} item(s) selected  •  Ctrl+click to add, Shift+click to range"
            )
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
            if item and bool(item.get("is_pinned", 0)) != pin:
                new_state = storage.toggle_pin(iid)
                card = self._cards.get(iid)
                if card:
                    card.update_pin_state(new_state)
        self.statusBar().showMessage(
            f"{'Pinned' if pin else 'Unpinned'} {len(self._selected_ids)} items ✓"
        )
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
        with open(path, "w", encoding="utf-8") as f:
            f.write(storage.export_items(list(self._selected_ids), fmt))
        self.statusBar().showMessage(
            f"Exported {len(self._selected_ids)} items → {path} ✓"
        )

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
        self.statusBar().showMessage(
            f"Tag {tag} added to {len(self._selected_ids)} items ✓"
        )

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

        # Clear current cards first
        for card in list(self._cards.values()):
            self._remove_card(card.item_id)

        if not raw:
            if self.active_collection_id is not None:
                self._current_view_mode = "collection"
            else:
                self._current_view_mode = "history"
        else:
            tokens = raw.split()
            tag_tokens = [t for t in tokens if t.startswith("#")]
            text_tokens = [t for t in tokens if not t.startswith("#")]

            self._current_search_query = " ".join(text_tokens)
            self._current_tag_filter = tag_tokens[0] if tag_tokens else None

            if self._current_tag_filter and not self._current_search_query:
                self._current_view_mode = "tag"
            else:
                self._current_view_mode = "search"

        self._history_offset = 0
        self._history_exhausted = False
        self._load_more_history(initial=True)

    # ══════════════════════════════════════════
    # Clear History
    # ══════════════════════════════════════════
    def _clear_history(self):
        # ── Stage 1: Aura Check 😂 ─────────────────────────────
        msg = QMessageBox(self)
        msg.setWindowTitle("Aura Check 🐦⬛")
        msg.setText(
            "<b>Do you have the aura of the Pigeon Doctor</b><br>"
            "to delete all this data?"
        )
        msg.setInformativeText(
            "Unpinned items will be permanently erased.\n"
            "Pinned items and collections will survive."
        )
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        if msg.exec() != QMessageBox.StandardButton.Yes:
            return   # User backed out / changed their mind 🐔

        # ── Stage 2: Pigeon Doctor Loading Screen 🎬 ───────────
        from ui.purge_easter_egg import PurgeEasterEggDialog

        # The actual DB purge runs inside the dialog at t=600ms (background thread).
        # We only need to tell it *what* to delete.
        dialog = PurgeEasterEggDialog(
            purge_fn=storage.delete_unpinned_items,
            parent=self,
        )
        dialog.exec()   # blocks until fade-out + worker.wait() are done

        # ── Stage 3: Remove cards + refresh UI after curtain falls ──
        for iid in [iid for iid, c in self._cards.items() if not c.is_pinned]:
            self._remove_card(iid)
        self._focused_idx = -1
        self._refresh_stats()
        self.statusBar().showMessage("🐦⬛ The Pigeon Doctor has cleansed the board.")


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
        self._reset_auto_lock()
        key   = event.key()
        cards = self._visible_cards()

        if not cards:
            super().keyPressEvent(event)
            return

        if key == Qt.Key.Key_Down:
            self._set_card_focus(
                cards,
                0 if self._focused_idx == -1
                else min(self._focused_idx + 1, len(cards) - 1)
            )
        elif key == Qt.Key.Key_Up:
            self._set_card_focus(
                cards,
                0 if self._focused_idx <= 0 else self._focused_idx - 1
            )
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
    # Eclipse — Lock / Unlock / Stealth / Auto-lock
    # ══════════════════════════════════════════

    def set_active_key(self, key: bytes | None) -> None:
        """Called from main.py after startup unlock, or cleared on lock."""
        self._active_key = key

    def _lock(self) -> None:
        """Lock the session: clear key, hide window, show lock screen."""
        self._active_key = None
        self._auto_lock_timer.stop()

        # Blank out any revealed secret content in cards
        for card in self._cards.values():
            card.on_session_locked()

        self.hide()
        self._show_lock_screen()

    def _show_lock_screen(self) -> None:
        """Show LockScreen dialog; restore window on success."""
        dlg = LockScreen(setup=False)
        if dlg.exec() == LockScreen.DialogCode.Accepted:
            self._active_key = dlg.get_key()
            self._reset_auto_lock()
            self.show_and_raise()
            self.statusBar().showMessage("🔓 Unlocked")

    def _reset_auto_lock(self) -> None:
        """Restart the inactivity timer.  Called on any user interaction."""
        minutes = self._settings.get("auto_lock_minutes", 0)
        if minutes > 0 and has_master_password():
            self._auto_lock_timer.start(minutes * 60 * 1000)
        else:
            self._auto_lock_timer.stop()

    def _set_stealth(self, enable: bool) -> None:
        """
        Hide / show the window in taskbar and alt-tab switcher.
        Cross-platform implementation natively using Qt Tool window hints.
        """
        geo = self.geometry()
        
        if enable:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.Tool)
            self.resize(400, self.height())
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.Tool)
            self.resize(750, self.height())
            
        # Re-apply visibility and position after flag modification
        self.show()
        self.setGeometry(geo)

    # ── Reset timer on user activity ──────────────────────────────────────────

    def _on_reveal_requested(self, item_id: int) -> None:
        """
        E003: Called when a secret card's 👁 Reveal button is clicked.
        Decrypt with the active session key and push plaintext to the card.
        """
        if self._active_key is None:
            self.statusBar().showMessage(
                "⚠ Session is locked — unlock first to reveal secrets."
            )
            return

        plaintext = storage.decrypt_item(item_id, self._active_key)
        if plaintext is None:
            self.statusBar().showMessage(
                "⚠ Decryption failed — wrong key or corrupted data."
            )
            return

        card = self._cards.get(item_id)
        if card:
            card.reveal_content(plaintext)
            self.statusBar().showMessage("🔓 Secret revealed  (visible until locked)")

    def mousePressEvent(self, event):
        self._reset_auto_lock()
        super().mousePressEvent(event)

    # ══════════════════════════════════════════
    # Responsive UI (Media Queries style)
    # ══════════════════════════════════════════
    def resizeEvent(self, event):
        super().resizeEvent(event)

        # Compact mode: hide sidebar, shrink top bar buttons
        if self.width() < 650:
            self.sidebar.hide()
            self.clear_btn.setText("🗑️")
            self.clear_btn.setFixedSize(28, 28)
            self.stats_label.hide()
        else:
            self.sidebar.show()
            self.clear_btn.setText("Clear History")
            self.clear_btn.setMinimumWidth(90)
            self.clear_btn.setMaximumWidth(150)
            self.stats_label.show()

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
            if getattr(self, "_api_thread", None):
                self._api_thread.stop()
                self._api_thread.wait()   # FIX: prevents IOT instruction crash
            if getattr(self, "_discovery_thread", None):
                self._discovery_thread.stop()
                self._discovery_thread.wait()
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

        drop_pos   = event.position().toPoint()
        layout     = self.cards_layout
        new_target = None

        for i in range(layout.count() - 1):
            w_item = layout.itemAt(i)
            if w_item and w_item.widget() and w_item.widget().geometry().contains(drop_pos):
                new_target = w_item.widget()
                break

        # Clear old highlight (safely — card may have been deleted)
        if self._drop_target_card and self._drop_target_card is not new_target:
            try:
                self._drop_target_card.set_drop_target(False)
            except RuntimeError:
                pass
            self._drop_target_card = None

        # Apply new highlight
        if new_target:
            try:
                new_target.set_drop_target(True)
            except RuntimeError:
                new_target = None

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
        layout      = self.cards_layout

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

    def closeEvent(self, event):
        """Handle application shutdown: stop threads gracefully."""
        print("[Dashboard] Shutting down...")
        
        # 1. Stop Watcher
        if hasattr(self, 'watcher') and self.watcher:
            self.watcher.stop()
            
        # 2. Stop Discovery
        if hasattr(self, '_discovery_thread') and self._discovery_thread:
            self._discovery_thread.stop()
            self._discovery_thread.wait(2000) # wait up to 2s
            
        # 3. Stop API Server
        if hasattr(self, '_api_thread') and self._api_thread:
            self._api_thread.stop()
            self._api_thread.wait(2000)
            
        # 4. Stop Update Thread if running
        try:
            if hasattr(self, '_update_thread') and self._update_thread and self._update_thread.isRunning():
                self._update_thread.terminate()
                self._update_thread.wait(1000)
        except RuntimeError:
            pass # Object already deleted

        super().closeEvent(event)
