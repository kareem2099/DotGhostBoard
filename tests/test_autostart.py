"""
tests/test_autostart.py — Tests for core/autostart.py
===================================================
Tests XDG Autostart resolution, XDG masking, target resolution,
exec line escaping, environment variables, permissions, and legacy migration.
"""

import os
import sys
import stat
import tempfile
import pytest
from unittest.mock import patch

from core.autostart import (
    format_exec_line,
    get_current_launch_command,
    get_autostart_state,
    enable_autostart,
    disable_autostart,
    migrate_legacy_entries,
    get_user_autostart_dir,
    get_user_autostart_file,
    get_system_autostart_files,
    AutostartResult,
)


def test_format_exec_line_simple():
    line = format_exec_line("/usr/bin/dotghostboard", ["--startup"])
    assert line == "/usr/bin/dotghostboard --startup"


def test_format_exec_line_with_spaces_and_quotes():
    binary = "/home/kareem/My Applications/DotGhostBoard.AppImage"
    line = format_exec_line(binary, ["--startup"])
    assert line == '"/home/kareem/My Applications/DotGhostBoard.AppImage" --startup'

    complex_arg = 'arg with "quotes" and spaces'
    line2 = format_exec_line("/bin/app", [complex_arg])
    assert line2 == '/bin/app "arg with \\"quotes\\" and spaces"'


def test_format_exec_line_percent_and_reserved_chars():
    # % must be escaped as %% in Desktop Entry Exec key
    line = format_exec_line("/opt/app%20dir/bin", ["--url=http://example.com/a%20b"])
    assert "app%%20dir" in line
    assert "a%%20b" in line

    # Reserved characters like #, ;, &, (, ), $, <, >, |, *, ' require quotes
    line2 = format_exec_line("/opt/my#app;(v1)&test/run")
    assert line2.startswith('"') and line2.endswith('"')
    assert "my#app;(v1)&test" in line2

    # Single quotes also require quoting the argument
    line3 = format_exec_line("/opt/kareem's_apps/dotghostboard")
    assert line3 == '"/opt/kareem\'s_apps/dotghostboard"'


def test_get_current_launch_command_appimage(tmp_path):
    fake_appimage = tmp_path / "App with spaces" / "DotGhostBoard.AppImage"
    fake_appimage.parent.mkdir(parents=True)
    fake_appimage.write_text("binary")

    with patch.dict(os.environ, {"APPIMAGE": str(fake_appimage)}):
        cmd, icon = get_current_launch_command()
        assert f'"{fake_appimage}" --startup' == cmd
        assert icon == "dotghostboard"


def test_get_current_launch_command_frozen(tmp_path):
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("APPIMAGE", None)
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", "/opt/dotghostboard/dotghostboard-app"):
            cmd, icon = get_current_launch_command()
            assert cmd == "/opt/dotghostboard/dotghostboard-app --startup"
            assert icon == "dotghostboard"


def test_get_current_launch_command_source():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("APPIMAGE", None)
        with patch.object(sys, "frozen", False, create=True):
            cmd, icon = get_current_launch_command()
            assert sys.executable in cmd
            assert "main.py" in cmd
            assert "--startup" in cmd


def test_get_autostart_state_none():
    res = get_autostart_state(user_file="/nonexistent/user.desktop", system_file="/nonexistent/sys.desktop")
    assert res.enabled is False
    assert res.source == "none"


def test_get_autostart_state_system_default(tmp_path):
    sys_file = tmp_path / "system.desktop"
    sys_file.write_text("[Desktop Entry]\nExec=/usr/bin/dotghostboard --startup\nHidden=false\n")

    res = get_autostart_state(user_file="/nonexistent/user.desktop", system_file=str(sys_file))
    assert res.enabled is True
    assert res.source == "system"


def test_get_autostart_state_user_enabled(tmp_path):
    user_file = tmp_path / "user.desktop"
    user_file.write_text("[Desktop Entry]\nExec=dotghostboard --startup\nHidden=false\n")

    res = get_autostart_state(user_file=str(user_file), system_file="/nonexistent/sys.desktop")
    assert res.enabled is True
    assert res.source == "user"


def test_xdg_masking_hidden_true(tmp_path):
    sys_file = tmp_path / "system.desktop"
    sys_file.write_text("[Desktop Entry]\nExec=/usr/bin/dotghostboard --startup\nHidden=false\n")

    user_file = tmp_path / "user.desktop"
    user_file.write_text("[Desktop Entry]\nHidden=true\n")

    res = get_autostart_state(user_file=str(user_file), system_file=str(sys_file))
    assert res.enabled is False
    assert res.source == "user_override"


def test_xdg_masking_gnome_disabled(tmp_path):
    sys_file = tmp_path / "system.desktop"
    sys_file.write_text("[Desktop Entry]\nExec=/usr/bin/dotghostboard --startup\n")

    user_file = tmp_path / "user.desktop"
    user_file.write_text("[Desktop Entry]\nX-GNOME-Autostart-enabled=false\n")

    res = get_autostart_state(user_file=str(user_file), system_file=str(sys_file))
    assert res.enabled is False
    assert res.source == "user_override"


def test_enable_autostart_creates_valid_entry(tmp_path):
    user_file = tmp_path / "dotghostboard.desktop"
    res = enable_autostart(user_file=str(user_file))
    assert res.enabled is True
    assert user_file.is_file()

    content = user_file.read_text()
    assert "Hidden=false" in content
    assert "X-GNOME-Autostart-Delay=2" in content
    assert "--startup" in content
    assert "X-GNOME-Autostart-enabled=true" in content

    # Check 0o644 permissions
    mode = stat.S_IMODE(user_file.stat().st_mode)
    assert mode == 0o644


def test_enable_autostart_with_command_and_icon_override(tmp_path):
    user_file = tmp_path / "dotghostboard.desktop"
    res = enable_autostart(
        user_file=str(user_file),
        command="/custom/bin/dotghostboard --startup",
        icon="my-custom-icon",
    )
    assert res.enabled is True
    content = user_file.read_text()
    assert "Exec=/custom/bin/dotghostboard --startup" in content
    assert "Icon=my-custom-icon" in content


def test_disable_autostart_without_system_entry(tmp_path):
    user_file = tmp_path / "dotghostboard.desktop"
    user_file.write_text("[Desktop Entry]\nHidden=false\n")

    res = disable_autostart(user_file=str(user_file), system_file="/nonexistent/sys.desktop")
    assert res.enabled is False
    assert not user_file.exists()


def test_disable_autostart_with_system_entry_masks(tmp_path):
    sys_file = tmp_path / "system.desktop"
    sys_file.write_text("[Desktop Entry]\nExec=/usr/bin/dotghostboard --startup\n")

    user_file = tmp_path / "dotghostboard.desktop"
    user_file.write_text("[Desktop Entry]\nHidden=false\n")

    res = disable_autostart(user_file=str(user_file), system_file=str(sys_file))
    assert res.enabled is False
    assert res.source == "user_override"
    assert user_file.is_file()

    content = user_file.read_text()
    assert "Hidden=true" in content
    assert "X-GNOME-Autostart-enabled=false" in content


def test_migrate_legacy_entries(tmp_path):
    legacy_file = tmp_path / "DotGhostBoard.desktop"
    legacy_file.write_text("legacy entry")

    unrelated_file = tmp_path / "other.desktop"
    unrelated_file.write_text("other entry")

    removed = migrate_legacy_entries(autostart_dir=str(tmp_path))
    assert str(legacy_file) in removed
    assert not legacy_file.exists()
    assert unrelated_file.exists()


def test_xdg_environment_variables(tmp_path):
    custom_config = tmp_path / "custom_config"
    custom_sys1 = tmp_path / "sys1"
    custom_sys2 = tmp_path / "sys2"

    with patch.dict(os.environ, {
        "XDG_CONFIG_HOME": str(custom_config),
        "XDG_CONFIG_DIRS": f"{custom_sys1}:{custom_sys2}",
    }):
        assert get_user_autostart_dir() == str(custom_config / "autostart")
        assert get_user_autostart_file() == str(custom_config / "autostart" / "dotghostboard.desktop")

        sys_files = get_system_autostart_files()
        assert str(custom_sys1 / "autostart" / "dotghostboard.desktop") in sys_files
        assert str(custom_sys2 / "autostart" / "dotghostboard.desktop") in sys_files

        # Put system file in the second XDG directory
        sys2_desktop = custom_sys2 / "autostart" / "dotghostboard.desktop"
        sys2_desktop.parent.mkdir(parents=True)
        sys2_desktop.write_text("[Desktop Entry]\nExec=/usr/bin/dotghostboard --startup\n")

        # Query state — should discover sys2 entry
        res = get_autostart_state()
        assert res.enabled is True
        assert res.source == "system"
        assert res.path == str(sys2_desktop)

        # Disable should mask into XDG_CONFIG_HOME
        dis_res = disable_autostart()
        assert dis_res.enabled is False
        assert dis_res.source == "user_override"
        user_file = custom_config / "autostart" / "dotghostboard.desktop"
        assert user_file.is_file()
        assert "Hidden=true" in user_file.read_text()
