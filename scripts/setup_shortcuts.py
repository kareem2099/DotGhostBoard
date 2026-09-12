#!/usr/bin/env python3
"""
scripts/setup_shortcuts.py
──────────────────────────
CLI tool to register DotGhostBoard global shortcuts.
Delegates to core.shortcuts.
"""

import sys
import os

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from core.shortcuts import setup_shortcuts, detect_desktop, SHORTCUT_DEFINITIONS


def main():
    print(f"⌨  Configuring DotGhostBoard Global Shortcuts (Desktop: {detect_desktop()})...")
    ok, msg = setup_shortcuts()
    if ok:
        print(f"   ✓ {msg}")
        for sc in SHORTCUT_DEFINITIONS:
            print(f"     - {sc['label']}")
    else:
        print(f"   ⚠ {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
