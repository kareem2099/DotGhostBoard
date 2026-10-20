"""Self-contained, authenticated recovery archives; no profile keys are required to read one."""

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from core import crypto
from core.security.passwords import derive_password_key, new_kdf_config, validate_new_password

FORMAT = 'dotghostboard-recovery'
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def key_aad(kdf):
    return b'dotghostboard:recovery:key:v1:' + canonical(kdf)


def password_envelope(password, key):
    validate_new_password(password)
    kdf = new_kdf_config()
    wrapped = crypto.encrypt(base64.b64encode(key).decode(), derive_password_key(password, kdf), key_aad(kdf))
    return kdf, wrapped


def pack(payload, key, config, reason, now=None):
    header = {
        'format': FORMAT, 'version': 1, 'created_at': (now or datetime.now(timezone.utc)).isoformat(),
        'count': len(payload['items']), 'reason': reason, 'profile_id': config['profile_id'],
        'kdf': config['kdf'], 'wrapped_key': config['wrapped_key'],
    }
    token = crypto.encrypt(json.dumps(payload, ensure_ascii=False), key, canonical(header))
    data = canonical({'header': header, 'ciphertext': token})
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError('Recovery archive exceeds the 128 MiB limit.')
    verify(data, key)
    return data


def parse(data):
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError('Recovery archive exceeds the 128 MiB limit.')
    try:
        archive = json.loads(data)
        header = archive['header']
        if header['format'] != FORMAT or header['version'] != 1:
            raise ValueError()
        if not isinstance(archive['ciphertext'], str) or not isinstance(header['count'], int):
            raise ValueError()
        return archive
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError('Invalid or damaged recovery archive.') from exc


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('items'), list):
        raise ValueError('Invalid recovery payload.')
    if len(payload['items']) > 100_000:
        raise ValueError('Too many recovery entries.')
    for item in payload['items']:
        if (not isinstance(item, dict)
                or not all(isinstance(item.get(k), str) for k in ('title', 'secret', 'category'))
                or not item['title'].strip() or not item['secret']
                or not isinstance(item.get('history', []), list)
                or not all(isinstance(v, str) for v in item.get('history', []))
                or (item.get('expires_at') is not None and not isinstance(item['expires_at'], str))):
            raise ValueError('Invalid recovery entry.')
    return payload


def verify(data, key):
    archive = parse(data)
    payload = validate_payload(json.loads(crypto.decrypt(archive['ciphertext'], key, canonical(archive['header']))))
    if len(payload['items']) != archive['header']['count']:
        raise ValueError('Recovery entry count does not match.')
    return payload


def open_archive(path, password):
    with open(path, 'rb') as stream:
        data = stream.read(MAX_ARCHIVE_BYTES + 1)
    return decrypt_archive(data, password)


def decrypt_archive(data, password):
    archive = parse(data)
    header = archive['header']
    try:
        wrapping_key = derive_password_key(password, header['kdf'])
        key = base64.b64decode(crypto.decrypt(header['wrapped_key'], wrapping_key, key_aad(header['kdf'])), validate=True)
        if len(key) != 32:
            raise ValueError()
        return verify(data, key)
    except Exception as exc:
        raise ValueError('Incorrect backup passphrase or damaged recovery archive.') from exc


def atomic_write(path, data):
    """Private temporary file, fsync, atomic publication, and parent-directory fsync."""
    import tempfile
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.recovery-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
