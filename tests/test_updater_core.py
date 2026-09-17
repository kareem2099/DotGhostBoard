import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch
from core.updater import (
    _parse_version,
    _classify_release,
    _release_matches_channel,
    _current_arch_tokens,
    check_for_updates,
    identify_platform_asset,
)

# ════════════════════════════════════════════
# Version Parsing Tests
# ════════════════════════════════════════════
def test_parse_version_valid():
    from packaging.version import Version
    v = _parse_version("v1.5.2")
    assert isinstance(v, Version)
    assert str(v) == "1.5.2"

def test_parse_version_no_v():
    v = _parse_version("1.5.2")
    assert str(v) == "1.5.2"

def test_parse_version_invalid():
    assert _parse_version("invalid-tag") is None

def test_parse_version_dash_beta():
    """v2.0.0-beta.2 must parse as a beta pre-release."""
    v = _parse_version("v2.0.0-beta.2")
    assert v is not None
    assert v.is_prerelease
    assert v.pre == ("b", 2)

def test_parse_version_dash_rc():
    """v2.0.0-rc.1 must parse as an rc pre-release."""
    v = _parse_version("v2.0.0-rc.1")
    assert v is not None
    assert v.pre == ("rc", 1)

def test_parse_version_dash_alpha():
    """v2.0.0-alpha.1 must parse as an alpha pre-release."""
    v = _parse_version("v2.0.0-alpha.1")
    assert v is not None
    assert v.pre == ("a", 1)


# ════════════════════════════════════════════
# Release Classification Tests
# ════════════════════════════════════════════

def test_classify_stable():
    from packaging.version import Version
    assert _classify_release(Version("2.0.0")) == "stable"

def test_classify_beta():
    from packaging.version import Version
    assert _classify_release(Version("2.0.0b1")) == "beta"

def test_classify_rc():
    from packaging.version import Version
    assert _classify_release(Version("2.0.0rc1")) == "rc"

def test_classify_alpha():
    from packaging.version import Version
    assert _classify_release(Version("2.0.0a1")) == "alpha"


# ════════════════════════════════════════════
# Channel Filter Tests
# ════════════════════════════════════════════

class TestStableChannel:
    def test_stable_accepts_stable(self):
        assert _release_matches_channel("stable", "stable") is True

    def test_stable_ignores_beta(self):
        assert _release_matches_channel("beta", "stable") is False

    def test_stable_ignores_rc(self):
        assert _release_matches_channel("rc", "stable") is False

    def test_stable_ignores_alpha(self):
        assert _release_matches_channel("alpha", "stable") is False


class TestBetaChannel:
    def test_beta_accepts_stable(self):
        assert _release_matches_channel("stable", "beta") is True

    def test_beta_accepts_beta(self):
        assert _release_matches_channel("beta", "beta") is True

    def test_beta_accepts_rc(self):
        assert _release_matches_channel("rc", "beta") is True

    def test_beta_ignores_alpha(self):
        assert _release_matches_channel("alpha", "beta") is False


class TestAlphaChannel:
    def test_alpha_accepts_stable(self):
        assert _release_matches_channel("stable", "alpha") is True

    def test_alpha_accepts_beta(self):
        assert _release_matches_channel("beta", "alpha") is True

    def test_alpha_accepts_rc(self):
        assert _release_matches_channel("rc", "alpha") is True

    def test_alpha_accepts_alpha(self):
        assert _release_matches_channel("alpha", "alpha") is True


# ════════════════════════════════════════════
# check_for_updates — Channel Matrix Tests
# ════════════════════════════════════════════

def _mock_releases(tags: list[str]):
    """Build a mocked urlopen that returns a JSON list of releases for the given tags."""
    releases = [
        {
            "tag_name": tag,
            "body": f"Notes for {tag}",
            "assets": [],
        }
        for tag in tags
    ]
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(releases).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


@patch("core.updater.urllib.request.urlopen")
def test_stable_ignores_beta_release(mock_urlopen):
    """Stable channel: only plain stable releases are returned."""
    mock_urlopen.return_value = _mock_releases(["v2.0.0-beta.1", "v2.0.0b1", "v1.9.0"])
    result = check_for_updates("v1.8.0", channel="stable")
    # v1.9.0 is stable and newer — should be returned
    assert result is not None
    assert result["version"] == "v1.9.0"


@patch("core.updater.urllib.request.urlopen")
def test_stable_ignores_alpha_and_rc(mock_urlopen):
    """Stable channel ignores alpha and rc tags even if they are the newest."""
    mock_urlopen.return_value = _mock_releases(["v2.1.0-alpha.1", "v2.0.0rc1", "v1.9.0"])
    result = check_for_updates("v1.8.0", channel="stable")
    assert result is not None
    assert result["version"] == "v1.9.0"


@patch("core.updater.urllib.request.urlopen")
def test_stable_no_update_when_only_prerelease_available(mock_urlopen):
    """Stable channel: no update if only pre-releases exist above current."""
    mock_urlopen.return_value = _mock_releases(["v2.0.0b1", "v2.0.0a1", "v2.0.0rc1"])
    result = check_for_updates("v1.9.0", channel="stable")
    assert result is None


@patch("core.updater.urllib.request.urlopen")
def test_beta_accepts_rc(mock_urlopen):
    """Beta channel: rc is accepted and preferred over stable if newer."""
    mock_urlopen.return_value = _mock_releases(["v2.0.0rc1", "v2.0.0b2", "v1.9.0"])
    result = check_for_updates("v1.9.0", channel="beta")
    assert result is not None
    assert result["version"] == "v2.0.0rc1"


@patch("core.updater.urllib.request.urlopen")
def test_beta_ignores_alpha(mock_urlopen):
    """Beta channel: alpha builds are hidden, rc/beta/stable are shown."""
    mock_urlopen.return_value = _mock_releases(["v2.1.0a1", "v2.0.0rc1"])
    result = check_for_updates("v1.9.0", channel="beta")
    assert result is not None
    assert result["version"] == "v2.0.0rc1"


@patch("core.updater.urllib.request.urlopen")
def test_alpha_accepts_all(mock_urlopen):
    """Alpha channel: picks the highest version regardless of release type."""
    mock_urlopen.return_value = _mock_releases(["v2.1.0a1", "v2.0.0rc1", "v2.0.0", "v1.9.0"])
    result = check_for_updates("v1.9.0", channel="alpha")
    assert result is not None
    assert result["version"] == "v2.1.0a1"


# ════════════════════════════════════════════
# No-Downgrade Guarantee Tests
# ════════════════════════════════════════════

@patch("core.updater.urllib.request.urlopen")
def test_stable_does_not_downgrade_from_beta_version(mock_urlopen):
    """
    User is on 2.1.0-beta.3 and switches to Stable channel.
    Latest stable is 2.0.0 — no downgrade should be offered.
    """
    mock_urlopen.return_value = _mock_releases(["v2.0.0", "v1.9.5"])
    # current version is a beta build above the available stable
    result = check_for_updates("v2.1.0b3", channel="stable")
    assert result is None


@patch("core.updater.urllib.request.urlopen")
def test_no_same_version_update(mock_urlopen):
    """Candidate equal to current must not be returned."""
    mock_urlopen.return_value = _mock_releases(["v2.0.0"])
    result = check_for_updates("v2.0.0", channel="stable")
    assert result is None


# ════════════════════════════════════════════
# Invalid / Unparseable Tag Tests
# ════════════════════════════════════════════

@patch("core.updater.urllib.request.urlopen")
def test_invalid_release_tags_are_silently_ignored(mock_urlopen):
    """
    Releases with unparseable tags (e.g. 'nightly-20240101', 'latest')
    must be skipped without raising an exception.
    """
    mock_urlopen.return_value = _mock_releases(
        ["nightly-20240101", "latest", "not-a-version", "v2.0.0"]
    )
    result = check_for_updates("v1.9.0", channel="stable")
    assert result is not None
    assert result["version"] == "v2.0.0"


@patch("core.updater.urllib.request.urlopen")
def test_all_invalid_tags_returns_none(mock_urlopen):
    """If every tag is invalid, return None gracefully."""
    mock_urlopen.return_value = _mock_releases(["nightly-X", "edge", "bad!!"])
    result = check_for_updates("v1.9.0", channel="stable")
    assert result is None


# ════════════════════════════════════════════
# Default Channel Tests
# ════════════════════════════════════════════

@patch("core.updater.urllib.request.urlopen")
def test_channel_defaults_to_stable(mock_urlopen):
    """check_for_updates with no channel argument behaves as stable channel."""
    mock_urlopen.return_value = _mock_releases(["v2.0.0b1", "v1.9.0"])
    result = check_for_updates("v1.8.0")  # no channel arg
    assert result is not None
    assert result["version"] == "v1.9.0"  # beta skipped, stable returned


def test_channel_default_in_settings():
    """Settings _DEFAULTS must include update_channel = 'stable'."""
    from ui.settings._io import _DEFAULTS
    assert "update_channel" in _DEFAULTS
    assert _DEFAULTS["update_channel"] == "stable"


@patch("core.updater.urllib.request.urlopen")
def test_network_error_returns_none(mock_urlopen):
    """Network failures must not raise — return None silently."""
    import urllib.error
    mock_urlopen.side_effect = urllib.error.URLError("timeout")
    result = check_for_updates("v1.9.0", channel="stable")
    assert result is None


# ════════════════════════════════════════════
# Version Comparison Tests (pre-existing)
# ════════════════════════════════════════════

@patch("core.updater.urllib.request.urlopen")
def test_check_for_updates_newer(mock_urlopen):
    mock_urlopen.return_value = _mock_releases(["v1.6.0"])
    result = check_for_updates("v1.5.2", channel="stable")
    assert result is not None
    assert result["version"] == "v1.6.0"

@patch("core.updater.urllib.request.urlopen")
def test_check_for_updates_older(mock_urlopen):
    mock_urlopen.return_value = _mock_releases(["v1.3.0"])
    result = check_for_updates("v1.5.2", channel="stable")
    assert result is None

def test_version_logic_v9_vs_v10():
    v9  = _parse_version("v1.9.0")
    v10 = _parse_version("v1.10.0")
    assert v10 > v9


# ════════════════════════════════════════════
# Architecture Detection Tests (pre-existing)
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
# Asset Identification Tests (pre-existing)
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
