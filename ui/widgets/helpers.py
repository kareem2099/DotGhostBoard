"""
ui/widgets/helpers.py
──────────────────────
Helper functions for UI widgets in DotGhostBoard.
"""

from datetime import datetime


def _format_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())

        if seconds < 45:
            return "just now"
        elif seconds < 3600:
            mins = max(1, seconds // 60)
            return f"{mins}m ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h ago"
        elif seconds < 86400 * 7:
            days = seconds // 86400
            return f"{days}d ago"
        else:
            return dt.strftime("%d %b, %H:%M")
    except Exception:
        return ""


def _copy_count_badge_state(count: int) -> tuple[str, str]:
    """
    Return ``(text, stylesheet)`` for a copy-count badge.

    An empty text string signals that the badge should be hidden.

    Presentation tiers (independent of business pin-thresholds):
        0–1   → hidden
        2–4   → ↩ teal   (mild interest)
        5–9   → ♻ orange  (warm usage)
        10+   → 🔥 hot    (high frequency)
    """
    if count < 2:
        return "", ""

    if count >= 10:
        bg, fg, icon = "#ff6b35", "#0a0a0a", "🔥"
    elif count >= 5:
        bg, fg, icon = "#e8a020", "#0a0a0a", "♻"
    else:
        bg, fg, icon = "#2a4a4a", "#7ecfcf", "↩"

    text  = f"{icon} ×{count}"
    style = (
        f"background: {bg}; color: {fg};"
        "border-radius: 9px; padding: 0 7px;"
        "font-size: 11px; font-weight: 600;"
    )
    return text, style
