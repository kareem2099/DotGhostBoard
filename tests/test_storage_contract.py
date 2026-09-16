"""
tests/test_storage_contract.py
──────────────────────────────
Contract tests for core.storage public API.
Freezes current interface, return shapes, and behavioral contracts
to ensure zero regression during modular decomposition.
"""

import os
import shutil
import pytest
from core import storage


@pytest.fixture
def tmp_storage(tmp_path, monkeypatch):
    db_file = str(tmp_path / "contract_test.db")
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    storage.init_db()
    return db_file


class TestStorageContracts:
    def test_add_item_and_retrieve_contract(self, tmp_storage):
        item_id = storage.add_item("text", "hello world", preview=None)
        assert isinstance(item_id, int)
        assert item_id > 0

        item = storage.get_item_by_id(item_id)
        assert item is not None
        assert item["id"] == item_id
        assert item["type"] == "text"
        assert item["content"] == "hello world"
        assert item["preview"] is None
        assert item["is_pinned"] == 0
        assert item["sort_order"] == 0
        assert item["copy_count"] == 1  # starts at 1 on first copy
        assert item["tags"] == ""
        assert item["is_secret"] == 0
        assert "created_at" in item
        assert "updated_at" in item

    def test_duplicate_text_updates_timestamp_and_returns_existing_id(self, tmp_storage):
        id1 = storage.add_item("text", "same text")
        before = storage.get_item_by_id(id1)

        id2 = storage.add_item("text", "same text")
        after = storage.get_item_by_id(id2)

        assert id1 == id2
        assert after["copy_count"] == 2
        assert after["updated_at"] >= before["updated_at"]

        all_items = storage.get_all_items()
        assert len(all_items) == 1

    def test_pinned_and_copy_count_contracts(self, tmp_storage):
        item_id = storage.add_item("text", "pin and copy test")
        assert storage.get_item_by_id(item_id)["copy_count"] == 1
        
        # Pinned toggle
        assert storage.toggle_pin(item_id) is True
        item = storage.get_item_by_id(item_id)
        assert item["is_pinned"] == 1

        assert storage.toggle_pin(item_id) is False
        item = storage.get_item_by_id(item_id)
        assert item["is_pinned"] == 0

        # Copy count
        assert storage.increment_copy_count(item_id) == 2
        assert storage.increment_copy_count(item_id) == 3
        item = storage.get_item_by_id(item_id)
        assert item["copy_count"] == 3

        assert storage.reset_copy_count(item_id) is True
        item = storage.get_item_by_id(item_id)
        assert item["copy_count"] == 0

    def test_tags_contract(self, tmp_storage):
        item_id = storage.add_item("text", "tagged content")

        tags = storage.add_tag(item_id, "Python")
        assert tags == ["#python"]
        assert storage.get_tags(item_id) == ["#python"]

        storage.add_tag(item_id, "code")
        tags = storage.get_tags(item_id)
        assert set(tags) == {"#python", "#code"}

        all_tags = storage.get_all_tags()
        assert set(all_tags) == {"#python", "#code"}

        # Search by tag
        items = storage.get_items_by_tag("#python")
        assert len(items) == 1
        assert items[0]["id"] == item_id

        # Rename tag
        assert storage.rename_tag("#python", "#py") == 1
        assert set(storage.get_tags(item_id)) == {"#code", "#py"}

        # Remove tag
        storage.remove_tag(item_id, "#code")
        assert storage.get_tags(item_id) == ["#py"]

        # Delete tag across items
        assert storage.delete_tag("#py") == 1
        assert storage.get_tags(item_id) == []

    def test_collections_contract(self, tmp_storage):
        coll_id = storage.create_collection("Work")
        assert isinstance(coll_id, int)
        assert coll_id > 0

        collections = storage.get_collections()
        assert any(c["name"] == "Work" and c["id"] == coll_id for c in collections)

        item_id = storage.add_item("text", "work related note")
        storage.move_to_collection(item_id, coll_id)

        coll_items = storage.get_items_by_collection(coll_id)
        assert len(coll_items) == 1
        assert coll_items[0]["id"] == item_id

        # Rename
        assert storage.rename_collection(coll_id, "WorkProjects") is True
        coll = storage.get_collection_by_id(coll_id)
        assert coll["name"] == "WorkProjects"

        # Delete collection moves items to uncategorized (NULL)
        assert storage.delete_collection(coll_id) is True
        item = storage.get_item_by_id(item_id)
        assert item["collection_id"] is None

    def test_trusted_peers_contract(self, tmp_storage):
        storage.add_trusted_peer("peer_01", "Laptop", "shared_sec_key", "192.168.1.100")
        assert storage.is_peer_trusted("peer_01") is True
        assert storage.is_peer_trusted("unknown_peer") is False

        peer = storage.get_trusted_peer("peer_01")
        assert peer is not None
        assert peer["device_name"] == "Laptop"
        assert peer["shared_secret"] == "shared_sec_key"
        assert peer["ip_address"] == "192.168.1.100"

        peers = storage.get_all_trusted_peers()
        assert len(peers) == 1

        assert storage.remove_trusted_peer("peer_01") is True
        assert storage.is_peer_trusted("peer_01") is False

    def test_search_and_export_contract(self, tmp_storage):
        id1 = storage.add_item("text", "Rust memory safety")
        id2 = storage.add_item("text", "Python duck typing")
        storage.add_tag(id1, "systems")

        results = storage.search_items("Rust")
        assert len(results) == 1
        assert results[0]["id"] == id1

        results = storage.search_items("Python", tag_filter="#systems")
        assert len(results) == 0

        # Export txt
        txt = storage.export_items_txt([id1, id2])
        assert "Rust memory safety" in txt
        assert "Python duck typing" in txt

        # Export json
        json_data = storage.export_items_json([id1])
        assert len(json_data) == 1
        assert json_data[0]["content"] == "Rust memory safety"
        assert json_data[0]["tags"] == "#systems"

    def test_delete_and_unpinned_contract(self, tmp_storage):
        id1 = storage.add_item("text", "Keep unpinned")
        id2 = storage.add_item("text", "Keep pinned")
        storage.toggle_pin(id2)

        # delete_unpinned_items
        storage.delete_unpinned_items()
        assert storage.get_item_by_id(id1) is None
        assert storage.get_item_by_id(id2) is not None

        # Cannot delete pinned item directly without unpinning
        assert storage.delete_item(id2) is False
        storage.toggle_pin(id2)
        assert storage.delete_item(id2) is True
        assert storage.get_item_by_id(id2) is None


class TestLegacyMigrationContract:
    """
    Ensures that existing databases with PRAGMA user_version = 0 (created by earlier v1.x versions)
    migrate smoothly without losing any user data.
    """
    def test_v157_database_migrates_without_data_loss(self, tmp_path, monkeypatch):
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "v1_5_7_ghost.db"
        )
        assert os.path.exists(fixture_path), "Fixture v1_5_7_ghost.db must exist"

        target_db = str(tmp_path / "migrated_ghost.db")
        shutil.copyfile(fixture_path, target_db)

        monkeypatch.setattr(storage, "DB_PATH", target_db)
        # Call init_db on the legacy database
        storage.init_db()

        # 1. Verify items preserved
        all_items = storage.get_all_items()
        assert len(all_items) == 3

        # Item 1: Pinned, copy_count=5, tags=['#git', '#dev'], collection=1
        item1 = storage.get_item_by_id(1)
        assert item1 is not None
        assert item1["content"] == "git status --short"
        assert item1["is_pinned"] == 1
        assert item1["copy_count"] == 5
        assert item1["collection_id"] == 1
        assert set(storage.get_tags(1)) == {"#git", "#dev"}

        # Item 2: Secret item
        item2 = storage.get_item_by_id(2)
        assert item2 is not None
        assert item2["is_secret"] == 1
        assert item2["content"] == "SecretAPIKey_123456"

        # Item 3: Image
        item3 = storage.get_item_by_id(3)
        assert item3 is not None
        assert item3["type"] == "image"

        # 2. Verify collection preserved
        collections = storage.get_collections()
        assert len(collections) == 1
        assert collections[0]["name"] == "Work Clips"

        # 3. Verify trusted peers preserved
        peer = storage.get_trusted_peer("node_abc_123")
        assert peer is not None
        assert peer["device_name"] == "ThinkPad-X1"
        assert peer["shared_secret"] == "secret_token_xyz"

        # 4. Verify user_version was stamped correctly
        import sqlite3
        from core.storage.migrations import CURRENT_SCHEMA_VERSION
        with sqlite3.connect(target_db) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION

    def test_fresh_database_initializes_with_current_version(self, tmp_path, monkeypatch):
        import sqlite3
        from core.storage.migrations import CURRENT_SCHEMA_VERSION

        fresh_db = str(tmp_path / "fresh_test.db")
        monkeypatch.setattr(storage, "DB_PATH", fresh_db)
        storage.init_db()

        with sqlite3.connect(fresh_db) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION

    def test_newer_schema_is_rejected(self, tmp_path):
        import sqlite3

        db = str(tmp_path / "future.db")
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA user_version = 999")

        with pytest.raises(RuntimeError, match="newer"):
            storage.init_db(db)


class TestPathOverridesContract:
    def test_media_paths_dynamic_override(self, tmp_path, monkeypatch):
        import core.storage as st
        custom_thumb = str(tmp_path / "custom_thumbs")
        custom_captures = str(tmp_path / "custom_captures")

        monkeypatch.setattr(st, "THUMB_DIR", custom_thumb)
        monkeypatch.setattr(st, "CAPTURES_DIR", custom_captures)

        assert st.get_thumb_dir() == custom_thumb
        assert st.get_captures_dir() == custom_captures
