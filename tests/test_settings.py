"""
tests/test_settings.py
──────────────────────
Unit tests for ui/settings.py helpers:
  - load_settings()
  - save_settings()
  - _DEFAULTS completeness

Run:
    pytest tests/test_settings.py -v
"""

import os
import json
import tempfile
import pytest

import ui.settings as settings_module


@pytest.fixture(autouse=True)
def tmp_settings_file(tmp_path):
    """Redirect SETTINGS_PATH to a fresh temp file for every test."""
    original = settings_module.SETTINGS_PATH
    settings_module.SETTINGS_PATH = str(tmp_path / "settings.json")
    yield settings_module.SETTINGS_PATH
    settings_module.SETTINGS_PATH = original


# ════════════════════════════════════════════
# _DEFAULTS
# ════════════════════════════════════════════
class TestDefaults:
    def test_required_keys_present(self):
        required = {"max_history", "max_captures", "theme", "clear_on_exit"}
        assert required.issubset(settings_module._DEFAULTS.keys())

    def test_default_max_history(self):
        assert settings_module._DEFAULTS["max_history"] == 200

    def test_default_max_captures(self):
        assert settings_module._DEFAULTS["max_captures"] == 100

    def test_default_theme(self):
        assert settings_module._DEFAULTS["theme"] == "dark"

    def test_default_clear_on_exit(self):
        assert settings_module._DEFAULTS["clear_on_exit"] is False


# ════════════════════════════════════════════
# load_settings
# ════════════════════════════════════════════
class TestLoadSettings:
    def test_returns_defaults_when_no_file(self):
        # File doesn't exist → should return defaults
        result = settings_module.load_settings()
        assert result == settings_module._DEFAULTS

    def test_reads_existing_file(self, tmp_settings_file):
        data = {"max_history": 50, "max_captures": 20,
                "theme": "dark", "clear_on_exit": True}
        with open(tmp_settings_file, "w") as f:
            json.dump(data, f)
        result = settings_module.load_settings()
        assert result["max_history"] == 50
        assert result["max_captures"] == 20
        assert result["clear_on_exit"] is True

    def test_merges_missing_keys_with_defaults(self, tmp_settings_file):
        """If settings file is missing keys, defaults fill in the gaps."""
        with open(tmp_settings_file, "w") as f:
            json.dump({"max_history": 300}, f)
        result = settings_module.load_settings()
        assert result["max_history"] == 300
        assert result["max_captures"] == 100   # from defaults
        assert result["theme"] == "dark"

    def test_survives_corrupt_json(self, tmp_settings_file):
        """Corrupt file should fall back to defaults, not crash."""
        with open(tmp_settings_file, "w") as f:
            f.write("{ this is not json }")
        result = settings_module.load_settings()
        assert result == settings_module._DEFAULTS


# ════════════════════════════════════════════
# save_settings
# ════════════════════════════════════════════
class TestSaveSettings:
    def test_writes_json_file(self, tmp_settings_file):
        data = {"max_history": 99, "max_captures": 50,
                "theme": "dark", "clear_on_exit": False}
        settings_module.save_settings(data)
        with open(tmp_settings_file) as f:
            on_disk = json.load(f)
        assert on_disk == data

    def test_creates_parent_dirs(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "settings.json")
        settings_module.SETTINGS_PATH = deep_path
        settings_module.save_settings({"max_history": 10, "max_captures": 5,
                                       "theme": "dark", "clear_on_exit": False})
        assert os.path.isfile(deep_path)

    def test_round_trip(self, tmp_settings_file):
        original = {"max_history": 123, "max_captures": 77,
                    "theme": "dark", "clear_on_exit": True}
        settings_module.save_settings(original)
        loaded = settings_module.load_settings()
        assert loaded["max_history"]  == 123
        assert loaded["max_captures"] == 77
        assert loaded["clear_on_exit"] is True
