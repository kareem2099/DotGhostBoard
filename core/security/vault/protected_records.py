"""Authenticated row-bound Vault payloads, including private listing metadata."""

import json
from core.crypto import encrypt, decrypt
from core.security.vault.database import _vault_db

PREFIX = 'v2:'
HISTORY_PREFIX = 'v2h:'
PLACEHOLDER = 'Protected item'


def encode_record(item_id, key, secret, title, category, expires_at=None):
    payload = json.dumps({'secret': secret, 'title': title, 'category': category,
                          'expires_at': expires_at}, ensure_ascii=False)
    return PREFIX + encrypt(payload, key, f'dotghostboard:vault:item:v2:{item_id}'.encode())


def decode_record(item, key):
    if item.ciphertext.startswith(PREFIX):
        payload = json.loads(decrypt(item.ciphertext[len(PREFIX):], key,
                                    f'dotghostboard:vault:item:v2:{item.id}'.encode()))
        if not all(isinstance(payload.get(field), str) for field in ('secret', 'title', 'category')):
            raise ValueError('Invalid Vault payload.')
        return payload
    return {'secret': decrypt(item.ciphertext, key), 'title': item.title,
            'category': item.category, 'expires_at': item.expires_at}


def encode_history(item_id, history_id, plaintext, key):
    return HISTORY_PREFIX + encrypt(plaintext, key, f'dotghostboard:vault:history:v2:{item_id}:{history_id}'.encode())


def decode_history(record, key):
    token = record['ciphertext']
    if token.startswith(HISTORY_PREFIX):
        return decrypt(token[len(HISTORY_PREFIX):], key,
                       f"dotghostboard:vault:history:v2:{record['vault_item_id']}:{record['id']}".encode())
    return decrypt(token, key)


class ProtectedRecords:
    def __init__(self, repository):
        self.repo = repository

    def needs_migration(self):
        with _vault_db(self.repo._db_path) as cur:
            cur.execute("SELECT 1 FROM vault_items WHERE ciphertext NOT LIKE 'v2:%' LIMIT 1")
            if cur.fetchone():
                return True
            cur.execute("SELECT 1 FROM vault_item_history WHERE ciphertext NOT LIKE 'v2h:%' LIMIT 1")
            return cur.fetchone() is not None

    def add(self, key, secret, title, category, expires_at, history=()):
        with _vault_db(self.repo._db_path) as cur:
            cur.execute('INSERT INTO vault_items(title,category,ciphertext) VALUES (?,?,?)',
                        (PLACEHOLDER, 'protected', ''))
            item_id = cur.lastrowid
            token = encode_record(item_id, key, secret, title, category, expires_at)
            cur.execute('UPDATE vault_items SET ciphertext=? WHERE id=?', (token, item_id))
            for previous in history:
                self._history(cur, item_id, previous, key)
        return item_id

    def add_history(self, item_id, plaintext, key):
        with _vault_db(self.repo._db_path) as cur:
            history_id = self._history(cur, item_id, plaintext, key)
        return history_id

    @staticmethod
    def _history(cur, item_id, plaintext, key):
        cur.execute('INSERT INTO vault_item_history(vault_item_id,ciphertext) VALUES (?,?)', (item_id, ''))
        history_id = cur.lastrowid
        cur.execute('UPDATE vault_item_history SET ciphertext=? WHERE id=?',
                    (encode_history(item_id, history_id, plaintext, key), history_id))
        cur.execute('DELETE FROM vault_item_history WHERE vault_item_id=? AND id NOT IN '
                    '(SELECT id FROM vault_item_history WHERE vault_item_id=? ORDER BY created_at DESC,id DESC LIMIT 3)',
                    (item_id, item_id))
        return history_id

    def update(self, item_id, payload, key, previous_secret=None):
        with _vault_db(self.repo._db_path) as cur:
            if previous_secret is not None:
                self._history(cur, item_id, previous_secret, key)
            token = encode_record(item_id, key, **payload)
            cur.execute('UPDATE vault_items SET title=?,category=?,ciphertext=?,metadata_encrypted=NULL,'
                        'expires_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                        (PLACEHOLDER, 'protected', token, item_id))
            return cur.rowcount > 0

    def migrate(self, key):
        # Validate the complete migration before updating anything. A failed row
        # rolls back every metadata/payload rewrite in this transaction.
        updates = []
        offset = 0
        while True:
            items = self.repo.list_items(limit=100, offset=offset)
            for item in items:
                payload = decode_record(item, key)
                if not item.ciphertext.startswith(PREFIX):
                    updates.append((encode_record(item.id, key, **payload), item.id))
            if len(items) < 100:
                break
            offset += len(items)
        with _vault_db(self.repo._db_path) as cur:
            cur.execute('SELECT id,vault_item_id,ciphertext FROM vault_item_history')
            histories = [dict(row) for row in cur.fetchall()]
            history_updates = []
            for history in histories:
                plaintext = decode_history(history, key)
                if not history['ciphertext'].startswith(HISTORY_PREFIX):
                    history_updates.append((encode_history(history['vault_item_id'], history['id'], plaintext, key), history['id']))
            for token, item_id in updates:
                cur.execute('UPDATE vault_items SET title=?,category=?,ciphertext=?,metadata_encrypted=NULL,'
                            'expires_at=NULL WHERE id=?', (PLACEHOLDER, 'protected', token, item_id))
            cur.executemany('UPDATE vault_item_history SET ciphertext=? WHERE id=?', history_updates)
        if updates or history_updates:
            # Drop old WAL pages after successful migration. External snapshots and
            # storage-device remanence are outside SQLite's deletion guarantees.
            import sqlite3
            from core.security.vault.database import get_vault_db_path
            with sqlite3.connect(self.repo._db_path or get_vault_db_path()) as conn:
                conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                conn.execute('VACUUM')
