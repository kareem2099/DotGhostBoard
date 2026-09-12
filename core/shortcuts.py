"""
core/shortcuts.py
─────────────────
Per-user global desktop keyboard shortcuts manager for DotGhostBoard.
Supports GNOME (via gsettings) and XFCE (via xfconf-query).
Accessible from CLI, install scripts, and the in-app Settings dialog.
"""

import os
import re
import sys
import ast
import shlex
import shutil
import subprocess

SHORTCUT_DEFINITIONS = [
    {
        "id": "dashboard",
        "name": "DotGhostBoard",
        "gnome_binding": "<Control><Alt>v",
        "xfce_prop": "/commands/custom/<Primary><Alt>v",
        "flag": "--toggle",
        "label": "Ctrl + Alt + V (Toggle Dashboard)",
    },
    {
        "id": "spotlight",
        "name": "DotGhostBoard Spotlight",
        "gnome_binding": "<Control><Alt>space",
        "xfce_prop": "/commands/custom/<Primary><Alt>space",
        "flag": "--spotlight",
        "label": "Ctrl + Alt + Space (Spotlight Search)",
    },
]


def detect_desktop() -> str:
    """
    Detect the active desktop environment from session environment variables.
    Checks XDG_CURRENT_DESKTOP and DESKTOP_SESSION to prevent false positives
    (e.g., gsettings installed on Kali XFCE).
    """
    current = (
        os.environ.get("XDG_CURRENT_DESKTOP", "")
        + ":"
        + os.environ.get("DESKTOP_SESSION", "")
    ).lower()

    if "xfce" in current:
        return "xfce"
    if "gnome" in current:
        return "gnome"
    return "unknown"


def _get_launch_command() -> list[str]:
    """Resolve the current DotGhostBoard artifact as argv components."""

    # 1. AppImage — always prefer the exact artifact currently running
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        appimage = os.path.abspath(appimage)
        if os.path.isfile(appimage):
            return [appimage]

    # 2. PyInstaller / frozen package
    if getattr(sys, "frozen", False):
        return [os.path.abspath(sys.executable)]

    # 3. Source checkout
    project_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    main_script = os.path.join(project_dir, "main.py")
    venv_python = os.path.join(
        project_dir, "venv", "bin", "python3"
    )

    if os.path.isfile(venv_python) and os.path.isfile(main_script):
        return [venv_python, main_script]

    if os.path.isfile(main_script):
        return [sys.executable, main_script]

    # 4. Installed package
    system_bin = shutil.which("dotghostboard")
    if system_bin:
        return [os.path.abspath(system_bin)]

    # Last-resort PATH command
    return ["dotghostboard"]


def _get_exec_commands() -> list[dict]:
    base = _get_launch_command()

    return [
        {
            **sc,
            "command": shlex.join([*base, sc["flag"]]),
        }
        for sc in SHORTCUT_DEFINITIONS
    ]


def _parse_gsettings_bindings(raw: str) -> list[str]:
    """Safely parse custom-keybindings list from gsettings output."""
    if raw.startswith("@as "):
        raw = raw[4:].strip()

    try:
        bindings = ast.literal_eval(raw)
        if not isinstance(bindings, list):
            return []
        return [str(b) for b in bindings]
    except (ValueError, SyntaxError):
        return []


def setup_gnome() -> tuple[bool, str]:
    """Register shortcuts in GNOME using gsettings without eval()."""
    if not shutil.which("gsettings"):
        return False, "gsettings utility not found"

    schema = "org.gnome.settings-daemon.plugins.media-keys"
    try:
        raw = subprocess.check_output(
            ["gsettings", "get", schema, "custom-keybindings"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
    except Exception as exc:
        return False, f"Failed to read GNOME keybindings: {exc}"

    bindings = _parse_gsettings_bindings(raw)

    commands = _get_exec_commands()
    for sc in commands:
        name = sc["name"]
        command = sc["command"]
        binding = sc["gnome_binding"]

        target_path = None
        for b in bindings:
            try:
                b_name = subprocess.check_output(
                    ["gsettings", "get", f"{schema}.custom-keybinding:{b}", "name"],
                    stderr=subprocess.DEVNULL,
                ).decode("utf-8").strip().strip("'\"")
                if b_name == name:
                    target_path = b
                    break
            except Exception:
                continue

        if not target_path:
            indices = []
            for b in bindings:
                m = re.search(r"custom(\d+)/?$", b)
                if m:
                    indices.append(int(m.group(1)))
            next_idx = 0
            while next_idx in indices:
                next_idx += 1
            target_path = f"/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom{next_idx}/"
            bindings.append(target_path)
            subprocess.check_call([
                "gsettings", "set",
                schema,
                "custom-keybindings", str(bindings)
            ])

        subprocess.check_call([
            "gsettings", "set",
            f"{schema}.custom-keybinding:{target_path}",
            "name", name
        ])
        subprocess.check_call([
            "gsettings", "set",
            f"{schema}.custom-keybinding:{target_path}",
            "command", command
        ])
        subprocess.check_call([
            "gsettings", "set",
            f"{schema}.custom-keybinding:{target_path}",
            "binding", binding
        ])

    return True, "GNOME shortcuts configured successfully"


def setup_xfce() -> tuple[bool, str]:
    """Register shortcuts in XFCE using xfconf-query idempotently."""
    if not shutil.which("xfconf-query"):
        return False, "xfconf-query utility not found"

    commands = _get_exec_commands()
    for sc in commands:
        prop = sc["xfce_prop"]
        command = sc["command"]
        # Try updating existing property first
        res = subprocess.run([
            "xfconf-query",
            "--channel", "xfce4-keyboard-shortcuts",
            "--property", prop,
            "--set", command
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode != 0:
            # If property does not exist yet, create it
            res = subprocess.run([
                "xfconf-query",
                "--channel", "xfce4-keyboard-shortcuts",
                "--property", prop,
                "--create",
                "--type", "string",
                "--set", command
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode != 0:
                return False, f"Failed to set XFCE property {prop}"

    return True, "XFCE shortcuts configured successfully"


def setup_shortcuts() -> tuple[bool, str]:
    """
    Main entrypoint: detects desktop environment and configures shortcuts.
    Returns (success: bool, message: str).
    """
    try:
        desktop = detect_desktop()

        if desktop == "xfce":
            ok, msg = setup_xfce()
            return (
                (True, f"Configured for XFCE ({msg})")
                if ok
                else (False, f"XFCE configuration failed: {msg}")
            )

        if desktop == "gnome":
            ok, msg = setup_gnome()
            return (
                (True, f"Configured for GNOME ({msg})")
                if ok
                else (False, f"GNOME configuration failed: {msg}")
            )

        return False, (
            "Desktop environment is not supported automatically. "
            "Currently supported: GNOME and XFCE. "
            "Please configure the shortcuts manually in system keyboard settings."
        )

    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Shortcut configuration failed: {exc}"
