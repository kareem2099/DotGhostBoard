"""
core/services/history_service.py
────────────────────────────────
Service managing clipboard history items, queries, pins, tags, and lifecycle.
Decouples UI and Controllers from direct SQLite storage operations.
"""

from __future__ import annotations

from typing import Optional
from core import storage
from core.constants import PIN_SUGGESTION_THRESHOLD, AUTO_PIN_THRESHOLD


class HistoryService:
    """Business logic and orchestrator for clipboard history items."""

    def __init__(self, storage_mod=None):
        self._storage = storage_mod or storage

    def get_items(
        self,
        limit: int = 20,
        offset: int = 0,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        collection_id: Optional[int] = None,
    ) -> list[dict]:
        """
        Fetch a page of clipboard history items according to active filters.
        Precedence: collection > search query > tag filter > all items.
        """
        if collection_id is not None:
            return self._storage.get_items_by_collection(collection_id, limit=limit, offset=offset)
        if query:
            return self._storage.search_items(query, tag, limit=limit, offset=offset)
        if tag:
            return self._storage.get_items_by_tag(tag, limit=limit, offset=offset)
        return self._storage.get_all_items(limit=limit, offset=offset)

    def add_item(self, item_type: str, content: str, preview: Optional[str] = None) -> int:
        """Add a new item to history and return its ID."""
        return self._storage.add_item(item_type, content, preview)

    def get_item(self, item_id: int) -> Optional[dict]:
        """Retrieve single item by id."""
        return self._storage.get_item_by_id(item_id)

    def delete_item(self, item_id: int) -> bool:
        """Delete an item and its associated media files."""
        return self._storage.delete_item(item_id)

    def delete_items(self, item_ids: list[int]) -> int:
        """Bulk delete items. Returns number of deleted items."""
        deleted = 0
        for iid in item_ids:
            if self._storage.delete_item(iid):
                deleted += 1
        return deleted

    def toggle_pin(self, item_id: int) -> Optional[bool]:
        """Toggle pinned status of an item. Returns new pinned state or None."""
        return self._storage.toggle_pin(item_id)

    def toggle_pins(self, item_ids: list[int]) -> dict[int, bool]:
        """Bulk toggle pinned status for a list of items."""
        results: dict[int, bool] = {}
        for iid in item_ids:
            new_state = self._storage.toggle_pin(iid)
            if new_state is not None:
                results[iid] = new_state
        return results

    def record_copy(self, item_id: int) -> tuple[int, bool, bool]:
        """
        Record a copy event for an item.
        Increments copy count in DB and determines if pin suggestions or auto-pins apply.

        Returns:
            (new_copy_count, should_suggest_pin, auto_pinned)
        """
        new_count = self._storage.increment_copy_count(item_id)
        should_suggest = (new_count == PIN_SUGGESTION_THRESHOLD)
        auto_pinned = False

        item = self._storage.get_item_by_id(item_id)
        if item and not item.get("is_pinned") and new_count >= AUTO_PIN_THRESHOLD:
            self._storage.toggle_pin(item_id)
            auto_pinned = True

        return new_count, should_suggest, auto_pinned

    def reset_copy_count(self, item_id: int) -> bool:
        """Reset copy count of an item back to 0."""
        return self._storage.reset_copy_count(item_id)

    def add_tag(self, item_id: int, tag: str) -> list[str]:
        """Add a tag to an item. Returns the updated tag list."""
        return self._storage.add_tag(item_id, tag)

    def remove_tag(self, item_id: int, tag: str) -> list[str]:
        """Remove a tag from an item. Returns the updated tag list."""
        return self._storage.remove_tag(item_id, tag)

    def export_items(self, item_ids: list[int], fmt: str) -> str:
        """Export specified items in json, csv, or txt format."""
        return self._storage.export_items(item_ids, fmt)

    def clean_old_captures(self, keep: int = 100) -> int:
        """Auto-cleanup older capture files keeping only the most recent `keep`."""
        return self._storage.clean_old_captures(keep)

    def delete_unpinned_items(self) -> None:
        """Delete all unpinned items (purge history)."""
        self._storage.delete_unpinned_items()

    def update_sort_order(self, item_id: int, order: int) -> None:
        """Update explicit manual sort order."""
        self._storage.update_sort_order(item_id, order)

    def get_stats(self) -> dict:
        """Return global usage and storage statistics."""
        return self._storage.get_stats()


# Alias for explicit naming
ClipService = HistoryService
