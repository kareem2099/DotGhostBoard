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
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
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
    send_to_vault_requested = pyqtSignal(int)       # item_id
    item_copied_ready = pyqtSignal(int, dict)       # item_id, item_data (for clipboard paste)
    pin_suggested = pyqtSignal(int, str)            # item_id, preview_text
    stats_updated = pyqtSignal(dict)
    status_message = pyqtSignal(str)
    selection_changed = pyqtSignal(int)             # count of selected items

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

    @property
    def selected_ids(self) -> set[int]:
        return set(self._selected_ids)

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
        self.selection_changed.emit(0)

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
        card.sig_send_to_vault.connect(self.send_to_vault_requested.emit)
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
            last_item = self._cards_layout.itemAt(self._cards_layout.count() - 1) if self._cards_layout.count() > 0 else None
            if last_item and last_item.widget() is None:
                self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
            else:
                self._cards_layout.addWidget(card)
        card.show()

    def remove_card(self, item_id: int):
        card = self._cards.pop(item_id, None)
        if card:
            self._cards_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        if item_id in self._selected_ids:
            self._selected_ids.discard(item_id)
            self.selection_changed.emit(len(self._selected_ids))

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
        new_card.show()

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

    def on_delete(self, item_id: int, secure: bool = False, force: bool = False):
        if secure or force:
            self._service.delete_item(item_id, secure=secure, force=force)
        else:
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

    def _visible_cards(self) -> list[ItemCard]:
        cards: list[ItemCard] = []
        if not self._cards_layout:
            return cards

        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            widget = item.widget() if item else None

            if widget and isinstance(widget, ItemCard) and widget.isVisible():
                cards.append(widget)

        return cards

    def on_card_clicked(self, item_id: int, modifiers) -> None:
        card = self._cards.get(item_id)
        if not card:
            return

        visible_cards = self._visible_cards()
        visible_ids = [c.item_id for c in visible_cards]

        is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        is_ctrl = bool(
            modifiers
            & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.MetaModifier
            )
        )

        if is_shift and self._last_clicked_id in visible_ids:
            start = visible_ids.index(self._last_clicked_id)
            end = visible_ids.index(item_id)

            for cid in visible_ids[min(start, end) : max(start, end) + 1]:
                self._selected_ids.add(cid)
                selected_card = self._cards.get(cid)
                if selected_card:
                    selected_card.set_selected(True)

        elif is_ctrl:
            self._toggle_selection(item_id)

        else:
            if self._selected_ids:
                self._clear_selection(emit=False)

            if card in visible_cards:
                self.set_card_focus(visible_cards, visible_cards.index(card))

        self._last_clicked_id = item_id
        self.selection_changed.emit(len(self._selected_ids))

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

    def _clear_selection(self, emit: bool = True) -> None:
        for cid in list(self._selected_ids):
            card = self._cards.get(cid)
            if card:
                card.set_selected(False)
        self._selected_ids.clear()
        self._last_clicked_id = None
        if emit:
            self.selection_changed.emit(0)

    def clear_selection(self):
        """Public method to deselect all cards and hide bulk actions bar."""
        self._clear_selection()

    def bulk_pin(self, pin: bool) -> int:
        """Toggle pin state for all currently selected items."""
        affected = 0
        for iid in list(self._selected_ids):
            item = self._service.get_item(iid)
            if item and bool(item.get("is_pinned", 0)) != pin:
                new_state = self._service.toggle_pin(iid)
                card = self._cards.get(iid)
                if card and new_state is not None:
                    card.update_pin_state(new_state)
                affected += 1
        action_str = "Pinned" if pin else "Unpinned"
        self.status_message.emit(f"{action_str} {len(self._selected_ids)} items ✓")
        self.refresh_stats()
        return affected

    def bulk_delete(self, parent_widget: Optional[QWidget] = None) -> int:
        """Delete unpinned items among the current selection after confirmation."""
        count = len(self._selected_ids)
        if count == 0:
            return 0
        reply = QMessageBox.question(
            parent_widget,
            "Delete Selected",
            f"Delete {count} selected item(s)?\nPinned items will be skipped.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return 0

        deleted = 0
        for iid in list(self._selected_ids):
            if self._service.delete_item(iid):
                self.remove_card(iid)
                deleted += 1
        self._clear_selection()
        self.refresh_stats()
        self.status_message.emit(f"Deleted {deleted} item(s) ✓")
        return deleted

    def bulk_export(self, parent_widget: Optional[QWidget] = None) -> Optional[str]:
        """Export currently selected items to a txt or json file."""
        if not self._selected_ids:
            return None
        fmt, ok = QInputDialog.getItem(
            parent_widget, "Export Format", "Choose format:", ["txt", "json"], 0, False
        )
        if not ok:
            return None
        path, _ = QFileDialog.getSaveFileName(
            parent_widget,
            "Export Items",
            f"dotghost_export.{fmt}",
            f"{'Text' if fmt == 'txt' else 'JSON'} Files (*.{fmt})",
        )
        if not path:
            return None
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._service.export_items(list(self._selected_ids), fmt))
        self.status_message.emit(
            f"Exported {len(self._selected_ids)} items → {path} ✓"
        )
        return path

    def bulk_add_tag(self, parent_widget: Optional[QWidget] = None) -> Optional[str]:
        """Prompt and add a common tag to all currently selected items."""
        if not self._selected_ids:
            return None
        tag, ok = QInputDialog.getText(
            parent_widget, "Add Tag", "Tag to add to all selected items:", QLineEdit.EchoMode.Normal, "#"
        )
        if not ok or not tag.strip():
            return None
        tag = tag.strip().lower()
        tag = tag if tag.startswith("#") else f"#{tag}"
        for iid in list(self._selected_ids):
            updated = self._service.add_tag(iid, tag)
            card = self._cards.get(iid)
            if card and tag in updated:
                card.on_tag_added(tag)
        self.status_message.emit(
            f"Tag {tag} added to {len(self._selected_ids)} items ✓"
        )
        return tag

    def clear_unpinned_history(self, parent_widget: Optional[QWidget] = None) -> bool:
        """Prompt Pigeon Doctor confirmation and purge all unpinned items."""
        msg = QMessageBox(parent_widget)
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
            return False

        from ui.purge_easter_egg import PurgeEasterEggDialog

        dialog = PurgeEasterEggDialog(
            purge_fn=self._service.delete_unpinned_items,
            parent=parent_widget,
        )
        dialog.exec()

        for iid in [iid for iid, c in self._cards.items() if not c.is_pinned]:
            self.remove_card(iid)
        self._focused_idx = -1
        self.refresh_stats()
        self.status_message.emit("🐦⬛ The Pigeon Doctor has cleansed the board.")
        return True

    def _on_card_context_menu(self, pos, card: ItemCard):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(card)
        menu.addAction(QAction("⎘ Copy", card, triggered=lambda: self.on_copy(card.item_id)))

        if card.item_type == "text":
            menu.addAction(QAction("🛡️ Send to Vault...", card,
                                   triggered=lambda: self.send_to_vault_requested.emit(card.item_id)))
        if card.is_secret:
            menu.addAction(QAction("🔓 Decrypt (remove lock)", card,
                                   triggered=lambda: self.decrypt_requested.emit(card.item_id)))
        else:
            menu.addAction(QAction("🔒 Mark as Secret (Encrypt)", card,
                                   triggered=lambda: self.encrypt_requested.emit(card.item_id)))

        pin_label = "📍 Unpin" if card.is_pinned else "📌 Pin"
        menu.addAction(QAction(pin_label, card, triggered=lambda: self.on_pin(card.item_id)))
        menu.addAction(QAction("✕ Delete", card, triggered=lambda: self.on_delete(card.item_id)))

        menu.exec(card.mapToGlobal(pos))

    # ──────────────────────────────────────────
    # History Maintenance & Reordering
    # ──────────────────────────────────────────
    def enforce_history_limit(self, limit: int = 200) -> None:
        """Trim unpinned cards if total count exceeds limit."""
        unpinned = [iid for iid, c in self._cards.items() if not c.is_pinned]
        excess = len(self._cards) - limit
        if excess > 0:
            for iid in unpinned[-excess:]:
                self._service.delete_item(iid)
                self.remove_card(iid)
            self.refresh_stats()

    def clean_old_captures(self, keep: int = 100) -> int:
        """Delete old capture records beyond keep count."""
        removed = self._service.clean_old_captures(keep)
        if removed:
            for iid in list(self._cards):
                if self._service.get_item(iid) is None:
                    self.remove_card(iid)
            self.refresh_stats()
        return removed

    def on_card_reordered(
        self,
        dragged_id: int,
        target_card_id: int,
        cards_view: Optional[QWidget] = None,
    ) -> None:
        """Update DB sort orders after user drags and drops a card in cards_view."""
        if not cards_view:
            return
        all_cards = cards_view.all_card_widgets()
        dragged_card = self._cards.get(dragged_id)
        target_card = self._cards.get(target_card_id)
        if (
            dragged_card
            and target_card
            and dragged_card in all_cards
            and target_card in all_cards
        ):
            all_cards.remove(dragged_card)
            target_idx = all_cards.index(target_card)
            all_cards.insert(target_idx, dragged_card)

            for order, card in enumerate(all_cards):
                if hasattr(card, "item_id"):
                    self._service.update_sort_order(card.item_id, order)

            cards_view.reorder_widgets(all_cards)

    # ──────────────────────────────────────────
    # Keyboard Navigation
    # ──────────────────────────────────────────
    def set_card_focus(self, cards: list[ItemCard], new_idx: int) -> None:
        """Set keyboard focus highlight on card at index and scroll into view."""
        if 0 <= self._focused_idx < len(cards):
            cards[self._focused_idx].set_focused(False)

        self._focused_idx = new_idx
        if 0 <= new_idx < len(cards):
            card = cards[new_idx]
            card.set_focused(True)
            if self._scroll_area:
                self._scroll_area.ensureWidgetVisible(card)

    def handle_key_press(self, event: QKeyEvent, cards: list[ItemCard]) -> bool:
        """
        Handle navigation keys (Up/Down/Return/Escape).
        Returns True if event was consumed, False otherwise.
        """
        if not cards:
            return False

        key = event.key()
        if key == Qt.Key.Key_Down:
            new_idx = (
                0
                if self._focused_idx == -1
                else min(self._focused_idx + 1, len(cards) - 1)
            )
            self.set_card_focus(cards, new_idx)
            return True
        elif key == Qt.Key.Key_Up:
            new_idx = 0 if self._focused_idx <= 0 else self._focused_idx - 1
            self.set_card_focus(cards, new_idx)
            return True
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if 0 <= self._focused_idx < len(cards):
                self.on_copy(cards[self._focused_idx].item_id)
                return True
        elif key == Qt.Key.Key_Escape:
            if 0 <= self._focused_idx < len(cards):
                cards[self._focused_idx].set_focused(False)
            self._focused_idx = -1
            self.clear_selection()
            return True
        return False

