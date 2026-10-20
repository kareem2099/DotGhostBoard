"""Security regressions for password separation, migration, metadata and AEAD binding."""

import base64
import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from main import _create_dashboard
from core import crypto, storage
from core.services import SecurityService
from core.security.passwords import derive_password_key, new_kdf_config
from core.security.vault import VaultService, VaultRepository, VaultUnlockError
from core.security.vault.database import _vault_db
from core.security.vault.backup import export_vault_package, import_vault_package

ROOT = 'DashboardMaster2026!'
VAULT = 'IndependentVault2026!'
NEW_ROOT = 'RotatedDashboard2027!'
NEW_VAULT = 'RotatedVault2027!'


@pytest.fixture
def secured(tmp_path, monkeypatch):
    import core.security.vault.database as database
    monkeypatch.setattr(crypto, '_CFG_DIR', str(tmp_path))
    monkeypatch.setattr(crypto, '_SALT_FILE', str(tmp_path / 'eclipse.salt'))
    monkeypatch.setattr(crypto, '_VERIFY_FILE', str(tmp_path / 'eclipse.verify'))
    monkeypatch.setattr(database, 'VAULT_DB_PATH', str(tmp_path / 'vault.db'))
    monkeypatch.setattr(storage, 'DB_PATH', str(tmp_path / 'ghost.db'))
    storage.init_db()
    service = SecurityService()
    service.setup_master_password(ROOT)
    item_id = service.vault.add_secret('Private Payroll Account 7821', 'secret-value-7821', category='password')
    return service, item_id, tmp_path


def test_default_is_shared_and_independent_mode_has_no_dashboard_key_fallback(secured):
    service, item_id, _ = secured
    assert not service.vault.independent_password
    service.lock()
    assert service.unlock(ROOT) and service.vault.is_unlocked
    service.vault.configure_password(ROOT, VAULT)
    assert service.vault.independent_password
    fresh = SecurityService()
    assert fresh.unlock(ROOT) and not fresh.is_locked
    assert not fresh.vault.is_unlocked and not fresh.vault.recognition_ready
    assert not fresh.vault.unlock(ROOT)
    with pytest.raises(ValueError):
        fresh.vault._credentials.unwrap(crypto.derive_vault_key(ROOT))
    assert fresh.vault.unlock(VAULT)
    assert fresh.vault.get_secret(item_id) == 'secret-value-7821'


def test_switching_password_modes_authenticates_both_and_preserves_history(secured):
    service, item_id, _ = secured
    service.vault.update_secret(item_id, secret_text='updated-value-7821')
    service.vault.configure_password(ROOT, VAULT)
    before = service.vault._repo.get_metadata('wrapped_dek')
    for dashboard, current in [('wrong', VAULT), (ROOT, 'wrong')]:
        with pytest.raises(ValueError):
            service.vault.configure_password(dashboard, None, current)
        assert service.vault._repo.get_metadata('wrapped_dek') == before
        assert service.vault.independent_password
    service.vault.configure_password(ROOT, NEW_VAULT, VAULT)
    assert not service.vault.unlock(VAULT)
    assert service.vault.unlock(NEW_VAULT)
    service.vault.configure_password(ROOT, None, NEW_VAULT)
    assert not service.vault.independent_password
    assert service.vault.unlock(ROOT)
    assert service.vault.get_secret(item_id) == 'updated-value-7821'
    assert service.vault.get_secret_history(item_id)[0]['plaintext'] == 'secret-value-7821'


def test_independent_password_cannot_equal_dashboard_or_be_weak(secured):
    service, _, _ = secured
    before = service.vault._repo.get_metadata('wrapped_dek')
    for password in (ROOT, 'short', ' ' * 12):
        with pytest.raises(ValueError):
            service.vault.configure_password(ROOT, password)
        assert service.vault._repo.get_metadata('wrapped_dek') == before


def test_dashboard_password_rotation_does_not_change_independent_vault(secured):
    service, item_id, _ = secured
    service.vault.configure_password(ROOT, VAULT)
    before = service.vault._repo.get_metadata('wrapped_dek')
    ok, _ = service.change_master_password(ROOT, VAULT)
    assert not ok
    ok, message = service.change_master_password(ROOT, NEW_ROOT)
    assert ok, message
    assert service.vault._repo.get_metadata('wrapped_dek') == before
    service.lock()
    assert not service.unlock(ROOT)
    assert service.unlock(NEW_ROOT) and not service.vault.is_unlocked
    assert service.vault.unlock(VAULT)
    assert service.vault.get_secret(item_id) == 'secret-value-7821'


def test_password_rotation_write_failure_rolls_back_encrypted_stores(secured, monkeypatch):
    service, item_id, _ = secured
    clip = storage.add_item('text', 'Eclipse confidential clip')
    assert service.encrypt_clip(clip)
    before = service.vault._repo.get_metadata('wrapped_dek')
    monkeypatch.setattr(crypto, 'save_master_password', MagicMock(side_effect=OSError('write failed')))
    ok, _ = service.change_master_password(ROOT, NEW_ROOT)
    assert not ok
    assert crypto.verify_password(ROOT) and not crypto.verify_password(NEW_ROOT)
    assert service.vault._repo.get_metadata('wrapped_dek') == before
    service.lock()
    assert service.unlock(ROOT)
    assert service.decrypt_clip_for_view(clip) == 'Eclipse confidential clip'
    assert service.vault.get_secret(item_id) == 'secret-value-7821'


@pytest.mark.parametrize('independent', [False, True])
def test_removing_dashboard_password_never_orphans_a_populated_vault(secured, independent):
    service, item_id, _ = secured
    if independent:
        service.vault.configure_password(ROOT, VAULT)
    salt = Path(crypto._SALT_FILE).read_bytes()
    ok, count, _ = service.remove_master_password(ROOT)
    assert not ok and count == 0
    assert crypto.verify_password(ROOT)
    assert Path(crypto._SALT_FILE).read_bytes() == salt
    assert service.vault.get_secret(item_id) == 'secret-value-7821'


def test_metadata_is_encrypted_and_record_swapping_is_detected(secured):
    service, first, root = secured
    second = service.vault.add_secret('Another Private Account 5392', 'another-value-5392', category='token')
    rows = service.vault._repo.list_items()
    assert all(row.title == 'Protected item' and row.category == 'protected' for row in rows)
    for file in root.glob('vault.db*'):
        raw = file.read_bytes()
        assert b'Private Payroll Account 7821' not in raw
        assert b'secret-value-7821' not in raw
        assert b'Another Private Account 5392' not in raw
    first_token = service.vault._repo.get_item(first).ciphertext
    second_token = service.vault._repo.get_item(second).ciphertext
    with _vault_db() as cur:
        cur.execute('UPDATE vault_items SET ciphertext=? WHERE id=?', (second_token, first))
        cur.execute('UPDATE vault_items SET ciphertext=? WHERE id=?', (first_token, second))
    with pytest.raises(ValueError):
        service.vault.get_secret(first)
    with pytest.raises(ValueError):
        service.vault.get_secret(second)


def test_history_swapping_is_detected(secured):
    service, first, _ = secured
    second = service.vault.add_secret('Second', 'history-value-2')
    service.vault.update_secret(first, secret_text='next-1')
    service.vault.update_secret(second, secret_text='next-2')
    record = service.vault._repo.get_history(first)[0]
    other = service.vault._repo.get_history(second)[0]
    with _vault_db() as cur:
        cur.execute('UPDATE vault_item_history SET ciphertext=? WHERE id=?', (other['ciphertext'], record['id']))
    with pytest.raises(ValueError):
        service.vault.get_secret_history(first)


def test_credential_configuration_write_is_atomic(secured, monkeypatch):
    service, item_id, _ = secured
    before = service.vault._repo.get_metadata('wrapped_dek')
    monkeypatch.setattr(service.vault._repo, 'set_metadata_many', MagicMock(side_effect=sqlite3.OperationalError('read only')))
    with pytest.raises(sqlite3.OperationalError):
        service.vault.configure_password(ROOT, VAULT)
    assert not service.vault.independent_password
    assert service.vault._repo.get_metadata('wrapped_dek') == before
    assert service.vault.get_secret(item_id) == 'secret-value-7821'


def test_argon_parameters_are_bounded_before_work_is_started(monkeypatch):
    config = new_kdf_config()
    config['memory_kib'] = 2 ** 40
    worker = MagicMock()
    monkeypatch.setattr('core.security.passwords.Argon2id', worker)
    with pytest.raises(ValueError):
        derive_password_key(VAULT, config)
    worker.assert_not_called()


def test_legacy_records_migrate_with_private_metadata_and_history(secured):
    service, _, root = secured
    dek = service.vault._require_unlocked()
    old_id = service.vault._repo.add_item('Legacy Confidential Name 4531', crypto.encrypt('legacy-payload-4531', dek), category='token')
    service.vault._repo.add_history_entry(old_id, crypto.encrypt('legacy-history-4531', dek))
    service.lock()
    assert service.unlock(ROOT)
    assert service.vault.get_secret(old_id) == 'legacy-payload-4531'
    assert service.vault.get_secret_history(old_id)[0]['plaintext'] == 'legacy-history-4531'
    assert any(s.title == 'Legacy Confidential Name 4531' for s in service.vault.list_secrets())
    for file in root.glob('vault.db*'):
        assert b'Legacy Confidential Name 4531' not in file.read_bytes()
    service.vault.lock()
    assert all(s.title == 'Protected item' for s in service.vault.list_secrets())


def test_legacy_backup_restores_and_new_backups_use_argon2(secured, tmp_path):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    service, _, _ = secured
    salt, nonce = os.urandom(16), os.urandom(12)
    password = 'old-pass'
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000).derive(password.encode())
    payload = {'version': 1, 'items': [{'title': 'Legacy backup item', 'category': 'password', 'secret': 'legacy-backup-secret'}]}
    prefix = b'DGBV\x01'
    legacy = prefix + salt + nonce + AESGCM(key).encrypt(nonce, json.dumps(payload).encode(), prefix)
    assert import_vault_package(service.vault, legacy, password)['imported_count'] == 1
    modern = export_vault_package(service.vault, VAULT)
    assert modern[:5] == b'DGBV\x02'
    destination = VaultService(VaultRepository(str(tmp_path / 'destination.db')))
    destination.unlock(ROOT)
    assert import_vault_package(destination, modern, VAULT)['imported_count'] == 2
    with pytest.raises(ValueError):
        import_vault_package(destination, modern, ROOT)
    with pytest.raises(ValueError):
        import_vault_package(destination, modern[:10] + bytes([modern[10] ^ 1]) + modern[11:], VAULT)


@pytest.mark.parametrize('raw', ['{broken', '[]', '{"version":2,"mode":"unknown"}',
                                '{"version":2,"mode":"independent"}'])
def test_malformed_credential_metadata_has_a_safe_startup_error(secured, qapp, monkeypatch, raw):
    service, _, _ = secured
    service.vault._repo.set_metadata('credential_config', raw)
    before = service.vault._repo.get_metadata('wrapped_dek')
    message = MagicMock()
    monkeypatch.setattr('PyQt6.QtWidgets.QMessageBox.critical', message)
    window = MagicMock()
    monkeypatch.setattr('ui.dashboard.Dashboard', window)
    assert _create_dashboard(startup_locked=False, active_key=crypto.derive_key(ROOT)) is None
    window.assert_not_called()
    message.assert_called_once()
    assert service.vault._repo.get_metadata('credential_config') == raw
    assert service.vault._repo.get_metadata('wrapped_dek') == before


@pytest.mark.parametrize('accept', [False, True])
def test_independent_startup_authenticates_before_creating_dashboard(secured, qapp, monkeypatch, accept):
    from PyQt6.QtWidgets import QDialog
    from ui.vault.unlock_dialog import VaultUnlockDialog
    service, item_id, _ = secured
    service.vault.configure_password(ROOT, VAULT)
    service.lock()
    prompts = []

    def vault_prompt(dialog):
        prompts.append(dialog.pw_input.line_edit.placeholderText())
        if not accept:
            return QDialog.DialogCode.Rejected
        dialog.pw_input.setText(VAULT)
        dialog._on_submit()
        assert dialog.pw_input.text() == ''
        return dialog.result()

    monkeypatch.setattr(VaultUnlockDialog, 'exec', vault_prompt)
    constructed = []

    def dashboard_factory(**kwargs):
        ready = kwargs['security_service']
        assert not ready.is_locked and ready.vault.is_unlocked
        assert ready.vault.get_secret(item_id) == 'secret-value-7821'
        constructed.append(ready)
        return ready

    monkeypatch.setattr('ui.dashboard.Dashboard', dashboard_factory)
    result = _create_dashboard(startup_locked=False, active_key=crypto.derive_key(ROOT))
    assert len(prompts) == 1 and 'Vault Password' in prompts[0]
    assert len(constructed) == int(accept)
    assert (result is not None) is accept


@pytest.mark.parametrize('accept', [False, True])
def test_runtime_two_stage_unlock_gates_capture(mock_dashboard, monkeypatch, accept):
    from PyQt6.QtWidgets import QDialog
    from core.watcher import ClipboardWatcher
    from core.clipboard.events import ClipboardEvent
    from ui.lock_screen import LockScreen
    from ui.vault.unlock_dialog import VaultUnlockDialog
    from ui.vault.send_to_vault import attach_send_to_vault
    dash = mock_dashboard
    service = dash.security_service
    service.setup_master_password(ROOT)
    service.vault.add_secret('Known password', 'known-simple-password', category='password')
    service.vault.configure_password(ROOT, VAULT)
    dash.security_controller.lock()
    service.vault._recognition.clear()
    service.vault._recognition_ready = False
    backend = MagicMock()
    dash.watcher = ClipboardWatcher(backend=backend)
    attach_send_to_vault(dash)
    order = []
    backend.start.side_effect = lambda: order.append('capture')

    def dashboard_prompt(dialog):
        order.append('dashboard')
        dialog.pw_input.setText(ROOT)
        dialog._on_submit()
        return dialog.result()

    def vault_prompt(dialog):
        order.append('vault')
        assert not backend.start.called
        assert dash._is_locked()
        dialog.pw_input.setText(ROOT)  # Dashboard credentials cannot bypass step two.
        dialog._on_submit()
        assert dialog.result() != QDialog.DialogCode.Accepted
        if not accept:
            return QDialog.DialogCode.Rejected
        dialog.pw_input.setText(VAULT)
        dialog._on_submit()
        return dialog.result()

    monkeypatch.setattr(LockScreen, 'exec', dashboard_prompt)
    monkeypatch.setattr(VaultUnlockDialog, 'exec', vault_prompt)
    assert dash._show_lock_screen(show_dashboard=False) is accept
    assert order == (['dashboard', 'vault', 'capture'] if accept else ['dashboard', 'vault'])
    assert dash._is_locked() is not accept
    assert service.vault.is_unlocked is accept
    if accept:
        dash.watcher._on_clipboard_event(ClipboardEvent('text', 'known-simple-password'))
        assert storage.get_item_by_content('known-simple-password') is None
        text = 'Ordinary note after both password steps'
        dash.watcher._on_clipboard_event(ClipboardEvent('text', text))
        assert storage.get_item_by_content(text) is not None
        dash.vault_controller._idle_timer.timeout.emit()
        assert not service.vault.is_unlocked and not dash._is_locked()
    else:
        assert service.active_key is None
        assert not dash.vault_controller._idle_timer.isActive()


def test_settings_password_actions_preserve_secrets_and_restore_cancelled_toggle(mock_dashboard, monkeypatch):
    from ui.settings import SettingsDialog
    from ui.settings.pages import security as page
    dash = mock_dashboard
    service = dash.security_service
    service.setup_master_password(ROOT)
    item_id = service.vault.add_secret('Settings rotation entry', 'keep-this-secret')
    dialog = SettingsDialog(parent=dash)
    warning, info = MagicMock(), MagicMock()
    monkeypatch.setattr(page.QMessageBox, 'warning', warning)
    monkeypatch.setattr(page.QMessageBox, 'information', info)

    def answers(*values):
        replies = iter(values)
        monkeypatch.setattr(page.QInputDialog, 'getText', lambda *args: next(replies))

    try:
        assert not dialog._independent_vault_check.isChecked()
        assert not dialog._change_vault_password_btn.isEnabled()
        answers(('', False))
        dialog._independent_vault_check.setChecked(True)
        assert not dialog._independent_vault_check.isChecked()

        answers((ROOT, True), (VAULT, True), (VAULT, True))
        dialog._independent_vault_check.setChecked(True)
        assert service.vault.independent_password
        assert dialog._change_vault_password_btn.isEnabled()
        assert service.vault.get_secret(item_id) == 'keep-this-secret'

        answers((ROOT, True), ('wrong', True))
        dialog._independent_vault_check.setChecked(False)
        assert dialog._independent_vault_check.isChecked()
        warning.assert_called_once()

        answers((ROOT, True), (VAULT, True))
        dialog._independent_vault_check.setChecked(False)
        assert not service.vault.independent_password
        answers((ROOT, True), (NEW_ROOT, True), (NEW_ROOT, True))
        dialog._set_pw_btn.click()
        assert crypto.verify_password(NEW_ROOT)
        assert service.vault.get_secret(item_id) == 'keep-this-secret'

        answers((NEW_ROOT, True))
        dialog._rm_pw_btn.click()
        assert crypto.verify_password(NEW_ROOT)
        assert service.vault.get_secret(item_id) == 'keep-this-secret'
        assert warning.call_count == 2
    finally:
        dialog.close()
        dialog.deleteLater()


def test_legacy_short_dashboard_password_can_unlock_then_upgrade(secured):
    service, item_id, _ = secured
    short = 'old123'
    old_kek, legacy_kek = crypto.derive_vault_key(ROOT), crypto.derive_vault_key(short)
    assert service.vault.rewrap_dek(old_kek, legacy_kek)
    crypto.write_verifier(crypto.encrypt(crypto._VERIFY_TOKEN, crypto.derive_key(short)))
    service.lock()
    assert service.unlock(short)
    assert service.vault.get_secret(item_id) == 'secret-value-7821'
    ok, message = service.change_master_password(short, NEW_ROOT)
    assert ok, message
    service.lock()
    assert service.unlock(NEW_ROOT)
    assert service.vault.get_secret(item_id) == 'secret-value-7821'


def test_missing_dashboard_salt_is_not_regenerated(secured):
    Path(crypto._SALT_FILE).unlink()
    assert not crypto.verify_password(ROOT)
    assert not Path(crypto._SALT_FILE).exists()
    with pytest.raises(RuntimeError, match='salt is missing'):
        crypto.derive_key(ROOT)


@pytest.mark.parametrize('mode', ['export', 'import'])
def test_backup_dialog_preserves_passphrase_spaces_and_scrubs_fields(qapp, mode):
    from PyQt6.QtWidgets import QDialog
    from ui.vault.backup_dialog import VaultBackupDialog
    dialog = VaultBackupDialog(mode=mode)
    passphrase = '  exact backup password  '
    dialog._pw_input.setText(passphrase)
    if mode == 'export':
        dialog._confirm_input.setText(passphrase)
    dialog._on_submit()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_passphrase() == passphrase
    assert dialog._pw_input.text() == ''
    if mode == 'export':
        assert dialog._confirm_input.text() == ''
    dialog.reject()
    assert dialog.get_passphrase() is None


def _backup_with_items(items):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from core.security.vault.backup import _derive_backup_key
    salt, nonce = os.urandom(16), os.urandom(12)
    header = b'DGBV\x02' + salt + nonce
    return header + AESGCM(_derive_backup_key(VAULT, salt)).encrypt(
        nonce, json.dumps({'version': 2, 'items': items}).encode(), header)


@pytest.mark.parametrize('invalid', [None, {'title': 123}, {'history': [123]}])
def test_backup_validates_every_entry_before_importing_any(secured, invalid):
    service, _, _ = secured
    count = service.vault.count()
    valid = {'title': 'Must not be partly restored', 'secret': 'new-backup-value'}
    with pytest.raises(ValueError, match='entry structure'):
        import_vault_package(service.vault, _backup_with_items([valid, invalid]), VAULT)
    assert service.vault.count() == count


def test_backup_restores_each_item_and_history_in_one_transaction(secured, monkeypatch):
    service, _, _ = secured
    count = service.vault.count()
    item = {'title': 'Interrupted history restore', 'secret': 'new-backup-value', 'history': ['previous']}
    package = _backup_with_items([item])
    monkeypatch.setattr(service.vault._records, '_history', MagicMock(side_effect=sqlite3.OperationalError('disk full')))
    result = import_vault_package(service.vault, package, VAULT)
    assert result['imported_count'] == 0 and result['skipped_count'] == 1
    assert service.vault.count() == count


def test_private_listings_recognition_and_backup_include_all_pages(secured, tmp_path):
    service, _, _ = secured
    for index in range(125):
        service.vault.add_secret(f'Paged entry {index}', f'paged-secret-value-{index}')
    service.lock()
    assert service.unlock(ROOT)
    assert len(service.vault.list_secrets()) == 126
    assert service.vault.match_clipboard_secret('paged-secret-value-124') is True
    modern = export_vault_package(service.vault, VAULT)
    target = VaultService(VaultRepository(str(tmp_path / 'paged-destination.db')))
    assert target.unlock(ROOT)
    result = import_vault_package(target, modern, VAULT)
    assert result['imported_count'] == 126 and result['skipped_count'] == 0
    assert len(target.list_secrets()) == 126
