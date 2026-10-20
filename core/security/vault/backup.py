"""
core/security/vault/backup.py
─────────────────────────────
Encrypted backup and restore subsystem for The Vault (.vault package).

Format:
  [4-byte MAGIC: "DGBV"]
  [1-byte VERSION: 2; legacy version 1 remains readable]
  [16-byte SALT]
  [12-byte GCM NONCE]
  [Ciphertext + 16-byte GCM Auth Tag]

Key Derivation:
  Version 2: Argon2id (64 MiB, 3 passes, 1 lane) with independent per-backup salt.
  Legacy version 1 PBKDF2-HMAC-SHA256 (100,000 iterations) remains readable.

Payload (pre-encryption):
  JSON object containing version, export timestamp, and encrypted items with history & expiry.

v2.1.0 Leviathan — Vault Backup & Restore.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.security.vault.service import VaultLockedError
from core.security.passwords import derive_password_key, validate_new_password
import base64

if TYPE_CHECKING:
    from core.security.vault.service import VaultService

MAGIC = b"DGBV"
BACKUP_FORMAT_VERSION = 2
MIN_PASSPHRASE_LEN = 12
KDF_ITERATIONS = 100_000
NONCE_SIZE = 12
SALT_SIZE = 16


def _derive_backup_key(passphrase: str, salt: bytes, version: int = BACKUP_FORMAT_VERSION) -> bytes:
    """Read legacy PBKDF2 backups; write Argon2id backups with bounded parameters."""
    if version == 2:
        return derive_password_key(passphrase, {
            "algorithm": "argon2id", "memory_kib": 65536, "iterations": 3,
            "lanes": 1, "salt": base64.b64encode(salt).decode("ascii"),
        })
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def export_vault_package(service: VaultService, passphrase: str) -> bytes:
    """
    Export all entries from an unlocked Vault into an encrypted .vault byte stream.

    Raises:
        VaultLockedError: If the vault is not unlocked.
        ValueError: If passphrase is too short.
    """
    if not service.is_unlocked:
        raise VaultLockedError("Cannot export locked vault. Unlock first.")

    validate_new_password(passphrase)

    # 1. Gather all secrets, their history, and expiry
    summaries = service.list_secrets()
    items: list[dict[str, Any]] = []

    for s in summaries:
        try:
            plaintext = service.get_secret(s.id)
            if plaintext is None:
                continue
            history_records = service.get_secret_history(s.id)
            history_plaintexts = [h["plaintext"] for h in history_records if "plaintext" in h]

            items.append({
                "title": s.title,
                "category": s.category,
                "secret": plaintext,
                "history": history_plaintexts,
                "expires_at": s.expires_at,
            })
        except Exception as exc:
            raise ValueError("Backup aborted: an encrypted item could not be read.") from exc

    # 2. Package into JSON bundle
    payload = {
        "version": BACKUP_FORMAT_VERSION,
        "app": "DotGhostBoard",
        "type": "vault_backup",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    # 3. Encrypt bundle with AES-256-GCM
    salt = os.urandom(SALT_SIZE)
    key = _derive_backup_key(passphrase, salt)
    nonce = os.urandom(NONCE_SIZE)
    header = MAGIC + bytes([BACKUP_FORMAT_VERSION]) + salt + nonce
    ciphertext = AESGCM(key).encrypt(nonce, payload_bytes, header)

    # 4. Formulate file format
    return header + ciphertext


def decrypt_vault_package(package_bytes: bytes, passphrase: str) -> dict:
    """Authenticate and validate a manual backup without needing the source Vault."""
    # Check minimum header size: 4 (magic) + 1 (ver) + 16 (salt) + 12 (nonce) + 16 (GCM tag)
    min_size = len(MAGIC) + 1 + SALT_SIZE + NONCE_SIZE + 16
    if len(package_bytes) < min_size:
        raise ValueError("Invalid or truncated .vault file.")

    if not package_bytes.startswith(MAGIC):
        raise ValueError("Invalid Vault backup header: not a DotGhostBoard .vault file.")

    file_version = package_bytes[4]
    if file_version not in (1, BACKUP_FORMAT_VERSION):
        raise ValueError(f"Unsupported .vault backup version {file_version}.")

    salt_start = 5
    salt_end = salt_start + SALT_SIZE
    salt = package_bytes[salt_start:salt_end]

    nonce_start = salt_end
    nonce_end = nonce_start + NONCE_SIZE
    nonce = package_bytes[nonce_start:nonce_end]

    ciphertext = package_bytes[nonce_end:]

    # Derive key and attempt GCM authenticated decryption
    key = _derive_backup_key(passphrase.strip() if file_version == 1 else passphrase, salt, file_version)
    header_aad = package_bytes[:salt_start] if file_version == 1 else package_bytes[:nonce_end]
    try:
        plaintext_bytes = AESGCM(key).decrypt(nonce, ciphertext, header_aad)
    except Exception as exc:
        raise ValueError("Incorrect passphrase or corrupted backup file.") from exc

    try:
        payload = json.loads(plaintext_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Corrupted backup payload: invalid JSON structure.") from exc

    if not isinstance(payload, dict) or payload.get("version") != file_version:
        raise ValueError("Invalid backup payload version.")
    items = payload.get("items", [])
    if not isinstance(items, list) or len(items) > 100_000:
        raise ValueError("Invalid backup item collection.")
    # Validate the complete authenticated payload before writing any entries.
    for item in items:
        if (not isinstance(item, dict)
                or not isinstance(item.get('title', ''), str)
                or not isinstance(item.get('secret', ''), str)
                or not isinstance(item.get('category', 'generic'), str)
                or not isinstance(item.get('history', []), list)
                or not all(isinstance(value, str) for value in item.get('history', []))
                or (item.get('expires_at') is not None and not isinstance(item['expires_at'], str))):
            raise ValueError('Invalid backup entry structure; no entries were imported.')
    return payload


def import_vault_package(service: VaultService, package_bytes: bytes, passphrase: str) -> dict[str, int]:
    """Authenticate a manual backup and merge its entries into an unlocked Vault."""
    if not service.is_unlocked:
        raise VaultLockedError("Cannot import into locked vault. Unlock first.")
    payload = decrypt_vault_package(package_bytes, passphrase)
    with service.recovery.batch('import'):
        return _import_payload(service, payload['items'])


def _import_payload(service, items):
    imported_count = 0
    skipped_count = 0

    # Build existing lookup to prevent duplicate identical entries
    existing_summaries = service.list_secrets()
    existing_items: list[tuple[str, str, str]] = []
    for s in existing_summaries:
        try:
            sec = service.get_secret(s.id)
            if sec:
                existing_items.append((s.title.strip().lower(), s.category.strip().lower(), sec))
        except Exception:
            pass

    for item in items:
        title = item.get("title", "").strip()
        secret = item.get("secret", "")
        category = item.get("category", "generic").strip()
        expires_at = item.get("expires_at")
        history = item.get("history", [])

        if not title or not secret:
            skipped_count += 1
            continue

        # Check duplicate
        if (title.lower(), category.lower(), secret) in existing_items:
            skipped_count += 1
            continue

        try:
            new_id = service.add_secret(
                title=title,
                secret_text=secret,
                category=category,
                expires_at=expires_at,
                history=list(reversed([value for value in history[:3] if value and value != secret])),
            )

            imported_count += 1
            existing_items.append((title.lower(), category.lower(), secret))
        except Exception:
            skipped_count += 1

    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "total_items": len(items),
    }
