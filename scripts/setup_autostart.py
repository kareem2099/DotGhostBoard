#!/usr/bin/env python3
"""
scripts/setup_autostart.py
──────────────────────────
Standalone Python script to set up DotGhostBoard autostart and app launcher
entries without requiring install.sh or bash.

Usage:
    python3 scripts/setup_autostart.py
    python3 scripts/setup_autostart.py --remove   # undo
"""

import sys
import os
import argparse
import stat
import shutil


# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VENV_PYTHON = os.path.join(PROJECT_DIR, "venv", "bin", "python3")
PYTHON      = VENV_PYTHON if os.path.isfile(VENV_PYTHON) else sys.executable
MAIN        = os.path.join(PROJECT_DIR, "main.py")
ICON        = os.path.join(PROJECT_DIR, "data", "icons", "icon.png")

AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
DESKTOP_DIR   = os.path.expanduser("~/.local/share/applications")

AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "DotGhostBoard.desktop")
LAUNCHER_FILE  = os.path.join(DESKTOP_DIR,   "DotGhostBoard.desktop")

DESKTOP_CONTENT = f"""\
[Desktop Entry]
Type=Application
Name=DotGhostBoard
GenericName=Clipboard Manager
Comment=Advanced clipboard manager — DotSuite
Exec={PYTHON} {MAIN}
Icon={ICON}
Categories=Utility;
Keywords=clipboard;copy;paste;pin;ghost;dotsuite;
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
X-XFCE-Autostart-Override=true
StartupNotify=false
Terminal=false
"""


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(path, 0o755)
    print(f"  ✓ Written: {path}")


def _remove(path: str) -> None:
    if os.path.isfile(path):
        os.remove(path)
        print(f"  ✓ Removed: {path}")
    else:
        print(f"  – Not found (skipped): {path}")


def install() -> None:
    print("👻 DotGhostBoard — setting up autostart & app launcher…\n")

    if not os.path.isfile(ICON):
        print("  ⚠ Icon not found. Run: python3 scripts/generate_icon.py\n")

    _write(AUTOSTART_FILE, DESKTOP_CONTENT)
    _write(LAUNCHER_FILE,  DESKTOP_CONTENT)

    # Refresh desktop database if available
    if shutil.which("update-desktop-database"):
        os.system(f"update-desktop-database {DESKTOP_DIR} 2>/dev/null")

    print(f"\n  Autostart : {AUTOSTART_FILE}")
    print(f"  Launcher  : {LAUNCHER_FILE}")
    print(f"  Python    : {PYTHON}")
    print(f"\n✅ Done! DotGhostBoard will start automatically on next login.")
    print(f'   Run now  : {PYTHON} {MAIN} &\n')


def uninstall() -> None:
    print("👻 DotGhostBoard — removing autostart & app launcher entries…\n")
    _remove(AUTOSTART_FILE)
    _remove(LAUNCHER_FILE)
    print("\n✅ Entries removed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DotGhostBoard autostart installer"
    )
    parser.add_argument(
        "--remove", action="store_true",
        help="Remove autostart and launcher entries"
    )
    args = parser.parse_args()

    if args.remove:
        uninstall()
    else:
        install()


if __name__ == "__main__":
    main()
