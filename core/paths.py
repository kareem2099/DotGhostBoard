"""
core/paths.py — Resource-path helper
=====================================
When the app is bundled with PyInstaller (deb / AppImage), all data files
are extracted to ``sys._MEIPASS`` at runtime.  This module provides a single
``resource_path()`` helper that resolves paths correctly in **both** contexts:

* **Source / dev run**: returns ``os path relative to the project root``
* **Frozen (PyInstaller)**: returns the path inside ``sys._MEIPASS``

Usage
-----
    from core.paths import resource_path

    qss = resource_path("ui", "ghost.qss")
    icon = resource_path("data", "icons", "icon.png")
"""

import os
import sys


def _base_dir() -> str:
    """Return the effective base directory for resource resolution.

    - Frozen (PyInstaller): ``sys._MEIPASS``
    - Dev / source run: the project root (two levels up from this file)
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    # __file__ is  <project>/core/paths.py  →  go up two levels
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    """Return the absolute path to a bundled resource.

    Args:
        *parts: Path components relative to the project root.
                Example: ``resource_path("ui", "ghost.qss")``

    Returns:
        Absolute path that works in both source and frozen environments.
    """
    return os.path.join(_base_dir(), *parts)
