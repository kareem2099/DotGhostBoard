"""
tests/test_vault_expiry.py
──────────────────────────
Unit tests for Vault secret expiry feature.
Tests timestamp persistence, active/warning/expired state computations,
SecretDialog expiry controls, SecretData backward-compatible unpacking,
and SecretCard badge rendering.
"""

from datetime import datetime, timezone, timedelta
import pytest
from PyQt6.QtCore import QDate

from core.crypto import save_master_password
from core.security.vault import (
    VaultRepository,
    VaultService,
    VaultSummary,
    VaultItem,
    init_vault_db,
)
from ui.vault.secret_card import SecretCard
from ui.vault.secret_dialog import SecretDialog, SecretData
from ui.vault.vault_controller import VaultController


@pytest.fixture
def expiry_vault_env(tmp_path, monkeypatch):
    """Isolated environment for vault expiry testing."""
    import core.crypto as crypto
    import core.security.vault.database as vdb
    import core.storage as storage

    vault_db = str(tmp_path / "vault_exp.db")
    ghost_db = str(tmp_path / "ghost.db")

    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))
    monkeypatch.setattr(crypto, "_VERIFY_FILE", str(tmp_path / "eclipse.verify"))
    monkeypatch.setattr(vdb, "VAULT_DB_PATH", vault_db)
    monkeypatch.setattr(storage, "DB_PATH", ghost_db)

    storage.init_db()
    init_vault_db(vault_db)

    save_master_password("MasterPass123!")

    return {
        "vault_db": vault_db,
        "tmp_path": tmp_path,
    }


def test_vault_item_and_summary_expiry_properties():
    """Verify is_expired and days_remaining calculations on models."""
    now = datetime.now(timezone.utc)
    future_date = (now + timedelta(days=15)).strftime("%Y-%m-%d") + "T23:59:59"
    near_date = (now + timedelta(days=3)).strftime("%Y-%m-%d") + "T23:59:59"
    past_date = (now - timedelta(days=2)).strftime("%Y-%m-%d") + "T23:59:59"

    # Future item
    sum_future = VaultSummary(
        id=1, title="Future", category="password",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        expires_at=future_date
    )
    assert not sum_future.is_expired
    assert sum_future.days_remaining is not None
    assert sum_future.days_remaining >= 14

    item_future = VaultItem(
        id=1, title="Future", category="password",
        ciphertext="enc",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        expires_at=future_date
    )
    assert not item_future.is_expired
    assert item_future.days_remaining is not None

    # Near expiry item
    sum_near = VaultSummary(
        id=2, title="Near", category="token",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        expires_at=near_date
    )
    assert not sum_near.is_expired
    assert sum_near.days_remaining is not None
    assert sum_near.days_remaining <= 4

    # Past expired item
    sum_past = VaultSummary(
        id=3, title="Past", category="key",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        expires_at=past_date
    )
    assert sum_past.is_expired
    assert sum_past.days_remaining is not None
    assert sum_past.days_remaining < 0

    # No expiry item
    sum_none = VaultSummary(
        id=4, title="None", category="generic",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        expires_at=None
    )
    assert not sum_none.is_expired
    assert sum_none.days_remaining is None


def test_expiry_persistence_in_service_and_repository(expiry_vault_env):
    """Verify adding and updating secret expiration date persists in SQLite."""
    service = VaultService(VaultRepository(db_path=expiry_vault_env["vault_db"]))
    service.unlock("MasterPass123!")

    exp_ts = "2027-01-01T23:59:59"
    item_id = service.add_secret("Rotating Token", "secret_token_123", category="token", expires_at=exp_ts)

    # Verify summary
    summaries = service.list_secrets()
    assert len(summaries) == 1
    assert summaries[0].expires_at == exp_ts

    # Verify item
    item = service._repo.get_item(item_id)
    assert item.expires_at == exp_ts

    # Update expiration date
    new_exp_ts = "2028-06-30T23:59:59"
    service.update_secret(item_id, expires_at=new_exp_ts)
    updated_item = service._repo.get_item(item_id)
    assert updated_item.expires_at == new_exp_ts

    # Remove expiration date
    service.update_secret(item_id, expires_at="")
    cleared_item = service._repo.get_item(item_id)
    assert cleared_item.expires_at is None


def test_secret_dialog_expiry_controls(qapp):
    """Verify SecretDialog controls, presets, and backward compatibility."""
    dlg = SecretDialog(title="Temp Secret", category="token", secret_payload="val123")

    # By default, expiry checkbox is unchecked
    assert not dlg._exp_check.isChecked()
    assert dlg._exp_container.isHidden()
    assert dlg.get_expires_at() is None

    # SecretData unpacking backward compatibility: 3 elements unpack
    title, payload, cat = dlg.get_data()
    assert title == "Temp Secret"
    assert payload == "val123"
    assert cat == "token"

    # Data also holds expires_at attribute
    data = dlg.get_data()
    assert isinstance(data, SecretData)
    assert data.expires_at is None

    # Check expiration checkbox
    dlg._exp_check.setChecked(True)
    assert not dlg._exp_container.isHidden()
    assert dlg.get_expires_at() is not None
    assert dlg._exp_date_edit.displayFormat() == "dd/MM/yyyy"

    # Select 90 Days preset
    idx_90 = dlg._exp_preset_combo.findData(90)
    dlg._exp_preset_combo.setCurrentIndex(idx_90)
    today = QDate.currentDate()
    expected_90 = today.addDays(90).toString("yyyy-MM-dd")
    assert dlg.get_expires_at().startswith(expected_90)

    # Custom date
    custom_qdate = today.addDays(45)
    dlg._exp_date_edit.setDate(custom_qdate)
    assert dlg.get_expires_at().startswith(custom_qdate.toString("yyyy-MM-dd"))
    # Preset combo switches to Custom
    assert dlg._exp_preset_combo.currentData() == -1


def test_secret_dialog_edit_prefills_expiry(qapp):
    """Verify SecretDialog pre-fills existing expiration date when editing."""
    initial_exp = "2027-12-31T23:59:59"
    dlg = SecretDialog(
        title="Existing Secret",
        category="password",
        item_id=10,
        secret_payload="curr_pass",
        expires_at=initial_exp,
    )
    assert dlg._exp_check.isChecked()
    assert not dlg._exp_container.isHidden()
    assert dlg.get_expires_at() == initial_exp


def test_secret_card_expiry_badge_rendering(expiry_vault_env, qapp):
    """Verify SecretCard renders correct visual badges based on expiration state."""
    service = VaultService(VaultRepository(db_path=expiry_vault_env["vault_db"]))
    controller = VaultController(service)

    now = datetime.now(timezone.utc)
    future_date = (now + timedelta(days=60)).strftime("%Y-%m-%d") + "T23:59:59"
    near_date = (now + timedelta(days=3)).strftime("%Y-%m-%d") + "T23:59:59"
    past_date = (now - timedelta(days=5)).strftime("%Y-%m-%d") + "T23:59:59"

    # 1. No expiry -> No badge
    s_none = VaultSummary(
        id=1, title="NoExp", category="password",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        expires_at=None
    )
    card_none = SecretCard(s_none, controller)
    assert card_none.expiry_badge is None

    # 2. Expired -> ⛔ EXPIRED
    s_expired = VaultSummary(
        id=2, title="Expired", category="password",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        expires_at=past_date
    )
    card_expired = SecretCard(s_expired, controller)
    assert card_expired.expiry_badge is not None
    assert "EXPIRED" in card_expired.expiry_badge.text()

    # 3. Near expiry -> ⚠️ Xd left
    s_near = VaultSummary(
        id=3, title="Near", category="password",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        expires_at=near_date
    )
    card_near = SecretCard(s_near, controller)
    assert card_near.expiry_badge is not None
    assert "left" in card_near.expiry_badge.text()

    # 4. Far future -> ⏳ YYYY-MM-DD
    s_future = VaultSummary(
        id=4, title="Future", category="password",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
        expires_at=future_date
    )
    card_future = SecretCard(s_future, controller)
    assert card_future.expiry_badge is not None
    assert future_date[:10] in card_future.expiry_badge.text()
