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
    """
    if count < 2:
        return "", ""

    if count >= 10:
        bg = "#2d2417"
        fg = "#d9aa55"
        border = "#4b3920"
    elif count >= 5:
        bg = "#22251f"
        fg = "#a9b87c"
        border = "#343a2c"
    else:
        bg = "#1c2225"
        fg = "#819096"
        border = "#2b3337"

    text = f"×{count}"

    style = (
        f"background: {bg};"
        f"color: {fg};"
        f"border: 1px solid {border};"
        "border-radius: 8px;"
        "padding: 0 7px;"
        "font-size: 10px;"
        "font-weight: 600;"
    )

    return text, style
