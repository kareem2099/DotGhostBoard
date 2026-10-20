"""
Eclipse Crypto Engine — AES-256-GCM authenticated encryption
DotGhostBoard v1.4.0
────────────────────────────────────────────────────────────
All secrets are encrypted with AES-256-GCM.
Key derivation: PBKDF2-SHA256 with 600 000 iterations + per-install random salt.
The salt is stored at ~/.config/dotghostboard/eclipse.salt
The verifier is at   ~/.config/dotghostboard/eclipse.verify
"""

from __future__ import annotations

import os
import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# ── Paths ─────────────────────────────────────────────────────────────────────
_DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".config", "dotghostboard")
_CFG_DIR      = os.getenv("DOTGHOST_HOME", _DEFAULT_HOME)
_SALT_FILE   = os.path.join(_CFG_DIR, "eclipse.salt")
_VERIFY_FILE = os.path.join(_CFG_DIR, "eclipse.verify")

_VERIFY_TOKEN = "DOTGHOST_ECLIPSE_OK"   # plaintext stored in verifier
_KDF_ITER     = 600_000                  # PBKDF2 iteration count
_NONCE_SIZE   = 12                       # GCM standard nonce (96-bit)


# ── Salt management ───────────────────────────────────────────────────────────

def _load_or_create_salt() -> bytes:
    """Load existing per-install salt, or generate and persist a new one."""
    os.makedirs(_CFG_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(_CFG_DIR, 0o700)
    except OSError:
        pass

    if os.path.exists(_SALT_FILE):
        with open(_SALT_FILE, "rb") as f:
            data = f.read()
        if len(data) != 32:
            raise RuntimeError(
                "Eclipse salt is corrupted; refusing to regenerate it."
            )
        return data

    if os.path.exists(_VERIFY_FILE):
        raise RuntimeError('Eclipse salt is missing; refusing to replace an existing credential salt.')

    # Generate fresh 256-bit salt only if file does not exist
    salt = os.urandom(32)
    with open(_SALT_FILE, "wb") as f:
        f.write(salt)
    try:
        os.chmod(_SALT_FILE, 0o600)
    except OSError:
        pass
    return salt


# ── Key Derivation ────────────────────────────────────────────────────────────

def derive_key(password: str) -> bytes:
    """
    Derive a 256-bit AES key from *password* using PBKDF2-HMAC-SHA256.

    The same password + same salt → same key, so decryption is deterministic
    across sessions as long as eclipse.salt is not deleted.
    """
    salt = _load_or_create_salt()
    kdf  = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITER,
    )
    return kdf.derive(password.encode("utf-8"))


def derive_vault_key(password: str) -> bytes:
    """
    Derive a domain-separated 256-bit AES key for The Vault (v2.x) from *password*.

    Uses HKDF-SHA256 with info context b"dotghostboard:vault:v2" over the base key.
    The contexts use different keys. In shared-password mode the Vault key remains
    derivable from the Eclipse session key; it is not an independent credential.
    """
    return derive_vault_key_from_session_key(derive_key(password))


def derive_vault_key_from_session_key(base_key: bytes) -> bytes:
    """Apply the existing Vault HKDF to an authenticated Eclipse session key.

    Produces exactly the same KEK as derive_vault_key(password), without retaining
    the password or changing the Vault's encryption format.
    """
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    if len(base_key) != 32:
        raise ValueError("An Eclipse session key must contain exactly 32 bytes.")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"dotghostboard:vault:v2",
    )
    return hkdf.derive(base_key)


def secure_zero(buf: bytearray) -> None:
    """
    Best-effort scrubbing of mutable in-memory bytearray buffers.
    """
    if isinstance(buf, bytearray):
        for i in range(len(buf)):
            buf[i] = 0


# ── AES-256-GCM ───────────────────────────────────────────────────────────────

def encrypt(plaintext: str, key: bytes, associated_data: bytes | None = None) -> str:
    """
    Encrypt *plaintext* string with AES-256-GCM.

    Wire format (base64url):
        [ 12-byte nonce ][ ciphertext ][ 16-byte GCM auth tag ]

    Returns a URL-safe base64 string safe to store in SQLite TEXT columns.
    """
    nonce      = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), associated_data)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str, key: bytes, associated_data: bytes | None = None) -> str:
    """
    Decrypt a token produced by encrypt().

    Raises:
        ValueError — wrong key, truncated data, or tampered ciphertext.
    """
    try:
        raw            = base64.urlsafe_b64decode(token.encode("ascii"))
        nonce, ct      = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
        plaintext_bytes = AESGCM(key).decrypt(nonce, ct, associated_data)
        return plaintext_bytes.decode("utf-8")
    except Exception as exc:
        raise ValueError("Decryption failed — wrong key or corrupted data") from exc


# ── Master Password ───────────────────────────────────────────────────────────

def has_master_password() -> bool:
    """Return True if a master password has been configured."""
    return os.path.exists(_VERIFY_FILE)


def save_master_password(password: str) -> None:
    """
    Set (or replace) the master password.

    Internally stores an encrypted verifier blob on disk.
    The raw password is *never* persisted — only the derived key is used
    to encrypt a known sentinel string.

    Raises:
        ValueError — if the new password fails the 12-character policy.
    """
    from core.security.passwords import validate_new_password
    validate_new_password(password)
    key   = derive_key(password)
    token = encrypt(_VERIFY_TOKEN, key)
    os.makedirs(_CFG_DIR, mode=0o700, exist_ok=True)
    write_verifier(token)


def write_verifier(token: str) -> None:
    """Atomically replace a verifier; never leave a truncated file on write failure."""
    import tempfile
    descriptor, temporary = tempfile.mkstemp(prefix=".verifier-", dir=_CFG_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(token)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, _VERIFY_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_password(password: str) -> bool:
    """
    Return True if *password* matches the stored master password.
    Always returns False if no master password is set.
    """
    if not has_master_password():
        return False
    try:
        with open(_VERIFY_FILE, encoding="ascii") as f:
            stored = f.read().strip()
        key    = derive_key(password)
        result = decrypt(stored, key)
        return result == _VERIFY_TOKEN
    except Exception:
        return False


def remove_master_password() -> None:
    """
    Remove master password and encryption salt.

    ⚠ WARNING: Any previously encrypted items in the DB will be
    unrecoverable after this call.  Caller is responsible for
    decrypting all items first.
    """
    for path in (_VERIFY_FILE, _SALT_FILE):
        if os.path.exists(path):
            os.remove(path)
