"""
tests/test_auto_tagger.py
─────────────────────────
Unit tests for core/security/auto_tagger.py (v2.1.0 Leviathan).
"""

from unittest.mock import patch
from core.security.auto_tagger import detect_tags, apply_auto_tags, _entropy_bits


def test_detect_tags_empty_or_invalid():
    assert detect_tags("") == []
    assert detect_tags("   ") == []
    assert detect_tags(None) == []  # type: ignore[arg-type]
    assert detect_tags(12345) == []  # type: ignore[arg-type]


def test_detect_tags_url():
    tags = detect_tags("Check out https://github.com/kareem2099/DotGhostBoard for updates!")
    assert "#link" in tags

    tags_ftp = detect_tags("ftp://mirror.dotsuite.org/repo")
    assert "#link" in tags_ftp


def test_detect_tags_email():
    tags = detect_tags("Send an email to contact@dotsuite.org or developer@kali.org")
    assert "#email" in tags


def test_detect_tags_ip_addresses():
    tags_v4 = detect_tags("Server running at 192.168.1.100 port 8080")
    assert "#ip" in tags_v4

    tags_v6 = detect_tags("Target host: 2001:0db8:85a3:0000:0000:8a2e:0370:7334")
    assert "#ip" in tags_v6


def test_detect_tags_path():
    tags = detect_tags("/home/kareem/StudioProjects/DotGhostBoard/main.py")
    assert "#path" in tags


def test_detect_tags_hash():
    tags = detect_tags("MD5 checksum: 5d41402abc4b2a76b9719d911017c592")
    assert "#hash" in tags

    sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    tags_sha = detect_tags(f"SHA-256: {sha256}")
    assert "#hash" in tags_sha


def test_detect_tags_secrets():
    # GitHub PAT
    assert "#secret" in detect_tags("ghp_1234567890abcdefghijklmnopqrstuvwxyz")
    # AWS Key
    assert "#secret" in detect_tags("AWS key is AKIAIOSFODNN7EXAMPLE")
    # High-entropy token
    high_entropy = "tn)eT2sabF*P#hbRb" + "XYZ123456"
    assert "#secret" in detect_tags(high_entropy)


def test_detect_tags_json():
    valid_json = '{"name": "DotGhostBoard", "version": "2.1.0", "active": true}'
    tags = detect_tags(valid_json)
    assert "#json" in tags

    invalid_json = '{"broken": json without closing'
    tags_broken = detect_tags(invalid_json)
    assert "#json" not in tags_broken


def test_detect_tags_code():
    code_snippet = (
        "def compute_hash(data: str) -> str:\n"
        "    import hashlib\n"
        "    return hashlib.sha256(data.encode()).hexdigest()\n"
    )
    tags = detect_tags(code_snippet)
    assert "#code" in tags


def test_entropy_bits():
    assert _entropy_bits("") == 0.0
    low = _entropy_bits("aaaa")
    high = _entropy_bits("aB3!zY9@qW2#")
    assert high > low


def test_apply_auto_tags_storage_integration():
    with patch("core.storage.get_tags") as mock_get, patch("core.storage.add_tag") as mock_add:
        mock_get.return_value = ["#manual"]

        added = apply_auto_tags(42, "https://github.com/kareem2099/DotGhostBoard")
        assert "#link" in added
        assert any(call.args == (42, "#link") for call in mock_add.call_args_list)

        # If tag already exists, do not duplicate
        mock_get.return_value = ["#link", "#secret", "#path"]
        added_again = apply_auto_tags(42, "https://github.com/kareem2099/DotGhostBoard")
        assert added_again == []
