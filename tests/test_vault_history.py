"""
tests/test_vault_history.py
───────────────────────────
Tests for Vault Password History subsystem (v2.1.0 Leviathan).
Validates encrypted history retention (last 3 versions), FIFO pruning,
in-memory reveal/scrubbing, and safe restoration.
"""

import pytest
from core.crypto import save_master_password
from core.security.vault import (
    VaultRepository,
    VaultService,
    VaultLockedError,
    init_vault_db,
)
from ui.vault.vault_controller import VaultController
from ui.vault.history_dialog import PasswordHistoryDialog


@pytest.fixture
def vault_history_env(tmp_path, monkeypatch):
    """Sandbox crypto config and vault.db path."""
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


def test_repository_history_retention_and_capping(vault_history_env):
    """Verify VaultRepository keeps up to 3 history records and prunes older ones."""
    repo = VaultRepository(vault_history_env["vault_db"])
    item_id = repo.add_item("API Key", "CIPHERTEXT_0", category="token")

    # Add 4 historical versions
    repo.add_history_entry(item_id, "CIPHERTEXT_V1", max_entries=3)
    repo.add_history_entry(item_id, "CIPHERTEXT_V2", max_entries=3)
    repo.add_history_entry(item_id, "CIPHERTEXT_V3", max_entries=3)
    assert repo.count_history(item_id) == 3

    # Adding a 4th must prune the oldest (V1)
    repo.add_history_entry(item_id, "CIPHERTEXT_V4", max_entries=3)
    assert repo.count_history(item_id) == 3

    history = repo.get_history(item_id, limit=10)
    ciphers = [h["ciphertext"] for h in history]
    assert "CIPHERTEXT_V4" in ciphers
    assert "CIPHERTEXT_V3" in ciphers
    assert "CIPHERTEXT_V2" in ciphers
    assert "CIPHERTEXT_V1" not in ciphers  # Oldest pruned


def test_repository_cascade_delete_history(vault_history_env):
    """Verify deleting a vault item deletes all associated history entries."""
    repo = VaultRepository(vault_history_env["vault_db"])
    item_id = repo.add_item("DB Pass", "CIPHER_CURRENT", category="password")
    repo.add_history_entry(item_id, "CIPHER_OLD_1")
    repo.add_history_entry(item_id, "CIPHER_OLD_2")
    assert repo.count_history(item_id) == 2

    repo.delete_item(item_id)
    assert repo.count_history(item_id) == 0


def test_service_password_history_lifecycle_and_restore(vault_history_env):
    """Verify VaultService saves history on password edit and restores correctly."""
    pw = "MasterSecretKey!2026"
    save_master_password(pw)

    service = VaultService(VaultRepository(vault_history_env["vault_db"]))
    assert service.unlock(pw) is True

    # 1. Create a secret
    item_id = service.add_secret("Production DB", "initial_pass_123", category="password")
    assert service.count_secret_history(item_id) == 0

    # 2. Update only title -> No history should be created
    service.update_secret(item_id, title="Production DB (Primary)")
    assert service.count_secret_history(item_id) == 0

    # 3. Update with the same password -> No history created
    service.update_secret(item_id, secret_text="initial_pass_123")
    assert service.count_secret_history(item_id) == 0

    # 4. Change password -> History entry created for "initial_pass_123"
    service.update_secret(item_id, secret_text="rotated_pass_456")
    assert service.count_secret_history(item_id) == 1

    history = service.get_secret_history(item_id)
    assert len(history) == 1
    assert history[0]["plaintext"] == "initial_pass_123"

    # 5. Change password again
    service.update_secret(item_id, secret_text="third_pass_789")
    assert service.count_secret_history(item_id) == 2

    history = service.get_secret_history(item_id)
    plaintexts = [h["plaintext"] for h in history]
    assert plaintexts[0] == "rotated_pass_456"
    assert plaintexts[1] == "initial_pass_123"

    # 6. Revert to the oldest version ("initial_pass_123")
    oldest_id = history[1]["id"]
    restored = service.restore_secret_history(item_id, oldest_id)
    assert restored is True

    # Current secret is now back to "initial_pass_123"
    assert service.get_secret(item_id) == "initial_pass_123"

    # And "third_pass_789" was saved into history during the restore!
    assert service.count_secret_history(item_id) == 3
    new_history = service.get_secret_history(item_id)
    assert new_history[0]["plaintext"] == "third_pass_789"


def test_service_locked_history_protection(vault_history_env):
    """Verify history queries and restore fail when vault is locked."""
    pw = "MasterSecretKey!2026"
    save_master_password(pw)

    service = VaultService(VaultRepository(vault_history_env["vault_db"]))
    service.unlock(pw)
    item_id = service.add_secret("Server Root", "pass1", category="password")
    service.update_secret(item_id, secret_text="pass2")
    service.lock()

    with pytest.raises(VaultLockedError):
        service.get_secret_history(item_id)

    with pytest.raises(VaultLockedError):
        service.restore_secret_history(item_id, 1)


def test_controller_and_history_dialog_ui(vault_history_env, qapp):
    """Verify VaultController and PasswordHistoryDialog integration."""
    from PyQt6.QtWidgets import QApplication

    pw = "MasterSecretKey!2026"
    save_master_password(pw)

    service = VaultService(VaultRepository(vault_history_env["vault_db"]))
    controller = VaultController(vault_service=service)
    controller.unlock(pw)

    item_id = controller.add_secret("GitHub PAT", "ghp_initial", category="token")
    controller.update_secret(item_id, secret_text="ghp_v2_rotated")

    summaries = controller.list_secrets()
    summary = summaries[0]

    dialog = PasswordHistoryDialog(summary, controller)
    dialog.show()

    assert len(dialog._entry_widgets) == 1
    entry_widget = dialog._entry_widgets[0]
    assert entry_widget._payload_label.text() == "••••••••••••••••"

    # Test reveal toggle
    entry_widget._reveal_btn.click()
    assert entry_widget._is_revealed is True
    assert entry_widget._payload_label.text() == "ghp_initial"

    # Test copy with auto-clear
    entry_widget._copy_btn.click()
    clipboard = QApplication.clipboard()
    assert clipboard.text() == "ghp_initial"

    # Test memory scrubbing on vault lock
    controller.lock()
    assert entry_widget._plaintext == "" or dialog.isHidden()
    dialog.close()
