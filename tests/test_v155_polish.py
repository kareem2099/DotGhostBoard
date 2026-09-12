"""
tests/test_v155_polish.py
Unit tests for v1.5.5 Polish features:
- reset_copy_count()
- get_today_stats()
- _format_time() relative timestamps
"""

import os
import pytest
from datetime import datetime, timedelta

from core import storage
from ui.widgets import _format_time, _copy_count_badge_state


def test_reset_copy_count(tmp_path):
    db_file = str(tmp_path / "test_ghost.db")
    storage.DB_PATH = db_file
    storage.init_db()

    item_id = storage.add_item("text", "Hello test reset")
    count1 = storage.increment_copy_count(item_id)
    count2 = storage.increment_copy_count(item_id)
    assert count2 >= 2

    assert storage.reset_copy_count(item_id) is True
    assert storage.reset_copy_count(999999) is False
    item = storage.get_item_by_id(item_id)
    assert item["copy_count"] == 0


def test_get_today_stats(tmp_path):
    db_file = str(tmp_path / "test_ghost_stats.db")
    storage.DB_PATH = db_file
    storage.init_db()

    id1 = storage.add_item("text", "Item 1 for stats")
    id2 = storage.add_item("text", "Item 2 for stats")
    storage.increment_copy_count(id1)
    storage.increment_copy_count(id1)
    storage.toggle_pin(id2)

    stats = storage.get_today_stats()
    assert stats["total_today"] == 2
    assert stats["total_pinned"] == 1
    assert stats["top_copied_count"] >= 2



def test_relative_time_formatting():
    now_iso = datetime.now().isoformat()
    assert _format_time(now_iso) == "just now"

    min_ago_iso = (datetime.now() - timedelta(minutes=5)).isoformat()
    assert _format_time(min_ago_iso) == "5m ago"

    hrs_ago_iso = (datetime.now() - timedelta(hours=3)).isoformat()
    assert _format_time(hrs_ago_iso) == "3h ago"

    days_ago_iso = (datetime.now() - timedelta(days=2)).isoformat()
    assert _format_time(days_ago_iso) == "2d ago"


def test_copy_count_badge_state():
    # Less than 2 should be hidden
    assert _copy_count_badge_state(0) == ("", "")
    assert _copy_count_badge_state(1) == ("", "")

    # 2-4: subtle slate
    text, style = _copy_count_badge_state(3)
    assert text == "×3"
    assert "#1c2225" in style
    assert "🔥" not in text

    # 5-9: warm green/olive
    text, style = _copy_count_badge_state(7)
    assert text == "×7"
    assert "#22251f" in style

    # 10+: amber/gold
    text, style = _copy_count_badge_state(12)
    assert text == "×12"
    assert "#2d2417" in style
    assert "🔥" not in text


def test_watcher_self_paste_no_recapture():
    from core.watcher import ClipboardWatcher
    watcher = ClipboardWatcher()
    watcher.mark_self_paste()
    assert watcher._is_self_paste is True


def test_image_deduplication_via_hash(tmp_path):
    db_file = str(tmp_path / "test_ghost_img.db")
    storage.DB_PATH = db_file
    storage.init_db()

    # Create two different PNG files with identical byte content
    img1 = tmp_path / "img1.png"
    img2 = tmp_path / "img2.png"
    img_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    img1.write_bytes(img_data)
    img2.write_bytes(img_data)

    id1 = storage.add_item("image", str(img1), preview=str(img1))
    id2 = storage.add_item("image", str(img2), preview=str(img2))

    # Second insert should detect duplicate hash, return same ID, and remove img2
    assert id1 == id2
    assert not img2.exists()

    item = storage.get_item_by_id(id1)
    assert item["copy_count"] == 2


def test_today_stats_excludes_old_and_secret_items(tmp_path):
    db_file = str(tmp_path / "test_today_filter.db")
    storage.DB_PATH = db_file
    storage.init_db()

    today_id = storage.add_item("text", "Public today")
    storage.increment_copy_count(today_id)
    storage.increment_copy_count(today_id)

    secret_id = storage.add_item("text", "Secret today")
    old_id = storage.add_item("text", "Old popular item")

    old_date = (datetime.now() - timedelta(days=1)).isoformat()

    with storage._db() as conn:
        conn.execute(
            "UPDATE clipboard_items SET copy_count = 100, is_secret = 1 WHERE id = ?",
            (secret_id,)
        )
        conn.execute(
            """
            UPDATE clipboard_items
            SET copy_count = 200, created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (old_date, old_date, old_id)
        )

    stats = storage.get_today_stats()

    assert stats["top_copied_preview"] == "Public today"
    assert stats["top_copied_count"] == 3


