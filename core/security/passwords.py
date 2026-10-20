"""Versioned, bounded password KDF profiles shared by independent Vaults and backups."""

import base64
import os
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

MIN_PASSWORD_LENGTH = 12
ARGON_MEMORY_KIB = 65536
ARGON_ITERATIONS = 3
ARGON_LANES = 1


def validate_new_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("Use a password or passphrase of at least 12 characters.")
    if not password.strip():
        raise ValueError("Password cannot consist only of spaces.")


def new_kdf_config() -> dict:
    return {
        "algorithm": "argon2id", "memory_kib": ARGON_MEMORY_KIB,
        "iterations": ARGON_ITERATIONS, "lanes": ARGON_LANES,
        "salt": base64.b64encode(os.urandom(16)).decode("ascii"),
    }


def derive_password_key(password: str, config: dict) -> bytes:
    # Only known profiles are accepted; edited files cannot request unbounded RAM/CPU.
    if (config.get("algorithm"), config.get("memory_kib"), config.get("iterations"), config.get("lanes")) != (
        "argon2id", ARGON_MEMORY_KIB, ARGON_ITERATIONS, ARGON_LANES,
    ):
        raise ValueError("Unsupported password KDF profile.")
    salt = base64.b64decode(config["salt"], validate=True)
    if len(salt) != 16:
        raise ValueError("Invalid password KDF salt.")
    return Argon2id(salt=salt, length=32, iterations=ARGON_ITERATIONS,
                    lanes=ARGON_LANES, memory_cost=ARGON_MEMORY_KIB).derive(password.encode("utf-8"))
