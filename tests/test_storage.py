"""
tests/test_storage.py
─────────────────────
Unit tests for core/storage.py

Run:
    pytest tests/test_storage.py -v
"""

import os
import pytest
import tempfile

# ── Point storage to a temp DB so we never touch ghost.db ──
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["GHOST_DB_PATH"] = _tmp.name   # storage.py reads this if set

# Now patch DB_PATH before importing storage
import core.storage as storage
storage.DB_PATH = _tmp.name


# ════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════
@pytest.fixture(autouse=True)
def fresh_db():
    """Create clean tables before each test"""
    storage.init_db()
    yield
    # Cleanup after each test
    from core.storage import _db
    with _db() as conn:
        conn.execute("DELETE FROM clipboard_items")


# ════════════════════════════════════════════
# init_db
# ════════════════════════════════════════════
class TestInitDb:
    def test_creates_table(self):
        """init_db should create clipboard_items table"""
        from core.storage import _db
        with _db() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='clipboard_items'"
            )
            assert cursor.fetchone() is not None

    def test_idempotent(self):
        """Calling init_db twice should not cause error"""
        storage.init_db()
        storage.init_db()   # Should not raise an exception


# ════════════════════════════════════════════
# add_item
# ════════════════════════════════════════════
class TestAddItem:
    def test_add_text_returns_id(self):
        item_id = storage.add_item("text", "Hello World")
        assert isinstance(item_id, int)
        assert item_id > 0

    def test_add_image_returns_id(self):
        item_id = storage.add_item("image", "/tmp/test.png", preview="/tmp/test.png")
        assert item_id > 0

    def test_add_video_returns_id(self):
        item_id = storage.add_item("video", "/tmp/test.mp4")
        assert item_id > 0

    def test_no_duplicate_content(self):
        """Same content should return the same ID"""
        id1 = storage.add_item("text", "Duplicate text")
        id2 = storage.add_item("text", "Duplicate text")
        assert id1 == id2

    def test_different_content_different_ids(self):
        id1 = storage.add_item("text", "First")
        id2 = storage.add_item("text", "Second")
        assert id1 != id2

    def test_new_item_not_pinned_by_default(self):
        item_id = storage.add_item("text", "Not pinned")
        item = storage.get_item_by_id(item_id)
        assert item["is_pinned"] == 0


# ════════════════════════════════════════════
# get_all_items
# ════════════════════════════════════════════
class TestGetAllItems:
    def test_empty_db_returns_empty_list(self):
        assert storage.get_all_items() == []

    def test_returns_all_added_items(self):
        storage.add_item("text", "A")
        storage.add_item("text", "B")
        storage.add_item("text", "C")
        items = storage.get_all_items()
        assert len(items) == 3

    def test_pinned_items_come_first(self):
        id1 = storage.add_item("text", "Normal item")
        id2 = storage.add_item("text", "Pinned item")
        storage.toggle_pin(id2)

        items = storage.get_all_items()
        assert items[0]["id"] == id2   # pinned comes first

    def test_respects_limit(self):
        for i in range(10):
            storage.add_item("text", f"Item {i}")
        items = storage.get_all_items(limit=5)
        assert len(items) == 5

    def test_returns_dicts(self):
        storage.add_item("text", "Test")
        items = storage.get_all_items()
        assert isinstance(items[0], dict)
        assert "id" in items[0]
        assert "content" in items[0]
        assert "type" in items[0]


# ════════════════════════════════════════════
# get_item_by_id
# ════════════════════════════════════════════
class TestGetItemById:
    def test_returns_correct_item(self):
        item_id = storage.add_item("text", "Find me")
        item = storage.get_item_by_id(item_id)
        assert item is not None
        assert item["content"] == "Find me"
        assert item["type"] == "text"

    def test_returns_none_for_missing_id(self):
        result = storage.get_item_by_id(99999)
        assert result is None


# ════════════════════════════════════════════
# get_item_by_content
# ════════════════════════════════════════════
class TestGetItemByContent:
    def test_finds_existing_content(self):
        storage.add_item("text", "Unique string 123")
        result = storage.get_item_by_content("Unique string 123")
        assert result is not None
        assert result["content"] == "Unique string 123"

    def test_returns_none_for_missing_content(self):
        result = storage.get_item_by_content("This doesn't exist")
        assert result is None


# ════════════════════════════════════════════
# search_items
# ════════════════════════════════════════════
class TestSearchItems:
    def test_finds_matching_text(self):
        storage.add_item("text", "Hello Python")
        storage.add_item("text", "Hello World")
        storage.add_item("text", "Goodbye")

        results = storage.search_items("Hello")
        assert len(results) == 2

    def test_case_insensitive(self):
        storage.add_item("text", "UPPER CASE TEXT")
        results = storage.search_items("upper")
        assert len(results) == 1

    def test_no_match_returns_empty(self):
        storage.add_item("text", "Something")
        results = storage.search_items("zzznomatch")
        assert results == []

    def test_does_not_search_images(self):
        """Search should not return images even if path matches"""
        storage.add_item("image", "/hello/path.png")
        results = storage.search_items("hello")
        assert results == []


# ════════════════════════════════════════════
# toggle_pin
# ════════════════════════════════════════════
class TestTogglePin:
    def test_pin_unpinned_item(self):
        item_id = storage.add_item("text", "Pin me")
        result = storage.toggle_pin(item_id)
        assert result is True
        item = storage.get_item_by_id(item_id)
        assert item["is_pinned"] == 1

    def test_unpin_pinned_item(self):
        item_id = storage.add_item("text", "Unpin me")
        storage.toggle_pin(item_id)   # pin
        result = storage.toggle_pin(item_id)   # unpin
        assert result is False
        item = storage.get_item_by_id(item_id)
        assert item["is_pinned"] == 0

    def test_toggle_nonexistent_item(self):
        result = storage.toggle_pin(99999)
        assert result is False


# ════════════════════════════════════════════
# delete_item
# ════════════════════════════════════════════
class TestDeleteItem:
    def test_delete_unpinned_item(self):
        item_id = storage.add_item("text", "Delete me")
        result = storage.delete_item(item_id)
        assert result is True
        assert storage.get_item_by_id(item_id) is None

    def test_cannot_delete_pinned_item(self):
        """Pinned items are protected from deletion"""
        item_id = storage.add_item("text", "Protect me")
        storage.toggle_pin(item_id)
        result = storage.delete_item(item_id)
        assert result is False
        assert storage.get_item_by_id(item_id) is not None   # Still exists

    def test_delete_nonexistent_item(self):
        result = storage.delete_item(99999)
        assert result is False


# ════════════════════════════════════════════
# delete_unpinned_items
# ════════════════════════════════════════════
class TestDeleteUnpinnedItems:
    def test_deletes_only_unpinned(self):
        id1 = storage.add_item("text", "Keep me")
        id2 = storage.add_item("text", "Delete me")
        storage.toggle_pin(id1)

        storage.delete_unpinned_items()

        assert storage.get_item_by_id(id1) is not None   # pinned → survived
        assert storage.get_item_by_id(id2) is None        # unpinned → gone

    def test_empty_db_no_error(self):
        """Should work without error even if DB is empty"""
        storage.delete_unpinned_items()   # no exception


# ════════════════════════════════════════════
# get_stats
# ════════════════════════════════════════════
class TestGetStats:
    def test_empty_db_stats(self):
        stats = storage.get_stats()
        assert stats == {"total": 0, "pinned": 0, "texts": 0, "images": 0}

    def test_counts_correctly(self):
        id1 = storage.add_item("text", "Text 1")
        id2 = storage.add_item("text", "Text 2")
        storage.add_item("image", "/img.png")
        storage.toggle_pin(id1)

        stats = storage.get_stats()
        assert stats["total"]  == 3
        assert stats["pinned"] == 1
        assert stats["texts"]  == 2
        assert stats["images"] == 1

    def test_stats_returns_dict(self):
        stats = storage.get_stats()
        assert isinstance(stats, dict)
        assert all(k in stats for k in ["total", "pinned", "texts", "images"])
