"""Selected or automatic recovery copies, calendar versions, and safety checkpoints."""

import base64
import calendar
import hashlib
import json
import logging
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import crypto
from core.security.vault import recovery_archive as archive
from core.security.vault.database import get_vault_db_path
from core.security.vault.database import _vault_db
from core.security.vault.models import VaultItem
from core.security.vault.protected_records import decode_record, decode_history

logger = logging.getLogger(__name__)
FREQUENCIES = ('daily', 'weekly', 'monthly')


class RecoveryError(ValueError):
    pass


def config_path(db_path=None):
    database = Path(db_path or get_vault_db_path())
    return database.with_name(database.stem + '-recovery.json')


def load_config(path):
    if not Path(path).exists():
        return {'enabled': False}
    try:
        config = json.loads(Path(path).read_text())
        if (config.get('version') != 1 or config.get('frequency') not in FREQUENCIES
                or config.get('scope') not in ('all', 'selected')
                or not isinstance(config.get('selected_ids'), list)
                or not 1 <= int(config.get('retention', 0)) <= 100
                or len(config.get('profile_id', '')) != 32
                or any(c not in '0123456789abcdef' for c in config['profile_id'])):
            raise ValueError()
        return config
    except Exception as exc:
        raise RecoveryError('Recovery settings are damaged. Existing backup files have not been changed.') from exc


def next_due(last, frequency):
    if frequency == 'monthly':
        month = last.month % 12 + 1
        year = last.year + (last.month == 12)
        return last.replace(year=year, month=month, day=min(last.day, calendar.monthrange(year, month)[1]))
    return last + timedelta(days=1 if frequency == 'daily' else 7)


class RecoveryManager:
    def __init__(self, service):
        self.service = service
        self.path = config_path(service._repo._db_path)
        self._lock = threading.RLock()
        self._key = None
        self._batch_depth = 0
        self._pending = False
        self._pending_removed_ids = set()
        self.error = ''
        try:
            self.config = load_config(self.path)
        except RecoveryError as exc:
            self.config = {'enabled': False}
            self.error = str(exc)

    @property
    def enabled(self):
        return self.config.get('enabled', False)

    def _save(self):
        archive.atomic_write(self.path, archive.canonical(self.config))

    def _local_aad(self):
        return b'dotghostboard:recovery:local-key:v1:' + self.config['profile_id'].encode()

    def lock(self):
        if self._key is not None:
            crypto.secure_zero(self._key)
            self._key = None

    def _get_key(self):
        if self._key is None:
            text = crypto.decrypt(self.config['local_key'], self.service._require_unlocked(), self._local_aad())
            value = base64.b64decode(text, validate=True)
            if len(value) != 32:
                raise RecoveryError('Invalid recovery key.')
            self._key = bytearray(value)
        return bytes(self._key)

    def configure(self, *, directory, scope='all', selected_ids=(), frequency='daily', retention=10, password=None):
        self.service._require_unlocked()
        destination = Path(directory).expanduser().resolve()
        if not destination.is_dir():
            raise RecoveryError('Choose an existing backup folder. Connect the external drive if needed.')
        if frequency not in FREQUENCIES or scope not in ('all', 'selected') or not 1 <= retention <= 100:
            raise RecoveryError('Invalid backup schedule or retention.')
        available = {s.id for s in self.service.list_secrets()}
        chosen = sorted(set(selected_ids) & available)
        if scope == 'selected' and not chosen:
            raise RecoveryError('Select at least one Vault item.')
        with self._lock:
            if self.enabled:
                try:
                    self._copy_latest('before-settings')
                except Exception as exc:
                    # A new destination is allowed while the old drive is offline:
                    # no old file is replaced there. Same-folder changes must first
                    # preserve the previous scope/key, including before narrowing it.
                    if str(destination) == self.config.get('directory'):
                        raise RecoveryError('Could not preserve the previous recovery copy. Check the backup folder first.') from exc
            old_config, old_key = self.config.copy(), self._key
            if password is None:
                if not self.config.get('wrapped_key'):
                    raise RecoveryError('Create a backup passphrase first.')
                key = self._get_key()
                kdf, wrapped = self.config['kdf'], self.config['wrapped_key']
            else:
                key = os.urandom(32)
                kdf, wrapped = archive.password_envelope(password, key)
            profile_id = self.config.get('profile_id', uuid.uuid4().hex)
            # A manual session lock can arrive while password derivation runs in
            # a worker. Finish wrapping before publishing any new configuration.
            local_key = crypto.encrypt(base64.b64encode(key).decode(),
                self.service._require_unlocked(),
                b'dotghostboard:recovery:local-key:v1:' + profile_id.encode())
            self.config = {
                'version': 1, 'enabled': True, 'profile_id': profile_id,
                'directory': str(destination), 'scope': scope, 'selected_ids': chosen,
                'frequency': frequency, 'retention': retention, 'kdf': kdf, 'wrapped_key': wrapped,
                'directory_device': destination.stat().st_dev, 'directory_inode': destination.stat().st_ino,
            }
            self.config['local_key'] = local_key
            self._key = bytearray(key)
            try:
                self.snapshot('setup', force_version=True)
            except Exception:
                self.lock()
                self.config, self._key = old_config, old_key
                raise
            if old_key is not None:
                crypto.secure_zero(old_key)

    def disable(self):
        if self.config.get('version'):
            self.config.update(enabled=False, last_error='', pending_sync=False)
            self._save()
        self.error = ''
        self.lock()

    def _payload(self):
        items = []
        selected = set(self.config['selected_ids'])
        key = self.service._require_unlocked()
        # One explicit read transaction gives metadata, records, and history the
        # same SQLite snapshot, including during background CSV imports.
        with _vault_db(self.service._repo._db_path) as cur:
            cur.execute('BEGIN')
            cur.execute('SELECT * FROM vault_items ORDER BY id')
            rows = cur.fetchall()
            for row in rows:
                item = VaultItem(**dict(row))
                if self.config['scope'] == 'selected' and item.id not in selected:
                    continue
                value = decode_record(item, key)
                cur.execute('SELECT id,vault_item_id,ciphertext FROM vault_item_history '
                            'WHERE vault_item_id=? ORDER BY created_at DESC,id DESC LIMIT 3', (item.id,))
                history = [decode_history(dict(h), key) for h in cur.fetchall()]
                items.append({'source_id': item.id, 'title': value['title'], 'category': value['category'], 'secret': value['secret'],
                              'expires_at': value.get('expires_at'), 'history': history})
        return {'version': 1, 'independent': self.service.independent_password, 'items': items}

    def _directory(self):
        destination = Path(self.config['directory'])
        # Do not recreate a disconnected mount point and silently write to the system disk.
        if not destination.is_dir():
            raise RecoveryError('Backup folder is unavailable. Connect the drive and retry.')
        info = destination.stat()
        if (info.st_dev, info.st_ino) != (self.config.get('directory_device'), self.config.get('directory_inode')):
            raise RecoveryError('Backup folder or drive changed. Select the folder again in Recovery settings.')
        return destination

    @property
    def latest_path(self):
        return self._directory() / (self.config['profile_id'] + '-latest.dgb-recovery')

    def _version_path(self, now, reason):
        return self._directory() / f"{self.config['profile_id']}-{now.strftime('%Y%m%dT%H%M%S%fZ')}-{reason}.dgb-recovery"

    def versions(self):
        if not self.config.get('directory'):
            return []
        root = self._directory()
        prefix = self.config['profile_id'] + '-'
        return sorted((p for p in root.iterdir() if p.name.startswith(prefix)
                       and p.name.endswith('.dgb-recovery') and p.is_file() and not p.is_symlink()),
                      key=lambda p: p.stat().st_mtime, reverse=True)

    def _prune(self):
        historical = [p for p in self.versions() if not p.name.endswith('-latest.dgb-recovery')]
        # Frequent edits must not evict the user's daily/weekly/monthly timeline.
        for scheduled in (True, False):
            group = [p for p in historical if ('-scheduled-' in p.name) is scheduled]
            for path in group[self.config['retention']:]:
                path.unlink()

    def due(self, now):
        last = self.config.get('last_scheduled')
        return not last or now >= next_due(datetime.fromisoformat(last), self.config['frequency'])

    def snapshot(self, reason='manual', *, force_version=False, now=None, removed_ids=()):
        if not self.enabled:
            return None
        now = now or datetime.now(timezone.utc)
        with self._lock:
            key = self._get_key()
            payload = self._payload()
            current_ids = {item['source_id'] for item in payload['items']}
            previous_ids = set(self.config.get('last_item_ids', []))
            allowed_missing = set(removed_ids)
            if (previous_ids - current_ids - allowed_missing
                    or len(payload['items']) < self.config.get('last_count', 0) - len(allowed_missing)):
                raise RecoveryError('Vault items decreased unexpectedly or were replaced outside the app. The last successful recovery copy was kept. '
                                    'Open Recovery to restore or explicitly review the backup selection.')
            data = archive.pack(payload, key, self.config, reason, now)
            latest = self.latest_path
            archive.atomic_write(latest, data)
            # Verify what was actually persisted before publishing success or pruning.
            archive.verify(latest.read_bytes(), key)
            scheduled = self.due(now)
            if force_version or scheduled:
                kind = 'scheduled-' if scheduled else 'safety-'
                version = self._version_path(now, kind + reason)
                archive.atomic_write(version, data)
                archive.verify(version.read_bytes(), key)
                self.config['last_version'] = now.isoformat()
                if scheduled:
                    self.config['last_scheduled'] = now.isoformat()
            self.config.update(last_success=now.isoformat(), last_count=len(payload['items']),
                               last_item_ids=sorted(current_ids), latest_sha256=hashlib.sha256(data).hexdigest(),
                               last_error='', pending_sync=False)
            self.error = ''
            self._save()
            self._prune()
            return latest

    def _failure(self, exc):
        self.error = 'Recovery backup failed: ' + str(exc)
        self.config['last_error'] = self.error
        self.config['pending_sync'] = True
        logger.warning('%s', self.error)
        try:
            self._save()
        except OSError:
            pass

    def after_change(self, *, removed_ids=()):
        if not self.enabled:
            return
        if self._batch_depth:
            self._pending = True
            self._pending_removed_ids.update(removed_ids)
            return
        try:
            self.snapshot('sync', removed_ids=removed_ids)
        except Exception as exc:
            self._failure(exc)

    def before_change(self, reason):
        if not self.enabled or self._batch_depth:
            return
        try:
            if self.service.is_unlocked:
                self.snapshot('before-' + reason, force_version=True)
            else:
                self._copy_latest('before-' + reason)
        except Exception as exc:
            self._failure(exc)
            raise RecoveryError('Safety backup failed. Reconnect the backup folder or disable backups before this operation.') from exc

    def _copy_latest(self, reason):
        data = self.latest_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.config.get('latest_sha256'):
            raise RecoveryError('The last recovery copy could not be verified.')
        version = self._version_path(datetime.now(timezone.utc), 'safety-' + reason)
        archive.atomic_write(version, data)
        if hashlib.sha256(version.read_bytes()).hexdigest() != self.config['latest_sha256']:
            raise RecoveryError('The safety copy could not be verified after saving.')
        self._prune()

    def tick(self):
        if self.enabled and self.service.is_unlocked and (self.config.get('pending_sync') or self.due(datetime.now(timezone.utc))):
            self.after_change()

    @contextmanager
    def batch(self, reason='import'):
        self.before_change(reason)
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if not self._batch_depth and self._pending:
                self._pending = False
                removed = self._pending_removed_ids.copy()
                self._pending_removed_ids.clear()
                self.after_change(removed_ids=removed)
