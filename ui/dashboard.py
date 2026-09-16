"""
ui/dashboard.py
───────────────
Main application window for DotGhostBoard.
Coordinates top-level layout, system tray, global hotkeys, and orchestrates
the domain services and behavioral controllers (CollectionController,
HistoryController, SecurityController, SyncController).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from core.app_filter import AppFilter
from core.constants import (
    AUTO_PIN_THRESHOLD,
    DEVICES_LIST_HEIGHT,
    PAGE_SIZE,
    PIN_SUGGESTION_THRESHOLD,
    PIN_TOAST_DURATION_MS,
    REL_TIME_INTERVAL_MS,
    SEARCH_DEBOUNCE_MS,
    SIDEBAR_WIDTH,
    TOP_BAR_HEIGHT,
)
from core.crypto import has_master_password
from core.network_discovery import DotGhostDiscovery
from core.paths import resource_path
from core.services import (
    CollectionService,
    HistoryService,
    SecurityService,
    SyncService,
)
from core.sync_engine import SyncEngine
from core.watcher import ClipboardWatcher
from ui.controllers import (
    CollectionController,
    HistoryController,
    SecurityController,
    SyncController,
)
from ui.lock_screen import LockScreen
from ui.settings import SettingsDialog, load_settings, save_settings
from ui.spotlight import SpotlightSearchDialog
from ui.widgets import ItemCard, PinSuggestionToast, StatsHeaderCard

logger = logging.getLogger(__name__)

QSS_PATH = resource_path("ui", "ghost.qss")


class UpdateCheckerThread(QThread):
    update_found = pyqtSignal(dict, str)  # update_info, asset_url

    def run(self):
        from core.config import APP_VERSION
        from core.updater import check_for_updates, identify_platform_asset

        update_info = check_for_updates(APP_VERSION)
        if update_info:
            asset_url = identify_platform_asset(update_info["assets"])
            if asset_url:
                self.update_found.emit(update_info, asset_url)


class Dashboard(QMainWindow):
    def __init__(self, startup_locked: bool = False, active_key: bytes | None = None):
        super().__init__()
        self.setWindowTitle("DotGhostBoard")
        self.resize(520, 680)
        self.setMinimumWidth(400)
        self.setWindowIcon(self._make_tray_icon())

        # ── Domain Services ──
        self._settings: dict = load_settings()
        self.collection_service = CollectionService()
        self.security_service = SecurityService()
        self.history_service = HistoryService()
        node_id = self._settings.get("node_id", "")
        port = self._settings.get("api_port", 9090)
        self.sync_service = SyncService(local_node_id=node_id, api_port=port)

        # ── Security Controller (Early Lifecycle) ──
        self.security_controller = SecurityController(
            service=self.security_service,
            parent_window=self,
            parent=self,
        )
        self.security_controller.lock_state_changed.connect(self._on_lock_state_changed)
        self.security_controller.status_message.connect(self.statusBar().showMessage)

        self._startup_locked: bool = startup_locked
        self._is_monitoring_paused: bool = False
        self._tray_retry_count: int = 0

        # ── Update & Sync State ──
        self._update_thread = None
        self._pending_update_info: dict | None = None
        self._pending_asset_url: str | None = None
        self._api_thread = None
        self._discovery_thread = None
        self._sync_engine: SyncEngine | None = None
        self._active_pairing_dialogs: dict = {}

        # ── Auto-Lock Timer ──
        self._auto_lock_timer = QTimer(self)
        self._auto_lock_timer.setSingleShot(True)
        self._auto_lock_timer.timeout.connect(self._lock)

        # ── Initialize UI & Subsystems ──
        self._load_stylesheet()
        self._build_ui()
        self._setup_tray()
        self._start_watcher()
        self._load_history()
        self._refresh_sidebar()
        self._clean_captures()

        self._start_api_server()
        self._start_discovery()
        self._init_sync_engine()

        # Connect property so SettingsDialog can access main_dashboard
        QApplication.instance().setProperty("main_dashboard", self)

        if self._settings.get("auto_update_check", True):
            self.check_for_updates()

        if active_key is not None:
            self.security_controller.set_active_key(active_key)
        elif startup_locked:
            self.security_controller.lock()

        # App filter
        self._app_filter = AppFilter(
            mode=self._settings.get("app_filter_mode", "blacklist"),
            app_list=self._settings.get("app_filter_list", []),
        )

        # Stealth mode
        if self._settings.get("stealth_mode", False):
            self._set_stealth(True)

        # Spotlight Search Overlay
        self.spotlight_dialog = SpotlightSearchDialog(self)
        self.spotlight_dialog.sig_item_selected.connect(self._on_spotlight_item_selected)

        # In-window shortcut (Ctrl+F to focus search)
        self.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.find_shortcut.activated.connect(self.search_box.setFocus)

        # Periodic timer for relative timestamps & stats
        self._rel_time_timer = QTimer(self)
        self._rel_time_timer.setInterval(REL_TIME_INTERVAL_MS)
        self._rel_time_timer.timeout.connect(self._update_relative_times)
        self._rel_time_timer.start()

    # ══════════════════════════════════════════
    # Build UI
    # ══════════════════════════════════════════
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_hbox = QHBoxLayout(central)
        main_hbox.setContentsMargins(0, 0, 0, 0)
        main_hbox.setSpacing(0)

        # ── Sidebar ──
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(SIDEBAR_WIDTH)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 8)
        sidebar_layout.setSpacing(10)

        # Collections Header
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
        sidebar_layout.addLayout(sidebar_header)
        sidebar_layout.addWidget(self.collections_list)

        self.collection_controller = CollectionController(
            service=self.collection_service,
            list_widget=self.collections_list,
            parent=self,
        )

        # Devices Header & List
        sidebar_layout.addSpacing(16)
        dev_header = QHBoxLayout()
        dev_label = QLabel("🌐 DEVICES")
        dev_label.setStyleSheet("color: #666; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
        dev_header.addWidget(dev_label)
        dev_header.addStretch()
        sidebar_layout.addLayout(dev_header)

        self.devices_list = QListWidget()
        self.devices_list.setObjectName("DevicesList")
        self.devices_list.setFixedHeight(DEVICES_LIST_HEIGHT)
        self.devices_list.setToolTip("Double-click a device to pair")
        sidebar_layout.addWidget(self.devices_list)

        self.sync_controller = SyncController(
            service=self.sync_service,
            devices_list=self.devices_list,
            settings=self._settings,
            parent_window=self,
            parent=self,
        )

        main_hbox.addWidget(self.sidebar)

        # ── Main Content Area ──
        main_area = QWidget()
        root = QVBoxLayout(main_area)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top Bar
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(TOP_BAR_HEIGHT)
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
        self.clear_btn.setObjectName("ClearHistoryBtn")
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.setToolTip("Delete all un-pinned items")
        self.clear_btn.clicked.connect(self._clear_history)

        self.lock_btn = QPushButton("🔒")
        self.lock_btn.setObjectName("SessionLockBtn")
        self.lock_btn.setFixedSize(28, 28)
        self.lock_btn.setToolTip("Lock session (Eclipse)")
        self.lock_btn.clicked.connect(self._lock)
        self.lock_btn.setVisible(has_master_password())

        self.update_btn = QPushButton("🎁 New Update!")
        self.update_btn.setStyleSheet("""
            background: #18251d;
            color: #77dd98;
            border: 1px solid #31513b;
            padding: 0 10px;
            border-radius: 5px;
            font-weight: 600;
        """)
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

        # Dashboard Stats Header
        self.stats_header = StatsHeaderCard()
        root.addWidget(self.stats_header)

        # Search Bar
        search_frame = QFrame()
        search_frame.setStyleSheet("padding: 8px 12px;")
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(0, 0, 0, 0)

        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setFixedHeight(40)
        self.search_box.setPlaceholderText("Search clips, tags, or collections…")

        search_layout.addWidget(self.search_box)
        root.addWidget(search_frame)

        # Multi-select hint strip
        self._hint_strip = QFrame()
        self._hint_strip.setObjectName("HintStrip")
        self._hint_strip.setFixedHeight(32)

        hint_layout = QHBoxLayout(self._hint_strip)
        hint_layout.setContentsMargins(12, 0, 8, 0)
        hint_layout.setSpacing(16)

        hint_text = QLabel(
            "Multi-select  ·  "
            "<span style='color:#8ac99d'>Ctrl+Click</span> select  ·  "
            "<span style='color:#8ac99d'>Shift+Click</span> range  ·  "
            "<span style='color:#8ac99d'>Esc</span> clear"
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
        if self._settings.get("multiselect_hint_dismissed", False):
            self._hint_strip.hide()

        # Scroll Area for Cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(12, 8, 12, 8)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()

        self.scroll.setWidget(self.cards_container)
        root.addWidget(self.scroll)

        # Drag & Drop inside cards container
        self.cards_container.setAcceptDrops(True)
        self.cards_container.dragEnterEvent = self._drag_enter
        self.cards_container.dragMoveEvent = self._drag_move
        self.cards_container.dropEvent = self._drop_event
        self._drop_target_card: Optional[ItemCard] = None

        # Bulk Actions Toolbar
        self._bulk_bar = QFrame()
        self._bulk_bar.setObjectName("BulkBar")
        self._bulk_bar.setFixedHeight(52)

        bulk_layout = QHBoxLayout(self._bulk_bar)
        bulk_layout.setContentsMargins(16, 0, 16, 0)
        bulk_layout.setSpacing(8)

        self._bulk_count_lbl = QLabel("0 selected")
        self._bulk_count_lbl.setObjectName("BulkCountLabel")

        btn_pin = QPushButton("📍 Pin All")
        btn_unpin = QPushButton("📌 Unpin All")
        btn_delete = QPushButton("✕ Delete All")
        btn_export = QPushButton("📤 Export")
        btn_tag = QPushButton("🏷 Add Tag")
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
        self._bulk_bar.hide()

        main_hbox.addWidget(main_area)

        # Status bar
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background: #0c0d0e;
                color: #697177;
                border-top: 1px solid #1d2022;
                font-size: 10px;
                padding-left: 6px;
            }
        """)
        self.statusBar().showMessage("Watching clipboard…")

        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cards_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Multi-select state
        self._selected_ids: set[int] = set()
        self._last_clicked_id: Optional[int] = None

        # ── History Controller ──
        self.history_controller = HistoryController(
            service=self.history_service,
            cards_layout=self.cards_layout,
            search_box=self.search_box,
            scroll_area=self.scroll,
            stats_card=self.stats_header,
            parent=self,
        )

        # ── Inter-Controller Signal Coordination ──
        # Collection -> History
        self.collection_controller.collection_selected.connect(
            self.history_controller.filter_by_collection
        )
        self.collection_controller.collection_changed.connect(
            self.history_controller.reload
        )
        self.collection_controller.item_moved_to_collection.connect(
            self._on_item_moved_to_collection
        )
        self.collection_controller.status_message.connect(
            self.statusBar().showMessage
        )

        # History <-> Security
        self.history_controller.secret_copy_requested.connect(
            self.security_controller.handle_secret_copy
        )
        self.security_controller.copy_payload_ready.connect(
            self.history_controller.record_copy_result
        )
        self.history_controller.encrypt_requested.connect(
            lambda iid: self.security_controller.encrypt_item(iid, self)
        )
        self.history_controller.decrypt_requested.connect(
            lambda iid: self.security_controller.decrypt_item(iid, confirm=True, parent_widget=self)
        )
        self.security_controller.item_security_changed.connect(
            self.history_controller.refresh_item
        )
        self.history_controller.reveal_requested.connect(
            self._on_reveal_requested
        )

        # History -> Pin Suggestion Toast
        self.history_controller.pin_suggested.connect(
            self._on_pin_suggested
        )

        # History -> Local Watcher Paste
        self.history_controller.item_copied_ready.connect(
            self._on_item_copied_ready
        )

        # Status message routing
        self.history_controller.status_message.connect(self.statusBar().showMessage)
        self.sync_controller.status_message.connect(self.statusBar().showMessage)

    # ══════════════════════════════════════════
    # Coordinator Properties & Compatibility Shims
    # ══════════════════════════════════════════
    @property
    def _cards(self) -> dict[int, ItemCard]:
        if hasattr(self, "history_controller"):
            return self.history_controller.cards
        return getattr(self, "_cards_fallback", {})

    @_cards.setter
    def _cards(self, val):
        if hasattr(self, "history_controller"):
            self.history_controller._cards = val
        else:
            self._cards_fallback = val

    @property
    def active_collection_id(self) -> int | None:
        if hasattr(self, "collection_controller"):
            return self.collection_controller.active_collection_id
        return getattr(self, "_active_coll_fallback", None)

    @active_collection_id.setter
    def active_collection_id(self, val: int | None):
        if hasattr(self, "collection_controller"):
            self.collection_controller.active_collection_id = val
        else:
            self._active_coll_fallback = val

    @property
    def _active_key(self) -> bytes | None:
        if hasattr(self, "security_controller"):
            return self.security_controller.active_key
        return getattr(self, "_active_key_fallback", None)

    @_active_key.setter
    def _active_key(self, val: bytes | None):
        if hasattr(self, "security_controller"):
            self.security_controller.set_active_key(val)
        else:
            self._active_key_fallback = val

    def _is_locked(self) -> bool:
        """Check whether the dashboard is currently in a locked state."""
        if hasattr(self, "security_controller"):
            return self._startup_locked or self.security_controller.is_locked
        return bool(self._startup_locked or (has_master_password() and self._active_key is None))

    def set_active_key(self, key: bytes | None) -> None:
        """Called from main.py or after unlock, or cleared on lock."""
        self._active_key = key
        if key is not None:
            self._startup_locked = False
            if hasattr(self, "watcher") and self.watcher and not self._is_monitoring_paused:
                self.watcher.start()
            if getattr(self, "_api_thread", None) is None:
                self._start_api_server()
            if getattr(self, "_discovery_thread", None) is None:
                self._start_discovery()
            if getattr(self, "_sync_engine", None) is None:
                self._init_sync_engine()
        self._update_tray_menu_and_tooltip()

    def _on_lock_state_changed(self, is_locked: bool):
        if is_locked:
            if hasattr(self, "watcher") and self.watcher:
                self.watcher.stop()
            if hasattr(self, "_api_thread") and self._api_thread:
                self._api_thread.stop()
                self._api_thread = None
            if hasattr(self, "_discovery_thread") and self._discovery_thread:
                self._discovery_thread.stop()
                self._discovery_thread = None
        else:
            if hasattr(self, "watcher") and self.watcher and not self._is_monitoring_paused:
                self.watcher.start()
            if getattr(self, "_api_thread", None) is None:
                self._start_api_server()
            if getattr(self, "_discovery_thread", None) is None:
                self._start_discovery()
            if getattr(self, "_sync_engine", None) is None:
                self._init_sync_engine()
        self._update_tray_menu_and_tooltip()

    def _on_pin_suggested(self, item_id: int, preview: str):
        if hasattr(self, "_active_toast") and self._active_toast:
            try:
                self._active_toast.deleteLater()
            except Exception:
                pass

        toast = PinSuggestionToast(item_id, preview, parent=self)
        toast.sig_pin.connect(self.history_controller.on_pin)
        toast.sig_close.connect(lambda: setattr(self, "_active_toast", None))
        self._active_toast = toast
        toast.adjustSize()
        toast.move(20, self.height() - toast.height() - 30)
        toast.show()

    def _on_item_copied_ready(self, item_id: int, item: dict):
        if hasattr(self, "watcher") and self.watcher:
            self.watcher.mark_self_paste()
            self.watcher.paste_item_to_clipboard(item)

    def _on_item_moved_to_collection(self, item_id: int, target_coll_id: int | None):
        if self.active_collection_id is not None and target_coll_id != self.active_collection_id:
            self.history_controller.remove_card(item_id)
        self.history_controller.refresh_stats()

    def _on_reveal_requested(self, item_id: int) -> None:
        plaintext = self.security_controller.reveal_secret(item_id)
        if plaintext is not None:
            card = self.history_controller.cards.get(item_id)
            if card:
                card.reveal_content(plaintext)

    def _refresh_sidebar(self):
        if hasattr(self, "collection_controller"):
            self.collection_controller.refresh()

    def _create_collection(self):
        if hasattr(self, "collection_controller"):
            self.collection_controller.prompt_create_collection(self)

    def _load_history(self):
        if hasattr(self, "history_controller"):
            self.history_controller.load_more(initial=True)

    def _load_more_history(self, initial: bool = False):
        if hasattr(self, "history_controller"):
            self.history_controller.load_more(initial=initial)

    def _refresh_stats(self):
        if hasattr(self, "history_controller"):
            self.history_controller.refresh_stats()

    def _add_card(self, item: dict, at_top: bool = True):
        if hasattr(self, "history_controller"):
            self.history_controller.add_card(item, at_top=at_top)

    def _remove_card(self, item_id: int):
        if hasattr(self, "history_controller"):
            self.history_controller.remove_card(item_id)

    def _rebuild_card_in_place(self, item_id: int):
        if hasattr(self, "history_controller"):
            self.history_controller.refresh_item(item_id)

    def _on_new_text(self, item_id: int, text: str):
        if hasattr(self, "history_controller"):
            self.history_controller.on_text_captured(item_id, text)

    def _on_new_image(self, item_id: int, file_path: str):
        if hasattr(self, "history_controller"):
            self.history_controller.on_image_captured(item_id, file_path)

    def _on_new_video(self, item_id: int, video_path: str):
        if hasattr(self, "history_controller"):
            self.history_controller.on_video_captured(item_id, video_path)

    def _on_thumb_ready(self, item_id: int, thumb_path: str):
        if hasattr(self, "history_controller"):
            self.history_controller.on_thumb_ready(item_id, thumb_path)

    def _on_copy(self, item_id: int):
        if hasattr(self, "history_controller"):
            self.history_controller.on_copy(item_id)

    def _on_pin(self, item_id: int):
        if hasattr(self, "history_controller"):
            self.history_controller.on_pin(item_id)

    def _on_delete(self, item_id: int):
        if hasattr(self, "history_controller"):
            self.history_controller.on_delete(item_id)

    def _encrypt_card(self, item_id: int):
        if hasattr(self, "security_controller"):
            self.security_controller.encrypt_item(item_id, self)

    def _decrypt_card(self, item_id: int):
        if hasattr(self, "security_controller"):
            self.security_controller.decrypt_item(item_id, confirm=True, parent_widget=self)

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
    def _make_tray_icon(self) -> QIcon:
        px = QPixmap(32, 32)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#00ff41"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.setPen(QColor("#000000"))
        f = QFont("monospace", 14, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "G")
        p.end()
        return QIcon(px)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self._make_tray_icon(), self)
        self.tray.activated.connect(self._on_tray_click)
        self._ensure_tray_visible()
        self._update_tray_menu_and_tooltip()

    def _ensure_tray_visible(self):
        if not hasattr(self, "tray") or self.tray is None:
            return
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
            self._update_tray_menu_and_tooltip()
        else:
            if self._tray_retry_count < 10:
                self._tray_retry_count += 1
                delay = min(500 * self._tray_retry_count, 3000)
                QTimer.singleShot(delay, self._ensure_tray_visible)

    def _update_tray_menu_and_tooltip(self):
        if not hasattr(self, "tray") or self.tray is None:
            return
        is_locked = self._is_locked()

        if is_locked:
            self.tray.setToolTip("DotGhostBoard — 🔒 Locked (Click to unlock)")
        elif self._is_monitoring_paused:
            self.tray.setToolTip("DotGhostBoard — ⏸ Monitoring paused")
        else:
            self.tray.setToolTip("DotGhostBoard — Monitoring clipboard")

        menu = QMenu()
        show_action = QAction("👻 Open DotGhostBoard", self)
        show_action.triggered.connect(self.show_and_raise)
        menu.addAction(show_action)

        if not is_locked:
            if self._is_monitoring_paused:
                toggle_monitor_action = QAction("▶ Resume Monitoring", self)
                toggle_monitor_action.triggered.connect(self._resume_monitoring)
            else:
                toggle_monitor_action = QAction("⏸ Pause Monitoring", self)
                toggle_monitor_action.triggered.connect(self._pause_monitoring)
            menu.addAction(toggle_monitor_action)

            settings_action = QAction("⚙ Settings", self)
            settings_action.triggered.connect(self._open_settings)
            menu.addAction(settings_action)

        menu.addSeparator()

        if has_master_password():
            if is_locked:
                lock_action = QAction("🔓 Unlock DotGhostBoard", self)
                lock_action.triggered.connect(self._show_lock_screen)
            else:
                lock_action = QAction("🔒 Lock", self)
                lock_action.triggered.connect(self._lock)
            menu.addAction(lock_action)
            menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)

    def _pause_monitoring(self):
        self._is_monitoring_paused = True
        if hasattr(self, "watcher") and self.watcher:
            self.watcher.stop()
        self._update_tray_menu_and_tooltip()
        self.statusBar().showMessage("⏸ Clipboard monitoring paused")

    def _resume_monitoring(self):
        if self._is_locked():
            self._is_monitoring_paused = True
            self._update_tray_menu_and_tooltip()
            self.statusBar().showMessage("🔒 Unlock DotGhostBoard before resuming clipboard monitoring")
            return

        self._is_monitoring_paused = False
        if hasattr(self, "watcher") and self.watcher:
            self.watcher.start()
        self._update_tray_menu_and_tooltip()
        self.statusBar().showMessage("▶ Clipboard monitoring active")

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visibility()

    def show_and_raise(self):
        if (self._startup_locked or self._active_key is None) and has_master_password():
            self._show_lock_screen()
            return
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show_and_raise()

    # ══════════════════════════════════════════
    # Settings
    # ══════════════════════════════════════════
    def _open_settings(self):
        if self._is_locked():
            self._show_lock_screen()
            return

        dlg = SettingsDialog(self)
        if dlg.exec():
            self._settings = load_settings()
            self._enforce_history_limit()
            self._clean_captures()
            self._app_filter.update(
                self._settings.get("app_filter_mode", "blacklist"),
                self._settings.get("app_filter_list", []),
            )
            self._set_stealth(self._settings.get("stealth_mode", False))
            self.lock_btn.setVisible(has_master_password())
            self._reset_auto_lock()
            self.statusBar().showMessage("Settings saved ✓")

    def _enforce_history_limit(self):
        """Trim unpinned cards if count exceeds max_history."""
        limit = self._settings.get("max_history", 200)
        unpinned = [iid for iid, c in self._cards.items() if not c.is_pinned]
        excess = len(self._cards) - limit
        if excess > 0:
            for iid in unpinned[-excess:]:
                self.history_service.delete_item(iid)
                self._remove_card(iid)
            self._refresh_stats()

    def _clean_captures(self):
        keep = self._settings.get("max_captures", 100)
        removed = self.history_service.clean_old_captures(keep)
        if removed:
            for iid in list(self._cards):
                if self.history_service.get_item(iid) is None:
                    self._remove_card(iid)
            self._refresh_stats()
            print(f"[Dashboard] Auto-cleanup removed {removed} old capture(s)")

    # ══════════════════════════════════════════
    # Watcher & Background Services
    # ══════════════════════════════════════════
    def _start_watcher(self):
        self.watcher = ClipboardWatcher()
        self.watcher.new_text_captured.connect(self.history_controller.on_text_captured)
        self.watcher.new_text_captured.connect(lambda iid, text: self.sync_controller.broadcast_text(text))
        self.watcher.new_image_captured.connect(self.history_controller.on_image_captured)
        self.watcher.new_video_captured.connect(self.history_controller.on_video_captured)
        self.watcher.thumb_ready.connect(self.history_controller.on_thumb_ready)
        if not self._is_locked():
            self.watcher.start()

    def _init_sync_engine(self):
        if self._is_locked():
            return
        node_id = self._settings.get("node_id", "")
        port = self._settings.get("api_port", 9090)
        self.sync_service.configure(node_id, port)
        self._sync_engine = self.sync_service._sync_engine

    def _start_api_server(self):
        if self._is_locked():
            return
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
        item = self.history_service.get_item(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()
            if self.sync_controller:
                self.sync_controller.broadcast_text(text)

    def _on_peer_unpaired(self, node_id: str):
        if hasattr(self, "sync_controller"):
            self.sync_controller.handle_peer_unpaired(node_id)

    def _on_sync_received(self, item_id: int, text: str):
        item = self.history_service.get_item(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()
            self.statusBar().showMessage(
                f"📥 Synced from peer: {text[:40]}..." if len(text) > 40 else f"📥 Synced: {text}"
            )

    def _start_discovery(self):
        if self._is_locked():
            return
        port = self._settings.get("api_port", 9090)
        device_name = self._settings.get("device_name", "Unknown Ghost")
        node_id = self._settings.get("node_id", "ghost_node")

        self._discovery_thread = DotGhostDiscovery(port, device_name, node_id, parent=self)
        self._discovery_thread.signals.device_discovered.connect(self._on_device_discovered)
        self._discovery_thread.signals.device_removed.connect(self._on_device_removed)
        self._discovery_thread.start()

    def _on_device_discovered(self, node_id, data):
        if hasattr(self, "sync_controller"):
            self.sync_controller.add_or_update_device(node_id, data)

    def _on_device_removed(self, node_id):
        if hasattr(self, "sync_controller"):
            self.sync_controller.remove_device(node_id)

    def _on_device_double_clicked(self, item):
        if hasattr(self, "sync_controller"):
            self.sync_controller._on_item_double_clicked(item)

    def _on_pairing_requested(self, node_id, device_name):
        salt = None
        if self._api_thread:
            salt = self._api_thread.pending_salts.get(node_id)

        from ui.pairing_dialog import PairingDialog

        dialog = PairingDialog(
            role="receiver",
            peer_node_id=node_id,
            peer_name=device_name,
            salt=salt,
            parent=self,
        )

        self._active_pairing_dialogs[node_id] = dialog

        if self._api_thread:
            self._api_thread.active_pairing_sessions[node_id] = dialog.session

        if dialog.exec():
            pass
        else:
            if self._api_thread:
                self._api_thread.active_pairing_sessions.pop(node_id, None)
                self._api_thread.pending_salts.pop(node_id, None)

        self._active_pairing_dialogs.pop(node_id, None)

    def _on_pairing_completed(self, node_id, device_name):
        self.statusBar().showMessage(f"Successfully paired with {device_name}!")
        self._on_device_discovered(node_id, {"device_name": device_name, "ip": "paired", "port": 0})
        if node_id in self._active_pairing_dialogs:
            self._active_pairing_dialogs[node_id].mark_completed()

    def _on_pairing_failed(self, node_id, error_message):
        self.statusBar().showMessage(f"Pairing failed: {error_message}", 5000)
        if node_id in self._active_pairing_dialogs:
            self._active_pairing_dialogs[node_id].mark_failed(error_message)

    # ══════════════════════════════════════════
    # Update Mechanisms
    # ══════════════════════════════════════════
    def check_for_updates(self):
        if self._update_thread and self._update_thread.isRunning():
            return
        self._update_thread = UpdateCheckerThread(self)
        self._update_thread.update_found.connect(self._on_update_found)
        self._update_thread.finished.connect(lambda: setattr(self, "_update_thread", None))
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
        dialog.exec()

    # ══════════════════════════════════════════
    # Multi-Select & Bulk Actions
    # ══════════════════════════════════════════
    def _on_card_clicked(self, item_id: int, modifiers):
        cards = self._visible_cards()
        card_ids = [c.item_id for c in cards]

        if (
            modifiers & Qt.KeyboardModifier.ControlModifier
            and not self._settings.get("multiselect_hint_dismissed", False)
        ):
            self._hint_strip.show()

        if modifiers & Qt.KeyboardModifier.ShiftModifier and self._last_clicked_id in card_ids:
            a, b = card_ids.index(self._last_clicked_id), card_ids.index(item_id)
            for iid in card_ids[min(a, b) : max(a, b) + 1]:
                self._selected_ids.add(iid)
                if iid in self._cards:
                    self._cards[iid].set_selected(True)
        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            if item_id in self._selected_ids:
                self._selected_ids.discard(item_id)
                if item_id in self._cards:
                    self._cards[item_id].set_selected(False)
            else:
                self._selected_ids.add(item_id)
                if item_id in self._cards:
                    self._cards[item_id].set_selected(True)
            self._last_clicked_id = item_id
        else:
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
        self._hint_strip.hide()
        self._settings["multiselect_hint_dismissed"] = True
        save_settings(self._settings)

    def _update_bulk_bar(self):
        count = len(self._selected_ids)
        if count >= 2:
            self._bulk_count_lbl.setText(f"{count} selected")
            self._bulk_bar.show()
        else:
            self._bulk_bar.hide()

    def _bulk_pin(self, pin: bool):
        for iid in list(self._selected_ids):
            item = self.history_service.get_item(iid)
            if item and bool(item.get("is_pinned", 0)) != pin:
                new_state = self.history_service.toggle_pin(iid)
                card = self._cards.get(iid)
                if card and new_state is not None:
                    card.update_pin_state(new_state)
        self.statusBar().showMessage(
            f"{'Pinned' if pin else 'Unpinned'} {len(self._selected_ids)} items ✓"
        )
        self._refresh_stats()

    def _bulk_delete(self):
        count = len(self._selected_ids)
        reply = QMessageBox.question(
            self,
            "Delete Selected",
            f"Delete {count} selected item(s)?\nPinned items will be skipped.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        deleted = 0
        for iid in list(self._selected_ids):
            if self.history_service.delete_item(iid):
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
            self, "Export Format", "Choose format:", ["txt", "json"], 0, False
        )
        if not ok:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Items",
            f"dotghost_export.{fmt}",
            f"{'Text' if fmt == 'txt' else 'JSON'} Files (*.{fmt})",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.history_service.export_items(list(self._selected_ids), fmt))
        self.statusBar().showMessage(
            f"Exported {len(self._selected_ids)} items → {path} ✓"
        )

    def _bulk_add_tag(self):
        tag, ok = QInputDialog.getText(
            self, "Add Tag", "Tag to add to all selected items:", QLineEdit.EchoMode.Normal, "#"
        )
        if not ok or not tag.strip():
            return
        tag = tag.strip().lower()
        tag = tag if tag.startswith("#") else f"#{tag}"
        for iid in list(self._selected_ids):
            updated = self.history_service.add_tag(iid, tag)
            card = self._cards.get(iid)
            if card and tag in updated:
                card.on_tag_added(tag)
        self.statusBar().showMessage(
            f"Tag {tag} added to {len(self._selected_ids)} items ✓"
        )

    def _on_tag_added(self, item_id: int, tag: str):
        if hasattr(self, "history_controller"):
            self.history_controller.on_tag_added(item_id, tag)

    def _on_tag_removed(self, item_id: int, tag: str):
        if hasattr(self, "history_controller"):
            self.history_controller.on_tag_removed(item_id, tag)

    # ══════════════════════════════════════════
    # Clear History & Reset Count
    # ══════════════════════════════════════════
    def _clear_history(self):
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
            return

        from ui.purge_easter_egg import PurgeEasterEggDialog

        dialog = PurgeEasterEggDialog(
            purge_fn=self.history_service.delete_unpinned_items,
            parent=self,
        )
        dialog.exec()

        for iid in [iid for iid, c in self._cards.items() if not c.is_pinned]:
            self._remove_card(iid)
        if hasattr(self, "history_controller"):
            self.history_controller._focused_idx = -1
        self._refresh_stats()
        self.statusBar().showMessage("🐦⬛ The Pigeon Doctor has cleansed the board.")

    def _on_reset_count(self, item_id: int):
        if hasattr(self, "history_controller"):
            self.history_controller.on_reset_count(item_id)

    def _update_relative_times(self):
        for card in self._cards.values():
            card.update_relative_time()
        self._refresh_stats()

    # ══════════════════════════════════════════
    # Spotlight Overlay
    # ══════════════════════════════════════════
    def show_spotlight(self):
        if self._is_locked():
            if not self._show_lock_screen(show_dashboard=False):
                return

        if not hasattr(self, "spotlight_dialog") or not self.spotlight_dialog:
            return

        if self.spotlight_dialog.isVisible():
            self.spotlight_dialog.hide()
            return

        self.spotlight_dialog.show()
        self.spotlight_dialog.raise_()
        self.spotlight_dialog.activateWindow()

    def _on_spotlight_item_selected(self, item: dict):
        item_id = item.get("id")
        if item_id:
            self._on_copy(item_id)

    # ══════════════════════════════════════════
    # Keyboard Navigation
    # ══════════════════════════════════════════
    def _visible_cards(self) -> list[ItemCard]:
        result = []
        layout = self.cards_layout
        for i in range(layout.count() - 1):
            item = layout.itemAt(i)
            if item and item.widget() and item.widget().isVisible():
                result.append(item.widget())
        return result

    def _set_card_focus(self, cards: list[ItemCard], new_idx: int):
        focused_idx = getattr(self.history_controller, "_focused_idx", -1)
        if 0 <= focused_idx < len(cards):
            cards[focused_idx].set_focused(False)

        if hasattr(self, "history_controller"):
            self.history_controller._focused_idx = new_idx
        if 0 <= new_idx < len(cards):
            card = cards[new_idx]
            card.set_focused(True)
            self.scroll.ensureWidgetVisible(card)

    def keyPressEvent(self, event: QKeyEvent):
        self._reset_auto_lock()
        key = event.key()
        cards = self._visible_cards()

        if not cards:
            super().keyPressEvent(event)
            return

        focused_idx = getattr(self.history_controller, "_focused_idx", -1)
        if key == Qt.Key.Key_Down:
            self._set_card_focus(
                cards,
                0 if focused_idx == -1 else min(focused_idx + 1, len(cards) - 1),
            )
        elif key == Qt.Key.Key_Up:
            self._set_card_focus(
                cards,
                0 if focused_idx <= 0 else focused_idx - 1,
            )
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if 0 <= focused_idx < len(cards):
                self._on_copy(cards[focused_idx].item_id)
            else:
                super().keyPressEvent(event)
        elif key == Qt.Key.Key_Escape:
            if 0 <= focused_idx < len(cards):
                cards[focused_idx].set_focused(False)
            if hasattr(self, "history_controller"):
                self.history_controller._focused_idx = -1
            self._clear_selection()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self._reset_auto_lock()
        super().mousePressEvent(event)

    # ══════════════════════════════════════════
    # Eclipse Lock / Unlock / Stealth / Auto-lock
    # ══════════════════════════════════════════
    def _lock(self) -> None:
        if hasattr(self, "security_controller"):
            self.security_controller.lock()
        else:
            self._active_key = None
        self._auto_lock_timer.stop()
        if hasattr(self, "watcher") and self.watcher:
            self.watcher.stop()
        if hasattr(self, "_api_thread") and self._api_thread:
            self._api_thread.stop()
            self._api_thread = None
        if hasattr(self, "_discovery_thread") and self._discovery_thread:
            self._discovery_thread.stop()
            self._discovery_thread = None
        self._update_tray_menu_and_tooltip()

        if hasattr(self, "history_controller"):
            self.history_controller.on_session_locked()

        self.hide()
        self._show_lock_screen()

    def _show_lock_screen(self, *, show_dashboard: bool = True) -> bool:
        if hasattr(self, "security_controller"):
            unlocked = self.security_controller.prompt_unlock(self)
            if not unlocked:
                return False
            self._startup_locked = False
            self.set_active_key(self.security_controller.active_key)
        else:
            dlg = LockScreen(setup=False)
            if dlg.exec() != LockScreen.DialogCode.Accepted:
                return False
            self._startup_locked = False
            self.set_active_key(dlg.get_key())

        self._reset_auto_lock()
        self._update_tray_menu_and_tooltip()

        if show_dashboard:
            self.show()
            self.raise_()
            self.activateWindow()
            self.statusBar().showMessage("🔓 Unlocked")

        return True

    def _reset_auto_lock(self) -> None:
        minutes = self._settings.get("auto_lock_minutes", 0)
        if minutes > 0 and has_master_password():
            self._auto_lock_timer.start(minutes * 60 * 1000)
        else:
            self._auto_lock_timer.stop()

    def _set_stealth(self, enable: bool) -> None:
        geo = self.geometry()
        if enable:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.Tool)
            self.resize(400, self.height())
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.Tool)
            self.resize(750, self.height())
        self.show()
        self.setGeometry(geo)

    # ══════════════════════════════════════════
    # Responsive UI
    # ══════════════════════════════════════════
    def resizeEvent(self, event):
        super().resizeEvent(event)
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
    # Close & Shutdown
    # ══════════════════════════════════════════
    def closeEvent(self, event):
        if event.spontaneous():
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "DotGhostBoard",
                "Running in background. Click tray icon to restore.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return

        print("[Dashboard] Shutting down...")
        if self._settings.get("clear_on_exit", False):
            self.history_service.delete_unpinned_items()

        if hasattr(self, "watcher") and self.watcher:
            self.watcher.stop()
        if hasattr(self, "_discovery_thread") and self._discovery_thread:
            self._discovery_thread.stop()
            self._discovery_thread.wait(2000)
        if hasattr(self, "_api_thread") and self._api_thread:
            self._api_thread.stop()
            self._api_thread.wait(2000)
        try:
            if hasattr(self, "_update_thread") and self._update_thread and self._update_thread.isRunning():
                self._update_thread.terminate()
                self._update_thread.wait(1000)
        except RuntimeError:
            pass

        self.tray.hide()
        event.accept()

    # ══════════════════════════════════════════
    # Card Reordering Drag & Drop
    # ══════════════════════════════════════════
    def _drag_enter(self, event):
        if event.mimeData().hasFormat("application/x-dotghost-card-id"):
            event.acceptProposedAction()

    def _drag_move(self, event):
        if not event.mimeData().hasFormat("application/x-dotghost-card-id"):
            return

        drop_pos = event.position().toPoint()
        layout = self.cards_layout
        new_target = None

        for i in range(layout.count() - 1):
            w_item = layout.itemAt(i)
            if w_item and w_item.widget() and w_item.widget().geometry().contains(drop_pos):
                new_target = w_item.widget()
                break

        if self._drop_target_card and self._drop_target_card is not new_target:
            try:
                self._drop_target_card.set_drop_target(False)
            except RuntimeError:
                pass
            self._drop_target_card = None

        if new_target:
            try:
                new_target.set_drop_target(True)
            except RuntimeError:
                new_target = None

        self._drop_target_card = new_target
        event.acceptProposedAction()

    def _drop_event(self, event):
        if self._drop_target_card:
            self._drop_target_card.set_drop_target(False)
            self._drop_target_card = None

        if not event.mimeData().hasFormat("application/x-dotghost-card-id"):
            return
        try:
            dragged_id = int(
                event.mimeData().data("application/x-dotghost-card-id").data().decode()
            )
        except (ValueError, AttributeError):
            return

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

        all_cards = [
            layout.itemAt(i).widget()
            for i in range(layout.count() - 1)
            if layout.itemAt(i) and layout.itemAt(i).widget()
        ]

        dragged_card = self._cards.get(dragged_id)
        if dragged_card and dragged_card in all_cards:
            all_cards.remove(dragged_card)
            target_idx = (
                all_cards.index(target_card)
                if target_card in all_cards
                else len(all_cards)
            )
            all_cards.insert(target_idx, dragged_card)

            for order, card in enumerate(all_cards):
                self.history_service.update_sort_order(card.item_id, order)

            for card in all_cards:
                layout.removeWidget(card)
            for order, card in enumerate(all_cards):
                layout.insertWidget(order, card)

        event.acceptProposedAction()
