"""
ui/widgets/stats_header.py
──────────────────────────
StatsHeaderCard widget — Dashboard state summary banner.
"""

import logging
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel
import core.storage as storage

logger = logging.getLogger(__name__)


class StatsHeaderCard(QFrame):
    """
    State summary widget displayed at top of history feed.
    Displays today's total captures, top copied clip, and total pinned count.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatsHeaderCard")
        self.setStyleSheet("""
            QFrame#StatsHeaderCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #161622, stop:1 #12121c);
                border: 1px solid #28283a;
                border-radius: 10px;
                padding: 4px 10px;
            }
            QLabel {
                font-size: 11px;
                font-family: monospace;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(12)

        self.lbl_today = QLabel("📋 Today: 0")
        self.lbl_today.setStyleSheet("color: #38bdf8; font-weight: 600;")

        self.lbl_top = QLabel("🔥 Top: None")
        self.lbl_top.setStyleSheet("color: #f59e0b; font-weight: 600;")

        self.lbl_pinned = QLabel("📍 Pinned: 0")
        self.lbl_pinned.setStyleSheet("color: #a855f7; font-weight: 600;")

        sep1 = QLabel("•")
        sep1.setStyleSheet("color: #334155;")
        sep2 = QLabel("•")
        sep2.setStyleSheet("color: #334155;")

        layout.addWidget(self.lbl_today)
        layout.addWidget(sep1)
        layout.addWidget(self.lbl_top)
        layout.addWidget(sep2)
        layout.addWidget(self.lbl_pinned)
        layout.addStretch()

        self.refresh_stats()

    def refresh_stats(self):
        try:
            stats = storage.get_today_stats()
            total_today = stats.get("total_today", 0)
            top_preview = stats.get("top_copied_preview", "")
            top_count = stats.get("top_copied_count", 0)
            total_pinned = stats.get("total_pinned", 0)

            self.lbl_today.setText(f"📋 Today: {total_today}")
            if top_preview and top_count > 0:
                self.lbl_top.setText(f"🔥 Top: {top_preview} (×{top_count})")
            else:
                self.lbl_top.setText("🔥 Top: None")

            self.lbl_pinned.setText(f"📍 Pinned: {total_pinned}")
        except Exception as e:
            logger.error(f"Error refreshing stats header: {e}")

    def update_stats(self, stats=None):
        """Update header displays with provided stats dict or fetch fresh."""
        if stats and isinstance(stats, dict) and "total_today" in stats:
            total_today = stats.get("total_today", 0)
            top_preview = stats.get("top_copied_preview", "")
            top_count = stats.get("top_copied_count", 0)
            total_pinned = stats.get("total_pinned", 0)

            self.lbl_today.setText(f"📋 Today: {total_today}")
            if top_preview and top_count > 0:
                self.lbl_top.setText(f"🔥 Top: {top_preview} (×{top_count})")
            else:
                self.lbl_top.setText("🔥 Top: None")

            self.lbl_pinned.setText(f"📍 Pinned: {total_pinned}")
        else:
            self.refresh_stats()
