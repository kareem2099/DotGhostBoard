"""Vault session lifecycle, authenticated encrypted records and password envelopes."""

from __future__ import annotations

import hmac
import os
import threading
from typing import Optional
from core.crypto import verify_password, secure_zero
from core.security.vault.repository import VaultRepository
from core.security.vault.models import VaultSummary
from core.security.vault.csv_importer import password_from_vault_payload
from core.security.vault.credentials import VaultCredentials
from core.security.vault.protected_records import ProtectedRecords, decode_record, decode_history


class VaultLockedError(RuntimeError):
    """An operation requires an unlocked Vault."""


class VaultUnlockError(RuntimeError):
    """The Vault key envelope could not be read or authenticated safely."""


class VaultService:
    def __init__(self, repository: Optional[VaultRepository] = None):
        self._repo = repository or VaultRepository()
        self._credentials = VaultCredentials(self._repo)
        self._records = ProtectedRecords(self._repo)
        self._vault_dek: Optional[bytearray] = None
        self._is_unlocked = False
        self._recognition_key = os.urandom(32)
        self._recognition: dict[int, tuple[str, str, tuple[bytes, ...]]] = {}
        self._recognition_lock = threading.RLock()
        self._recognition_ready = False
        self._recovery = None

    @property
    def recovery(self):
        if self._recovery is None:
            from core.security.vault.recovery import RecoveryManager
            self._recovery = RecoveryManager(self)
        return self._recovery

    def reload_after_recovery(self):
        self.lock()
        self._recovery = None
        with self._recognition_lock:
            self._recognition.clear()
            self._recognition_key = os.urandom(32)
            self._recognition_ready = False

    @property
    def is_unlocked(self):
        return self._is_unlocked and self._vault_dek is not None

    @property
    def independent_password(self):
        try:
            return self._credentials.independent
        except Exception as exc:
            raise VaultUnlockError('The Vault credential configuration could not be read safely.') from exc

    @property
    def recognition_ready(self):
        return self._recognition_ready or self.count() == 0

    def _unwrap_or_create_dek(self, vault_kek):
        return self._credentials.unwrap(vault_kek)

    def unlock(self, password):
        try:
            if not self.independent_password and not verify_password(password):
                return False
            self.unlock_with_key(self._credentials.key_for_password(password))
            return True
        except Exception:
            self.lock()
            return False

    def unlock_with_key(self, vault_kek):
        self.lock()
        try:
            dek = self._unwrap_or_create_dek(vault_kek)
            self._vault_dek = bytearray(dek)
            self._is_unlocked = True
            if self._records.needs_migration():
                self.recovery.before_change('migration')
            self._records.migrate(dek)
            self._recognition_ready = self.match_clipboard_secret('') is False
            self.recovery.tick()
        except Exception as exc:
            self.lock()
            raise VaultUnlockError('The Vault key or encrypted records could not be opened safely.') from exc

    def configure_password(self, dashboard_password, new_password=None, current_password=None):
        """Authenticate both sides before changing modes; never persist alternate keys."""
        self.recovery.before_change('password')
        self._credentials.configure(dashboard_password, new_password, current_password)
        self.lock()
        with self._recognition_lock:
            self._recognition.clear()
            self._recognition_key = os.urandom(32)
            self._recognition_ready = False
        if not self.unlock(new_password if new_password is not None else dashboard_password):
            raise VaultUnlockError('Credentials were updated, but the Vault could not be reopened.')
        self.recovery.after_change()

    def rewrap_dek(self, old_kek, new_kek):
        # An independent Vault must not be tied to Dashboard password rotation.
        if self.independent_password:
            return True
        if self._repo.get_metadata('wrapped_dek') is None:
            return self.count() == 0
        try:
            dek = self._credentials.unwrap(old_kek)
            self._credentials.write(dek, new_kek, self._credentials.config())
            return True
        except Exception:
            return False

    def reset_empty_envelope(self):
        if self.count():
            raise RuntimeError('Cannot reset envelope on non-empty Vault.')
        self.lock()
        self._repo.delete_metadata('wrapped_dek')
        self._repo.delete_metadata('credential_config')
        self._recognition_ready = False

    def lock(self):
        if self._recovery is not None:
            self._recovery.lock()
        if self._vault_dek is not None:
            secure_zero(self._vault_dek)
            self._vault_dek = None
        self._is_unlocked = False

    def _require_unlocked(self):
        if not self.is_unlocked:
            raise VaultLockedError('Vault is locked. Unlock before accessing secrets.')
        return bytes(self._vault_dek)

    def add_secret(self, title, secret_text, category='generic', expires_at=None, history=()):
        key = self._require_unlocked()
        if not title.strip() or not secret_text:
            raise ValueError('Secret title and content cannot be empty.')
        item_id = self._records.add(key, secret_text, title.strip(), category.strip().lower(), expires_at, history)
        self._remember_secret(self._repo.get_item(item_id), secret_text, category)
        self.recovery.after_change()
        return item_id

    def _secret_digest(self, plaintext):
        return hmac.digest(self._recognition_key, plaintext.strip().encode('utf-8'), 'sha256')

    def _remember_secret(self, item, plaintext, category):
        values = [plaintext]
        if category.strip().lower() == 'password':
            password = password_from_vault_payload(plaintext)
            if password:
                values.append(password)
        with self._recognition_lock:
            self._recognition[item.id] = (item.ciphertext, item.category,
                                          tuple(self._secret_digest(value) for value in values))

    def match_clipboard_secret(self, plaintext):
        needle = self._secret_digest(plaintext)
        seen, matched, complete, offset = set(), False, True, 0
        with self._recognition_lock:
            while True:
                items = self._repo.list_items(limit=100, offset=offset)
                for item in items:
                    seen.add(item.id)
                    cached = self._recognition.get(item.id)
                    if cached is None or cached[:2] != (item.ciphertext, item.category):
                        self._recognition.pop(item.id, None)
                        if self.is_unlocked:
                            try:
                                payload = decode_record(item, self._require_unlocked())
                                self._remember_secret(item, payload['secret'], payload['category'])
                            except Exception:
                                complete = False
                        else:
                            complete = False
                        cached = self._recognition.get(item.id)
                    if cached and any(hmac.compare_digest(digest, needle) for digest in cached[2]):
                        matched = True
                if len(items) < 100:
                    break
                offset += len(items)
            self._recognition = {item_id: value for item_id, value in self._recognition.items() if item_id in seen}
        return True if matched else (False if complete else None)

    def find_duplicate(self, plaintext):
        if not self.is_unlocked:
            return None
        for summary in self.list_secrets():
            value = self.get_secret(summary.id)
            if value is not None and hmac.compare_digest(value.encode(), plaintext.encode()):
                return summary
        return None

    def get_secret(self, item_id):
        key = self._require_unlocked()
        item = self._repo.get_item(item_id)
        return decode_record(item, key)['secret'] if item else None

    def update_secret(self, item_id, title=None, secret_text=None, category=None, save_history=True, expires_at=None):
        key = self._require_unlocked()
        item = self._repo.get_item(item_id)
        if item is None:
            return False
        payload = decode_record(item, key)
        self.recovery.before_change('edit')
        previous = payload['secret'] if save_history and secret_text is not None and secret_text != payload['secret'] else None
        if title is not None:
            payload['title'] = title.strip()
        if secret_text is not None:
            payload['secret'] = secret_text
        if category is not None:
            payload['category'] = category.strip().lower()
        if expires_at is not None:
            payload['expires_at'] = expires_at or None
        updated = self._records.update(item_id, payload, key, previous)
        if updated:
            self._remember_secret(self._repo.get_item(item_id), payload['secret'], payload['category'])
            self.recovery.after_change()
        return updated

    def add_secret_history(self, item_id, plaintext):
        result = self._records.add_history(item_id, plaintext, self._require_unlocked())
        self.recovery.after_change()
        return result

    def get_secret_history(self, item_id, limit=3):
        key = self._require_unlocked()
        return [{**record, 'plaintext': decode_history(record, key)}
                for record in self._repo.get_history(item_id, limit=limit)]

    def restore_secret_history(self, item_id, history_id):
        self._require_unlocked()
        target = next((record for record in self.get_secret_history(item_id, limit=10) if record['id'] == history_id), None)
        return self.update_secret(item_id, secret_text=target['plaintext']) if target else False

    def count_secret_history(self, item_id):
        return self._repo.count_history(item_id)

    def delete_secret(self, item_id):
        self._require_unlocked()
        self.recovery.before_change('delete')
        deleted = self._repo.delete_item(item_id)
        if deleted:
            self.recovery.after_change(removed_ids=(item_id,))
        return deleted

    def list_secrets(self, category=None):
        summaries, offset = [], 0
        while True:
            items = self._repo.list_items(limit=100, offset=offset)
            for item in items:
                if self.is_unlocked:
                    payload = decode_record(item, self._require_unlocked())
                    if category and payload['category'] != category:
                        continue
                    title, actual_category, expiry = payload['title'], payload['category'], payload['expires_at']
                else:
                    if category:
                        continue
                    title, actual_category, expiry = 'Protected item', 'generic', None
                summaries.append(VaultSummary(item.id, title, actual_category, item.created_at, item.updated_at, expiry))
            if len(items) < 100:
                return summaries
            offset += len(items)

    def count(self, category=None):
        return len(self.list_secrets(category)) if category else self._repo.count_items()
