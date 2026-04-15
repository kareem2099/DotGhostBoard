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
    os.makedirs(_CFG_DIR, exist_ok=True)
    if os.path.exists(_SALT_FILE):
        with open(_SALT_FILE, "rb") as f:
            data = f.read()
        if len(data) == 32:
            return data
    # Generate fresh 256-bit salt
    salt = os.urandom(32)
    with open(_SALT_FILE, "wb") as f:
        f.write(salt)
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


# ── AES-256-GCM ───────────────────────────────────────────────────────────────

def encrypt(plaintext: str, key: bytes) -> str:
    """
    Encrypt *plaintext* string with AES-256-GCM.

    Wire format (base64url):
        [ 12-byte nonce ][ ciphertext ][ 16-byte GCM auth tag ]

    Returns a URL-safe base64 string safe to store in SQLite TEXT columns.
    """
    nonce      = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str, key: bytes) -> str:
    """
    Decrypt a token produced by encrypt().

    Raises:
        ValueError — wrong key, truncated data, or tampered ciphertext.
    """
    try:
        raw            = base64.urlsafe_b64decode(token.encode("ascii"))
        nonce, ct      = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
        plaintext_bytes = AESGCM(key).decrypt(nonce, ct, None)
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
        ValueError — if password is shorter than 6 characters.
    """
    password = password.strip()
    if len(password) < 6:
        raise ValueError("Master password must be at least 6 characters.")
    key   = derive_key(password)
    token = encrypt(_VERIFY_TOKEN, key)
    os.makedirs(_CFG_DIR, exist_ok=True)
    with open(_VERIFY_FILE, "w", encoding="ascii") as f:
        f.write(token)


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