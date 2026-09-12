#!/usr/bin/env python3
"""
scripts/setup_autostart.py
──────────────────────────
CLI tool to configure DotGhostBoard autostart & app launcher entries.
Uses core.autostart for XDG compliance, masking, and runtime detection.

Usage:
    python3 scripts/setup_autostart.py            # Enable for current environment
    python3 scripts/setup_autostart.py --deb      # Configure for system deb (/usr/bin/dotghostboard)
    python3 scripts/setup_autostart.py --appimage /path/to/DotGhostBoard.AppImage
    python3 scripts/setup_autostart.py --remove   # Disable / mask autostart
"""

import sys
import os
import argparse

# Add project root to sys.path
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from core.autostart import (
    enable_autostart,
    disable_autostart,
    migrate_legacy_entries,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DotGhostBoard autostart & launcher installer"
    )
    parser.add_argument(
        "--remove", "--disable", action="store_true",
        help="Disable autostart (masks system entry if present)"
    )
    parser.add_argument(
        "--deb", action="store_true",
        help="Configure autostart to use /usr/bin/dotghostboard"
    )
    parser.add_argument(
        "--appimage", type=str, default="",
        help="Configure autostart to use a specific AppImage path"
    )
    args = parser.parse_args()

    # Always migrate old entries first
    removed = migrate_legacy_entries()
    if removed:
        print(f"🧹 Cleaned up {len(removed)} legacy entry: {', '.join(removed)}")

    if args.remove:
        print("👻 DotGhostBoard — disabling autostart…\n")
        res = disable_autostart()
        print(f"  Result : {res.message}")
        print(f"  Source : {res.source}")
        if res.path:
            print(f"  Path   : {res.path}")
        print("\n✅ Autostart disabled.")
        return

    # If explicit target specified, pass command override to enable_autostart
    if args.deb:
        print("👻 DotGhostBoard — setting up autostart for DEB (/usr/bin/dotghostboard)…\n")
        res = enable_autostart(
            command="/usr/bin/dotghostboard --startup",
            icon="dotghostboard",
        )
        print(f"  ✓ Written: {res.path}")
        print("\n✅ Done! DotGhostBoard will start automatically in tray on next login.")
        return

    if args.appimage:
        appimage_path = os.path.abspath(args.appimage)
        if not os.path.isfile(appimage_path):
            print(f"❌ Error: AppImage file not found at: {appimage_path}")
            sys.exit(1)
        from core.autostart import format_exec_line
        cmd = format_exec_line(appimage_path, ["--startup"])
        print(f"👻 DotGhostBoard — setting up autostart for AppImage ({appimage_path})…\n")
        res = enable_autostart(command=cmd, icon="dotghostboard")
        print(f"  ✓ Written: {res.path}")
        print("\n✅ Done! DotGhostBoard will start automatically in tray on next login.")
        return

    print("👻 DotGhostBoard — enabling autostart for current runtime…\n")
    res = enable_autostart()
    print(f"  Result : {res.message}")
    print(f"  Target : {res.path}")
    print("\n✅ Done! DotGhostBoard will start automatically in tray on next login.")


if __name__ == "__main__":
    main()
