"""
tests/test_password_generator.py
─────────────────────────────────
Unit tests for password and token generation in ui/vault/secret_dialog.py (v2.1.0 Leviathan).
"""

import string
from ui.vault.secret_dialog import (
    _generate_password,
    _generate_token,
    _entropy_bits,
)


def test_generate_password_default():
    pwd = _generate_password()
    assert len(pwd) == 20
    assert any(c in string.ascii_uppercase for c in pwd)
    assert any(c in string.ascii_lowercase for c in pwd)
    assert any(c in string.digits for c in pwd)
    assert any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in pwd)


def test_generate_password_custom_length():
    pwd_short = _generate_password(length=8)
    assert len(pwd_short) == 8

    pwd_long = _generate_password(length=64)
    assert len(pwd_long) == 64


def test_generate_password_digits_only():
    pwd = _generate_password(length=12, upper=False, lower=False, digits=True, symbols=False)
    assert len(pwd) == 12
    assert all(c in string.digits for c in pwd)


def test_generate_password_fallback_when_all_false():
    # When everything is disabled, falls back safely to letters + digits
    pwd = _generate_password(length=16, upper=False, lower=False, digits=False, symbols=False)
    assert len(pwd) == 16
    assert all(c in string.ascii_letters + string.digits for c in pwd)


def test_generate_token_formats():
    hex_token = _generate_token("hex", length=32)
    assert len(hex_token) == 32
    int(hex_token, 16)  # valid hex

    uuid_token = _generate_token("uuid4")
    assert len(uuid_token) == 36
    assert uuid_token.count("-") == 4

    bearer_token = _generate_token("bearer", length=24)
    assert bearer_token.startswith("Bearer ")

    b64_token = _generate_token("base64", length=16)
    assert isinstance(b64_token, str)
    assert len(b64_token) > 0


def test_entropy_bits_calculation():
    assert _entropy_bits("") == 0.0
    bits_simple = _entropy_bits("password")
    bits_complex = _entropy_bits("tn)eT2sabF*P#hbRb")
    assert bits_complex > bits_simple
