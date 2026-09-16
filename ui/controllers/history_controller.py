"""
ui/controllers/history_controller.py
───────────────────────────────────
Controller managing clipboard history list, card life-cycle,
search & collection filters, pagination, and card actions.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
)

from core.constants import PAGE_SIZE
from core.services.history_service import HistoryService
from ui.widgets import ItemCard, StatsHeaderCard

logger = logging.getLogger(__name__)


class HistoryController(QObject):
    """
    Behavioral controller managing clipboard history rendering,
    infinite scroll pagination, and card interactions.
    """
    secret_copy_requested = pyqtSignal(int, dict)   # item_id, item_data
    encrypt_requested = pyqtSignal(int)             # item_id
    decrypt_requested = pyqtSignal(int)             # item_id
    reveal_requested = pyqtSignal(int)              # item_id
    item_copied_ready = pyqtSignal(int, dict)       # item_id, item_data (for clipboard paste)
    pin_suggested = pyqtSignal(int, str)            # item_id, preview_text
    stats_updated = pyqtSignal(dict)
    status_message = pyqtSignal(str)

    def __init__(
        self,
        service: HistoryService,
        cards_layout: QVBoxLayout,
        search_box: Optional[QLineEdit] = None,
        scroll_area: Optional[QScrollArea] = None,
        stats_card: Optional[StatsHeaderCard] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._service = service
        self._cards_layout = cards_layout
        self._search_box = search_box
        self._scroll_area = scroll_area
        self._stats_card = stats_card

        self._cards: dict[int, ItemCard] = {}
        self._offset: int = 0
        self._exhausted: bool = False
        self._loading: bool = False

        # Active filters
        self._active_collection_id: Optional[int] = None
        self._active_tag_filter: Optional[str] = None
        self._active_search_query: str = ""

        # Selection state
        self._selected_ids: set[int] = set()
        self._last_clicked_id: Optional[int] = None
        self._focused_idx: int = -1

        self._setup_wiring()

    @property
    def cards(self) -> dict[int, ItemCard]:
        return self._cards

    @property
    def active_collection_id(self) -> Optional[int]:
        return self._active_collection_id

    def _setup_wiring(self):
        if self._search_box:
            self._search_box.textChanged.connect(self.on_search_text_changed)
        if self._scroll_area:
            self._scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def reload(self):
        """Clear existing cards and reload from offset 0."""
        self.clear_cards()
        self._offset = 0
        self._exhausted = False
        self.load_more(initial=True)
        self.refresh_stats()

    def clear_cards(self):
        for card in list(self._cards.values()):
            self.remove_card(card.item_id)
        self._cards.clear()
        self._selected_ids.clear()
        self._last_clicked_id = None
        self._focused_idx = -1

    def load_more(self, initial: bool = False):
        if self._loading or (self._exhausted and not initial):
            return
        self._loading = True
        try:
            batch_size = PAGE_SIZE if not initial else PAGE_SIZE * 2
            items = self._service.get_items(
                limit=batch_size,
                offset=self._offset,
                query=self._active_search_query if self._active_search_query else None,
                tag=self._active_tag_filter,
                collection_id=self._active_collection_id,
            )
            if not items:
                self._exhausted = True
                return

            for item in items:
                self.add_card(item, at_top=False)

            self._offset += len(items)
            if len(items) < batch_size:
                self._exhausted = True
        finally:
            self._loading = False

    def _connect_card_signals(self, card: "ItemCard") -> None:
        """Wire all standard signals for a card. Centralises signal connections
        to avoid duplication between add_card() and refresh_item()."""
        card.sig_copy.connect(self.on_copy)
        card.sig_pin.connect(self.on_pin)
        card.sig_delete.connect(self.on_delete)
        card.sig_tag_added.connect(self.on_tag_added)
        card.sig_tag_removed.connect(self.on_tag_removed)
        card.sig_clicked.connect(self.on_card_clicked)
        card.sig_reveal_requested.connect(self.reveal_requested.emit)
        card.sig_reset_count.connect(self.on_reset_count)
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card: self._on_card_context_menu(pos, c)
        )

    def add_card(self, item: dict, at_top: bool = True):
        item_id = item["id"]
        if item_id in self._cards:
            if at_top:
                card = self._cards[item_id]
                self._cards_layout.removeWidget(card)
                self._cards_layout.insertWidget(0, card)
            return

        card = ItemCard(item)
        self._connect_card_signals(card)

        self._cards[item_id] = card
        if at_top:
            self._cards_layout.insertWidget(0, card)
        else:
            insert_idx = max(0, self._cards_layout.count() - 1)
            self._cards_layout.insertWidget(insert_idx, card)

    def remove_card(self, item_id: int):
        card = self._cards.pop(item_id, None)
        if card:
            self._cards_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._selected_ids.discard(item_id)

    def refresh_item(self, item_id: int):
        """Re-fetches item from service and updates/rebuilds card in place."""
        item = self._service.get_item(item_id)
        if not item:
            self.remove_card(item_id)
            return

        card = self._cards.get(item_id)
        if not card:
            return

        idx = self._cards_layout.indexOf(card)
        self.remove_card(item_id)

        new_card = ItemCard(item)
        self._connect_card_signals(new_card)

        self._cards[item_id] = new_card
        self._cards_layout.insertWidget(max(0, idx), new_card)

    def refresh_stats(self):
        stats = self._service.get_stats()
        if self._stats_card:
            self._stats_card.update_stats(stats)
        self.stats_updated.emit(stats)

    # ── Watcher Event Receivers ───────────────────────────────────────────────

    def on_text_captured(self, item_id: int, text: str):
        item = self._service.get_item(item_id)
        if item:
            self.add_card(item, at_top=True)
            self.refresh_stats()
            copy_count = item.get("copy_count", 0) or 0
            card = self._cards.get(item_id)
            if card:
                card.update_copy_count(copy_count)
            preview = text[:40] + "…" if len(text) > 40 else text
            self.status_message.emit(f"Text captured: {preview}  (×{copy_count})")

    def on_image_captured(self, item_id: int, file_path: str):
        item = self._service.get_item(item_id)
        if item:
            self.add_card(item, at_top=True)
            self.refresh_stats()
            copy_count = item.get("copy_count", 0) or 0
            card = self._cards.get(item_id)
            if card:
                card.update_copy_count(copy_count)
            self.status_message.emit("Image captured 📸")

    def on_video_captured(self, item_id: int, video_path: str):
        item = self._service.get_item(item_id)
        if item:
            self.add_card(item, at_top=True)
            self.refresh_stats()
            copy_count = item.get("copy_count", 0) or 0
            card = self._cards.get(item_id)
            if card:
                card.update_copy_count(copy_count)
            self.status_message.emit("Video path captured 🎬")

    def on_thumb_ready(self, item_id: int, thumb_path: str):
        card = self._cards.get(item_id)
        if card:
            card.update_video_thumb(thumb_path)

    # ── Card Actions ──────────────────────────────────────────────────────────

    def on_copy(self, item_id: int):
        item = self._service.get_item(item_id)
        if not item:
            return

        if item.get("is_secret"):
            self.secret_copy_requested.emit(item_id, item)
            return

        self.record_copy_result(item_id, item)

    def record_copy_result(self, item_id: int, item: dict):
        """Called when a copy operation is finalized (plaintext ready)."""
        new_count, should_suggest, auto_pinned = self._service.record_copy(item_id)
        card = self._cards.get(item_id)
        if card:
            card.update_copy_count(new_count)
            if auto_pinned:
                card.update_pin_state(True)

        if should_suggest:
            preview = (item.get("content") or "")[:40]
            self.pin_suggested.emit(item_id, preview)

        self.item_copied_ready.emit(item_id, item)
        self.status_message.emit(f"Copied! ⏘  (×{new_count})")
        self.refresh_stats()

    def on_pin(self, item_id: int):
        new_state = self._service.toggle_pin(item_id)
        card = self._cards.get(item_id)
        if card:
            card.update_pin_state(new_state)
        self.refresh_stats()
        self.status_message.emit("Pinned 📌" if new_state else "Unpinned")

    def on_delete(self, item_id: int):
        self._service.delete_item(item_id)
        self.remove_card(item_id)
        self.refresh_stats()
        self.status_message.emit("Item deleted 🗑")

    def on_tag_added(self, item_id: int, tag: str):
        self._service.add_tag(item_id, tag)
        self.refresh_stats()

    def on_tag_removed(self, item_id: int, tag: str):
        self._service.remove_tag(item_id, tag)
        self.refresh_stats()

    def on_reset_count(self, item_id: int):
        self._service.reset_copy_count(item_id)
        card = self._cards.get(item_id)
        if card:
            card.update_copy_count(0)
        self.status_message.emit("Copy count reset ✓")

    def on_session_locked(self):
        for card in self._cards.values():
            card.on_session_locked()

    def filter_by_collection(self, coll_id: Optional[int]):
        self._active_collection_id = coll_id
        self.reload()

    def filter_by_tag(self, tag: Optional[str]):
        self._active_tag_filter = tag
        self.reload()

    def on_search_text_changed(self, query: str):
        self._active_search_query = query.strip()
        self.reload()

    def _on_scroll(self, val: int):
        if not self._scroll_area:
            return
        bar = self._scroll_area.verticalScrollBar()
        if bar.maximum() - val <= 100:
            self.load_more()

    def on_card_clicked(self, item_id: int, modifiers):
        card = self._cards.get(item_id)
        if not card:
            return

        is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        is_ctrl = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))

        if is_shift and self._last_clicked_id is not None:
            # Range select
            keys = list(self._cards.keys())
            try:
                start = keys.index(self._last_clicked_id)
                end = keys.index(item_id)
                rng = keys[min(start, end): max(start, end) + 1]
                for cid in rng:
                    self._selected_ids.add(cid)
                    if cid in self._cards:
                        self._cards[cid].set_selected(True)
            except ValueError:
                self._toggle_selection(item_id)
        elif is_ctrl:
            self._toggle_selection(item_id)
        else:
            self._clear_selection()
            self._toggle_selection(item_id)

        self._last_clicked_id = item_id

    def _toggle_selection(self, item_id: int):
        card = self._cards.get(item_id)
        if not card:
            return
        if item_id in self._selected_ids:
            self._selected_ids.remove(item_id)
            card.set_selected(False)
        else:
            self._selected_ids.add(item_id)
            card.set_selected(True)

    def _clear_selection(self):
        for cid in list(self._selected_ids):
            card = self._cards.get(cid)
            if card:
                card.set_selected(False)
        self._selected_ids.clear()

    def _on_card_context_menu(self, pos, card: ItemCard):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(card)
        if card.is_secret:
            menu.addAction(QAction("🔓 Decrypt (remove lock)", card,
                                   triggered=lambda: self.decrypt_requested.emit(card.item_id)))
        else:
            menu.addAction(QAction("🔒 Mark as Secret (Encrypt)", card,
                                   triggered=lambda: self.encrypt_requested.emit(card.item_id)))
        menu.exec(card.mapToGlobal(pos))
