# Centralized application configuration

import os
import sys

APP_VERSION = "v1.5.3"
APP_CODENAME = "Nexus"

GITHUB_REPO = "kareem2099/DotGhostBoard"
GITHUB_API_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def get_asset_path(filename: str) -> str:
    """
    Returns the absolute path to an asset file inside the `assets/` folder.

    Works in all environments:
      - Normal `python main.py` development run
      - PyInstaller one-file / one-dir bundle  (_MEIPASS)
      - AppImage / Debian package installs

    Args:
        filename: Relative filename inside `assets/`, e.g. "pigeon_boss.gif"

    Returns:
        Absolute path string.
    """
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller unpacks data files here at runtime
        base_dir = sys._MEIPASS
    else:
        # config.py lives in  <root>/core/config.py
        # so we go up one level to reach <root>/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_dir, "data", "assets", filename)
