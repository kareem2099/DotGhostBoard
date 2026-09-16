"""
core/services/collection_service.py
───────────────────────────────────
Service managing collections, categorization, and item assignments.
"""

from __future__ import annotations

from typing import Optional
from core import storage


class CollectionService:
    """Business logic for collections and categorization."""

    def __init__(self, storage_mod=None):
        self._storage = storage_mod or storage

    def get_collections(self) -> list[dict]:
        """Fetch all collections."""
        return self._storage.get_collections()

    def get_collection(self, coll_id: int) -> Optional[dict]:
        """Find a collection by id."""
        return self._storage.get_collection_by_id(coll_id)


    def create_collection(self, name: str) -> Optional[int]:
        """
        Create a new collection.
        Raises ValueError if name is empty.
        """
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Collection name cannot be empty.")
        return self._storage.create_collection(clean_name)

    def rename_collection(self, coll_id: int, new_name: str) -> bool:
        """
        Rename an existing collection.
        Raises ValueError if new_name is empty.
        """
        clean_name = new_name.strip()
        if not clean_name:
            raise ValueError("Collection name cannot be empty.")
        return self._storage.rename_collection(coll_id, clean_name)

    def delete_collection(self, coll_id: int) -> bool:
        """Delete collection and unassign its items."""
        return self._storage.delete_collection(coll_id)

    def move_item_to_collection(self, item_id: int, coll_id: Optional[int]) -> bool:
        """Assign or unassign an item to/from a collection."""
        self._storage.move_to_collection(item_id, coll_id)
        return True
