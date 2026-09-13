"""
tests/test_vault.py
───────────────────
Tests for The Vault subsystem (vault.db physical isolation & envelope encryption).
"""

import pytest
from core.crypto import save_master_password
from core.security.vault import (
    VaultRepository,
    VaultService,
    VaultLockedError,
    init_vault_db,
    get_vault_db_path,
)
from core.storage.database import _db


@pytest.fixture
def vault_env(tmp_path, monkeypatch):
    """Sandbox both crypto config and vault.db path."""
    import core.crypto as crypto
    import core.security.vault.database as vdb
    import core.storage as storage

    vault_db_file = str(tmp_path / "vault.db")
    ghost_db_file = str(tmp_path / "ghost.db")

    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))
    monkeypatch.setattr(crypto, "_VERIFY_FILE", str(tmp_path / "eclipse.verify"))
    monkeypatch.setattr(vdb, "VAULT_DB_PATH", vault_db_file)
    monkeypatch.setattr(storage, "DB_PATH", ghost_db_file)

    storage.init_db()
    init_vault_db(vault_db_file)

    return {
        "vault_db": vault_db_file,
        "ghost_db": ghost_db_file,
    }


def test_physical_database_isolation(vault_env):
    """Verify that vault.db and ghost.db are strictly isolated and do not share tables."""
    import sqlite3

    # Check ghost.db tables
    with sqlite3.connect(vault_env["ghost_db"]) as g_conn:
        g_cur = g_conn.cursor()
        g_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        g_tables = {row[0] for row in g_cur.fetchall()}
        assert "clipboard_items" in g_tables
        assert "vault_items" not in g_tables

    # Check vault.db tables
    with sqlite3.connect(vault_env["vault_db"]) as v_conn:
        v_cur = v_conn.cursor()
        v_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        v_tables = {row[0] for row in v_cur.fetchall()}
        assert "vault_items" in v_tables
        assert "clipboard_items" not in v_tables


def test_vault_repository_crud(vault_env):
    repo = VaultRepository(vault_env["vault_db"])

    # Add item
    item_id = repo.add_item(
        title="Production AWS Token",
        ciphertext="encrypted_blob_sample",
        category="token",
    )
    assert item_id > 0

    # Get item
    item = repo.get_item(item_id)
    assert item is not None
    assert item.title == "Production AWS Token"
    assert item.category == "token"
    assert item.ciphertext == "encrypted_blob_sample"

    # List items
    items = repo.list_items()
    assert len(items) == 1

    # Update item
    success = repo.update_item(item_id, title="Staging AWS Token")
    assert success is True
    updated = repo.get_item(item_id)
    assert updated.title == "Staging AWS Token"

    # Count
    assert repo.count_items() == 1
    assert repo.count_items(category="token") == 1
    assert repo.count_items(category="password") == 0

    # Delete item
    deleted = repo.delete_item(item_id)
    assert deleted is True
    assert repo.get_item(item_id) is None
    assert repo.count_items() == 0


def test_vault_service_session_lifecycle_and_encryption(vault_env):
    password = "MasterPassword123!"
    save_master_password(password)

    service = VaultService()
    assert service.is_unlocked is False

    # Locked operations must fail
    with pytest.raises(VaultLockedError):
        service.add_secret("GitHub PAT", "ghp_1234567890", category="token")

    with pytest.raises(VaultLockedError):
        service.get_secret(1)

    # Unlock with wrong password
    assert service.unlock("WrongPassword") is False
    assert service.is_unlocked is False

    # Unlock with correct password
    assert service.unlock(password) is True
    assert service.is_unlocked is True

    # Add secret
    item_id = service.add_secret("GitHub PAT", "ghp_1234567890", category="token")
    assert item_id > 0

    # Retrieve and decrypt secret
    secret = service.get_secret(item_id)
    assert secret == "ghp_1234567890"

    # Update secret
    updated = service.update_secret(item_id, secret_text="ghp_NEW_TOKEN_STRING")
    assert updated is True
    assert service.get_secret(item_id) == "ghp_NEW_TOKEN_STRING"

    # Metadata summary list works even while locked!
    service.lock()
    assert service.is_unlocked is False

    summaries = service.list_secrets()
    assert len(summaries) == 1
    assert summaries[0].title == "GitHub PAT"
    assert summaries[0].category == "token"

    # But getting plaintext fails when locked
    with pytest.raises(VaultLockedError):
        service.get_secret(item_id)


def test_vault_schema_versioning_and_downgrade_rejection(vault_env):
    """Ensure vault.db has user_version = 1 and rejects future schema versions."""
    import sqlite3
    db_path = vault_env["vault_db"]

    with sqlite3.connect(db_path) as conn:
        ver = conn.execute("PRAGMA user_version;").fetchone()[0]
        assert ver == 1

        # Simulate future schema from v3.0
        conn.execute("PRAGMA user_version = 99;")

    # Calling init_vault_db on newer version must raise RuntimeError
    with pytest.raises(RuntimeError, match="newer than supported version"):
        init_vault_db(db_path)


def test_vault_file_permissions(vault_env):
    """Ensure vault.db is created with strict 0600 POSIX permissions."""
    import os
    import stat
    db_path = vault_env["vault_db"]

    mode = stat.S_IMODE(os.stat(db_path).st_mode)
    assert mode == 0o600


def test_vault_envelope_dek_rewrap(vault_env):
    """Ensure Vault DEK can be re-wrapped with a new KEK without losing secrets."""
    from core.crypto import derive_vault_key

    pw1 = "OldPasswordPass123"
    pw2 = "NewPasswordPass456"

    kek1 = derive_vault_key(pw1)
    kek2 = derive_vault_key(pw2)

    service = VaultService()
    service.unlock_with_key(kek1)

    sec_id = service.add_secret("API Key", "super-secret-token", category="token")
    assert service.get_secret(sec_id) == "super-secret-token"

    # Re-wrap DEK to kek2
    assert service.rewrap_dek(kek1, kek2) is True

    # Lock and unlock with kek2
    service.lock()
    service.unlock_with_key(kek2)
    assert service.get_secret(sec_id) == "super-secret-token"


def test_vault_items_without_wrapped_dek_fail_closed(vault_env):
    """If vault contains items but wrapped DEK is missing/wiped, unlocking must fail closed."""
    from core.crypto import derive_vault_key

    pw = "TestVaultPassword123"
    kek = derive_vault_key(pw)

    service = VaultService()
    service.unlock_with_key(kek)
    service.add_secret("Secret Item", "plaintext-secret")

    # Manually delete wrapped_dek metadata while leaving vault_items intact
    service.lock()
    service._repo.delete_metadata("wrapped_dek")
    assert service._repo.count_items() > 0

    # Unlocking must fail closed and raise RuntimeError
    with pytest.raises(RuntimeError, match="Vault contains encrypted items but wrapped DEK is missing"):
        service._unwrap_or_create_dek(kek)


def test_vault_empty_database_can_create_new_dek(vault_env):
    """An empty database without wrapped_dek successfully generates and stores a new DEK."""
    from core.crypto import derive_vault_key

    pw = "FreshVaultPassword123"
    kek = derive_vault_key(pw)

    service = VaultService()
    assert service._repo.count_items() == 0
    assert service._repo.get_metadata("wrapped_dek") is None

    # First unlock generates a new DEK and stores it wrapped
    dek = service._unwrap_or_create_dek(kek)
    assert len(dek) == 32
    assert service._repo.get_metadata("wrapped_dek") is not None
