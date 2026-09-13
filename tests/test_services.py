"""
tests/test_services.py
───────────────────────
Tests for Core Services Layer (HistoryService, CollectionService, SecurityService, SyncService).
"""

import pytest
import time
from core.services import (
    HistoryService,
    ClipService,
    CollectionService,
    SecurityService,
    SyncService,
)
from core.constants import PIN_SUGGESTION_THRESHOLD, AUTO_PIN_THRESHOLD


@pytest.fixture
def services_env(tmp_path, monkeypatch):
    """Sandbox environment for testing core services."""
    import core.storage as storage
    import core.crypto as crypto
    import core.security.vault.database as vdb

    db_file = str(tmp_path / "ghost.db")
    vault_db_file = str(tmp_path / "vault.db")

    monkeypatch.setattr(storage, "DB_PATH", db_file)
    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))
    monkeypatch.setattr(crypto, "_VERIFY_FILE", str(tmp_path / "eclipse.verify"))
    monkeypatch.setattr(vdb, "VAULT_DB_PATH", vault_db_file)

    storage.init_db()

    return {
        "storage": storage,
        "crypto": crypto,
        "db_file": db_file,
    }


def test_history_service_queries_and_crud(services_env):
    storage = services_env["storage"]
    service = HistoryService(storage_mod=storage)

    # Alias check
    assert ClipService is HistoryService

    # Add sample clips
    id1 = storage.add_item("text", "First item note")
    id2 = storage.add_item("text", "Second item secret")
    id3 = storage.add_item("text", "Third item note")

    # 1. Fetch all items
    items = service.get_items(limit=10)
    assert len(items) == 3

    # 2. Search query filter
    searched = service.get_items(query="secret")
    assert len(searched) == 1
    assert searched[0]["id"] == id2

    # 3. Tags contract: returns updated list[str]
    assert service.add_tag(id1, "work") == ["#work"]
    tagged = service.get_items(tag="work")
    assert len(tagged) == 1
    assert tagged[0]["id"] == id1

    assert service.remove_tag(id1, "work") == []
    assert len(service.get_items(tag="work")) == 0

    # 4. Single & Bulk Pin
    assert service.toggle_pin(id1) is True
    assert service.get_item(id1)["is_pinned"] == 1
    assert service.toggle_pin(id1) is False

    bulk_pins = service.toggle_pins([id1, id2])
    assert bulk_pins[id1] is True
    assert bulk_pins[id2] is True

    # 5. Sort order and cleanups
    service.update_sort_order(id1, 99)
    assert service.get_item(id1)["sort_order"] == 99

    # Unpin before deleting (pinned items are protected from deletion in storage)
    unpins = service.toggle_pins([id1, id2])
    assert unpins[id1] is False
    assert unpins[id2] is False

    # 6. Bulk Delete
    deleted_count = service.delete_items([id1, id2])
    assert deleted_count == 2
    assert service.get_item(id1) is None
    assert service.get_item(id2) is None

    # 7. Delete unpinned
    service.delete_unpinned_items()
    assert service.get_item(id3) is None


def test_history_service_copy_thresholds(services_env):
    storage = services_env["storage"]
    service = HistoryService(storage_mod=storage)

    item_id = storage.add_item("text", "Frequently copied snippet")
    # Initial copy_count is 1

    # Copy up to PIN_SUGGESTION_THRESHOLD - 1 (count: 2, 3, 4)
    for _ in range(PIN_SUGGESTION_THRESHOLD - 2):
        count, suggest, auto_pin = service.record_copy(item_id)
        assert suggest is False
        assert auto_pin is False

    # Next copy reaches PIN_SUGGESTION_THRESHOLD (count: 5)
    count, suggest, auto_pin = service.record_copy(item_id)
    assert count == PIN_SUGGESTION_THRESHOLD
    assert suggest is True
    assert auto_pin is False

    # Advance to AUTO_PIN_THRESHOLD - 1 (count: 6, 7, 8, 9)
    for _ in range(AUTO_PIN_THRESHOLD - PIN_SUGGESTION_THRESHOLD - 1):
        count, suggest, auto_pin = service.record_copy(item_id)
        assert auto_pin is False

    # Reaching AUTO_PIN_THRESHOLD (count: 10) should auto-pin the item
    count, suggest, auto_pin = service.record_copy(item_id)
    assert count == AUTO_PIN_THRESHOLD
    assert auto_pin is True
    assert service.get_item(item_id)["is_pinned"] == 1


def test_collection_service_lifecycle(services_env):
    storage = services_env["storage"]
    service = CollectionService(storage_mod=storage)

    # Validation: empty name
    with pytest.raises(ValueError, match="cannot be empty"):
        service.create_collection("   ")

    # Create collection
    coll_id = service.create_collection("Project Alpha")
    assert coll_id is not None

    colls = service.get_collections()
    assert any(c["name"] == "Project Alpha" for c in colls)

    # Rename collection
    assert service.rename_collection(coll_id, "Project Beta") is True
    coll = service.get_collection(coll_id)
    assert coll is not None
    assert coll["name"] == "Project Beta"

    # Move item into collection
    item_id = storage.add_item("text", "Alpha note")
    assert service.move_item_to_collection(item_id, coll_id) is True
    item = storage.get_item_by_id(item_id)
    assert item["collection_id"] == coll_id

    # Delete collection (unassigns items)
    assert service.delete_collection(coll_id) is True
    assert service.get_collection(coll_id) is None
    item_after = storage.get_item_by_id(item_id)
    assert item_after["collection_id"] is None


def test_security_service_session_and_encryption(services_env):
    storage = services_env["storage"]
    crypto = services_env["crypto"]
    service = SecurityService(crypto_mod=crypto, storage_mod=storage)

    password = "MasterPassword999"

    assert service.has_master_password() is False
    assert service.is_locked is False  # When no master password, not locked

    # Setup master password -> automatically unlocks
    service.setup_master_password(password)
    assert service.has_master_password() is True
    assert service.is_locked is False
    assert service.active_key is not None
    assert service.vault.is_unlocked is True

    # Lock session
    service.lock()
    assert service.is_locked is True
    assert service.active_key is None
    assert service.vault.is_unlocked is False

    # Operations while locked must fail
    item_id = storage.add_item("text", "Secret api key token")
    assert service.encrypt_clip(item_id) is False

    # Unlock session
    assert service.unlock("WrongPassword") is False
    assert service.unlock(password) is True
    assert service.is_locked is False
    assert service.active_key is not None
    assert service.vault.is_unlocked is True

    # Encrypt clip
    assert service.encrypt_clip(item_id) is True
    raw_item = storage.get_item_by_id(item_id)
    assert raw_item["is_secret"] == 1
    assert raw_item["content"] != "Secret api key token"

    # Decrypt for view
    decrypted_content = service.decrypt_clip_for_view(item_id)
    assert decrypted_content == "Secret api key token"

    # Auto-lock expiration
    service.touch()
    assert service.is_auto_lock_expired(10) is False
    # Simulate past activity
    service._last_activity = time.time() - 15
    assert service.is_auto_lock_expired(10) is True

    # Permanent decrypt
    assert service.decrypt_clip_permanent(item_id) is True
    restored = storage.get_item_by_id(item_id)
    assert restored["is_secret"] == 0
    assert restored["content"] == "Secret api key token"


def test_security_service_password_rotation_and_removal(services_env):
    storage = services_env["storage"]
    crypto = services_env["crypto"]
    service = SecurityService(crypto_mod=crypto, storage_mod=storage)

    pw1 = "OriginalPassword123"
    pw2 = "RotatedPassword456"

    service.setup_master_password(pw1)

    # 1. Add secret Eclipse clip
    clip_id = storage.add_item("text", "Top Secret Clip Content")
    assert service.encrypt_clip(clip_id) is True

    # 2. Add secret Vault entry
    v_id = service.vault.add_secret("Production DB", "super_secret_db_pass", category="password")
    assert v_id > 0

    # 3. Rotate password
    ok, msg = service.change_master_password(pw1, pw2)
    assert ok is True
    assert "successfully" in msg

    # Old password no longer verifies
    assert service.verify_master_password(pw1) is False
    assert service.verify_master_password(pw2) is True

    # Eclipse clip was re-encrypted with pw2 and can be decrypted
    decrypted_clip = service.decrypt_clip_for_view(clip_id)
    assert decrypted_clip == "Top Secret Clip Content"

    # Vault secret is still decryptable with pw2 via envelope DEK rewrapping!
    vault_secret = service.vault.get_secret(v_id)
    assert vault_secret == "super_secret_db_pass"

    # 4. Attempt remove master password while Vault has entries -> MUST FAIL safely
    ok, count, msg = service.remove_master_password(pw2)
    assert ok is False
    assert count == 0
    assert "Vault contains" in msg
    assert service.has_master_password() is True  # preserved!

    # 5. Empty Vault and try with wrong password -> MUST FAIL
    service.vault.delete_secret(v_id)
    assert service.vault.count() == 0

    ok, count, msg = service.remove_master_password("WrongPassword")
    assert ok is False
    assert count == 0
    assert "incorrect" in msg
    assert service.has_master_password() is True  # preserved!

    # 6. Remove master password with correct password
    ok, count, msg = service.remove_master_password(pw2)
    assert ok is True
    assert count == 1  # 1 Eclipse item was decrypted
    assert service.has_master_password() is False

    # Verify Eclipse item is now unencrypted in ghost.db
    unencrypted_item = storage.get_item_by_id(clip_id)
    assert unencrypted_item["is_secret"] == 0
    assert unencrypted_item["content"] == "Top Secret Clip Content"


def test_sync_service_peers(services_env):
    storage = services_env["storage"]
    sync_service = SyncService(local_node_id="node_123", api_port=9090, storage_mod=storage)

    # Initial state
    assert sync_service.is_peer_trusted("peer_abc") is False

    # Add peer to storage with correct parameter order:
    # add_trusted_peer(node_id, device_name, shared_secret, ip)
    storage.add_trusted_peer("peer_abc", "Test Laptop", "shared_sec", "http://192.168.1.50:9090")
    assert sync_service.is_peer_trusted("peer_abc") is True

    peer = sync_service.get_trusted_peer("peer_abc")
    assert peer is not None
    assert peer["device_name"] == "Test Laptop"
    assert peer["shared_secret"] == "shared_sec"
    assert peer["ip_address"] == "http://192.168.1.50:9090"

    # Test get_trusted_peers() calls get_all_trusted_peers()
    all_peers = sync_service.get_trusted_peers()
    assert len(all_peers) == 1
    assert all_peers[0]["node_id"] == "peer_abc"

    # Unpair (notify=False so no HTTP call)
    assert sync_service.unpair_peer("peer_abc", notify=False) is True
    assert sync_service.is_peer_trusted("peer_abc") is False
    assert len(sync_service.get_trusted_peers()) == 0


def test_setup_master_password_rejects_existing_password(services_env):
    """setup_master_password must raise RuntimeError if password is already configured."""
    crypto = services_env["crypto"]
    storage = services_env["storage"]
    service = SecurityService(crypto_mod=crypto, storage_mod=storage)

    service.setup_master_password("FirstPassword123")
    assert service.has_master_password() is True

    # Overwriting must fail closed and raise RuntimeError
    with pytest.raises(RuntimeError, match="Master password already exists"):
        service.setup_master_password("OverwritingPassword456")


def test_bulk_decrypt_failure_is_atomic(services_env):
    """If any secret item fails decryption during bulk decrypt, NO items are mutated."""
    storage = services_env["storage"]
    crypto = services_env["crypto"]
    key = crypto.derive_key("TestAtomicPassword")

    # Add 3 text items and encrypt them
    id1 = storage.add_item("text", "Valid Secret One")
    id2 = storage.add_item("text", "Valid Secret Two")
    id3 = storage.add_item("text", "Valid Secret Three")

    storage.encrypt_item(id1, key)
    storage.encrypt_item(id2, key)
    storage.encrypt_item(id3, key)

    # Corrupt item 2's ciphertext directly in DB
    from core.storage.database import _db
    with _db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET content = 'corrupted_base64_payload' WHERE id = ?",
            (id2,)
        )

    # Attempt bulk decryption with the valid key
    result = storage.decrypt_all_secret_items(key)
    assert result == -1  # Aborted!

    # Verify that id1 and id3 are STILL secret and NOT decrypted to plaintext!
    item1 = storage.get_item_by_id(id1)
    item2 = storage.get_item_by_id(id2)
    item3 = storage.get_item_by_id(id3)

    assert item1["is_secret"] == 1
    assert item2["is_secret"] == 1
    assert item3["is_secret"] == 1
