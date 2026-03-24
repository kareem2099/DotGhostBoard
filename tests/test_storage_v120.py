"""
tests/test_storage_v120.py
───────────────────────────
Tests for the new storage functions added in v1.2.0:
  - update_preview()
  - update_sort_order()
  - clean_old_captures()

Run:
    pytest tests/test_storage_v120.py -v
"""

import os
import tempfile
import pytest

# ── Use the same temp DB pattern as test_storage.py ──
_tmp = tempfile.NamedTemporaryFile(suffix="_v120.db", delete=False)
_tmp.close()

import core.storage as storage
storage.DB_PATH   = _tmp.name
storage.THUMB_DIR = tempfile.mkdtemp(prefix="ghost_thumb_")
storage.CAPTURES_DIR = tempfile.mkdtemp(prefix="ghost_cap_")


@pytest.fixture(autouse=True)
def fresh_db():
    storage.init_db()
    yield
    from core.storage import _db
    with _db() as conn:
        conn.execute("DELETE FROM clipboard_items")


# ════════════════════════════════════════════
# update_preview
# ════════════════════════════════════════════
class TestUpdatePreview:
    def test_sets_preview_path(self):
        item_id = storage.add_item("video", "/tmp/clip.mp4")
        storage.update_preview(item_id, "/tmp/thumb.png")
        item = storage.get_item_by_id(item_id)
        assert item["preview"] == "/tmp/thumb.png"

    def test_overwrites_existing_preview(self):
        item_id = storage.add_item("image", "/tmp/a.png", preview="/tmp/a.png")
        storage.update_preview(item_id, "/tmp/new_thumb.png")
        item = storage.get_item_by_id(item_id)
        assert item["preview"] == "/tmp/new_thumb.png"

    def test_update_nonexistent_item_no_error(self):
        # Should not raise — just a no-op
        storage.update_preview(99999, "/tmp/ghost.png")


# ════════════════════════════════════════════
# update_sort_order
# ════════════════════════════════════════════
class TestUpdateSortOrder:
    def test_sets_sort_order(self):
        item_id = storage.add_item("text", "Sort me")
        storage.update_sort_order(item_id, 5)
        item = storage.get_item_by_id(item_id)
        assert item["sort_order"] == 5

    def test_updates_multiple_items(self):
        id1 = storage.add_item("text", "First")
        id2 = storage.add_item("text", "Second")
        storage.update_sort_order(id1, 10)
        storage.update_sort_order(id2, 20)
        assert storage.get_item_by_id(id1)["sort_order"] == 10
        assert storage.get_item_by_id(id2)["sort_order"] == 20

    def test_update_nonexistent_no_error(self):
        storage.update_sort_order(99999, 0)


# ════════════════════════════════════════════
# sort_order column migration
# ════════════════════════════════════════════
class TestSortOrderMigration:
    def test_column_exists_after_init(self):
        """sort_order column must exist (migration runs on init_db)."""
        from core.storage import _db
        with _db() as conn:
            cursor = conn.execute("PRAGMA table_info(clipboard_items)")
            columns = [row[1] for row in cursor.fetchall()]
        assert "sort_order" in columns

    def test_default_sort_order_is_zero(self):
        item_id = storage.add_item("text", "Default order")
        item = storage.get_item_by_id(item_id)
        assert item["sort_order"] == 0


# ════════════════════════════════════════════
# clean_old_captures
# ════════════════════════════════════════════
class TestCleanOldCaptures:
    def _make_tmp_file(self, suffix=".png") -> str:
        """Create a real temp file and return its path."""
        f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        f.write(b"fake png data")
        f.close()
        return f.name

    def test_no_cleanup_needed(self):
        """Fewer items than keep limit — nothing deleted."""
        for i in range(3):
            path = self._make_tmp_file()
            storage.add_item("image", path, preview=path)
        removed = storage.clean_old_captures(keep=10)
        assert removed == 0

    def test_removes_excess_items(self):
        """Items beyond the keep limit are removed from DB."""
        paths = []
        for i in range(5):
            path = self._make_tmp_file()
            paths.append(path)
            storage.add_item("image", path, preview=path)

        removed = storage.clean_old_captures(keep=3)
        assert removed == 2

        remaining = storage.get_all_items(limit=100)
        image_items = [r for r in remaining if r["type"] == "image"]
        assert len(image_items) == 3

    def test_deletes_capture_files_from_disk(self):
        """clean_old_captures also removes the .png files from disk."""
        paths = []
        for i in range(4):
            path = self._make_tmp_file()
            paths.append(path)
            storage.add_item("image", path, preview=path)

        storage.clean_old_captures(keep=2)

        # The 2 oldest files should be gone
        surviving = [p for p in paths if os.path.isfile(p)]
        assert len(surviving) == 2

    def test_pinned_items_never_cleaned(self):
        """Pinned captures are always kept regardless of keep limit."""
        pinned_path = self._make_tmp_file()
        pinned_id = storage.add_item("image", pinned_path, preview=pinned_path)
        storage.toggle_pin(pinned_id)

        for i in range(5):
            path = self._make_tmp_file()
            storage.add_item("image", path, preview=path)

        storage.clean_old_captures(keep=2)

        # Pinned item must not be deleted
        assert storage.get_item_by_id(pinned_id) is not None
        assert os.path.isfile(pinned_path)

    def test_empty_db_no_error(self):
        removed = storage.clean_old_captures(keep=10)
        assert removed == 0

    def test_text_items_not_counted(self):
        """Text items are never touched by clean_old_captures."""
        for i in range(5):
            storage.add_item("text", f"Text item {i}")
        removed = storage.clean_old_captures(keep=0)
        assert removed == 0
        assert len(storage.get_all_items()) == 5
