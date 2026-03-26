"""
tests/test_storage_v130.py
───────────────────────────
Unit tests for v1.3.0 (Wraith) storage features:
  W001 — Tag CRUD (get_tags, add_tag, remove_tag, get_items_by_tag, get_all_tags)
  W004 — Collection CRUD (create, delete, rename, get, move, get_by_collection)
  W003 — search_items with tag filter
  W008 — export_items (txt + json)
  W009 — rename_tag, delete_tag (global tag ops)

Run:
    pytest tests/test_storage_v130.py -v
"""

import json
import os
import tempfile
import pytest

# ── Redirect storage to a temp DB so we never touch the real one ──
_tmp = tempfile.NamedTemporaryFile(suffix="_v130.db", delete=False)
_tmp.close()

import core.storage as storage
storage.DB_PATH      = _tmp.name
storage.THUMB_DIR    = tempfile.mkdtemp(prefix="ghost_thumb_v130_")
storage.CAPTURES_DIR = tempfile.mkdtemp(prefix="ghost_cap_v130_")


# ── Auto-fixture: fresh tables before every test ──────────────────────────────
@pytest.fixture(autouse=True)
def fresh_db():
    storage.init_db()
    yield
    from core.storage import _db
    with _db() as conn:
        conn.execute("DELETE FROM clipboard_items")
        conn.execute("DELETE FROM collections")


# ══════════════════════════════════════════════════════════════
# W001 — Tag CRUD
# ══════════════════════════════════════════════════════════════

class TestGetTags:
    def test_returns_empty_list_for_new_item(self):
        iid = storage.add_item("text", "No tags here")
        assert storage.get_tags(iid) == []

    def test_returns_empty_for_nonexistent_item(self):
        assert storage.get_tags(99999) == []


class TestAddTag:
    def test_adds_single_tag(self):
        iid = storage.add_item("text", "Hello")
        result = storage.add_tag(iid, "#python")
        assert "#python" in result

    def test_normalises_tag_without_hash(self):
        iid = storage.add_item("text", "Hello")
        result = storage.add_tag(iid, "code")
        assert "#code" in result

    def test_normalises_tag_to_lowercase(self):
        iid = storage.add_item("text", "Hello")
        result = storage.add_tag(iid, "#Python")
        assert "#python" in result
        assert "#Python" not in result

    def test_idempotent_no_duplicates(self):
        iid = storage.add_item("text", "Hello")
        storage.add_tag(iid, "#dup")
        storage.add_tag(iid, "#dup")
        tags = storage.get_tags(iid)
        assert tags.count("#dup") == 1

    def test_multiple_tags_on_same_item(self):
        iid = storage.add_item("text", "Tagged item")
        storage.add_tag(iid, "#code")
        storage.add_tag(iid, "#python")
        storage.add_tag(iid, "#work")
        tags = storage.get_tags(iid)
        assert set(tags) == {"#code", "#python", "#work"}

    def test_persisted_after_reload(self):
        iid = storage.add_item("text", "Persisted tag")
        storage.add_tag(iid, "#saved")
        fresh = storage.get_item_by_id(iid)
        assert "#saved" in fresh["tags"]


class TestRemoveTag:
    def test_removes_existing_tag(self):
        iid = storage.add_item("text", "Remove me")
        storage.add_tag(iid, "#remove")
        result = storage.remove_tag(iid, "#remove")
        assert "#remove" not in result

    def test_no_error_removing_nonexistent_tag(self):
        iid = storage.add_item("text", "No tag")
        result = storage.remove_tag(iid, "#ghost")
        assert result == []

    def test_remove_one_keeps_others(self):
        iid = storage.add_item("text", "Multi")
        storage.add_tag(iid, "#keep")
        storage.add_tag(iid, "#drop")
        storage.remove_tag(iid, "#drop")
        tags = storage.get_tags(iid)
        assert "#keep" in tags
        assert "#drop" not in tags

    def test_normalises_tag_before_remove(self):
        iid = storage.add_item("text", "Norm")
        storage.add_tag(iid, "#norm")
        result = storage.remove_tag(iid, "norm")   # no # prefix
        assert "#norm" not in result


class TestGetItemsByTag:
    def test_finds_item_with_tag(self):
        iid = storage.add_item("text", "Find me")
        storage.add_tag(iid, "#find")
        results = storage.get_items_by_tag("#find")
        assert any(r["id"] == iid for r in results)

    def test_does_not_return_untagged_item(self):
        iid_tagged   = storage.add_item("text", "Tagged")
        iid_untagged = storage.add_item("text", "Untagged")
        storage.add_tag(iid_tagged, "#only")
        results = storage.get_items_by_tag("#only")
        ids = [r["id"] for r in results]
        assert iid_tagged in ids
        assert iid_untagged not in ids

    def test_tag_at_start_middle_end_of_list(self):
        """Tag matching must work regardless of position in comma-separated list."""
        iid = storage.add_item("text", "Positions")
        storage.add_tag(iid, "#first")
        storage.add_tag(iid, "#middle")
        storage.add_tag(iid, "#last")
        for tag in ("#first", "#middle", "#last"):
            results = storage.get_items_by_tag(tag)
            assert any(r["id"] == iid for r in results), f"{tag} not found"


class TestGetAllTags:
    def test_returns_all_unique_tags(self):
        id1 = storage.add_item("text", "A")
        id2 = storage.add_item("text", "B")
        storage.add_tag(id1, "#alpha")
        storage.add_tag(id2, "#beta")
        storage.add_tag(id2, "#alpha")   # duplicate across items
        all_tags = storage.get_all_tags()
        assert "#alpha" in all_tags
        assert "#beta" in all_tags
        assert all_tags.count("#alpha") == 1   # deduplicated

    def test_empty_when_no_tags(self):
        storage.add_item("text", "No tags")
        assert storage.get_all_tags() == []


# ══════════════════════════════════════════════════════════════
# W004 — Collections CRUD
# ══════════════════════════════════════════════════════════════

class TestCreateCollection:
    def test_creates_and_returns_id(self):
        cid = storage.create_collection("Work")
        assert isinstance(cid, int)
        assert cid > 0

    def test_duplicate_name_returns_existing_id(self):
        cid1 = storage.create_collection("Same")
        cid2 = storage.create_collection("Same")
        assert cid1 == cid2

    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            storage.create_collection("   ")


class TestGetCollections:
    def test_lists_all_collections(self):
        storage.create_collection("Alpha")
        storage.create_collection("Beta")
        colls = storage.get_collections()
        names = [c["name"] for c in colls]
        assert "Alpha" in names
        assert "Beta" in names

    def test_item_count_correct(self):
        cid = storage.create_collection("Counted")
        iid = storage.add_item("text", "Belongs here")
        storage.move_to_collection(iid, cid)
        colls = storage.get_collections()
        target = next(c for c in colls if c["id"] == cid)
        assert target["item_count"] == 1


class TestDeleteCollection:
    def test_deletes_collection(self):
        cid = storage.create_collection("ToDelete")
        storage.delete_collection(cid)
        colls = storage.get_collections()
        assert not any(c["id"] == cid for c in colls)

    def test_items_become_uncategorized(self):
        cid = storage.create_collection("Temp")
        iid = storage.add_item("text", "Orphan item")
        storage.move_to_collection(iid, cid)
        storage.delete_collection(cid)
        item = storage.get_item_by_id(iid)
        assert item["collection_id"] is None


class TestRenameCollection:
    def test_renames_successfully(self):
        cid = storage.create_collection("OldName")
        storage.rename_collection(cid, "NewName")
        colls = storage.get_collections()
        target = next((c for c in colls if c["id"] == cid), None)
        assert target is not None
        assert target["name"] == "NewName"

    def test_empty_name_returns_false(self):
        cid = storage.create_collection("Valid")
        result = storage.rename_collection(cid, "   ")
        assert result is False


class TestMoveToCollection:
    def test_moves_item_to_collection(self):
        cid = storage.create_collection("Target")
        iid = storage.add_item("text", "Move me")
        storage.move_to_collection(iid, cid)
        item = storage.get_item_by_id(iid)
        assert item["collection_id"] == cid

    def test_moves_item_to_uncategorized(self):
        cid = storage.create_collection("Source")
        iid = storage.add_item("text", "Remove from coll")
        storage.move_to_collection(iid, cid)
        storage.move_to_collection(iid, None)
        item = storage.get_item_by_id(iid)
        assert item["collection_id"] is None


class TestGetItemsByCollection:
    def test_returns_items_in_collection(self):
        cid = storage.create_collection("MyBox")
        iid = storage.add_item("text", "In box")
        storage.move_to_collection(iid, cid)
        items = storage.get_items_by_collection(cid)
        assert any(i["id"] == iid for i in items)

    def test_returns_uncategorized_items(self):
        iid = storage.add_item("text", "Uncategorized")
        items = storage.get_items_by_collection(None)
        assert any(i["id"] == iid for i in items)

    def test_does_not_mix_collections(self):
        c1 = storage.create_collection("Box1")
        c2 = storage.create_collection("Box2")
        i1 = storage.add_item("text", "In Box1")
        i2 = storage.add_item("text", "In Box2")
        storage.move_to_collection(i1, c1)
        storage.move_to_collection(i2, c2)
        box1_ids = [i["id"] for i in storage.get_items_by_collection(c1)]
        assert i1 in box1_ids
        assert i2 not in box1_ids


# ══════════════════════════════════════════════════════════════
# W003 — search_items with tag filter
# ══════════════════════════════════════════════════════════════

class TestSearchItemsWithTagFilter:
    def test_text_only_search(self):
        iid = storage.add_item("text", "python is great")
        results = storage.search_items("python")
        assert any(r["id"] == iid for r in results)

    def test_tag_only_filter(self):
        iid = storage.add_item("text", "anything")
        storage.add_tag(iid, "#work")
        results = storage.search_items("", tag_filter="#work")
        assert any(r["id"] == iid for r in results)

    def test_combined_text_and_tag(self):
        iid_match  = storage.add_item("text", "python script")
        iid_no_tag = storage.add_item("text", "python tutorial")
        storage.add_tag(iid_match, "#code")
        results = storage.search_items("python", tag_filter="#code")
        ids = [r["id"] for r in results]
        assert iid_match in ids
        assert iid_no_tag not in ids

    def test_no_false_positive_on_partial_tag_name(self):
        """#py should NOT match items tagged only with #python."""
        iid = storage.add_item("text", "Test")
        storage.add_tag(iid, "#python")
        results = storage.search_items("", tag_filter="#py")
        assert not any(r["id"] == iid for r in results)


# ══════════════════════════════════════════════════════════════
# W008 — export_items
# ══════════════════════════════════════════════════════════════

class TestExportItems:
    def _make_items(self):
        id1 = storage.add_item("text", "Export item one")
        id2 = storage.add_item("text", "Export item two")
        storage.add_tag(id1, "#export")
        return id1, id2

    def test_txt_contains_content(self):
        id1, id2 = self._make_items()
        output = storage.export_items([id1, id2], "txt")
        assert "Export item one" in output
        assert "Export item two" in output

    def test_txt_contains_tags(self):
        id1, _ = self._make_items()
        output = storage.export_items([id1], "txt")
        assert "#export" in output

    def test_txt_contains_separator(self):
        id1, _ = self._make_items()
        output = storage.export_items([id1], "txt")
        assert "─" in output

    def test_json_is_valid(self):
        id1, id2 = self._make_items()
        output = storage.export_items([id1, id2], "json")
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_json_has_expected_keys(self):
        id1, _ = self._make_items()
        output = storage.export_items([id1], "json")
        obj = json.loads(output)[0]
        for key in ("id", "type", "content", "created_at", "tags"):
            assert key in obj, f"Missing key: {key}"

    def test_json_tags_is_list(self):
        id1, _ = self._make_items()
        output = storage.export_items([id1], "json")
        obj = json.loads(output)[0]
        assert isinstance(obj["tags"], list)
        assert "#export" in obj["tags"]

    def test_skips_nonexistent_ids_gracefully(self):
        id1, _ = self._make_items()
        output = storage.export_items([id1, 99999], "json")
        parsed = json.loads(output)
        assert len(parsed) == 1

    def test_empty_list_returns_empty(self):
        txt_out  = storage.export_items([], "txt")
        json_out = storage.export_items([], "json")
        assert txt_out == ""
        assert json.loads(json_out) == []


# ══════════════════════════════════════════════════════════════
# W009 — rename_tag / delete_tag (global ops)
# ══════════════════════════════════════════════════════════════

class TestRenameTag:
    def test_renames_across_multiple_items(self):
        id1 = storage.add_item("text", "One")
        id2 = storage.add_item("text", "Two")
        storage.add_tag(id1, "#old")
        storage.add_tag(id2, "#old")
        count = storage.rename_tag("#old", "#new")
        assert count == 2
        assert "#new" in storage.get_tags(id1)
        assert "#new" in storage.get_tags(id2)
        assert "#old" not in storage.get_tags(id1)

    def test_rename_to_same_name_is_noop(self):
        iid = storage.add_item("text", "Same")
        storage.add_tag(iid, "#same")
        count = storage.rename_tag("#same", "#same")
        assert count == 0

    def test_normalises_both_tags(self):
        iid = storage.add_item("text", "Norm")
        storage.add_tag(iid, "#old")
        storage.rename_tag("old", "new")   # no # prefix
        assert "#new" in storage.get_tags(iid)


class TestDeleteTag:
    def test_removes_tag_from_all_items(self):
        id1 = storage.add_item("text", "One")
        id2 = storage.add_item("text", "Two")
        storage.add_tag(id1, "#gone")
        storage.add_tag(id2, "#gone")
        count = storage.delete_tag("#gone")
        assert count == 2
        assert "#gone" not in storage.get_tags(id1)
        assert "#gone" not in storage.get_tags(id2)

    def test_preserves_other_tags(self):
        iid = storage.add_item("text", "Keep other")
        storage.add_tag(iid, "#keep")
        storage.add_tag(iid, "#drop")
        storage.delete_tag("#drop")
        assert "#keep" in storage.get_tags(iid)

    def test_nonexistent_tag_returns_zero(self):
        count = storage.delete_tag("#ghost")
        assert count == 0