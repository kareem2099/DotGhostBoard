import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from core.updater import (
    _parse_version,
    _current_arch_tokens,
    check_for_updates,
    identify_platform_asset
)

# ════════════════════════════════════════════
# Version Parsing Tests
# ════════════════════════════════════════════
def test_parse_version_valid():
    from packaging.version import Version
    v = _parse_version("v1.5.0")
    assert isinstance(v, Version)
    assert str(v) == "1.5.0"

def test_parse_version_no_v():
    v = _parse_version("1.5.0")
    assert str(v) == "1.5.0"

def test_parse_version_invalid():
    assert _parse_version("invalid-tag") is None


# ════════════════════════════════════════════
# Version Comparison Tests
# ════════════════════════════════════════════
@patch("core.updater.urllib.request.urlopen")
def test_check_for_updates_newer(mock_urlopen):
    # Mocking a response with v1.6.0 when current is v1.5.0
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"tag_name": "v1.6.0", "body": "New features", "assets": []}'
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = check_for_updates("v1.5.0")
    assert result is not None
    assert result["version"] == "v1.6.0"

@patch("core.updater.urllib.request.urlopen")
def test_check_for_updates_older(mock_urlopen):
    # Mocking v1.3.0 when current is v1.5.0 (no update expected)
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"tag_name": "v1.3.0", "body": "Old", "assets": []}'
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = check_for_updates("v1.5.0")
    assert result is None

def test_version_logic_v9_vs_v10():
    # Semantic check: 1.10.0 > 1.9.0
    v9 = _parse_version("v1.9.0")
    v10 = _parse_version("v1.10.0")
    assert v10 > v9


# ════════════════════════════════════════════
# Architecture Detection Tests
# ════════════════════════════════════════════
@patch("platform.machine")
def test_arch_tokens_x86(mock_machine):
    mock_machine.return_value = "x86_64"
    tokens = _current_arch_tokens()
    assert "x86_64" in tokens
    assert "amd64" in tokens

@patch("platform.machine")
def test_arch_tokens_arm(mock_machine):
    mock_machine.return_value = "aarch64"
    tokens = _current_arch_tokens()
    assert "arm64" in tokens
    assert "aarch64" in tokens


# ════════════════════════════════════════════
# Asset Identification Tests
# ════════════════════════════════════════════
@patch("platform.machine")
@patch.dict(os.environ, {"APPIMAGE": "/path/to/app.AppImage"})
def test_identify_asset_appimage_arm64(mock_machine):
    mock_machine.return_value = "aarch64"
    with patch("sys.platform", "linux"):
        assets = [
            {"name": "DotGhostBoard-x86_64.AppImage", "browser_download_url": "https://test.com/DotGhostBoard-x86_64.AppImage"},
            {"name": "DotGhostBoard-arm64.AppImage",  "browser_download_url": "https://test.com/DotGhostBoard-arm64.AppImage"},
            {"name": "DotGhostBoard.deb",             "browser_download_url": "https://test.com/DotGhostBoard.deb"},
        ]
        # Should pick the arm64 AppImage
        url = identify_platform_asset(assets, strict_arch=True)
        assert url == "https://test.com/DotGhostBoard-arm64.AppImage"

@patch("platform.machine")
@patch.dict(os.environ, {"APPIMAGE": ""})
def test_identify_asset_deb_fallback(mock_machine):
    mock_machine.return_value = "x86_64"
    with patch("sys.platform", "linux"):
        assets = [
            {"name": "DotGhostBoard.deb", "browser_download_url": "https://test.com/DotGhostBoard.deb"},
        ]
        # No APPIMAGE env means we look for .deb
        url = identify_platform_asset(assets)
        assert url == "https://test.com/DotGhostBoard.deb"

@patch("platform.machine")
def test_identify_asset_windows(mock_machine):
    mock_machine.return_value = "x86_64"
    with patch("sys.platform", "win32"):
        assets = [
            {"name": "DotGhostBoard-Setup.exe", "browser_download_url": "https://test.com/DotGhostBoard-Setup.exe"},
        ]
        url = identify_platform_asset(assets)
        assert url == "https://test.com/DotGhostBoard-Setup.exe"
