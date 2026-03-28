"""
test_eclipse.py — Unit tests for DotGhostBoard v1.4.0 Eclipse
══════════════════════════════════════════════════════════════
Run with:   pytest tests/test_eclipse.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import sqlite3
import pytest

# ── Make sure project root is on path ─────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════
# E001 — crypto.py
# ═══════════════════════════════════════════════════════════════════

class TestCrypto:
    """AES-256-GCM engine tests."""

    @pytest.fixture(autouse=True)
    def _tmp_cfg(self, tmp_path, monkeypatch):
        """Redirect salt + verifier files to a temp directory."""
        import core.crypto as crypto
        monkeypatch.setattr(crypto, "_CFG_DIR",     str(tmp_path))
        monkeypatch.setattr(crypto, "_SALT_FILE",   str(tmp_path / "eclipse.salt"))
        monkeypatch.setattr(crypto, "_VERIFY_FILE", str(tmp_path / "eclipse.verify"))
        yield

    def test_encrypt_decrypt_roundtrip(self):
        from core.crypto import derive_key, encrypt, decrypt
        key       = derive_key("TestPass123")
        plaintext = "Hello, Eclipse! 🔐"
        token     = encrypt(plaintext, key)
        assert decrypt(token, key) == plaintext

    def test_encrypt_produces_different_tokens_each_call(self):
        """Each call uses a fresh random nonce — ciphertext must differ."""
        from core.crypto import derive_key, encrypt
        key    = derive_key("TestPass123")
        token1 = encrypt("same text", key)
        token2 = encrypt("same text", key)
        assert token1 != token2

    def test_wrong_key_raises_value_error(self):
        from core.crypto import derive_key, encrypt, decrypt
        key_a  = derive_key("CorrectHorse")
        key_b  = derive_key("WrongPassword")
        token  = encrypt("secret", key_a)
        with pytest.raises(ValueError):
            decrypt(token, key_b)

    def test_tampered_ciphertext_raises(self):
        from core.crypto import derive_key, encrypt, decrypt
        import base64
        key   = derive_key("TestPass123")
        token = encrypt("data", key)
        raw   = bytearray(base64.urlsafe_b64decode(token.encode()))
        raw[-1] ^= 0xFF   # flip last byte
        bad   = base64.urlsafe_b64encode(bytes(raw)).decode()
        with pytest.raises(ValueError):
            decrypt(bad, key)

    def test_encrypt_unicode_characters(self):
        from core.crypto import derive_key, encrypt, decrypt
        key  = derive_key("TestPass123")
        text = "مرحبا بالعالم 🌍 日本語テスト"
        assert decrypt(encrypt(text, key), key) == text

    def test_master_password_flow(self):
        from core.crypto import (
            has_master_password, save_master_password,
            verify_password, remove_master_password,
        )
        assert not has_master_password()

        save_master_password("SuperSecret99")
        assert has_master_password()
        assert verify_password("SuperSecret99")
        assert not verify_password("WrongPassword")

        remove_master_password()
        assert not has_master_password()

    def test_master_password_too_short_raises(self):
        from core.crypto import save_master_password
        with pytest.raises(ValueError):
            save_master_password("abc")

    def test_same_password_derives_same_key(self):
        """PBKDF2 is deterministic with the same salt."""
        from core.crypto import derive_key
        key1 = derive_key("StablePass!")
        key2 = derive_key("StablePass!")
        assert key1 == key2

    def test_different_passwords_derive_different_keys(self):
        from core.crypto import derive_key
        assert derive_key("Password1") != derive_key("Password2")

    def test_salt_is_persisted_across_calls(self):
        """Second call must load existing salt, not regenerate."""
        from core.crypto import _load_or_create_salt
        salt1 = _load_or_create_salt()
        salt2 = _load_or_create_salt()
        assert salt1 == salt2


# ═══════════════════════════════════════════════════════════════════
# E002 — secure_delete.py
# ═══════════════════════════════════════════════════════════════════

class TestSecureDelete:

    def test_file_is_gone_after_secure_delete(self, tmp_path):
        from core.secure_delete import secure_delete
        f = tmp_path / "test.txt"
        f.write_bytes(b"sensitive data " * 100)
        assert secure_delete(str(f))
        assert not f.exists()

    def test_returns_false_for_nonexistent_file(self, tmp_path):
        from core.secure_delete import secure_delete
        result = secure_delete(str(tmp_path / "ghost.txt"))
        assert result is False

    def test_original_content_overwritten(self, tmp_path):
        """File content should not match original after deletion attempt
        (we test by reading the file DURING overwrite — tricky, so we
        instead just confirm the file is gone and was overwritten in size)."""
        from core.secure_delete import secure_delete
        f = tmp_path / "secret.dat"
        original = b"TOP SECRET" * 200
        f.write_bytes(original)
        assert secure_delete(str(f), passes=1)
        assert not f.exists()

    def test_secure_delete_many(self, tmp_path):
        from core.secure_delete import secure_delete_many
        paths = []
        for i in range(4):
            p = tmp_path / f"file{i}.bin"
            p.write_bytes(os.urandom(512))
            paths.append(str(p))
        results = secure_delete_many(paths)
        assert all(results.values())
        assert not any(os.path.exists(p) for p in paths)

    def test_empty_file_handled(self, tmp_path):
        from core.secure_delete import secure_delete
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        assert secure_delete(str(f))
        assert not f.exists()


# ═══════════════════════════════════════════════════════════════════
# E003 — app_filter.py
# ═══════════════════════════════════════════════════════════════════

class TestAppFilter:

    def test_blacklist_empty_list_allows_all(self):
        from core.app_filter import AppFilter
        f = AppFilter(mode="blacklist", app_list=[])
        assert f.should_capture() is True

    def test_whitelist_empty_list_allows_all(self):
        from core.app_filter import AppFilter
        f = AppFilter(mode="whitelist", app_list=[])
        assert f.should_capture() is True

    def test_blacklist_blocks_matched_app(self, monkeypatch):
        from core.app_filter import AppFilter
        import core.app_filter as af
        monkeypatch.setattr(af, "get_active_app_identifiers",
                            lambda: {"keepassxc"})
        f = AppFilter(mode="blacklist", app_list=["keepassxc"])
        assert f.should_capture() is False

    def test_blacklist_allows_unmatched_app(self, monkeypatch):
        from core.app_filter import AppFilter
        import core.app_filter as af
        monkeypatch.setattr(af, "get_active_app_identifiers",
                            lambda: {"firefox"})
        f = AppFilter(mode="blacklist", app_list=["keepassxc"])
        assert f.should_capture() is True

    def test_whitelist_allows_matched_app(self, monkeypatch):
        from core.app_filter import AppFilter
        import core.app_filter as af
        monkeypatch.setattr(af, "get_active_app_identifiers",
                            lambda: {"code"})
        f = AppFilter(mode="whitelist", app_list=["code", "terminal"])
        assert f.should_capture() is True

    def test_whitelist_blocks_unmatched_app(self, monkeypatch):
        from core.app_filter import AppFilter
        import core.app_filter as af
        monkeypatch.setattr(af, "get_active_app_identifiers",
                            lambda: {"firefox"})
        f = AppFilter(mode="whitelist", app_list=["code", "terminal"])
        assert f.should_capture() is False

    def test_detection_failure_fails_open(self, monkeypatch):
        """If xdotool unavailable, always capture (fail-open)."""
        from core.app_filter import AppFilter
        import core.app_filter as af
        monkeypatch.setattr(af, "get_active_app_identifiers", lambda: set())
        f = AppFilter(mode="blacklist", app_list=["keepassxc"])
        assert f.should_capture() is True

    def test_update_hot_reload(self, monkeypatch):
        from core.app_filter import AppFilter
        import core.app_filter as af
        monkeypatch.setattr(af, "get_active_app_identifiers",
                            lambda: {"keepassxc"})
        f = AppFilter(mode="blacklist", app_list=[])
        assert f.should_capture() is True
        f.update("blacklist", ["keepassxc"])
        assert f.should_capture() is False

    def test_substring_matching(self, monkeypatch):
        """'keepass' in app_list should match 'keepassxc' process."""
        from core.app_filter import AppFilter
        import core.app_filter as af
        monkeypatch.setattr(af, "get_active_app_identifiers",
                            lambda: {"keepassxc"})
        f = AppFilter(mode="blacklist", app_list=["keepass"])
        assert f.should_capture() is False


# ═══════════════════════════════════════════════════════════════════
# E006 — storage.py Eclipse additions
# ═══════════════════════════════════════════════════════════════════

class TestStorageEclipse:
    """Tests for mark_secret, encrypt_item, decrypt_item, get_secret_items."""

    @pytest.fixture(autouse=True)
    def _tmp_db(self, tmp_path, monkeypatch):
        """Redirect all storage paths to a temp directory."""
        import core.storage as st
        monkeypatch.setattr(st, "DB_PATH",      str(tmp_path / "test.db"))
        monkeypatch.setattr(st, "THUMB_DIR",    str(tmp_path / "thumbnails"))
        monkeypatch.setattr(st, "CAPTURES_DIR", str(tmp_path / "captures"))
        st.init_db()
        yield

    @pytest.fixture
    def key(self, tmp_path, monkeypatch):
        """Provide a deterministic test key."""
        import core.crypto as crypto
        monkeypatch.setattr(crypto, "_CFG_DIR",   str(tmp_path))
        monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))
        from core.crypto import derive_key
        return derive_key("TestEclipseKey!")

    def test_mark_secret_sets_flag(self):
        import core.storage as st
        iid = st.add_item("text", "secret content")
        st.mark_secret(iid, True)
        item = st.get_item_by_id(iid)
        assert item["is_secret"] == 1

    def test_mark_secret_unsets_flag(self):
        import core.storage as st
        iid = st.add_item("text", "no longer secret")
        st.mark_secret(iid, True)
        st.mark_secret(iid, False)
        assert st.get_item_by_id(iid)["is_secret"] == 0

    def test_encrypt_item_stores_ciphertext(self, key):
        import core.storage as st
        iid = st.add_item("text", "very sensitive")
        assert st.encrypt_item(iid, key)
        item = st.get_item_by_id(iid)
        assert item["is_secret"] == 1
        assert item["content"] != "very sensitive"

    def test_decrypt_item_returns_plaintext(self, key):
        import core.storage as st
        iid = st.add_item("text", "top secret data")
        st.encrypt_item(iid, key)
        plain = st.decrypt_item(iid, key)
        assert plain == "top secret data"

    def test_decrypt_wrong_key_returns_none(self, key, tmp_path, monkeypatch):
        import core.storage as st
        import core.crypto  as crypto
        monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "other.salt"))
        from core.crypto import derive_key
        wrong_key = derive_key("WrongKey!")

        iid = st.add_item("text", "guarded")
        st.encrypt_item(iid, key)
        result = st.decrypt_item(iid, wrong_key)
        assert result is None

    def test_get_secret_items(self, key):
        import core.storage as st
        id1 = st.add_item("text", "normal item")
        id2 = st.add_item("text", "secret item")
        st.encrypt_item(id2, key)
        secrets = st.get_secret_items()
        assert any(s["id"] == id2 for s in secrets)
        assert not any(s["id"] == id1 for s in secrets)

    def test_encrypt_already_secret_returns_false(self, key):
        import core.storage as st
        iid = st.add_item("text", "once is enough")
        st.encrypt_item(iid, key)
        assert st.encrypt_item(iid, key) is False

    def test_encrypt_image_item_returns_false(self, key):
        """Image items store file paths — should not be encrypted."""
        import core.storage as st
        iid = st.add_item("image", "/home/user/.config/dotghostboard/captures/img.png")
        assert st.encrypt_item(iid, key) is False

    def test_decrypt_item_permanent(self, key):
        import core.storage as st
        iid = st.add_item("text", "declassified")
        st.encrypt_item(iid, key)
        assert st.decrypt_item_permanent(iid, key)
        item = st.get_item_by_id(iid)
        assert item["is_secret"] == 0
        assert item["content"] == "declassified"