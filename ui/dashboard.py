"""
ui/dashboard.py
───────────────
Main application window for DotGhostBoard.
Coordinates top-level layout, system tray, global hotkeys, and orchestrates
the domain services and behavioral controllers (CollectionController,
HistoryController, SecurityController, SyncController, UpdateController).
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLineEdit, QMainWindow,
    QVBoxLayout, QWidget,
)

from core.app_filter import AppFilter
from core.constants import REL_TIME_INTERVAL_MS, VAULT_DRAWER_WIDTH
from core.crypto import has_master_password
from core.paths import resource_path
from core.services import (
    CollectionService, HistoryService, SecurityService, SyncService,
)
from core.watcher import ClipboardWatcher
from ui.controllers import (
    CollectionController, HistoryController, SecurityController,
    SyncController, UpdateController, wire_dashboard_controllers,
)
from ui.lock_screen import LockScreen
from ui.settings import SettingsDialog, load_settings
from ui.spotlight import SpotlightSearchDialog
from ui.components import (
    BulkToolbar, CardsView, DashboardTrayManager, SidebarWidget, TopBarWidget,
)
from ui.vault import attach_vault, attach_send_to_vault
from ui.widgets import StatsHeaderCard
from ui.window_utils import (
    bring_to_current_workspace, is_on_current_workspace,
    prepare_dialog_for_current_workspace,
)
from ui.dashboard_compat import DashboardCompatibilityMixin

logger = logging.getLogger(__name__)
QSS_PATH = resource_path("ui", "ghost.qss")


class Dashboard(DashboardCompatibilityMixin, QMainWindow):
    def __init__(
        self, startup_locked: bool = False, active_key: bytes | None = None
    ):
        super().__init__()
        self.setWindowTitle("DotGhostBoard")
        self.resize(520, 680)
        self.setMinimumWidth(400)
        self.setWindowIcon(self._make_tray_icon())

        self._settings: dict = load_settings()
        self.collection_service = CollectionService()
        self.security_service = SecurityService()
        self.history_service = HistoryService()
        self.sync_service = SyncService(
            local_node_id=self._settings.get("node_id", ""),
            api_port=self._settings.get("api_port", 9090),
        )

        self.security_controller = SecurityController(
            service=self.security_service,
            parent_window=self,
            parent=self,
        )
        self.security_controller.lock_state_changed.connect(
            self._on_lock_state_changed
        )
        self.security_controller.status_message.connect(
            self.statusBar().showMessage
        )
        self.security_controller.auto_lock_triggered.connect(self._lock)

        self._startup_locked: bool = startup_locked
        self._is_monitoring_paused: bool = False

        self.update_controller = UpdateController(
            parent_window=self, parent=self
        )
        self.update_controller.update_found.connect(self._on_update_found)

        self._load_stylesheet()
        self._build_ui()
        self._setup_tray()
        self._start_watcher()
        attach_send_to_vault(self)
        self._load_history()
        self._refresh_sidebar()
        self._clean_captures()
        self._start_api_server()
        self._start_discovery()
        self._init_sync_engine()

        QApplication.instance().setProperty("main_dashboard", self)

        if self._settings.get("auto_update_check", True):
            self.check_for_updates()
        if active_key is not None:
            self.security_controller.set_active_key(active_key)
        elif startup_locked:
            self.security_controller.lock()

        self._app_filter = AppFilter(
            mode=self._settings.get("app_filter_mode", "blacklist"),
            app_list=self._settings.get("app_filter_list", []),
        )
        if self._settings.get("stealth_mode", False):
            self._set_stealth(True)

        self.spotlight_dialog = SpotlightSearchDialog(self)
        self.spotlight_dialog.sig_item_selected.connect(
            self._on_spotlight_item_selected
        )

        self.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.find_shortcut.activated.connect(self.search_box.setFocus)

        self._rel_time_timer = QTimer(self)
        self._rel_time_timer.timeout.connect(self._update_relative_times)
        self._rel_time_timer.start(REL_TIME_INTERVAL_MS)

    # ══════════════════════════════════════════
    # Build UI & Wire Controllers
    # ══════════════════════════════════════════
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_hbox = QHBoxLayout(central)
        main_hbox.setContentsMargins(0, 0, 0, 0)
        main_hbox.setSpacing(0)

        self.sidebar_widget = SidebarWidget(parent=self)
        self.sidebar_widget.create_collection_requested.connect(
            self._create_collection
        )
        self.collection_controller = CollectionController(
            service=self.collection_service,
            list_widget=self.sidebar_widget.collections_list,
            parent=self,
        )
        self.sync_controller = SyncController(
            service=self.sync_service,
            devices_list=self.sidebar_widget.devices_list,
            settings=self._settings,
            parent_window=self,
            parent=self,
        )
        main_hbox.addWidget(self.sidebar_widget)

        main_area = QWidget()
        root = QVBoxLayout(main_area)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.topbar = TopBarWidget(parent=self)
        self.topbar.settings_clicked.connect(self._open_settings)
        self.topbar.clear_history_clicked.connect(self._clear_history)
        self.topbar.lock_clicked.connect(self._lock)
        self.topbar.update_clicked.connect(self._show_updater_dialog)
        self.topbar.set_lock_visible(has_master_password())
        root.addWidget(self.topbar)

        self.stats_header = StatsHeaderCard()
        root.addWidget(self.stats_header)

        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setFixedHeight(40)
        self.search_box.setPlaceholderText(
            "Search clips, tags, or collections…"
        )
        search_frame = QFrame()
        search_frame.setStyleSheet("padding: 8px 12px;")
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(self.search_box)
        root.addWidget(search_frame)

        self.bulk_toolbar = BulkToolbar(parent=self, parent_widget=main_area)
        if self._settings.get("multiselect_hint_dismissed", False):
            self.bulk_toolbar.hide_hint()
        root.addWidget(self.bulk_toolbar.hint_strip)

        self.cards_view = CardsView(parent=self)
        self.cards_view.card_reordered.connect(self._on_card_reordered)
        root.addWidget(self.cards_view)
        root.addWidget(self.bulk_toolbar.bulk_bar)
        main_hbox.addWidget(main_area)

        attach_vault(self, main_hbox)

        self.statusBar().setStyleSheet(
            "QStatusBar { background: #0c0d0e; color: #697177; "
            "border-top: 1px solid #1d2022; font-size: 10px; "
            "padding-left: 6px; }"
        )
        self.statusBar().showMessage("Watching clipboard…")
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cards_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.history_controller = HistoryController(
            service=self.history_service,
            cards_layout=self.cards_layout,
            search_box=self.search_box,
            scroll_area=self.scroll,
            stats_card=self.stats_header,
            parent=self,
        )

        # Wire inter-controller and UI signals
        wire_dashboard_controllers(self)

    def _is_locked(self) -> bool:
        if hasattr(self, "security_controller"):
            return self._startup_locked or self.security_controller.is_locked
        return bool(
            self._startup_locked
            or (has_master_password() and self._active_key is None)
        )

    def set_active_key(self, key: bytes | None) -> None:
        self._active_key = key
        if key is not None:
            self._startup_locked = False
            w = getattr(self, "watcher", None)
            if w and not self._is_monitoring_paused:
                self.watcher.start()
            self._start_api_server()
            self._start_discovery()
            self._init_sync_engine()
        self._update_tray_menu_and_tooltip()

    def _on_lock_state_changed(self, is_locked: bool):
        if is_locked:
            vc = getattr(self, "vault_controller", None)
            if vc and vc.is_unlocked:
                vc.lock()
            if getattr(self, "watcher", None):
                self.watcher.stop()
            if getattr(self, "sync_controller", None):
                self.sync_controller.stop_all()
        else:
            w = getattr(self, "watcher", None)
            if w and not self._is_monitoring_paused:
                self.watcher.start()
            self._start_api_server()
            self._start_discovery()
            self._init_sync_engine()
        self._update_tray_menu_and_tooltip()

    # ══════════════════════════════════════════
    # Stylesheet, Watcher & System Tray
    # ══════════════════════════════════════════
    def _load_stylesheet(self):
        if os.path.exists(QSS_PATH):
            with open(QSS_PATH, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _setup_tray(self):
        tm = self.tray_manager = DashboardTrayManager(parent=self)
        tm.configure_notifications(self._settings)
        tm.toggle_visibility_requested.connect(self.toggle_visibility)
        tm.show_requested.connect(self.show_and_raise)  # notification click → always show
        tm.pause_monitoring_requested.connect(self._pause_monitoring)
        tm.resume_monitoring_requested.connect(self._resume_monitoring)
        tm.open_settings_requested.connect(self._open_settings)
        tm.lock_requested.connect(self._lock)
        tm.unlock_requested.connect(self._show_lock_screen)
        tm.quit_requested.connect(QApplication.quit)
        tm.setup_tray()
        self._update_tray_menu_and_tooltip()

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
            self.statusBar().showMessage(
                "🔒 Unlock DotGhostBoard before resuming clipboard monitoring"
            )
            return
        self._is_monitoring_paused = False
        if hasattr(self, "watcher") and self.watcher:
            self.watcher.start()
        self._update_tray_menu_and_tooltip()
        self.statusBar().showMessage("▶ Clipboard monitoring active")

    def show_and_raise(self):
        has_pwd = has_master_password()
        is_unauth = self._startup_locked or self._active_key is None
        if is_unauth and has_pwd:
            self._show_lock_screen()
            return
        bring_to_current_workspace(self)

    def toggle_visibility(self):
        if self.isVisible() and is_on_current_workspace(self):
            vc = getattr(self, "vault_controller", None)
            if vc and vc.is_unlocked:
                vc.lock(wipe_clipboard=False)
            self.hide()
        else:
            self.show_and_raise()

    def _open_settings(self):
        if self._is_locked():
            self._show_lock_screen()
            return
        dlg = SettingsDialog(self)
        prepare_dialog_for_current_workspace(dlg)
        if dlg.exec():
            self._settings = load_settings()
            if getattr(self, "tray_manager", None):
                self.tray_manager.configure_notifications(self._settings)
            self._enforce_history_limit()
            self._clean_captures()
            self._app_filter.update(
                self._settings.get("app_filter_mode", "blacklist"),
                self._settings.get("app_filter_list", []),
            )
            self._set_stealth(self._settings.get("stealth_mode", False))
            self.lock_btn.setVisible(has_master_password())
            self._reset_auto_lock()
            if hasattr(self, "watcher"):
                self.watcher.set_monitor_primary(
                    self._settings.get("monitor_primary_selection", False)
                )
                self.watcher.set_sync_primary_to_clipboard(
                    self._settings.get("sync_primary_to_clipboard", True)
                )
                self.watcher.set_capture_sound_enabled(
                    self._settings.get("capture_sound_enabled", False)
                )
            self.statusBar().showMessage("Settings saved ✓")

    def _start_watcher(self):
        w = self.watcher = ClipboardWatcher()
        w.set_monitor_primary(self._settings.get("monitor_primary_selection", False))
        w.set_sync_primary_to_clipboard(self._settings.get("sync_primary_to_clipboard", True))
        w.set_capture_sound_enabled(self._settings.get("capture_sound_enabled", False))
        w.primary_fragment_replaced.connect(self.history_controller.remove_card)
        w.new_text_captured.connect(self.history_controller.on_text_captured)
        w.new_text_captured.connect(
            lambda iid, text: self.sync_controller.broadcast_text(text)
        )
        w.new_image_captured.connect(self.history_controller.on_image_captured)
        w.new_video_captured.connect(self.history_controller.on_video_captured)
        w.thumb_ready.connect(self.history_controller.on_thumb_ready)
        if not self._is_locked():
            w.start()

    # ══════════════════════════════════════════
    # Spotlight, Navigation & Shutdown
    # ══════════════════════════════════════════
    def show_spotlight(self):
        if self._is_locked() and not self._show_lock_screen(
            show_dashboard=False
        ):
            return
        dlg = getattr(self, "spotlight_dialog", None)
        if dlg:
            if dlg.isVisible() and is_on_current_workspace(dlg):
                dlg.hide()
            else:
                bring_to_current_workspace(dlg)

    def keyPressEvent(self, event: QKeyEvent):
        self._reset_auto_lock()
        hc = getattr(self, "history_controller", None)
        if hc and hc.handle_key_press(event, self._visible_cards()):
            return
        if event.key() == Qt.Key.Key_Escape:
            if hasattr(self, "search_box") and self.search_box.text():
                self.search_box.clear()
                return
            self.hide()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self._reset_auto_lock()
        super().mousePressEvent(event)

    def _lock(self) -> None:
        if getattr(self, "security_controller", None):
            self.security_controller.lock()
        else:
            self._active_key = None
        if getattr(self, "watcher", None):
            self.watcher.stop()
        if getattr(self, "sync_controller", None):
            self.sync_controller.stop_all()
        self._update_tray_menu_and_tooltip()
        hc = getattr(self, "history_controller", None)
        if hc:
            hc.on_session_locked()
        self.hide()
        self._show_lock_screen()

    def _show_lock_screen(self, *, show_dashboard: bool = True) -> bool:
        if hasattr(self, "security_controller"):
            if not self.security_controller.prompt_unlock(self):
                return False
            self._startup_locked = False
            self.set_active_key(self.security_controller.active_key)
        else:
            dlg = LockScreen(setup=False)
            prepare_dialog_for_current_workspace(dlg)
            if dlg.exec() != LockScreen.DialogCode.Accepted:
                return False
            self._startup_locked = False
            self.set_active_key(dlg.get_key())

        self._reset_auto_lock()
        self._update_tray_menu_and_tooltip()
        if show_dashboard:
            bring_to_current_workspace(self)
            self.statusBar().showMessage("🔓 Unlocked")
        return True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        vp = getattr(self, "vault_panel", None)
        vault_w = VAULT_DRAWER_WIDTH if vp and vp.isVisible() else 0
        avail = self.width() - vault_w
        is_compact = avail < 650
        if getattr(self, "sidebar_widget", None):
            self.sidebar_widget.set_collapsed(is_compact)
        if getattr(self, "topbar", None):
            self.topbar.set_compact_mode(is_compact)

    def closeEvent(self, event):
        if event.spontaneous():
            event.ignore()
            vc = getattr(self, "vault_controller", None)
            if vc and vc.is_unlocked:
                vc.lock(wipe_clipboard=False)
            self.hide()
            self.tray_manager.show_message(
                "DotGhostBoard",
                "Running in background. Click tray icon to restore.",
                timeout=2000,
                action_callback=self.show_and_raise,
                dedupe_key="background",
                once=True,
            )
            return

        print("[Dashboard] Shutting down...")
        if self._settings.get("clear_on_exit", False):
            self.history_service.delete_unpinned_items()
        if hasattr(self, "watcher") and self.watcher:
            self.watcher.stop()
        if hasattr(self, "sync_controller"):
            self.sync_controller.stop_all(2000)
        if hasattr(self, "update_controller"):
            self.update_controller.cleanup()
        if hasattr(self, "tray") and self.tray:
            self.tray.hide()
        event.accept()
