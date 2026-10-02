"""
core/security/vault/backup.py
─────────────────────────────
Encrypted backup and restore subsystem for The Vault (.vault package).

Format:
  [4-byte MAGIC: "DGBV"]
  [1-byte VERSION: 1]
  [16-byte SALT]
  [12-byte GCM NONCE]
  [Ciphertext + 16-byte GCM Auth Tag]

Key Derivation:
  PBKDF2-HMAC-SHA256 (100,000 iterations) with independent per-backup salt.

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

if TYPE_CHECKING:
    from core.security.vault.service import VaultService

MAGIC = b"DGBV"
BACKUP_FORMAT_VERSION = 1
MIN_PASSPHRASE_LEN = 8
KDF_ITERATIONS = 100_000
NONCE_SIZE = 12
SALT_SIZE = 16


def _derive_backup_key(passphrase: str, salt: bytes) -> bytes:
    """Derive 256-bit AES key from backup passphrase and salt using PBKDF2."""
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

    passphrase = passphrase.strip()
    if len(passphrase) < MIN_PASSPHRASE_LEN:
        raise ValueError(f"Export passphrase must be at least {MIN_PASSPHRASE_LEN} characters.")

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
        except Exception:
            continue

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
    header_aad = MAGIC + bytes([BACKUP_FORMAT_VERSION])
    ciphertext = AESGCM(key).encrypt(nonce, payload_bytes, header_aad)

    # 4. Formulate file format
    header = header_aad + salt + nonce
    return header + ciphertext


def import_vault_package(
    service: VaultService,
    package_bytes: bytes,
    passphrase: str,
) -> dict[str, int]:
    """
    Decrypt a .vault package and import items into the active unlocked Vault.

    Returns:
        dict with {"imported_count": int, "skipped_count": int, "total_items": int}

    Raises:
        VaultLockedError: If the target vault is locked.
        ValueError: If magic header is invalid, version unsupported, or passphrase wrong.
    """
    if not service.is_unlocked:
        raise VaultLockedError("Cannot import into locked vault. Unlock first.")

    # Check minimum header size: 4 (magic) + 1 (ver) + 16 (salt) + 12 (nonce) + 16 (GCM tag)
    min_size = len(MAGIC) + 1 + SALT_SIZE + NONCE_SIZE + 16
    if len(package_bytes) < min_size:
        raise ValueError("Invalid or truncated .vault file.")

    if not package_bytes.startswith(MAGIC):
        raise ValueError("Invalid Vault backup header: not a DotGhostBoard .vault file.")

    file_version = package_bytes[4]
    if file_version != BACKUP_FORMAT_VERSION:
        raise ValueError(f"Unsupported .vault backup version {file_version}.")

    salt_start = 5
    salt_end = salt_start + SALT_SIZE
    salt = package_bytes[salt_start:salt_end]

    nonce_start = salt_end
    nonce_end = nonce_start + NONCE_SIZE
    nonce = package_bytes[nonce_start:nonce_end]

    ciphertext = package_bytes[nonce_end:]

    # Derive key and attempt GCM authenticated decryption
    key = _derive_backup_key(passphrase.strip(), salt)
    header_aad = package_bytes[:salt_start]
    try:
        plaintext_bytes = AESGCM(key).decrypt(nonce, ciphertext, header_aad)
    except Exception as exc:
        raise ValueError("Incorrect passphrase or corrupted backup file.") from exc

    try:
        payload = json.loads(plaintext_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Corrupted backup payload: invalid JSON structure.") from exc

    items = payload.get("items", [])
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
            )
            # Restore past history entries in chronological order
            if history and hasattr(service, "_repo"):
                for old_val in reversed(history[:3]):
                    if old_val and old_val != secret:
                        try:
                            # Encrypt with active DEK and add history entry
                            key = service._require_unlocked()
                            from core.crypto import encrypt
                            old_cipher = encrypt(old_val, key)
                            service._repo.add_history_entry(new_id, old_cipher, max_entries=3)
                        except Exception:
                            pass

            imported_count += 1
            existing_items.append((title.lower(), category.lower(), secret))
        except Exception:
            skipped_count += 1

    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "total_items": len(items),
    }
