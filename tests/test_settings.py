"""
tests/test_settings.py
──────────────────────
Unit tests for ui/settings helpers:
  - load_settings()
  - save_settings()
  - _DEFAULTS completeness

Run:
    pytest tests/test_settings.py -v
"""

import os
import json
import pytest

import ui.settings as settings_module
import ui.settings._io as _io_module


@pytest.fixture(autouse=True)
def tmp_settings_file(tmp_path):
    """Redirect SETTINGS_PATH to a fresh temp file for every test.

    Must patch _io_module.SETTINGS_PATH because load_settings() and
    save_settings() read from ui.settings._io, not from the facade.
    """
    new_path = str(tmp_path / "settings.json")
    original_io      = _io_module.SETTINGS_PATH
    original_facade  = settings_module.SETTINGS_PATH
    _io_module.SETTINGS_PATH     = new_path
    settings_module.SETTINGS_PATH = new_path
    yield new_path
    _io_module.SETTINGS_PATH     = original_io
    settings_module.SETTINGS_PATH = original_facade


# ════════════════════════════════════════════
# _DEFAULTS
# ════════════════════════════════════════════
class TestDefaults:
    def test_required_keys_present(self):
        required = {
            "max_history", "max_captures", "theme", "clear_on_exit",
            "api_enabled", "api_port", "api_token"
        }
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
        # File doesn't exist → should return defaults + generated values
        result = settings_module.load_settings()
        # Non-dynamic fields should match defaults
        for key in ["max_history", "max_captures", "theme", "clear_on_exit", "api_port"]:
            assert result[key] == settings_module._DEFAULTS[key]
        
        # Dynamic fields should be populated
        assert len(result["api_token"]) > 0
        assert len(result["node_id"]) > 0
        assert len(result["device_name"]) > 0

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
        assert result["max_history"] == settings_module._DEFAULTS["max_history"]
        assert len(result["api_token"]) > 0


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
        _io_module.SETTINGS_PATH     = deep_path
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


# ════════════════════════════════════════════
# Backward Compatibility & Facade Integrity
# ════════════════════════════════════════════
class TestBackwardCompatibility:
    def test_facade_all_exports(self):
        expected = [
            "SettingsDialog", "load_settings", "save_settings",
            "SETTINGS_PATH", "_DEFAULTS", "TagManagerDialog"
        ]
        for item in expected:
            assert hasattr(settings_module, item), f"Missing export: {item}"
            assert item in settings_module.__all__, f"{item} not in __all__"

    def test_package_module_identity(self):
        assert settings_module.__file__.endswith("__init__.py"), (
            f"Expected package __init__.py, got {settings_module.__file__}"
        )

    def test_tag_manager_dialog_export(self):
        from ui.tag_manager import TagManagerDialog as TM1
        from ui.settings import TagManagerDialog as TM2
        assert TM1 is TM2


# ════════════════════════════════════════════
# Direct _io Module Tests
# ════════════════════════════════════════════
class TestIOModuleDirect:
    def test_io_direct_imports(self):
        from ui.settings._io import load_settings, save_settings, SETTINGS_PATH, _DEFAULTS
        assert callable(load_settings)
        assert callable(save_settings)
        assert isinstance(_DEFAULTS, dict)
        assert isinstance(SETTINGS_PATH, str)

    def test_defaults_immutability(self):
        data = _io_module.load_settings()
        data["max_history"] = 99999
        assert _io_module._DEFAULTS["max_history"] == 200

    def test_preserves_dynamic_keys(self, tmp_settings_file):
        initial = {
            "api_token": "custom-token-xyz",
            "node_id": "node-123",
            "device_name": "dev-box",
        }
        _io_module.save_settings(initial)
        loaded = _io_module.load_settings()
        assert loaded["api_token"] == "custom-token-xyz"
        assert loaded["node_id"] == "node-123"
        assert loaded["device_name"] == "dev-box"


# ════════════════════════════════════════════
# AppFilterEditor Widget Tests
# ════════════════════════════════════════════
class TestAppFilterEditor:
    def test_app_filter_editor_modes(self, qapp):
        from ui.settings.pages.general import AppFilterEditor
        editor = AppFilterEditor(mode="whitelist", app_list=["firefox", "code"])
        assert editor.get_mode() == "whitelist"
        assert editor.get_app_list() == ["firefox", "code"]

        editor._mode_combo.setCurrentIndex(0)
        assert editor.get_mode() == "blacklist"

        editor._mode_combo.setCurrentIndex(1)
        assert editor.get_mode() == "whitelist"

    def test_app_filter_editor_add_remove(self, qapp):
        from ui.settings.pages.general import AppFilterEditor
        editor = AppFilterEditor(mode="whitelist", app_list=["firefox"])
        editor._app_input.setText("slack")
        editor._add_app()
        assert "slack" in editor.get_app_list()

        # Select first item and remove
        editor._app_list.setCurrentRow(0)
        editor._remove_selected()
        assert editor.get_app_list() == ["slack"]


# ════════════════════════════════════════════
# Settings Pages Tab Builders
# ════════════════════════════════════════════
class TestPageBuilders:
    def test_build_general_tab(self, qapp):
        from PyQt6.QtWidgets import QWidget
        from ui.settings.dialog import SettingsDialog
        from ui.settings.pages.general import build_general_tab

        dlg = SettingsDialog()
        tab = build_general_tab(dlg)
        assert isinstance(tab, QWidget)
        assert hasattr(dlg, "_max_history")
        assert hasattr(dlg, "_max_captures")
        assert hasattr(dlg, "_clear_on_exit")
        assert hasattr(dlg, "_theme")
        assert hasattr(dlg, "_auto_update")
        assert hasattr(dlg, "_autostart_chk")
        dlg.close()

    def test_build_security_tab(self, qapp):
        from PyQt6.QtWidgets import QWidget
        from ui.settings.dialog import SettingsDialog
        from ui.settings.pages.security import build_security_tab

        dlg = SettingsDialog()
        tab = build_security_tab(dlg)
        assert isinstance(tab, QWidget)
        assert hasattr(dlg, "_pw_status_lbl")
        assert hasattr(dlg, "_set_pw_btn")
        assert hasattr(dlg, "_rm_pw_btn")
        assert hasattr(dlg, "_auto_lock_spin")
        assert hasattr(dlg, "_stealth_check")
        assert hasattr(dlg, "_app_filter_editor")
        dlg.close()

    def test_build_api_tab(self, qapp):
        from PyQt6.QtWidgets import QWidget
        from ui.settings.dialog import SettingsDialog
        from ui.settings.pages.api import build_api_tab

        dlg = SettingsDialog()
        tab = build_api_tab(dlg)
        assert isinstance(tab, QWidget)
        assert hasattr(dlg, "_api_check")
        assert hasattr(dlg, "_api_port")
        assert hasattr(dlg, "_api_token_in")
        assert hasattr(dlg, "_device_name")
        dlg.close()

    def test_build_about_tab(self, qapp):
        from PyQt6.QtWidgets import QWidget
        from ui.settings.dialog import SettingsDialog
        from ui.settings.pages.about import build_about_tab

        dlg = SettingsDialog()
        tab = build_about_tab(dlg)
        assert isinstance(tab, QWidget)
        dlg.close()


# ════════════════════════════════════════════
# SettingsDialog Shell Tests
# ════════════════════════════════════════════
class TestSettingsDialogShell:
    def test_settings_dialog_tabs(self, qapp):
        from ui.settings.dialog import SettingsDialog
        dlg = SettingsDialog()
        assert dlg._tabs.count() == 4
        labels = [dlg._tabs.tabText(i) for i in range(4)]
        assert any("General" in l for l in labels)
        assert any("Eclipse" in l for l in labels)
        assert any("API" in l for l in labels)
        assert any("About" in l for l in labels)
        dlg.close()

    def test_settings_dialog_save_and_close(self, qapp, tmp_settings_file):
        from ui.settings.dialog import SettingsDialog
        dlg = SettingsDialog()
        dlg._max_history.setValue(789)
        dlg._clear_on_exit.setChecked(True)
        dlg._save_and_close()

        assert dlg.settings["max_history"] == 789
        assert dlg.settings["clear_on_exit"] is True

        loaded = settings_module.load_settings()
        assert loaded["max_history"] == 789
        assert loaded["clear_on_exit"] is True
        dlg.close()

    def test_settings_dialog_helpers(self, qapp):
        from ui.settings.dialog import SettingsDialog
        lbl = SettingsDialog._section_label("Test Section")
        assert lbl.text() == "Test Section"
        sep = SettingsDialog._hsep()
        assert sep is not None


# ════════════════════════════════════════════
# Security Page Helper Functions
# ════════════════════════════════════════════
class TestSecurityPageHelpers:
    def test_refresh_eclipse_pw_ui(self, qapp, monkeypatch):
        from ui.settings.dialog import SettingsDialog
        from ui.settings.pages.security import refresh_eclipse_pw_ui

        dlg = SettingsDialog()

        # Simulate password is set
        monkeypatch.setattr("core.crypto.has_master_password", lambda: True)
        refresh_eclipse_pw_ui(dlg)
        assert "SET" in dlg._pw_status_lbl.text()
        assert dlg._rm_pw_btn.isEnabled() is True
        assert "Change Password" in dlg._set_pw_btn.text()

        # Simulate password is not set
        monkeypatch.setattr("core.crypto.has_master_password", lambda: False)
        refresh_eclipse_pw_ui(dlg)
        assert "No master password" in dlg._pw_status_lbl.text()
        assert dlg._rm_pw_btn.isEnabled() is False
        assert "Set Password" in dlg._set_pw_btn.text()

        dlg.close()
