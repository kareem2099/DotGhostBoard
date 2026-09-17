"""
ui/settings/__init__.py
────────────────────────
Backward-compatible facade for the ui.settings package.

v2.0.0 Cerberus — Phase 5 Settings Decomposition.

All existing callers continue to work without any changes:

    from ui.settings import SettingsDialog        # ✅
    from ui.settings import load_settings         # ✅
    from ui.settings import save_settings         # ✅
    from ui.settings import TagManagerDialog      # ✅ (zero-break)
"""

from ui.settings.dialog import SettingsDialog
from ui.settings._io import load_settings, save_settings, SETTINGS_PATH, _DEFAULTS
from ui.tag_manager import TagManagerDialog

__all__ = [
    "SettingsDialog",
    "load_settings",
    "save_settings",
    "SETTINGS_PATH",
    "_DEFAULTS",
    "TagManagerDialog",
]
