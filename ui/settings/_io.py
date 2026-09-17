"""
ui/settings/_io.py
──────────────────
Settings file I/O — load, save, defaults, and path resolution.

Extracted from ui/settings.py (v1.6.0 Phantom) in v2.0.0 Cerberus
as part of the settings package decomposition.

Original history:
  v1.1.0  Phantom  — Initial settings panel
  v1.3.0  Wraith   — W009: Tag Manager dialog
  v1.4.0  Eclipse  — E009: Master password, auto-lock, stealth, app filter
"""

import json
import os
import secrets
import socket

# ── Settings file path ────────────────────────────────────────────────────────
_DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".config", "dotghostboard")
_USER_DATA    = os.getenv("DOTGHOST_HOME", _DEFAULT_HOME)
SETTINGS_PATH = os.path.join(_USER_DATA, "settings.json")

_DEFAULTS: dict = {
    # General
    "max_history":                200,
    "max_captures":               100,
    "theme":                      "dark",
    "clear_on_exit":              False,
    "multiselect_hint_dismissed": False,
    # Eclipse
    "master_lock_enabled":        False,
    "auto_lock_minutes":          0,
    "stealth_mode":               False,
    "app_filter_mode":            "blacklist",
    "app_filter_list":            [],
    # API & Sync
    "api_enabled":                False,
    "api_port":                   9090,
    "api_token":                  "",
}


# ── Public helpers ────────────────────────────────────────────────────────────

def load_settings() -> dict:
    """Return settings dict. Missing keys fall back to defaults."""
    settings = dict(_DEFAULTS)
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            settings.update(data)
        except Exception:
            pass
            
    # Auto-generate API token if missing
    if not settings.get("api_token"):
        settings["api_token"] = secrets.token_hex(16)
        save_settings(settings)
        
    # Auto-generate Node ID and default device name for Sync Phase
    needs_save = False
    if not settings.get("node_id"):
        settings["node_id"] = secrets.token_hex(8)
        needs_save = True
    if not settings.get("device_name"):
        settings["device_name"] = socket.gethostname()
        needs_save = True
        
    if needs_save:
        save_settings(settings)
        
    return settings


def save_settings(settings: dict) -> None:
    """Persist settings dict to data/settings.json."""
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
