"""
core/autostart.py — Strict XDG Autostart & Execution Target Manager
===================================================================
Handles autostart configuration across all distribution formats:
- .deb & .pkg.tar.zst (system installations)
- AppImage (portable single-file executable)
- Portable tarball
- Development / source execution

Adheres strictly to the Freedesktop XDG Desktop Entry Specification:
- Dynamic XDG resolution: respects $XDG_CONFIG_HOME and $XDG_CONFIG_DIRS
- Unified Desktop ID: dotghostboard.desktop
- XDG Masking: writes Hidden=true to user autostart if system autostart exists
- Execution target priority: APPIMAGE -> sys.frozen -> sys.executable -> fallback
- Desktop Entry Exec string escaping (% -> %%, quotes, reserved characters)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

DESKTOP_ID = "dotghostboard.desktop"
LEGACY_FILENAMES = ["DotGhostBoard.desktop"]


@dataclass
class AutostartResult:
    """Represents the outcome or current status of an autostart operation."""
    enabled: bool
    source: str       # "user", "system", "user_override", "none"
    path: str
    message: str = ""


def get_user_autostart_dir() -> str:
    """Return the user autostart directory per XDG Base Directory Specification."""
    config_home = os.environ.get("XDG_CONFIG_HOME", "").strip() or os.path.expanduser("~/.config")
    return os.path.join(config_home, "autostart")


def get_user_autostart_file() -> str:
    """Return the full path to the user's autostart desktop file."""
    return os.path.join(get_user_autostart_dir(), DESKTOP_ID)


def get_system_autostart_files() -> list[str]:
    """Return all potential system-wide autostart paths parsed from XDG_CONFIG_DIRS."""
    dirs_env = os.environ.get("XDG_CONFIG_DIRS", "").strip() or "/etc/xdg"
    system_dirs = [d.strip() for d in dirs_env.split(":") if d.strip()]
    return [os.path.join(d, "autostart", DESKTOP_ID) for d in system_dirs]


# Compatibility aliases for callers
DEFAULT_USER_AUTOSTART_DIR = get_user_autostart_dir()
DEFAULT_USER_AUTOSTART_FILE = get_user_autostart_file()
DEFAULT_SYSTEM_AUTOSTART_FILE = "/etc/xdg/autostart/dotghostboard.desktop"


def _escape_exec_arg(arg: str) -> str:
    """Escape an argument according to Freedesktop Desktop Entry Exec key rules.

    - Literal '%' is a field-code prefix and must be escaped as '%%'
    - Double quotes '"' and backslashes '\\' are escaped
    - Reserved characters or whitespace necessitate quoting the entire argument
    """
    if not arg:
        return '""'
    escaped = arg.replace("%", "%%")
    needs_quotes = any(c in escaped for c in " \t\n\r\"'\\$`#;&()|*?~<>")
    if needs_quotes:
        escaped = escaped.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return escaped


def format_exec_line(binary_path: str, args: list[str] | None = None) -> str:
    """Format a binary path and its arguments for a Desktop Entry Exec line."""
    parts = [_escape_exec_arg(binary_path)]
    if args:
        parts.extend(_escape_exec_arg(a) for a in args)
    return " ".join(parts)


def get_current_launch_command() -> tuple[str, str]:
    """Determine the launch command and icon for the current runtime context.

    Hierarchy:
    1. APPIMAGE environment variable (AppImage portable execution)
    2. sys.frozen: PyInstaller binary (sys.executable)
    3. Source / Dev: sys.executable (running python interpreter) + main.py
    4. Fallback: /usr/bin/dotghostboard
    """
    # 1. AppImage
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path and os.path.isfile(appimage_path):
        return format_exec_line(appimage_path, ["--startup"]), "dotghostboard"

    # 2. Frozen binary (PyInstaller)
    if getattr(sys, "frozen", False):
        return format_exec_line(sys.executable, ["--startup"]), "dotghostboard"

    # 3. Running from source
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_py = os.path.join(project_dir, "main.py")
    icon_path = os.path.join(project_dir, "data", "icons", "icon.png")

    if os.path.isfile(main_py):
        icon = icon_path if os.path.isfile(icon_path) else "dotghostboard"
        return format_exec_line(sys.executable, [main_py, "--startup"]), icon

    # 4. Fallback to system installation if present
    if os.path.isfile("/usr/bin/dotghostboard"):
        return format_exec_line("/usr/bin/dotghostboard", ["--startup"]), "dotghostboard"

    return format_exec_line("dotghostboard", ["--startup"]), "dotghostboard"


def _is_file_hidden(path: str) -> bool:
    """Parse desktop file to check if Hidden=true or X-GNOME-Autostart-enabled=false."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                lower = stripped.lower()
                if lower == "hidden=true":
                    return True
                if lower == "x-gnome-autostart-enabled=false":
                    return True
    except OSError:
        pass
    return False


def get_autostart_state(
    user_file: str | None = None,
    system_file: str | None = None,
    system_files: list[str] | None = None,
) -> AutostartResult:
    """Query current autostart state considering user overrides and XDG system defaults."""
    u_file = user_file or get_user_autostart_file()

    # 1. User override check
    if os.path.isfile(u_file):
        if _is_file_hidden(u_file):
            return AutostartResult(
                enabled=False,
                source="user_override",
                path=u_file,
                message="Autostart masked by user override (Hidden=true)",
            )
        return AutostartResult(
            enabled=True,
            source="user",
            path=u_file,
            message="Autostart enabled via user configuration",
        )

    # 2. System-wide default check (searches all dirs in XDG_CONFIG_DIRS)
    s_files = [system_file] if system_file else (system_files or get_system_autostart_files())
    for s_file in s_files:
        if os.path.isfile(s_file):
            if _is_file_hidden(s_file):
                return AutostartResult(
                    enabled=False,
                    source="system",
                    path=s_file,
                    message="System-wide autostart is hidden",
                )
            return AutostartResult(
                enabled=True,
                source="system",
                path=s_file,
                message=f"Autostart enabled via system package ({s_file})",
            )

    return AutostartResult(
        enabled=False,
        source="none",
        path="",
        message="Autostart is not configured",
    )


def is_autostart_enabled(
    user_file: str | None = None,
    system_file: str | None = None,
    system_files: list[str] | None = None,
) -> bool:
    """Convenience helper returning True if autostart is active."""
    return get_autostart_state(user_file, system_file, system_files).enabled


def enable_autostart(
    user_file: str | None = None,
    command: str | None = None,
    icon: str | None = None,
) -> AutostartResult:
    """Enable autostart for the current user pointing to the active or specified runtime."""
    u_file = user_file or get_user_autostart_file()
    u_dir = os.path.dirname(u_file)

    migrate_legacy_entries(u_dir)

    if command is not None:
        exec_cmd = command
        icon_path = icon or "dotghostboard"
    else:
        exec_cmd, icon_path = get_current_launch_command()
        if icon is not None:
            icon_path = icon

    content = f"""[Desktop Entry]
Type=Application
Name=DotGhostBoard
GenericName=Clipboard Manager
Comment=Advanced clipboard manager — DotSuite
Exec={exec_cmd}
Icon={icon_path}
Categories=Utility;
Terminal=false
StartupNotify=false
Hidden=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=2
X-XFCE-Autostart-Override=true
"""

    try:
        os.makedirs(u_dir, exist_ok=True)
        with open(u_file, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(u_file, 0o644)
        return AutostartResult(
            enabled=True,
            source="user",
            path=u_file,
            message="Autostart successfully enabled",
        )
    except OSError as exc:
        return AutostartResult(
            enabled=False,
            source="user",
            path=u_file,
            message=f"Failed to write autostart entry: {exc}",
        )


def disable_autostart(
    user_file: str | None = None,
    system_file: str | None = None,
    system_files: list[str] | None = None,
) -> AutostartResult:
    """Disable autostart. Masks system-wide entry with Hidden=true if present."""
    u_file = user_file or get_user_autostart_file()
    u_dir = os.path.dirname(u_file)

    migrate_legacy_entries(u_dir)

    s_files = [system_file] if system_file else (system_files or get_system_autostart_files())
    system_exists = any(os.path.isfile(sf) for sf in s_files)

    if system_exists:
        # XDG Masking: write Hidden=true in user directory to override system entry
        exec_cmd, icon = get_current_launch_command()
        content = f"""[Desktop Entry]
Type=Application
Name=DotGhostBoard
Exec={exec_cmd}
Icon={icon}
Hidden=true
X-GNOME-Autostart-enabled=false
"""
        try:
            os.makedirs(u_dir, exist_ok=True)
            with open(u_file, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(u_file, 0o644)
            return AutostartResult(
                enabled=False,
                source="user_override",
                path=u_file,
                message="System autostart masked with Hidden=true",
            )
        except OSError as exc:
            return AutostartResult(
                enabled=True,
                source="user_override",
                path=u_file,
                message=f"Failed to mask autostart: {exc}",
            )
    else:
        # No system entry: simply remove user file if it exists
        if os.path.isfile(u_file):
            try:
                os.remove(u_file)
                return AutostartResult(
                    enabled=False,
                    source="none",
                    path="",
                    message="Autostart entry removed",
                )
            except OSError as exc:
                return AutostartResult(
                    enabled=True,
                    source="user",
                    path=u_file,
                    message=f"Failed to remove autostart entry: {exc}",
                )
        return AutostartResult(
            enabled=False,
            source="none",
            path="",
            message="Autostart already disabled",
        )


def migrate_legacy_entries(autostart_dir: str | None = None) -> list[str]:
    """Clean up legacy autostart entries (e.g. DotGhostBoard.desktop)."""
    target_dir = autostart_dir or get_user_autostart_dir()
    removed: list[str] = []
    for fname in LEGACY_FILENAMES:
        path = os.path.join(target_dir, fname)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed.append(path)
            except OSError:
                pass
    return removed
