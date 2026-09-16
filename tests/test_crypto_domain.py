"""
tests/test_crypto_domain.py
───────────────────────────
Tests for Cryptographic Domain Separation and Memory Scrubbing.
"""

import pytest
from core.crypto import (
    derive_key,
    derive_vault_key,
    encrypt,
    decrypt,
    secure_zero,
    _load_or_create_salt,
)


def test_domain_separation_produces_distinct_keys(tmp_path, monkeypatch):
    """
    Ensure that the Eclipse key and Vault key derived from the EXACT same password
    are cryptographically independent (HKDF domain separation).
    """
    import core.crypto as crypto
    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))

    password = "SuperSecretPassword123!"

    eclipse_key = derive_key(password)
    vault_key = derive_vault_key(password)

    assert isinstance(eclipse_key, bytes)
    assert isinstance(vault_key, bytes)
    assert len(eclipse_key) == 32
    assert len(vault_key) == 32

    # CRITICAL: Keys must not match!
    assert eclipse_key != vault_key


def test_keys_are_deterministic(tmp_path, monkeypatch):
    """Deriving twice with same password and salt must yield identical keys."""
    import core.crypto as crypto
    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))

    password = "ConsistentPassword999"

    k1_e = derive_key(password)
    k2_e = derive_key(password)
    assert k1_e == k2_e

    k1_v = derive_vault_key(password)
    k2_v = derive_vault_key(password)
    assert k1_v == k2_v


def test_encrypt_decrypt_roundtrip_with_both_keys(tmp_path, monkeypatch):
    """Both keys must function properly with standard AES-256-GCM."""
    import core.crypto as crypto
    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))

    password = "TestPassword456"
    eclipse_key = derive_key(password)
    vault_key = derive_vault_key(password)

    secret = "Top Secret Token: ghp_1234567890"

    # Encrypt with Vault key, decrypt with Vault key
    v_token = encrypt(secret, vault_key)
    assert decrypt(v_token, vault_key) == secret

    # Cross-decrypt with Eclipse key must fail!
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt(v_token, eclipse_key)


def test_secure_zero_scrubs_bytearray():
    """secure_zero must zero-fill all bytes of a bytearray in-place."""
    buf = bytearray(b"\xde\xad\xbe\xef\xca\xfe\xba\xbe")
    length = len(buf)

    secure_zero(buf)

    assert len(buf) == length
    assert all(b == 0 for b in buf)


def test_crypto_file_permissions(tmp_path, monkeypatch):
    """Ensure salt and verifier files are created with 0600 and dir with 0700."""
    import os
    import stat
    import core.crypto as crypto

    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    salt_file = tmp_path / "eclipse.salt"
    verify_file = tmp_path / "eclipse.verify"
    monkeypatch.setattr(crypto, "_SALT_FILE", str(salt_file))
    monkeypatch.setattr(crypto, "_VERIFY_FILE", str(verify_file))

    crypto.save_master_password("TestSecretPass1")

    dir_mode = stat.S_IMODE(os.stat(str(tmp_path)).st_mode)
    salt_mode = stat.S_IMODE(os.stat(str(salt_file)).st_mode)
    verify_mode = stat.S_IMODE(os.stat(str(verify_file)).st_mode)

    assert dir_mode == 0o700
    assert salt_mode == 0o600
    assert verify_mode == 0o600


def test_corrupt_existing_salt_is_never_regenerated(tmp_path, monkeypatch):
    """Refuse to regenerate salt if file exists with length != 32."""
    import core.crypto as crypto
    salt_file = tmp_path / "eclipse.salt"
    # Write a corrupt 16-byte salt file
    salt_file.write_bytes(b"short_16_bytes!!")

    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(salt_file))

    with pytest.raises(RuntimeError, match="Eclipse salt is corrupted; refusing to regenerate it"):
        _load_or_create_salt()
