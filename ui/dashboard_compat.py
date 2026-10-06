"""
ui/dashboard_compat.py
──────────────────────
Backward compatibility mixin providing delegation properties and legacy
methods for Dashboard coordination and test suites.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from core.crypto import has_master_password
from ui.components import DashboardTrayManager
from ui.settings import save_settings

if TYPE_CHECKING:
    from ui.widgets import ItemCard


class DashboardCompatibilityMixin:
    """Provides backward-compatible attributes and shims for Dashboard."""

    # UI widget properties
    @property
    def sidebar(self):
        return getattr(self, "sidebar_widget", None)

    @property
    def collections_list(self):
        if hasattr(self, "sidebar_widget"):
            return getattr(self.sidebar_widget, "collections_list", None)
        return None

    @property
    def devices_list(self):
        if hasattr(self, "sidebar_widget"):
            return getattr(self.sidebar_widget, "devices_list", None)
        return None

    @property
    def stats_label(self):
        if hasattr(self, "topbar"):
            return getattr(self.topbar, "stats_label", None)
        return None

    @property
    def clear_btn(self):
        if hasattr(self, "topbar"):
            return getattr(self.topbar, "clear_btn", None)
        return None

    @property
    def lock_btn(self):
        if hasattr(self, "topbar"):
            return getattr(self.topbar, "lock_btn", None)
        return None

    @property
    def update_btn(self):
        if hasattr(self, "topbar"):
            return getattr(self.topbar, "update_btn", None)
        return None

    @property
    def vault(self):
        return getattr(self, "vault_panel", None)

    @property
    def vault_btn(self):
        if hasattr(self, "sidebar_widget"):
            return getattr(self.sidebar_widget, "vault_btn", None)
        return None

    @property
    def scroll(self):
        return getattr(self, "cards_view", None)

    @property
    def cards_container(self):
        if hasattr(self, "cards_view"):
            return getattr(self.cards_view, "cards_container", None)
        return None

    @property
    def cards_layout(self):
        if hasattr(self, "cards_view"):
            return getattr(self.cards_view, "cards_layout", None)
        return None

    @property
    def _hint_strip(self):
        if hasattr(self, "bulk_toolbar"):
            return getattr(self.bulk_toolbar, "hint_strip", None)
        return None

    @property
    def _bulk_bar(self):
        if hasattr(self, "bulk_toolbar"):
            return getattr(self.bulk_toolbar, "bulk_bar", None)
        return None

    @property
    def _bulk_count_lbl(self):
        if hasattr(self, "bulk_toolbar"):
            return getattr(self.bulk_toolbar, "bulk_count_lbl", None)
        return None

    @property
    def tray(self):
        if hasattr(self, "tray_manager"):
            return getattr(self.tray_manager, "tray", None)
        return None

    # State & controller properties
    @property
    def _cards(self):
        if hasattr(self, "history_controller"):
            return self.history_controller.cards
        return getattr(self, "_cards_fallback", {})

    @_cards.setter
    def _cards(self, val):
        if hasattr(self, "history_controller"):
            setattr(self.history_controller, "_cards", val)
        else:
            setattr(self, "_cards_fallback", val)

    @property
    def active_collection_id(self):
        if hasattr(self, "collection_controller"):
            return self.collection_controller.active_collection_id
        return getattr(self, "_active_coll_fallback", None)

    @active_collection_id.setter
    def active_collection_id(self, val):
        if hasattr(self, "collection_controller"):
            setattr(self.collection_controller, "active_collection_id", val)
        else:
            setattr(self, "_active_coll_fallback", val)

    @property
    def _active_key(self):
        if hasattr(self, "security_controller"):
            return self.security_controller.active_key
        return getattr(self, "_active_key_fallback", None)

    @_active_key.setter
    def _active_key(self, val):
        if hasattr(self, "security_controller"):
            self.security_controller.set_active_key(val)
        else:
            setattr(self, "_active_key_fallback", val)

    @property
    def _selected_ids(self):
        if hasattr(self, "history_controller"):
            return self.history_controller.selected_ids
        return getattr(self, "_selected_ids_fallback", set())

    @_selected_ids.setter
    def _selected_ids(self, val):
        if hasattr(self, "history_controller"):
            setattr(self.history_controller, "_selected_ids", set(val))
        else:
            setattr(self, "_selected_ids_fallback", set(val))

    @property
    def _last_clicked_id(self):
        if hasattr(self, "history_controller"):
            return self.history_controller._last_clicked_id
        return getattr(self, "_last_clicked_id_fallback", None)

    @_last_clicked_id.setter
    def _last_clicked_id(self, val):
        if hasattr(self, "history_controller"):
            setattr(self.history_controller, "_last_clicked_id", val)
        else:
            setattr(self, "_last_clicked_id_fallback", val)

    @property
    def _api_thread(self):
        if hasattr(self, "sync_controller"):
            return self.sync_controller.api_thread
        return getattr(self, "_api_thread_fallback", None)

    @_api_thread.setter
    def _api_thread(self, val):
        if hasattr(self, "sync_controller"):
            setattr(self.sync_controller, "_api_thread", val)
        else:
            setattr(self, "_api_thread_fallback", val)

    @property
    def _discovery_thread(self):
        if hasattr(self, "sync_controller"):
            return self.sync_controller.discovery_thread
        return getattr(self, "_discovery_thread_fallback", None)

    @_discovery_thread.setter
    def _discovery_thread(self, val):
        if hasattr(self, "sync_controller"):
            setattr(self.sync_controller, "_discovery_thread", val)
        else:
            setattr(self, "_discovery_thread_fallback", val)

    @property
    def _sync_engine(self):
        if hasattr(self, "sync_controller"):
            return self.sync_controller.sync_engine
        return getattr(self, "_sync_engine_fallback", None)

    @_sync_engine.setter
    def _sync_engine(self, val):
        if hasattr(self, "sync_controller"):
            setattr(self.sync_controller, "_sync_engine", val)
        else:
            setattr(self, "_sync_engine_fallback", val)

    @property
    def _active_pairing_dialogs(self):
        if hasattr(self, "sync_controller"):
            return self.sync_controller.active_pairing_dialogs
        return getattr(self, "_active_pairing_dialogs_fallback", {})

    @property
    def _update_thread(self):
        if hasattr(self, "update_controller"):
            return self.update_controller.update_thread
        return getattr(self, "_update_thread_fallback", None)

    @_update_thread.setter
    def _update_thread(self, val):
        if hasattr(self, "update_controller"):
            setattr(self.update_controller, "_update_thread", val)
        else:
            setattr(self, "_update_thread_fallback", val)

    @property
    def _pending_update_info(self):
        if hasattr(self, "update_controller"):
            return self.update_controller.pending_update_info
        return getattr(self, "_pending_update_info_fallback", None)

    @property
    def _pending_asset_url(self):
        if hasattr(self, "update_controller"):
            return self.update_controller.pending_asset_url
        return getattr(self, "_pending_asset_url_fallback", None)

    @property
    def _auto_lock_timer(self):
        if hasattr(self, "security_controller"):
            return self.security_controller.auto_lock_timer
        return getattr(self, "_auto_lock_timer_fallback", None)

    # Shims delegating to controllers
    def _refresh_sidebar(self):
        self.collection_controller.refresh()

    def _create_collection(self):
        self.collection_controller.prompt_create_collection(self)

    def _load_history(self):
        self.history_controller.load_more(initial=True)

    def _load_more_history(self, initial: bool = False):
        self.history_controller.load_more(initial=initial)

    def _refresh_stats(self):
        self.history_controller.refresh_stats()

    def _add_card(self, item: dict, at_top: bool = True):
        self.history_controller.add_card(item, at_top=at_top)

    def _remove_card(self, item_id: int):
        self.history_controller.remove_card(item_id)

    def _on_copy(self, item_id: int):
        self.history_controller.on_copy(item_id)

    def _on_card_clicked(self, item_id: int, modifiers):
        ctrl = Qt.KeyboardModifier.ControlModifier
        hint_dismissed = self._settings.get(
            "multiselect_hint_dismissed", False
        )
        if (modifiers & ctrl) and not hint_dismissed:
            self.bulk_toolbar.show_hint()
        self.history_controller.on_card_clicked(item_id, modifiers)

    def _on_selection_count_changed(self, count: int):
        if count > 0:
            msg = (
                f"{count} item(s) selected  •  "
                "Ctrl+click to add, Shift+click to range"
            )
        else:
            msg = "Watching clipboard…"
        self.statusBar().showMessage(msg)

    def _clear_selection(self):
        self.history_controller.clear_selection()

    def _dismiss_hint(self):
        self.bulk_toolbar.hide_hint()
        self._settings["multiselect_hint_dismissed"] = True
        save_settings(self._settings)

    def _update_bulk_bar(self):
        self.bulk_toolbar.update_selection_count(len(self._selected_ids))

    def _bulk_pin(self, pin: bool):
        return self.history_controller.bulk_pin(pin)

    def _bulk_delete(self):
        return self.history_controller.bulk_delete(self)

    def _bulk_export(self):
        return self.history_controller.bulk_export(self)

    def _bulk_add_tag(self):
        return self.history_controller.bulk_add_tag(self)

    def _clear_history(self):
        return self.history_controller.clear_unpinned_history(self)

    def _on_reset_count(self, item_id: int):
        self.history_controller.on_reset_count(item_id)

    def _update_relative_times(self):
        for card in self._cards.values():
            card.update_relative_time()
        self._refresh_stats()

    def _visible_cards(self) -> list[ItemCard]:
        if hasattr(self, "cards_view"):
            return self.cards_view.visible_cards()
        return []

    def _set_card_focus(self, cards: list[ItemCard], new_idx: int):
        self.history_controller.set_card_focus(cards, new_idx)

    def _on_card_reordered(self, dragged_id: int, target_card_id: int):
        self.history_controller.on_card_reordered(
            dragged_id, target_card_id, self.cards_view
        )

    def _enforce_history_limit(self):
        limit = self._settings.get("max_history", 200)
        self.history_controller.enforce_history_limit(limit)

    def _clean_captures(self):
        limit = self._settings.get("max_captures", 100)
        rem = self.history_controller.clean_old_captures(limit)
        if rem:
            print(f"[Dashboard] Auto-cleanup removed {rem} old capture(s)")

    def _init_sync_engine(self):
        self.sync_controller.init_sync_engine(is_locked=self._is_locked())

    def _start_api_server(self):
        self.sync_controller.start_api_server(is_locked=self._is_locked())

    def _start_discovery(self):
        self.sync_controller.start_discovery(is_locked=self._is_locked())

    def check_for_updates(self):
        channel = self._settings.get("update_channel", "stable")
        self.update_controller.check_for_updates(channel=channel)

    def _on_update_found(self, update_info: dict, asset_url: str):
        self.topbar.set_update_visible(True)
        tray = getattr(self, "tray_manager", None)
        if tray and not self.isVisible():
            def open_update():
                self.show_and_raise()
                if not self._is_locked():
                    self._show_updater_dialog()

            tray.show_message(
                "DotGhostBoard — Update available",
                "A new version is available. Open to review the release details.",
                timeout=5000,
                category="updates",
                action_label="View update",
                action_callback=open_update,
                dedupe_key=f"update:{update_info.get('tag_name', asset_url)}",
                once=True,
            )

    def _show_updater_dialog(self):
        self.update_controller.show_updater_dialog(self)

    def _make_tray_icon(self) -> QIcon:
        return DashboardTrayManager.make_tray_icon()

    def _ensure_tray_visible(self):
        if getattr(self, "tray_manager", None):
            self.tray_manager.ensure_tray_visible()

    def _update_tray_menu_and_tooltip(self):
        if not getattr(self, "tray_manager", None):
            return
        self.tray_manager.update_menu_and_tooltip(
            is_locked=self._is_locked(),
            is_monitoring_paused=getattr(self, "_is_monitoring_paused", False),
            has_password=has_master_password(),
        )

    # Event handlers & coordination helpers
    def _on_pin_suggested(self, item_id: int, preview: str):
        from ui.widgets import PinSuggestionToast
        if getattr(self, "_active_toast", None):
            try:
                self._active_toast.deleteLater()
            except Exception:
                pass
        toast = self._active_toast = PinSuggestionToast(
            item_id, preview, parent=self
        )
        toast.sig_pin.connect(self.history_controller.on_pin)
        toast.sig_close.connect(lambda: setattr(self, "_active_toast", None))
        toast.adjustSize()
        toast.move(20, self.height() - toast.height() - 30)
        toast.show()

    def _on_item_copied_ready(self, item_id: int, item: dict):
        if getattr(self, "watcher", None):
            self.watcher.mark_self_paste()
            self.watcher.paste_item_to_clipboard(item)
        if getattr(self, "_hide_after_secret_copy", False):
            self._hide_after_secret_copy = False
            self.hide()

    def _on_item_activated(self, item_id: int):
        """Called when a card is activated via Enter or double-click."""
        if self._settings.get("hide_on_select", False):
            item = self.history_service.get_item(item_id)
            if (
                item
                and item.get("is_secret")
                and getattr(self, "security_controller", None)
                and self.security_controller.is_locked
            ):
                self._hide_after_secret_copy = True
            else:
                self.hide()

    def _on_item_moved_to_collection(
        self, item_id: int, target_coll_id: int | None
    ):
        coll_id = self.active_collection_id
        if coll_id is not None and target_coll_id != coll_id:
            self.history_controller.remove_card(item_id)
        self.history_controller.refresh_stats()

    def _on_reveal_requested(self, item_id: int) -> None:
        plaintext = self.security_controller.reveal_secret(item_id)
        card = self.history_controller.cards.get(item_id)
        if plaintext is not None and card:
            card.reveal_content(plaintext)

    def _on_sync_item_received(self, item_id: int, text: str):
        item = self.history_service.get_item(item_id)
        if item:
            self._add_card(item, at_top=True)
            self._refresh_stats()

    def _on_api_new_text(self, item_id: int, text: str):
        self._on_sync_item_received(item_id, text)
        if getattr(self, "sync_controller", None):
            self.sync_controller.broadcast_text(text)

    def _on_sync_received(self, item_id: int, text: str):
        self._on_sync_item_received(item_id, text)
        if len(text) > 40:
            msg = f"📥 Synced from peer: {text[:40]}..."
        else:
            msg = f"📥 Synced: {text}"
        self.statusBar().showMessage(msg)

    def _on_spotlight_item_selected(self, item: dict):
        item_id = item.get("id")
        if item_id:
            self._on_copy(item_id)

    def _reset_auto_lock(self) -> None:
        if getattr(self, "security_controller", None):
            minutes = self._settings.get("auto_lock_minutes", 0)
            self.security_controller.reset_auto_lock(minutes)

    def _set_stealth(self, enable: bool) -> None:
        geo = self.geometry()
        tool_flag = Qt.WindowType.Tool
        if enable:
            flags = self.windowFlags() | tool_flag
        else:
            flags = self.windowFlags() & ~tool_flag
        self.setWindowFlags(flags)
        self.resize(400 if enable else 750, self.height())
        self.show()
        self.setGeometry(geo)
