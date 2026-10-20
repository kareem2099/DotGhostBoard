"""Recovery regressions: selective/live copies, scheduling, failure safety, and lost profiles."""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from core import crypto, storage
from core.services import SecurityService
from core.security.vault import VaultService, VaultRepository
from core.security.vault.recovery import RecoveryError, load_config, next_due
from core.security.vault.recovery_archive import open_archive
from core.security.vault.recovery_restore import needs_recovery, read_recovery, restore_recovery

ROOT = 'RecoveryDashboard2026!'
BACKUP = 'OfflineRecoveryPass2026!'
VAULT = 'SeparateVaultRecovery2026!'


@pytest.fixture
def recovery_env(tmp_path, monkeypatch):
    import core.security.vault.database as database
    monkeypatch.setattr(crypto, '_CFG_DIR', str(tmp_path))
    monkeypatch.setattr(crypto, '_SALT_FILE', str(tmp_path / 'eclipse.salt'))
    monkeypatch.setattr(crypto, '_VERIFY_FILE', str(tmp_path / 'eclipse.verify'))
    monkeypatch.setattr(database, 'VAULT_DB_PATH', str(tmp_path / 'vault.db'))
    monkeypatch.setattr(storage, 'DB_PATH', str(tmp_path / 'ghost.db'))
    storage.init_db()
    service = SecurityService()
    service.setup_master_password(ROOT)
    first = service.vault.add_secret('Private selected account', 'selected-secret-1843', category='password')
    second = service.vault.add_secret('Private excluded account', 'excluded-secret-2532', category='token')
    folder = tmp_path / 'backups'
    folder.mkdir()
    return service, first, second, folder


def configure(env, **kwargs):
    service, _, _, folder = env
    options = dict(directory=folder, scope='all', frequency='daily', retention=10, password=BACKUP)
    options.update(kwargs)
    service.vault.recovery.configure(**options)
    return service.vault.recovery


def secrets(manager, password=BACKUP):
    return [item['secret'] for item in open_archive(manager.latest_path, password)['items']]


def test_backups_are_opt_in_and_private(recovery_env):
    service, _, _, folder = recovery_env
    assert not service.vault.recovery.enabled and list(folder.iterdir()) == []
    manager = configure(recovery_env)
    assert manager.enabled and len(manager.versions()) == 2
    for file in folder.iterdir():
        data = file.read_bytes()
        assert b'Private selected account' not in data and b'selected-secret-1843' not in data
        assert file.stat().st_mode & 0o777 == 0o600
    config = manager.path.read_text()
    assert ROOT not in config and BACKUP not in config and 'selected-secret' not in config
    with pytest.raises(ValueError):
        open_archive(manager.latest_path, ROOT)


def test_selected_scope_excludes_unselected_and_future_items(recovery_env):
    service, first, _, _ = recovery_env
    manager = configure(recovery_env, scope='selected', selected_ids=[first])
    service.vault.add_secret('Future entry', 'future-excluded')
    assert secrets(manager) == ['selected-secret-1843']
    service.vault.update_secret(first, secret_text='selected-updated')
    payload = open_archive(manager.latest_path, BACKUP)
    assert payload['items'][0]['secret'] == 'selected-updated'
    assert payload['items'][0]['history'] == ['selected-secret-1843']


def test_auto_sync_includes_new_items_immediately_and_keeps_dated_copy(recovery_env):
    service, _, _, _ = recovery_env
    manager = configure(recovery_env, frequency='monthly')
    originals = [p for p in manager.versions() if 'latest' not in p.name]
    service.vault.add_secret('Future entry', 'future-included')
    assert 'future-included' in secrets(manager)
    assert [p for p in manager.versions() if 'latest' not in p.name] == originals
    manager.before_change('password')
    assert len(manager.versions()) == 3


@pytest.mark.parametrize('frequency,days', [('daily', 1), ('weekly', 7)])
def test_calendar_schedules(frequency, days):
    instant = datetime(2026, 10, 19, tzinfo=timezone.utc)
    assert next_due(instant, frequency) == instant + timedelta(days=days)


def test_monthly_schedule_handles_short_months_and_year_rollover():
    assert next_due(datetime(2028, 1, 31, tzinfo=timezone.utc), 'monthly').day == 29
    assert next_due(datetime(2026, 12, 31, tzinfo=timezone.utc), 'monthly') == datetime(2027, 1, 31, tzinfo=timezone.utc)


def test_safety_copies_do_not_postpone_scheduled_versions(recovery_env):
    manager = configure(recovery_env)
    start = datetime(2026, 10, 19, tzinfo=timezone.utc)
    manager.config['last_scheduled'] = start.isoformat()
    manager.snapshot('before-edit', force_version=True, now=start + timedelta(hours=23))
    assert manager.config['last_scheduled'] == start.isoformat()
    assert manager.due(start + timedelta(days=1))
    manager.snapshot('scheduled', now=start + timedelta(days=1))
    assert not manager.due(start + timedelta(days=1, hours=1))


def test_retention_only_prunes_this_profiles_versions(recovery_env):
    _, _, _, folder = recovery_env
    manager = configure(recovery_env, retention=2)
    unrelated = folder / 'another-profile-copy.dgb-recovery'
    unrelated.write_bytes(b'do not remove')
    for _ in range(4):
        manager.snapshot('manual', force_version=True)
    assert len(manager.versions()) == 4  # latest + one scheduled + two manual/safety versions
    assert len([p for p in manager.versions() if '-scheduled-' in p.name]) == 1
    assert unrelated.read_bytes() == b'do not remove'


def test_safety_backup_preserves_deleted_item_and_latest_tracks_removal(recovery_env):
    service, first, _, _ = recovery_env
    manager = configure(recovery_env)
    assert service.vault.delete_secret(first)
    assert 'selected-secret-1843' not in secrets(manager)
    safety = next(p for p in manager.versions() if 'before-delete' in p.name)
    assert 'selected-secret-1843' in [i['secret'] for i in open_archive(safety, BACKUP)['items']]


def test_unavailable_drive_reports_failure_and_blocks_destructive_changes(recovery_env):
    service, first, _, folder = recovery_env
    manager = configure(recovery_env)
    disconnected = folder.with_name('disconnected')
    folder.rename(disconnected)
    service.vault.add_secret('Still saved in Vault', 'new-vault-value')
    assert manager.error and service.vault.count() == 3
    with pytest.raises(RecoveryError, match='Safety backup failed'):
        service.vault.delete_secret(first)
    assert service.vault.get_secret(first) == 'selected-secret-1843'
    assert not folder.exists()
    folder.mkdir()  # A disconnected mount point must not count as the same drive.
    service.vault.add_secret('Another saved item', 'another-vault-value')
    assert 'folder or drive changed' in manager.error
    folder.rmdir()
    disconnected.rename(folder)
    manager.tick()
    assert not manager.error and len(secrets(manager)) == 4


def test_atomic_write_failure_does_not_report_success_or_destroy_previous_copy(recovery_env, monkeypatch):
    from core.security.vault import recovery_archive
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    original = manager.latest_path.read_bytes()
    before = manager.config['last_success']
    monkeypatch.setattr(recovery_archive.os, 'replace', MagicMock(side_effect=OSError('disk full')))
    service.vault.add_secret('Pending backup', 'pending-backup-secret')
    assert manager.config['last_success'] == before
    assert manager.error and manager.latest_path.read_bytes() == original


def test_backup_key_is_scrubbed_and_due_work_resumes_on_unlock(recovery_env):
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    key_buffer = manager._key
    service.vault.lock()
    assert manager._key is None and not any(key_buffer)
    manager.config['last_scheduled'] = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    assert service.vault.unlock(ROOT)
    assert manager._key is not None
    assert not manager.due(datetime.now(timezone.utc))


def test_password_changes_leave_archives_readable_and_independent(recovery_env):
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    service.vault.configure_password(ROOT, VAULT)
    ok, message = service.change_master_password(ROOT, 'RotatedDashboard2027!')
    assert ok, message
    assert len(secrets(manager)) == 2
    service.lock()
    assert service.unlock('RotatedDashboard2027!')
    assert service.vault.unlock(VAULT)
    service.vault.add_secret('New independent entry', 'new-independent-value')
    assert 'new-independent-value' in secrets(manager)


def test_passphrase_rotation_preserves_old_copies_and_cancelled_setup(recovery_env):
    service, _, _, folder = recovery_env
    manager = configure(recovery_env)
    previous = next(p for p in manager.versions() if 'latest' not in p.name)
    manager.configure(directory=folder, password='AnotherBackupPass2027!')
    assert len(secrets(manager, 'AnotherBackupPass2027!')) == 2
    assert len(open_archive(previous, BACKUP)['items']) == 2
    before = manager.config.copy()
    with pytest.raises(ValueError):
        manager.configure(directory=folder, scope='selected', selected_ids=[], password=BACKUP)
    assert manager.config == before


def test_batch_import_creates_one_live_copy(recovery_env, monkeypatch):
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    snapshot = MagicMock(wraps=manager.snapshot)
    monkeypatch.setattr(manager, 'snapshot', snapshot)
    with manager.batch('import'):
        for index in range(8):
            service.vault.add_secret(f'Imported {index}', f'imported-value-{index}')
    assert snapshot.call_count == 2  # safety checkpoint + final synchronized copy
    assert len(secrets(manager)) == 10


def test_missing_or_corrupt_database_is_detected_without_recreating_it(recovery_env):
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    path = Path(service.vault._repo._db_path or manager.path.with_name('vault.db'))
    path.unlink()
    assert needs_recovery(path) and not path.exists()
    path.write_bytes(b'not a database')
    assert needs_recovery(path) and path.read_bytes() == b'not a database'


def test_restore_lost_database_preserves_root_credentials_and_old_file(recovery_env):
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    archive = manager.latest_path
    credentials = [Path(p).read_bytes() for p in (crypto._SALT_FILE, crypto._VERIFY_FILE)]
    target = manager.path.with_name('vault.db')
    service.lock()
    target.write_bytes(b'broken vault')
    result = restore_recovery(archive, BACKUP, ROOT)
    assert result['count'] == 2
    assert Path(result['preserved'][0]).read_bytes() == b'broken vault'
    assert any('eclipse.salt.before-recovery' in p for p in result['preserved'])
    assert any('eclipse.verify.before-recovery' in p for p in result['preserved'])
    assert credentials == [Path(p).read_bytes() for p in (crypto._SALT_FILE, crypto._VERIFY_FILE)]
    fresh = SecurityService()
    assert fresh.unlock(ROOT) and len(fresh.vault.list_secrets()) == 2
    assert not fresh.vault.recovery.enabled
    assert not needs_recovery(target)


def test_restore_requires_all_passwords_and_keeps_independent_mode(recovery_env):
    service, _, _, _ = recovery_env
    service.vault.configure_password(ROOT, VAULT)
    manager = configure(recovery_env)
    old = manager.path.with_name('vault.db').read_bytes()
    with pytest.raises(ValueError):
        restore_recovery(manager.latest_path, BACKUP, ROOT)
    with pytest.raises(ValueError):
        restore_recovery(manager.latest_path, 'wrong', ROOT, vault_password=VAULT)
    with pytest.raises(ValueError):
        restore_recovery(manager.latest_path, BACKUP, 'wrong', vault_password=VAULT)
    assert manager.path.with_name('vault.db').read_bytes() == old
    service.lock()
    restore_recovery(manager.latest_path, BACKUP, ROOT, vault_password=VAULT)
    fresh = SecurityService()
    assert fresh.unlock(ROOT) and not fresh.vault.is_unlocked
    assert fresh.vault.unlock(VAULT) and fresh.vault.count() == 2


def test_recovery_works_after_every_original_profile_file_is_lost(recovery_env, tmp_path, monkeypatch):
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    archive = manager.latest_path
    service.lock()
    for name in ['vault.db', 'ghost.db', 'eclipse.salt', 'eclipse.verify', 'vault-recovery.json']:
        path = tmp_path / name
        if path.exists():
            path.unlink()
    destination = tmp_path / 'recovered-profile'
    restore_recovery(archive, BACKUP, ROOT, new_profile=destination)
    monkeypatch.setattr(crypto, '_CFG_DIR', str(destination))
    monkeypatch.setattr(crypto, '_SALT_FILE', str(destination / 'eclipse.salt'))
    monkeypatch.setattr(crypto, '_VERIFY_FILE', str(destination / 'eclipse.verify'))
    fresh = VaultService(VaultRepository(str(destination / 'vault.db')))
    assert crypto.verify_password(ROOT)
    assert fresh.unlock(ROOT) and fresh.count() == 2
    assert not (tmp_path / 'vault.db').exists()
    assert destination.stat().st_mode & 0o777 == 0o700
    from ui.vault.recovery_dialog import RecoveryDialog
    appimage = tmp_path / 'DotGhostBoard.AppImage'
    appimage.write_text('placeholder executable')
    appimage.chmod(0o700)
    monkeypatch.setenv('APPIMAGE', str(appimage))
    launch = MagicMock()
    monkeypatch.setattr('ui.vault.recovery_dialog.subprocess.Popen', launch)
    RecoveryDialog._open_profile(str(destination))
    assert launch.call_args.args[0] == [str(appimage)]
    assert launch.call_args.kwargs['env']['DOTGHOST_HOME'] == str(destination)


def test_tampered_recovery_archive_never_replaces_the_vault(recovery_env):
    _, _, _, _ = recovery_env
    manager = configure(recovery_env)
    target = manager.path.with_name('vault.db')
    before = target.read_bytes()
    file = manager.latest_path
    data = json.loads(file.read_bytes())
    data['header']['count'] += 1
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        restore_recovery(file, BACKUP, ROOT)
    assert target.read_bytes() == before


def test_manual_backup_can_also_be_recovered_without_source_vault(recovery_env, tmp_path):
    from core.security.vault.backup import export_vault_package
    service, _, _, _ = recovery_env
    file = tmp_path / 'manual.vault'
    file.write_bytes(export_vault_package(service.vault, BACKUP))
    assert len(read_recovery(file, BACKUP)['items']) == 2
    service.lock()
    result = restore_recovery(file, BACKUP, ROOT)
    assert result['count'] == 2


def test_restore_rejects_a_changed_preview_without_touching_the_vault(recovery_env):
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    _, digest = read_recovery(manager.latest_path, BACKUP, with_digest=True)
    service.vault.add_secret('After preview', 'changed-after-preview')
    current = manager.path.with_name('vault.db').read_bytes()
    with pytest.raises(RecoveryError, match='changed after preview'):
        restore_recovery(manager.latest_path, BACKUP, ROOT, expected_digest=digest)
    assert manager.path.with_name('vault.db').read_bytes() == current


def test_failed_database_replacement_rolls_back_the_original_files(recovery_env, monkeypatch):
    from core.security.vault import recovery_restore
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    service.lock()
    target = manager.path.with_name('vault.db')
    original = target.read_bytes()
    replace = recovery_restore.os.replace

    def fail_install(source, destination):
        if '.vault-restore-' in str(source) and str(source).endswith('vault.db'):
            raise OSError('install failed')
        return replace(source, destination)

    monkeypatch.setattr(recovery_restore.os, 'replace', fail_install)
    with pytest.raises(OSError, match='install failed'):
        restore_recovery(manager.latest_path, BACKUP, ROOT)
    assert target.read_bytes() == original
    assert crypto.verify_password(ROOT)


def test_invalid_recovery_kdf_is_rejected_before_memory_allocation(recovery_env, monkeypatch):
    manager = configure(recovery_env)
    data = json.loads(manager.latest_path.read_bytes())
    data['header']['kdf']['memory_kib'] = 2 ** 40
    manager.latest_path.write_text(json.dumps(data))
    allocation = MagicMock()
    monkeypatch.setattr('core.security.passwords.Argon2id', allocation)
    with pytest.raises(ValueError):
        open_archive(manager.latest_path, BACKUP)
    allocation.assert_not_called()


def test_settings_select_items_auto_sync_and_immediate_apply(mock_dashboard, tmp_path, monkeypatch):
    from ui.settings import SettingsDialog
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QListWidget
    dash = mock_dashboard
    dash.security_service.setup_master_password(ROOT)
    first = dash.security_service.vault.add_secret('Include me', 'included-ui-value')
    dash.security_service.vault.add_secret('Leave me out', 'excluded-ui-value')
    dialog = SettingsDialog(parent=dash)
    page = dialog._recovery_page
    folder = tmp_path / 'ui-backups'
    folder.mkdir()
    try:
        assert page.scope.currentData() == 'selected'

        def choose(prompt):
            listing = prompt.findChild(QListWidget)
            for index in range(listing.count()):
                row = listing.item(index)
                if row.text() == 'Include me':
                    row.setCheckState(Qt.CheckState.Checked)
            return QDialog.DialogCode.Accepted

        monkeypatch.setattr(QDialog, 'exec', choose)
        page.select_items()
        assert page.selected_ids == [first]
        page.enabled.setChecked(True)
        page.directory.setText(str(folder))
        page.new_password.setText(BACKUP)
        page.confirm_password.setText(BACKUP)
        assert page.apply_settings()
        assert secrets(page.manager) == ['included-ui-value']
        assert page.new_password.text() == page.confirm_password.text() == ''
        page.scope.setCurrentIndex(page.scope.findData('all'))
        assert not page.choose_items.isEnabled()
        assert page.apply_settings()
        dash.security_service.vault.add_secret('New item', 'auto-included-ui-value')
        assert len(secrets(page.manager)) == 3
        dialog.reject()  # Explicit Apply took effect; cancelling the outer dialog does not undo it.
        assert page.manager.enabled
    finally:
        dialog.deleteLater()


def test_settings_refuses_empty_selection_and_can_disable_without_deleting_copies(mock_dashboard, tmp_path, monkeypatch):
    from ui.settings import SettingsDialog
    dash = mock_dashboard
    dash.security_service.setup_master_password(ROOT)
    dash.security_service.vault.add_secret('Test', 'test-secret')
    dialog = SettingsDialog(parent=dash)
    folder = tmp_path / 'empty-selection'
    folder.mkdir()
    page = dialog._recovery_page
    warning = MagicMock()
    monkeypatch.setattr('ui.settings.pages.recovery.QMessageBox.warning', warning)
    page.enabled.setChecked(True)
    page.directory.setText(str(folder))
    page.new_password.setText(BACKUP)
    page.confirm_password.setText(BACKUP)
    try:
        assert not page.apply_settings()
        warning.assert_called_once()
        assert not list(folder.iterdir())
        page.scope.setCurrentIndex(page.scope.findData('all'))
        assert page.apply_settings()
        files = list(folder.iterdir())
        page.enabled.setChecked(False)
        assert page.apply_settings()
        assert not page.manager.enabled
        assert list(folder.iterdir()) == files
        page.new_password.setText('UnsavedCancelledPass2026!')
        page.confirm_password.setText('UnsavedCancelledPass2026!')
        dialog.reject()
        assert page.new_password.text() == page.confirm_password.text() == ''
    finally:
        dialog.close()
        dialog.deleteLater()


@pytest.mark.parametrize('use_latest', [False, True])
def test_recovery_dialog_previews_and_restores_with_capture_gated(mock_dashboard, tmp_path, monkeypatch, use_latest):
    from PyQt6.QtWidgets import QDialog, QMessageBox
    from ui.vault.recovery_dialog import RecoveryDialog
    dash = mock_dashboard
    service = dash.security_service
    service.setup_master_password(ROOT)
    first = service.vault.add_secret('Before edit', 'before-edit-value')
    folder = tmp_path / 'dialog-backups'
    folder.mkdir()
    manager = service.vault.recovery
    manager.configure(directory=folder, password=BACKUP)
    version = next(p for p in manager.versions() if 'latest' not in p.name)
    service.vault.update_secret(first, secret_text='after-edit-value')
    if use_latest:
        version = manager.latest_path
    prompt = RecoveryDialog(service=service, dashboard=dash, parent=dash)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, 'information', MagicMock())
    prompt.path.setText(str(version))
    prompt.backup_password.setText(BACKUP)
    prompt.dashboard_password.setText(ROOT)
    try:
        assert prompt._verify()
        assert prompt.preview.count() == 1
        prompt._restore()
        assert prompt.result() == QDialog.DialogCode.Accepted, prompt.message.text()
        assert service.vault.get_secret(1) == ('after-edit-value' if use_latest else 'before-edit-value')
        assert not dash._is_locked()
        assert not service.vault.recovery.enabled
        assert prompt.backup_password.text() == prompt.dashboard_password.text() == ''
    finally:
        prompt.deleteLater()


def test_recovery_dialog_cancel_scrubs_inputs_without_changing_files(recovery_env, qapp):
    from ui.vault.recovery_dialog import RecoveryDialog
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    before = manager.path.with_name('vault.db').read_bytes()
    prompt = RecoveryDialog(service=service)
    prompt.path.setText(str(manager.latest_path))
    prompt.backup_password.setText(BACKUP)
    prompt.dashboard_password.setText(ROOT)
    assert prompt._verify()
    prompt.reject()
    assert prompt.preview.count() == 0
    assert prompt.backup_password.text() == prompt.dashboard_password.text() == ''
    assert manager.path.with_name('vault.db').read_bytes() == before
    prompt.deleteLater()


def test_startup_unlock_failure_offers_recovery_before_constructing_dashboard(recovery_env, qapp, monkeypatch):
    from main import _create_dashboard
    from PyQt6.QtWidgets import QDialog
    from ui.vault.recovery_dialog import RecoveryDialog
    service, _, _, _ = recovery_env
    configure(recovery_env)
    service.vault._repo.set_metadata('wrapped_dek', 'damaged')
    creation = MagicMock()
    monkeypatch.setattr('ui.dashboard.Dashboard', creation)
    prompts = []

    def cancel(prompt):
        prompts.append(prompt.versions.count())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(RecoveryDialog, 'exec', cancel)
    assert _create_dashboard(startup_locked=False, active_key=crypto.derive_key(ROOT)) is None
    assert prompts and prompts[0] >= 3
    creation.assert_not_called()
    assert service.vault._repo.get_metadata('wrapped_dek') == 'damaged'


def test_controller_reports_failed_backups_once_and_honors_notification_preferences(mock_dashboard, tmp_path):
    dash = mock_dashboard
    service = dash.security_service
    service.setup_master_password(ROOT)
    service.vault.add_secret('Item', 'secret')
    folder = tmp_path / 'notification-backups'
    folder.mkdir()
    service.vault.recovery.configure(directory=folder, password=BACKUP)
    folder.rename(folder.with_name('offline'))
    tray = MagicMock()
    dash.tray_manager = tray
    dash.vault_controller.add_secret('Still saved', 'another-secret')
    dash.vault_controller.add_secret('Also saved', 'third-secret')
    tray.show_message.assert_called_once()
    assert tray.show_message.call_args.kwargs['category'] == 'security'
    assert 'Still saved' not in str(tray.show_message.call_args)


def test_migration_has_a_readable_safety_version(recovery_env):
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    dek = service.vault._require_unlocked()
    service.vault._repo.add_item('Legacy recovery entry', crypto.encrypt('legacy-recovery-value', dek))
    service.lock()
    assert service.unlock(ROOT)
    file = next(p for p in manager.versions() if 'before-migration' in p.name)
    assert 'legacy-recovery-value' in [i['secret'] for i in open_archive(file, BACKUP)['items']]


def test_unexpected_empty_or_partly_deleted_vault_never_overwrites_last_good_copy(recovery_env):
    service, first, _, _ = recovery_env
    manager = configure(recovery_env)
    original = manager.latest_path.read_bytes()
    # Bypass the app's authorized delete path to simulate external loss/corruption.
    service.vault._repo.delete_item(first)
    manager.after_change()
    assert 'decreased unexpectedly' in manager.error
    assert manager.latest_path.read_bytes() == original
    assert len(secrets(manager)) == 2
    for item in service.vault.list_secrets():
        service.vault._repo.delete_item(item.id)
    manager.tick()
    assert manager.latest_path.read_bytes() == original


def test_narrowing_selection_preserves_previous_full_copy(recovery_env):
    _, first, _, folder = recovery_env
    manager = configure(recovery_env)
    manager.configure(directory=folder, scope='selected', selected_ids=[first])
    assert len(secrets(manager)) == 1
    previous = next(p for p in manager.versions() if 'before-settings' in p.name)
    assert len(open_archive(previous, BACKUP)['items']) == 2


def test_new_item_cannot_hide_an_unexpected_loss_with_the_same_total_count(recovery_env):
    service, first, _, _ = recovery_env
    manager = configure(recovery_env)
    original = manager.latest_path.read_bytes()
    service.vault._repo.delete_item(first)
    service.vault.add_secret('New entry after external loss', 'different-entry-same-count')
    assert service.vault.count() == 2
    assert manager.latest_path.read_bytes() == original
    assert 'decreased unexpectedly' in manager.error


def test_session_lock_during_backup_setup_keeps_previous_configuration(recovery_env, monkeypatch):
    from core.security.vault import recovery_archive
    service, _, _, _ = recovery_env
    manager = configure(recovery_env)
    previous = dict(manager.config)
    saved = manager.path.read_bytes()
    envelope = recovery_archive.password_envelope

    def lock_during_derivation(password, key):
        result = envelope(password, key)
        service.lock()
        return result

    monkeypatch.setattr(recovery_archive, 'password_envelope', lock_during_derivation)
    with pytest.raises(RuntimeError, match='locked'):
        manager.configure(directory=previous['directory'], password='RotatedBackupPass2026!')
    assert manager.config == previous
    assert manager.path.read_bytes() == saved
    assert not service.vault.is_unlocked
