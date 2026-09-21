"""
core/constants.py
─────────────────
Centralized application constants for DotGhostBoard.

Introduced in v2.x refactor to eliminate magic numbers scattered
across dashboard.py and widgets.py.

Usage:
    from core.constants import PREVIEW_MAX_LEN, PAGE_SIZE
"""

# ── History / Pagination ─────────────────────────────────────────────────────
PAGE_SIZE: int = 20
"""Number of clipboard cards loaded per page (lazy loading)."""

# ── Preview ──────────────────────────────────────────────────────────────────
PREVIEW_MAX_LEN: int = 120
"""Maximum character length for text preview in ItemCard."""

# ── Thumbnail ────────────────────────────────────────────────────────────────
THUMB_MAX_W: int = 300
"""Maximum thumbnail width in pixels."""

THUMB_MAX_H: int = 180
"""Maximum thumbnail height in pixels."""

# ── Search ───────────────────────────────────────────────────────────────────
SEARCH_DEBOUNCE_MS: int = 200
"""Debounce delay (ms) for the main search bar before triggering a DB query."""

SPOTLIGHT_DEBOUNCE_MS: int = 150
"""Debounce delay (ms) for the Spotlight search overlay."""

SPOTLIGHT_RESULT_LIMIT: int = 15
"""Maximum number of results shown in the Spotlight overlay."""

SPOTLIGHT_PREVIEW_MAX_LEN: int = 60
"""Maximum character length for a Spotlight result preview line."""

# ── Timers ───────────────────────────────────────────────────────────────────
REL_TIME_INTERVAL_MS: int = 60_000
"""Interval (ms) for refreshing relative timestamps on cards ("2m ago", etc.)."""

PIN_TOAST_DURATION_MS: int = 6_000
"""How long the pin-suggestion toast is visible before auto-dismissing."""

# ── Copy-count thresholds ────────────────────────────────────────────────────
PIN_SUGGESTION_THRESHOLD: int = 5
"""Copy count at which the 'Pin it?' toast is shown."""

AUTO_PIN_THRESHOLD: int = 10
"""Copy count at which an item is silently auto-pinned."""

# ── UI dimensions ────────────────────────────────────────────────────────────
SIDEBAR_WIDTH: int = 160
"""Fixed width of the collections sidebar in pixels."""

TOP_BAR_HEIGHT: int = 56
"""Fixed height of the top bar in pixels."""

DEVICES_LIST_HEIGHT: int = 140
"""Fixed height of the devices list widget in the sidebar."""

VAULT_DRAWER_WIDTH: int = 340
"""Width of the sliding vault drawer panel in pixels."""

VAULT_CATEGORIES: tuple[str, ...] = ("all", "password", "token", "key", "note", "generic")
"""Supported secret category filters in The Vault."""

VAULT_IDLE_TIMEOUT_SECONDS: int = 120
"""Auto-lock idle countdown timeout in seconds for The Vault."""
