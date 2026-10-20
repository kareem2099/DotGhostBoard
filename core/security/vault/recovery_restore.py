"""Validate recovery data before replacing a Vault; preserve the original files."""

import base64
import json
import hashlib
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core import crypto
from core.security.passwords import derive_password_key, new_kdf_config, validate_new_password
from core.security.vault.recovery import config_path, load_config, RecoveryError
from core.security.vault import recovery_archive as archive
from core.security.vault.database import get_vault_db_path


def read_recovery(path, password, *, with_digest=False):
    with open(path, 'rb') as stream:
        data = stream.read(archive.MAX_ARCHIVE_BYTES + 1)
    if len(data) > archive.MAX_ARCHIVE_BYTES:
        raise RecoveryError('Recovery file exceeds the 128 MiB limit.')
    if data.startswith(b'DGBV'):
        from core.security.vault.backup import decrypt_vault_package
        payload = decrypt_vault_package(data, password)
        # Empty legacy entries were historically skipped during ordinary import.
        payload = {'version': 1, 'independent': False,
                   'items': [dict(i, category=i.get('category', 'generic'))
                             for i in payload['items'] if i.get('title', '').strip() and i.get('secret')]}
        payload = archive.validate_payload(payload)
    else:
        payload = archive.decrypt_archive(data, password)
    return (payload, hashlib.sha256(data).hexdigest()) if with_digest else payload


def needs_recovery(db_path=None):
    """Read-only startup preflight: never create a replacement database here."""
    path = Path(db_path or get_vault_db_path()).absolute()
    if not path.exists():
        return config_path(path).exists() or crypto.has_master_password()
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
            if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                return True
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'vault_items' not in tables:
                return True
            count = conn.execute('SELECT count(*) FROM vault_items').fetchone()[0]
            if count and ('vault_metadata' not in tables or not conn.execute(
                    "SELECT value FROM vault_metadata WHERE key='wrapped_dek'").fetchone()):
                return True
            try:
                cfg = load_config(config_path(path))
                return bool(not count and cfg.get('enabled') and cfg.get('last_count', 0))
            except RecoveryError:
                return False  # A settings error alone does not make the Vault unreadable.
    except sqlite3.Error:
        return True


def restore_recovery(path, backup_password, dashboard_password, *, vault_password=None,
                     new_profile=None, db_path=None, expected_digest=None):
    """Replace only Vault data, or create a new profile if original credentials are lost.

    Caller stops all writers before replacement and confirms the destructive change.
    The current profile's Dashboard verifier and salt are never reset.
    """
    from core.security.vault.repository import VaultRepository
    from core.security.vault.service import VaultService

    payload, digest = read_recovery(path, backup_password, with_digest=True)
    if expected_digest is not None and digest != expected_digest:
        raise RecoveryError('The backup changed after preview. Verify it again before restoring.')
    if payload.get('independent') and not vault_password:
        raise RecoveryError('Choose a new independent Vault password for this recovery.')
    if vault_password is not None:
        validate_new_password(vault_password)
        if vault_password == dashboard_password:
            raise RecoveryError('The independent Vault password must differ from Dashboard.')
    if new_profile:
        profile = Path(new_profile).expanduser().resolve()
        if profile.exists() and any(profile.iterdir()):
            raise RecoveryError('Choose an empty folder for the recovered profile.')
        validate_new_password(dashboard_password)
        salt = os.urandom(32)
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        root_key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                             iterations=600_000).derive(dashboard_password.encode())
        profile.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(profile, 0o700)
        target = profile / 'vault.db'
    else:
        if not crypto.verify_password(dashboard_password):
            raise RecoveryError('Incorrect Dashboard password. Use a new profile if its credentials are unavailable.')
        root_key = crypto.derive_key(dashboard_password)
        target = Path(db_path or get_vault_db_path())
        profile = target.parent
    profile.mkdir(parents=True, mode=0o700, exist_ok=True)
    token = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    moved = []
    kept_credentials = []
    with tempfile.TemporaryDirectory(prefix='.vault-restore-', dir=profile) as temp:
        staging = Path(temp) / 'vault.db'
        service = VaultService(VaultRepository(str(staging)))
        try:
            kek = crypto.derive_vault_key_from_session_key(root_key)
            service.unlock_with_key(kek)
            for item in payload['items']:
                service.add_secret(item['title'], item['secret'], category=item['category'],
                                   expires_at=item.get('expires_at'),
                                   history=list(reversed(item.get('history', [])[:3])))
            if vault_password is not None:
                cfg = {'version': 2, 'mode': 'independent', 'kdf': new_kdf_config()}
                service._credentials.write(service._require_unlocked(),
                                            derive_password_key(vault_password, cfg['kdf']), cfg)
            with sqlite3.connect(staging) as conn:
                conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                conn.execute('PRAGMA journal_mode=DELETE')
                if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RecoveryError('The restored database failed verification.')
            if service.count() != len(payload['items']):
                raise RecoveryError('Restored entry count does not match.')
            service.lock()
            if not new_profile:
                for name in (crypto._SALT_FILE, crypto._VERIFY_FILE):
                    original = Path(name)
                    if original.exists():
                        kept = profile / (original.name + '.before-recovery-' + token)
                        archive.atomic_write(kept, original.read_bytes())
                        kept_credentials.append(str(kept))
            # Preserve main DB and sidecars together, even when SQLite cannot read them.
            try:
                for suffix in ('', '-wal', '-shm'):
                    old = Path(str(target) + suffix)
                    if old.exists():
                        kept = Path(str(target) + '.before-recovery-' + token + suffix)
                        os.replace(old, kept)
                        moved.append((old, kept))
                os.replace(staging, target)
            except Exception:
                for old, kept in reversed(moved):
                    os.replace(kept, old)
                raise
        finally:
            service.lock()
    if new_profile:
        archive.atomic_write(profile / 'eclipse.salt', salt)
        archive.atomic_write(profile / 'eclipse.verify', crypto.encrypt(crypto._VERIFY_TOKEN, root_key).encode('ascii'))
    # Old selection IDs and local key belonged to the previous database; require review.
    cfg_path = config_path(target)
    if cfg_path.exists():
        data = cfg_path.read_bytes()
        archive.atomic_write(Path(str(cfg_path) + '.before-recovery-' + token), data)
        try:
            cfg = json.loads(data)
            cfg.update(enabled=False, selected_ids=[], last_error='Recovery completed. Review backup settings to resume.')
            cfg.pop('local_key', None)
            cfg.pop('wrapped_key', None)
            archive.atomic_write(cfg_path, archive.canonical(cfg))
        except (ValueError, TypeError):
            os.replace(cfg_path, Path(str(cfg_path) + '.disabled-' + token))
    directory_fd = os.open(profile, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return {'count': len(payload['items']), 'profile': str(profile),
            'preserved': [str(kept) for _, kept in moved] + kept_credentials}
