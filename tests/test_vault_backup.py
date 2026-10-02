"""
tests/test_vault_backup.py
──────────────────────────
Unit tests for Vault encrypted export/import (.vault package) subsystem.
Tests cryptographic isolation, file integrity, passphrase validation,
and duplicate resolution policies.
"""

import os
import pytest

from core.crypto import save_master_password
from core.security.vault import (
    VaultRepository,
    VaultService,
    VaultLockedError,
    init_vault_db,
    export_vault_package,
    import_vault_package,
)
from core.security.vault.backup import MAGIC, BACKUP_FORMAT_VERSION
from ui.vault.vault_controller import VaultController


@pytest.fixture
def backup_vault_env(tmp_path, monkeypatch):
    """Isolated environment for vault backup testing."""
    import core.crypto as crypto
    import core.security.vault.database as vdb
    import core.storage as storage

    vault_db_1 = str(tmp_path / "vault1.db")
    vault_db_2 = str(tmp_path / "vault2.db")
    ghost_db = str(tmp_path / "ghost.db")

    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))
    monkeypatch.setattr(crypto, "_VERIFY_FILE", str(tmp_path / "eclipse.verify"))
    monkeypatch.setattr(vdb, "VAULT_DB_PATH", vault_db_1)
    monkeypatch.setattr(storage, "DB_PATH", ghost_db)

    storage.init_db()
    init_vault_db(vault_db_1)
    init_vault_db(vault_db_2)

    save_master_password("MasterPass123!")

    return {
        "vault_db_1": vault_db_1,
        "vault_db_2": vault_db_2,
        "tmp_path": tmp_path,
    }


def test_export_package_format_and_cryptographic_confidentiality(backup_vault_env):
    """Verify exported file contains valid magic header and NO plaintext leaks."""
    vault_db = backup_vault_env["vault_db_1"]
    service = VaultService(VaultRepository(db_path=vault_db))
    service.unlock("MasterPass123!")

    service.add_secret("Production DB", "super_secret_database_password_999", category="password")
    service.add_secret("Stripe Key", "sk_live_very_secret_api_key_456", category="token")

    data = export_vault_package(service, "BackupPassphrase888!")

    # Magic header check
    assert data.startswith(MAGIC)
    assert data[4] == BACKUP_FORMAT_VERSION
    # Header (4) + Version (1) + Salt (16) + Nonce (12) + Tag (16) = minimum 49 bytes
    assert len(data) > 49

    # Plaintext leak test: Raw sensitive text must NOT appear anywhere in the binary
    assert b"super_secret_database_password_999" not in data
    assert b"sk_live_very_secret_api_key_456" not in data
    assert b"Production DB" not in data
    assert b"Stripe Key" not in data


def test_export_import_full_roundtrip(backup_vault_env):
    """Verify secrets and metadata are accurately decrypted and restored into target vault."""
    vault_db_1 = backup_vault_env["vault_db_1"]
    vault_db_2 = backup_vault_env["vault_db_2"]

    # Source vault
    service_src = VaultService(VaultRepository(db_path=vault_db_1))
    service_src.unlock("MasterPass123!")

    service_src.add_secret("API Token", "token_payload_abc", category="token", expires_at="2026-12-31T23:59:59")
    service_src.add_secret("SSH Key", "ssh-rsa AAAAB3NzaC1yc2E...", category="key")

    package_bytes = export_vault_package(service_src, "TransferKey99!")

    # Destination vault
    service_dst = VaultService(VaultRepository(db_path=vault_db_2))
    service_dst.unlock("MasterPass123!")
    assert len(service_dst.list_secrets()) == 0

    result = import_vault_package(service_dst, package_bytes, "TransferKey99!")
    assert result["imported_count"] == 2
    assert result["skipped_count"] == 0
    assert result["total_items"] == 2

    summaries = service_dst.list_secrets()
    assert len(summaries) == 2

    token_item = [s for s in summaries if s.title == "API Token"][0]
    assert token_item.category == "token"
    assert token_item.expires_at == "2026-12-31T23:59:59"
    assert service_dst.get_secret(token_item.id) == "token_payload_abc"

    ssh_item = [s for s in summaries if s.title == "SSH Key"][0]
    assert ssh_item.category == "key"
    assert service_dst.get_secret(ssh_item.id) == "ssh-rsa AAAAB3NzaC1yc2E..."


def test_import_with_wrong_passphrase_raises_error(backup_vault_env):
    """Verify incorrect passphrase cannot decrypt the package and raises ValueError."""
    vault_db_1 = backup_vault_env["vault_db_1"]
    vault_db_2 = backup_vault_env["vault_db_2"]

    service_src = VaultService(VaultRepository(db_path=vault_db_1))
    service_src.unlock("MasterPass123!")
    service_src.add_secret("Secret", "top_secret_val")

    package_bytes = export_vault_package(service_src, "CorrectPass123!")

    service_dst = VaultService(VaultRepository(db_path=vault_db_2))
    service_dst.unlock("MasterPass123!")

    with pytest.raises(ValueError, match="Incorrect passphrase or corrupted backup file"):
        import_vault_package(service_dst, package_bytes, "WrongPass999!")


def test_import_corrupted_file_raises_error(backup_vault_env):
    """Verify corrupted header or truncated files are rejected immediately."""
    vault_db = backup_vault_env["vault_db_1"]
    service = VaultService(VaultRepository(db_path=vault_db))
    service.unlock("MasterPass123!")

    with pytest.raises(ValueError, match="Invalid or truncated .vault file"):
        import_vault_package(service, b"DGBV\x01short", "AnyPass123!")

    with pytest.raises(ValueError, match="not a DotGhostBoard .vault file"):
        import_vault_package(service, b"NOT_A_VAULT_BACKUP_1234567890_1234567890_1234567890", "AnyPass123!")

    # Verify that tampering with version or header fails authentication
    service.add_secret("Secret", "tamper_proof_value")
    package = export_vault_package(service, "Passphrase123!")
    tampered_ver = package[:4] + b"\x02" + package[5:]
    with pytest.raises(ValueError):
        import_vault_package(service, tampered_ver, "Passphrase123!")


def test_import_duplicate_skipping_policy(backup_vault_env):
    """Verify duplicate secrets with same title, category, and payload are skipped."""
    vault_db_1 = backup_vault_env["vault_db_1"]
    service = VaultService(VaultRepository(db_path=vault_db_1))
    service.unlock("MasterPass123!")

    service.add_secret("Existing Item", "identical_secret_payload", category="password")
    package_bytes = export_vault_package(service, "Pass12345!")

    # Import back into same vault
    result = import_vault_package(service, package_bytes, "Pass12345!")
    assert result["imported_count"] == 0
    assert result["skipped_count"] == 1
    assert len(service.list_secrets()) == 1


def test_vault_controller_export_and_import(backup_vault_env, qapp):
    """Verify VaultController methods handle export/import and lock state enforcement."""
    service = VaultService(VaultRepository(db_path=backup_vault_env["vault_db_1"]))
    controller = VaultController(service)

    export_path = str(backup_vault_env["tmp_path"] / "ctrl_backup.vault")

    # Locked controller must raise VaultLockedError
    with pytest.raises(VaultLockedError):
        controller.export_vault("Pass12345!", export_path)

    with pytest.raises(VaultLockedError):
        controller.import_vault("Pass12345!", export_path)

    # Unlock and test export
    controller.unlock("MasterPass123!")
    controller.add_secret("Ctrl Secret", "some_payload_data")
    count = controller.export_vault("BackupPass77!", export_path)
    assert count == 1
    assert os.path.isfile(export_path)

    # Import into fresh controller
    service2 = VaultService(VaultRepository(db_path=backup_vault_env["vault_db_2"]))
    controller2 = VaultController(service2)
    controller2.unlock("MasterPass123!")

    result = controller2.import_vault("BackupPass77!", export_path)
    assert result["imported_count"] == 1
    assert result["skipped_count"] == 0
    assert len(controller2.list_secrets()) == 1


def test_vault_backup_dialog_export_and_import(qapp):
    """Verify VaultBackupDialog validation rules, toggle show pw, and return values."""
    from ui.vault.backup_dialog import VaultBackupDialog

    # Export mode: min length 8
    dlg = VaultBackupDialog(mode="export")
    dlg._pw_input.setText("short")
    dlg._confirm_input.setText("short")
    dlg._on_submit()
    assert dlg.result() != VaultBackupDialog.DialogCode.Accepted
    assert "at least 8" in dlg._error_lbl.text()

    # Export mode: mismatch
    dlg._pw_input.setText("ValidPass123!")
    dlg._confirm_input.setText("DifferentPass123!")
    dlg._on_submit()
    assert dlg.result() != VaultBackupDialog.DialogCode.Accepted
    assert "do not match" in dlg._error_lbl.text()

    # Export mode: matching valid
    dlg._confirm_input.setText("ValidPass123!")
    dlg._on_submit()
    assert dlg.get_passphrase() == "ValidPass123!"

    # Show password checkbox
    dlg._show_pw_check.setChecked(True)
    assert dlg._pw_input.echoMode() == dlg._pw_input.EchoMode.Normal
    dlg._show_pw_check.setChecked(False)
    assert dlg._pw_input.echoMode() == dlg._pw_input.EchoMode.Password

    # Import mode: empty rejected
    dlg_imp = VaultBackupDialog(mode="import", file_path="/tmp/test.vault")
    dlg_imp._pw_input.setText("")
    dlg_imp._on_submit()
    assert dlg_imp.result() != VaultBackupDialog.DialogCode.Accepted
    assert "cannot be empty" in dlg_imp._error_lbl.text()

    # Import mode: valid
    dlg_imp._pw_input.setText("ValidPass123!")
    dlg_imp._on_submit()
    assert dlg_imp.get_passphrase() == "ValidPass123!"
