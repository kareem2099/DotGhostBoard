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
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QKeyEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLineEdit, QMainWindow,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from core.app_filter import AppFilter
from core.constants import REL_TIME_INTERVAL_MS
from core.crypto import has_master_password
from core.paths import resource_path
from core.services import CollectionService, HistoryService, SecurityService, SyncService
from core.watcher import ClipboardWatcher
from ui.controllers import (
    CollectionController, HistoryController, SecurityController,
    SyncController, UpdateController,
)
from ui.controllers.update_controller import UpdateCheckerThread
from ui.lock_screen import LockScreen
from ui.settings import SettingsDialog, load_settings, save_settings
from ui.spotlight import SpotlightSearchDialog
from ui.components import BulkToolbar, CardsView, DashboardTrayManager, SidebarWidget, TopBarWidget
from ui.widgets import ItemCard, PinSuggestionToast, StatsHeaderCard

logger = logging.getLogger(__name__)
QSS_PATH = resource_path("ui", "ghost.qss")


class Dashboard(QMainWindow):
    def __init__(self, startup_locked: bool = False, active_key: bytes | None = None):
        super().__init__()
        self.setWindowTitle("DotGhostBoard")
        self.resize(520, 680)
        self.setMinimumWidth(400)
        self.setWindowIcon(self._make_tray_icon())

        self._settings: dict = load_settings()
        self.collection_service = CollectionService()
        self.security_service = SecurityService()
        self.history_service = HistoryService()
        self.sync_service = SyncService(local_node_id=self._settings.get("node_id", ""), api_port=self._settings.get("api_port", 9090))

        self.security_controller = SecurityController(service=self.security_service, parent_window=self, parent=self)
        self.security_controller.lock_state_changed.connect(self._on_lock_state_changed)
        self.security_controller.status_message.connect(self.statusBar().showMessage)
        self.security_controller.auto_lock_triggered.connect(self._lock)

        self._startup_locked: bool = startup_locked
        self._is_monitoring_paused: bool = False

        self.update_controller = UpdateController(parent_window=self, parent=self)
        self.update_controller.update_found.connect(self._on_update_found)

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

        QApplication.instance().setProperty("main_dashboard", self)

        if self._settings.get("auto_update_check", True): self.check_for_updates()
        if active_key is not None: self.security_controller.set_active_key(active_key)
        elif startup_locked: self.security_controller.lock()

        self._app_filter = AppFilter(mode=self._settings.get("app_filter_mode", "blacklist"), app_list=self._settings.get("app_filter_list", []))
        if self._settings.get("stealth_mode", False): self._set_stealth(True)

        self.spotlight_dialog = SpotlightSearchDialog(self)
        self.spotlight_dialog.sig_item_selected.connect(self._on_spotlight_item_selected)

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
        self.sidebar_widget.create_collection_requested.connect(self._create_collection)
        self.collection_controller = CollectionController(service=self.collection_service, list_widget=self.sidebar_widget.collections_list, parent=self)
        self.sync_controller = SyncController(service=self.sync_service, devices_list=self.sidebar_widget.devices_list, settings=self._settings, parent_window=self, parent=self)
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
        self.search_box.setPlaceholderText("Search clips, tags, or collections…")
        search_frame = QFrame()
        search_frame.setStyleSheet("padding: 8px 12px;")
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(self.search_box)
        root.addWidget(search_frame)

        self.bulk_toolbar = BulkToolbar(parent=self, parent_widget=main_area)
        if self._settings.get("multiselect_hint_dismissed", False): self.bulk_toolbar.hide_hint()
        root.addWidget(self.bulk_toolbar.hint_strip)

        self.cards_view = CardsView(parent=self)
        self.cards_view.card_reordered.connect(self._on_card_reordered)
        root.addWidget(self.cards_view)
        root.addWidget(self.bulk_toolbar.bulk_bar)
        main_hbox.addWidget(main_area)

        self.statusBar().setStyleSheet("QStatusBar { background: #0c0d0e; color: #697177; border-top: 1px solid #1d2022; font-size: 10px; padding-left: 6px; }")
        self.statusBar().showMessage("Watching clipboard…")
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cards_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.history_controller = HistoryController(service=self.history_service, cards_layout=self.cards_layout, search_box=self.search_box, scroll_area=self.scroll, stats_card=self.stats_header, parent=self)

        # Wire inter-controller and UI signals
        bt, hc, sc, cc = self.bulk_toolbar, self.history_controller, self.security_controller, self.collection_controller
        bt.pin_all_requested.connect(hc.bulk_pin)
        bt.delete_all_requested.connect(lambda: hc.bulk_delete(self))
        bt.export_requested.connect(lambda: hc.bulk_export(self))
        bt.add_tag_requested.connect(lambda: hc.bulk_add_tag(self))
        bt.cancel_requested.connect(hc.clear_selection)
        bt.hint_dismissed.connect(self._dismiss_hint)
        hc.selection_changed.connect(bt.update_selection_count)
        hc.selection_changed.connect(self._on_selection_count_changed)

        cc.collection_selected.connect(hc.filter_by_collection)
        cc.collection_changed.connect(hc.reload)
        cc.item_moved_to_collection.connect(self._on_item_moved_to_collection)

        hc.secret_copy_requested.connect(sc.handle_secret_copy)
        sc.copy_payload_ready.connect(hc.record_copy_result)
        hc.encrypt_requested.connect(lambda iid: sc.encrypt_item(iid, self))
        hc.decrypt_requested.connect(lambda iid: sc.decrypt_item(iid, confirm=True, parent_widget=self))
        sc.item_security_changed.connect(hc.refresh_item)
        hc.reveal_requested.connect(self._on_reveal_requested)
        hc.pin_suggested.connect(self._on_pin_suggested)
        hc.item_copied_ready.connect(self._on_item_copied_ready)

        self.sync_controller.api_text_received.connect(self._on_sync_item_received)
        self.sync_controller.sync_received_signal.connect(self._on_sync_item_received)

        hc.status_message.connect(self.statusBar().showMessage)
        cc.status_message.connect(self.statusBar().showMessage)
        self.sync_controller.status_message.connect(self.statusBar().showMessage)

    # ══════════════════════════════════════════
    # Coordinator Properties & Compatibility Shims
    # ══════════════════════════════════════════
    sidebar = property(lambda s: getattr(s, "sidebar_widget", None))
    collections_list = property(lambda s: getattr(s.sidebar_widget, "collections_list", None) if hasattr(s, "sidebar_widget") else None)
    devices_list = property(lambda s: getattr(s.sidebar_widget, "devices_list", None) if hasattr(s, "sidebar_widget") else None)
    stats_label = property(lambda s: getattr(s.topbar, "stats_label", None) if hasattr(s, "topbar") else None)
    clear_btn = property(lambda s: getattr(s.topbar, "clear_btn", None) if hasattr(s, "topbar") else None)
    lock_btn = property(lambda s: getattr(s.topbar, "lock_btn", None) if hasattr(s, "topbar") else None)
    update_btn = property(lambda s: getattr(s.topbar, "update_btn", None) if hasattr(s, "topbar") else None)
    scroll = property(lambda s: getattr(s, "cards_view", None))
    cards_container = property(lambda s: getattr(s.cards_view, "cards_container", None) if hasattr(s, "cards_view") else None)
    cards_layout = property(lambda s: getattr(s.cards_view, "cards_layout", None) if hasattr(s, "cards_view") else None)
    _hint_strip = property(lambda s: getattr(s.bulk_toolbar, "hint_strip", None) if hasattr(s, "bulk_toolbar") else None)
    _bulk_bar = property(lambda s: getattr(s.bulk_toolbar, "bulk_bar", None) if hasattr(s, "bulk_toolbar") else None)
    _bulk_count_lbl = property(lambda s: getattr(s.bulk_toolbar, "bulk_count_lbl", None) if hasattr(s, "bulk_toolbar") else None)
    tray = property(lambda s: getattr(s.tray_manager, "tray", None) if hasattr(s, "tray_manager") else None)

    _cards = property(lambda s: s.history_controller.cards if hasattr(s, "history_controller") else getattr(s, "_cards_fallback", {}), lambda s, v: setattr(s.history_controller, "_cards", v) if hasattr(s, "history_controller") else setattr(s, "_cards_fallback", v))
    active_collection_id = property(lambda s: s.collection_controller.active_collection_id if hasattr(s, "collection_controller") else getattr(s, "_active_coll_fallback", None), lambda s, v: setattr(s.collection_controller, "active_collection_id", v) if hasattr(s, "collection_controller") else setattr(s, "_active_coll_fallback", v))
    _active_key = property(lambda s: s.security_controller.active_key if hasattr(s, "security_controller") else getattr(s, "_active_key_fallback", None), lambda s, v: s.security_controller.set_active_key(v) if hasattr(s, "security_controller") else setattr(s, "_active_key_fallback", v))
    _selected_ids = property(lambda s: s.history_controller.selected_ids if hasattr(s, "history_controller") else getattr(s, "_selected_ids_fallback", set()), lambda s, v: setattr(s.history_controller, "_selected_ids", set(v)) if hasattr(s, "history_controller") else setattr(s, "_selected_ids_fallback", set(v)))
    _last_clicked_id = property(lambda s: s.history_controller._last_clicked_id if hasattr(s, "history_controller") else getattr(s, "_last_clicked_id_fallback", None), lambda s, v: setattr(s.history_controller, "_last_clicked_id", v) if hasattr(s, "history_controller") else setattr(s, "_last_clicked_id_fallback", v))
    _api_thread = property(lambda s: s.sync_controller.api_thread if hasattr(s, "sync_controller") else getattr(s, "_api_thread_fallback", None), lambda s, v: setattr(s.sync_controller, "_api_thread", v) if hasattr(s, "sync_controller") else setattr(s, "_api_thread_fallback", v))
    _discovery_thread = property(lambda s: s.sync_controller.discovery_thread if hasattr(s, "sync_controller") else getattr(s, "_discovery_thread_fallback", None), lambda s, v: setattr(s.sync_controller, "_discovery_thread", v) if hasattr(s, "sync_controller") else setattr(s, "_discovery_thread_fallback", v))
    _sync_engine = property(lambda s: s.sync_controller.sync_engine if hasattr(s, "sync_controller") else getattr(s, "_sync_engine_fallback", None), lambda s, v: setattr(s.sync_controller, "_sync_engine", v) if hasattr(s, "sync_controller") else setattr(s, "_sync_engine_fallback", v))
    _active_pairing_dialogs = property(lambda s: s.sync_controller.active_pairing_dialogs if hasattr(s, "sync_controller") else getattr(s, "_active_pairing_dialogs_fallback", {}))
    _update_thread = property(lambda s: s.update_controller.update_thread if hasattr(s, "update_controller") else getattr(s, "_update_thread_fallback", None), lambda s, v: setattr(s.update_controller, "_update_thread", v) if hasattr(s, "update_controller") else setattr(s, "_update_thread_fallback", v))
    _pending_update_info = property(lambda s: s.update_controller.pending_update_info if hasattr(s, "update_controller") else getattr(s, "_pending_update_info_fallback", None))
    _pending_asset_url = property(lambda s: s.update_controller.pending_asset_url if hasattr(s, "update_controller") else getattr(s, "_pending_asset_url_fallback", None))
    _auto_lock_timer = property(lambda s: s.security_controller.auto_lock_timer if hasattr(s, "security_controller") else getattr(s, "_auto_lock_timer_fallback", None))

    def _is_locked(self) -> bool:
        if hasattr(self, "security_controller"): return self._startup_locked or self.security_controller.is_locked
        return bool(self._startup_locked or (has_master_password() and self._active_key is None))

    def set_active_key(self, key: bytes | None) -> None:
        self._active_key = key
        if key is not None:
            self._startup_locked = False
            if getattr(self, "watcher", None) and not self._is_monitoring_paused: self.watcher.start()
            self._start_api_server()
            self._start_discovery()
            self._init_sync_engine()
        self._update_tray_menu_and_tooltip()

    def _on_lock_state_changed(self, is_locked: bool):
        if is_locked:
            if getattr(self, "watcher", None): self.watcher.stop()
            if getattr(self, "sync_controller", None): self.sync_controller.stop_all()
        else:
            if getattr(self, "watcher", None) and not self._is_monitoring_paused: self.watcher.start()
            self._start_api_server()
            self._start_discovery()
            self._init_sync_engine()
        self._update_tray_menu_and_tooltip()

    def _on_pin_suggested(self, item_id: int, preview: str):
        if getattr(self, "_active_toast", None):
            try: self._active_toast.deleteLater()
            except Exception: pass
        toast = self._active_toast = PinSuggestionToast(item_id, preview, parent=self)
        toast.sig_pin.connect(self.history_controller.on_pin)
        toast.sig_close.connect(lambda: setattr(self, "_active_toast", None))
        toast.adjustSize()
        toast.move(20, self.height() - toast.height() - 30)
        toast.show()

    def _on_item_copied_ready(self, item_id: int, item: dict):
        if getattr(self, "watcher", None):
            self.watcher.mark_self_paste(); self.watcher.paste_item_to_clipboard(item)

    def _on_item_moved_to_collection(self, item_id: int, target_coll_id: int | None):
        if self.active_collection_id is not None and target_coll_id != self.active_collection_id:
            self.history_controller.remove_card(item_id)
        self.history_controller.refresh_stats()

    def _on_reveal_requested(self, item_id: int) -> None:
        plaintext = self.security_controller.reveal_secret(item_id)
        if plaintext is not None and (card := self.history_controller.cards.get(item_id)):
            card.reveal_content(plaintext)

    def _on_sync_item_received(self, item_id: int, text: str):
        if (item := self.history_service.get_item(item_id)):
            self._add_card(item, at_top=True); self._refresh_stats()

    def _on_api_new_text(self, item_id: int, text: str):
        self._on_sync_item_received(item_id, text)
        if getattr(self, "sync_controller", None): self.sync_controller.broadcast_text(text)

    def _on_sync_received(self, item_id: int, text: str):
        self._on_sync_item_received(item_id, text)
        self.statusBar().showMessage(f"📥 Synced from peer: {text[:40]}..." if len(text) > 40 else f"📥 Synced: {text}")

    # ══════════════════════════════════════════
    # Delegation Shims for Backward Compatibility
    # ══════════════════════════════════════════
    def _refresh_sidebar(self): self.collection_controller.refresh()
    def _create_collection(self): self.collection_controller.prompt_create_collection(self)
    def _load_history(self): self.history_controller.load_more(initial=True)
    def _load_more_history(self, initial: bool = False): self.history_controller.load_more(initial=initial)
    def _refresh_stats(self): self.history_controller.refresh_stats()
    def _add_card(self, item: dict, at_top: bool = True): self.history_controller.add_card(item, at_top=at_top)
    def _remove_card(self, item_id: int): self.history_controller.remove_card(item_id)
    def _rebuild_card_in_place(self, item_id: int): self.history_controller.refresh_item(item_id)
    def _on_new_text(self, item_id: int, text: str): self.history_controller.on_text_captured(item_id, text)
    def _on_new_image(self, item_id: int, file_path: str): self.history_controller.on_image_captured(item_id, file_path)
    def _on_new_video(self, item_id: int, video_path: str): self.history_controller.on_video_captured(item_id, video_path)
    def _on_thumb_ready(self, item_id: int, thumb_path: str): self.history_controller.on_thumb_ready(item_id, thumb_path)
    def _on_copy(self, item_id: int): self.history_controller.on_copy(item_id)
    def _on_pin(self, item_id: int): self.history_controller.on_pin(item_id)
    def _on_delete(self, item_id: int): self.history_controller.on_delete(item_id)
    def _encrypt_card(self, item_id: int): self.security_controller.encrypt_item(item_id, self)
    def _decrypt_card(self, item_id: int): self.security_controller.decrypt_item(item_id, confirm=True, parent_widget=self)
    def _on_card_clicked(self, item_id: int, modifiers):
        if modifiers & Qt.KeyboardModifier.ControlModifier and not self._settings.get("multiselect_hint_dismissed", False): self.bulk_toolbar.show_hint()
        self.history_controller.on_card_clicked(item_id, modifiers)
    def _on_selection_count_changed(self, count: int):
        self.statusBar().showMessage(f"{count} item(s) selected  •  Ctrl+click to add, Shift+click to range" if count > 0 else "Watching clipboard…")
    def _clear_selection(self): self.history_controller.clear_selection()
    def _dismiss_hint(self): self.bulk_toolbar.hide_hint(); self._settings["multiselect_hint_dismissed"] = True; save_settings(self._settings)
    def _update_bulk_bar(self): self.bulk_toolbar.update_selection_count(len(self._selected_ids))
    def _bulk_pin(self, pin: bool): return self.history_controller.bulk_pin(pin)
    def _bulk_delete(self): return self.history_controller.bulk_delete(self)
    def _bulk_export(self): return self.history_controller.bulk_export(self)
    def _bulk_add_tag(self): return self.history_controller.bulk_add_tag(self)
    def _clear_history(self): return self.history_controller.clear_unpinned_history(self)
    def _on_reset_count(self, item_id: int): self.history_controller.on_reset_count(item_id)
    def _update_relative_times(self):
        for card in self._cards.values(): card.update_relative_time()
        self._refresh_stats()
    def _visible_cards(self) -> list[ItemCard]: return self.cards_view.visible_cards() if hasattr(self, "cards_view") else []
    def _set_card_focus(self, cards: list[ItemCard], new_idx: int): self.history_controller.set_card_focus(cards, new_idx)
    def _on_card_reordered(self, dragged_id: int, target_card_id: int): self.history_controller.on_card_reordered(dragged_id, target_card_id, self.cards_view)
    def _enforce_history_limit(self): self.history_controller.enforce_history_limit(self._settings.get("max_history", 200))
    def _clean_captures(self):
        if (rem := self.history_controller.clean_old_captures(self._settings.get("max_captures", 100))): print(f"[Dashboard] Auto-cleanup removed {rem} old capture(s)")
    def _init_sync_engine(self): self.sync_controller.init_sync_engine(is_locked=self._is_locked())
    def _start_api_server(self): self.sync_controller.start_api_server(is_locked=self._is_locked())
    def _start_discovery(self): self.sync_controller.start_discovery(is_locked=self._is_locked())
    def _on_device_discovered(self, node_id, data): self.sync_controller.add_or_update_device(node_id, data)
    def _on_device_removed(self, node_id): self.sync_controller.remove_device(node_id)
    def _on_device_double_clicked(self, item): self.sync_controller._on_item_double_clicked(item)
    def _on_pairing_requested(self, node_id, device_name): self.sync_controller._on_pairing_requested(node_id, device_name)
    def _on_pairing_completed(self, node_id, device_name): self.sync_controller._on_pairing_completed(node_id, device_name)
    def _on_pairing_failed(self, node_id, error_message): self.sync_controller._on_pairing_failed(node_id, error_message)
    def check_for_updates(self): self.update_controller.check_for_updates(channel=self._settings.get("update_channel", "stable"))
    def _on_update_found(self, update_info: dict, asset_url: str): self.topbar.set_update_visible(True)
    def _show_updater_dialog(self): self.update_controller.show_updater_dialog(self)
    def _make_tray_icon(self) -> QIcon: return DashboardTrayManager.make_tray_icon()
    def _ensure_tray_visible(self): getattr(self, "tray_manager", None) and self.tray_manager.ensure_tray_visible()
    def _update_tray_menu_and_tooltip(self): getattr(self, "tray_manager", None) and self.tray_manager.update_menu_and_tooltip(is_locked=self._is_locked(), is_monitoring_paused=getattr(self, "_is_monitoring_paused", False), has_password=has_master_password())

    # ══════════════════════════════════════════
    # Stylesheet, Watcher & System Tray
    # ══════════════════════════════════════════
    def _load_stylesheet(self):
        if os.path.exists(QSS_PATH):
            with open(QSS_PATH, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _setup_tray(self):
        tm = self.tray_manager = DashboardTrayManager(parent=self)
        tm.toggle_visibility_requested.connect(self.toggle_visibility)
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
        if hasattr(self, "watcher") and self.watcher: self.watcher.stop()
        self._update_tray_menu_and_tooltip()
        self.statusBar().showMessage("⏸ Clipboard monitoring paused")

    def _resume_monitoring(self):
        if self._is_locked():
            self._is_monitoring_paused = True
            self._update_tray_menu_and_tooltip()
            self.statusBar().showMessage("🔒 Unlock DotGhostBoard before resuming clipboard monitoring")
            return
        self._is_monitoring_paused = False
        if hasattr(self, "watcher") and self.watcher: self.watcher.start()
        self._update_tray_menu_and_tooltip()
        self.statusBar().showMessage("▶ Clipboard monitoring active")

    def show_and_raise(self):
        if (self._startup_locked or self._active_key is None) and has_master_password():
            self._show_lock_screen()
            return
        self.show(); self.raise_(); self.activateWindow()

    def toggle_visibility(self):
        self.hide() if self.isVisible() else self.show_and_raise()

    def _open_settings(self):
        if self._is_locked():
            self._show_lock_screen()
            return
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._settings = load_settings()
            self._enforce_history_limit()
            self._clean_captures()
            self._app_filter.update(self._settings.get("app_filter_mode", "blacklist"), self._settings.get("app_filter_list", []))
            self._set_stealth(self._settings.get("stealth_mode", False))
            self.lock_btn.setVisible(has_master_password())
            self._reset_auto_lock()
            self.statusBar().showMessage("Settings saved ✓")

    def _start_watcher(self):
        w = self.watcher = ClipboardWatcher()
        w.new_text_captured.connect(self.history_controller.on_text_captured)
        w.new_text_captured.connect(lambda iid, text: self.sync_controller.broadcast_text(text))
        w.new_image_captured.connect(self.history_controller.on_image_captured)
        w.new_video_captured.connect(self.history_controller.on_video_captured)
        w.thumb_ready.connect(self.history_controller.on_thumb_ready)
        if not self._is_locked(): w.start()

    # ══════════════════════════════════════════
    # Spotlight, Navigation & Shutdown
    # ══════════════════════════════════════════
    def show_spotlight(self):
        if self._is_locked() and not self._show_lock_screen(show_dashboard=False):
            return
        if hasattr(self, "spotlight_dialog") and self.spotlight_dialog:
            if self.spotlight_dialog.isVisible(): self.spotlight_dialog.hide()
            else: self.spotlight_dialog.show(); self.spotlight_dialog.raise_(); self.spotlight_dialog.activateWindow()

    def _on_spotlight_item_selected(self, item: dict):
        item_id = item.get("id")
        if item_id: self._on_copy(item_id)

    def keyPressEvent(self, event: QKeyEvent):
        self._reset_auto_lock()
        if hasattr(self, "history_controller") and self.history_controller.handle_key_press(event, self._visible_cards()):
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self._reset_auto_lock()
        super().mousePressEvent(event)

    def _lock(self) -> None:
        if getattr(self, "security_controller", None): self.security_controller.lock()
        else: self._active_key = None
        if getattr(self, "watcher", None): self.watcher.stop()
        if getattr(self, "sync_controller", None): self.sync_controller.stop_all()
        self._update_tray_menu_and_tooltip()
        if getattr(self, "history_controller", None): self.history_controller.on_session_locked()
        self.hide(); self._show_lock_screen()

    def _show_lock_screen(self, *, show_dashboard: bool = True) -> bool:
        if hasattr(self, "security_controller"):
            if not self.security_controller.prompt_unlock(self): return False
            self._startup_locked = False
            self.set_active_key(self.security_controller.active_key)
        else:
            dlg = LockScreen(setup=False)
            if dlg.exec() != LockScreen.DialogCode.Accepted: return False
            self._startup_locked = False
            self.set_active_key(dlg.get_key())

        self._reset_auto_lock()
        self._update_tray_menu_and_tooltip()
        if show_dashboard:
            self.show(); self.raise_(); self.activateWindow()
            self.statusBar().showMessage("🔓 Unlocked")
        return True

    def _reset_auto_lock(self) -> None:
        if getattr(self, "security_controller", None):
            self.security_controller.reset_auto_lock(self._settings.get("auto_lock_minutes", 0))

    def _set_stealth(self, enable: bool) -> None:
        geo = self.geometry()
        flags = (self.windowFlags() | Qt.WindowType.Tool) if enable else (self.windowFlags() & ~Qt.WindowType.Tool)
        self.setWindowFlags(flags)
        self.resize(400 if enable else 750, self.height())
        self.show()
        self.setGeometry(geo)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        is_compact = self.width() < 650
        if getattr(self, "sidebar_widget", None): self.sidebar_widget.set_collapsed(is_compact)
        if getattr(self, "topbar", None): self.topbar.set_compact_mode(is_compact)

    def closeEvent(self, event):
        if event.spontaneous():
            event.ignore()
            self.hide()
            self.tray.showMessage("DotGhostBoard", "Running in background. Click tray icon to restore.", QSystemTrayIcon.MessageIcon.Information, 2000)
            return

        print("[Dashboard] Shutting down...")
        if self._settings.get("clear_on_exit", False):
            self.history_service.delete_unpinned_items()
        if hasattr(self, "watcher") and self.watcher: self.watcher.stop()
        if hasattr(self, "sync_controller"): self.sync_controller.stop_all(2000)
        if hasattr(self, "update_controller"): self.update_controller.cleanup()
        if hasattr(self, "tray") and self.tray: self.tray.hide()
        event.accept()
