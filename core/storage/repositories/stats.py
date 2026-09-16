"""
core/storage/repositories/stats.py
──────────────────────────────────
Repository queries for dashboard statistics and counters.
"""

from datetime import datetime
from ..database import _db


def get_today_stats() -> dict:
    """
    Get summary statistics for the dashboard state header:
    - total_today: number of items created today
    - total_copies: sum of all item copy counts
    - top_copied_preview: snippet of most copied item created today
    - top_copied_count: copy count of top item
    - total_pinned: total count of pinned items
    """
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    with _db() as conn:
        cur1 = conn.execute(
            "SELECT COUNT(*) as cnt FROM clipboard_items WHERE created_at LIKE ?",
            (f"{today_prefix}%",)
        )
        total_today = cur1.fetchone()["cnt"]

        cur2 = conn.execute("SELECT SUM(copy_count) as total_copies FROM clipboard_items")
        row2 = cur2.fetchone()
        total_copies = row2["total_copies"] if row2 and row2["total_copies"] else 0

        cur3 = conn.execute(
            """
            SELECT preview, content, copy_count
            FROM clipboard_items
            WHERE copy_count > 0
              AND created_at LIKE ?
              AND COALESCE(is_secret, 0) = 0
            ORDER BY copy_count DESC, updated_at DESC
            LIMIT 1
            """,
            (f"{today_prefix}%",)
        )
        top_row = cur3.fetchone()
        top_copied_preview = ""
        top_copied_count = 0
        if top_row:
            top_copied_preview = top_row["preview"] or top_row["content"] or ""
            top_copied_count = top_row["copy_count"]

        cur4 = conn.execute("SELECT COUNT(*) as cnt FROM clipboard_items WHERE is_pinned = 1")
        total_pinned = cur4.fetchone()["cnt"]

        return {
            "total_today": total_today,
            "total_copies": total_copies,
            "top_copied_preview": top_copied_preview[:25] + "…" if len(top_copied_preview) > 25 else top_copied_preview,
            "top_copied_count": top_copied_count,
            "total_pinned": total_pinned,
        }


def get_stats() -> dict:
    """Quick statistics for the Dashboard."""
    with _db() as conn:
        total  = conn.execute("SELECT COUNT(*) FROM clipboard_items").fetchone()[0]
        pinned = conn.execute("SELECT COUNT(*) FROM clipboard_items WHERE is_pinned = 1").fetchone()[0]
        texts  = conn.execute("SELECT COUNT(*) FROM clipboard_items WHERE type = 'text'").fetchone()[0]
        images = conn.execute("SELECT COUNT(*) FROM clipboard_items WHERE type = 'image'").fetchone()[0]
    return {"total": total, "pinned": pinned, "texts": texts, "images": images}
