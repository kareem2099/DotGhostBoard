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
        layout.setSpacing(10)

        self.lbl_total = QLabel("📦 Total: 0")
        self.lbl_total.setStyleSheet("color: #38bdf8; font-weight: 600;")
        self.lbl_total.setToolTip("Total items stored in clipboard history")

        self.lbl_today = QLabel("📋 Today: 0")
        self.lbl_today.setStyleSheet("color: #60a5fa; font-weight: 600;")
        self.lbl_today.setToolTip("Items captured today")

        self.lbl_copies = QLabel("⚡ Copies: 0")
        self.lbl_copies.setStyleSheet("color: #34d399; font-weight: 600;")
        self.lbl_copies.setToolTip("Total lifetime copy count across all items")

        self.lbl_pinned = QLabel("📍 Pinned: 0")
        self.lbl_pinned.setStyleSheet("color: #c084fc; font-weight: 600;")
        self.lbl_pinned.setToolTip("Pinned items protected from deletion")

        self.lbl_top = QLabel("🔥 Top: None")
        self.lbl_top.setStyleSheet("color: #f59e0b; font-weight: 600;")
        self.lbl_top.setToolTip("Most frequently copied clip")

        layout.addWidget(self.lbl_total)
        layout.addWidget(self._make_sep())
        layout.addWidget(self.lbl_today)
        layout.addWidget(self._make_sep())
        layout.addWidget(self.lbl_copies)
        layout.addWidget(self._make_sep())
        layout.addWidget(self.lbl_pinned)
        layout.addWidget(self._make_sep())
        layout.addWidget(self.lbl_top)
        layout.addStretch()

        self.refresh_stats()

    def _make_sep(self) -> QLabel:
        sep = QLabel("•")
        sep.setStyleSheet("color: #334155;")
        return sep

    def refresh_stats(self):
        try:
            today_stats = storage.get_today_stats()
            quick_stats = storage.get_stats()
            combined = {**quick_stats, **today_stats}
            self.update_stats(combined)
        except Exception as e:
            logger.error(f"Error refreshing stats header: {e}")

    def update_stats(self, stats=None):
        """Update header displays with provided stats dict or fetch fresh."""
        if not stats or not isinstance(stats, dict):
            self.refresh_stats()
            return

        total = stats.get("total", 0)
        total_today = stats.get("total_today", 0)
        total_copies = stats.get("total_copies", 0)
        total_pinned = stats.get("total_pinned", stats.get("pinned", 0))
        # Prioritize all-time top so the most copied clip is displayed, fallback to today's top
        top_preview = stats.get("all_time_top_preview") or stats.get("top_copied_preview", "")
        top_count = (
            stats.get("all_time_top_count")
            if stats.get("all_time_top_count") is not None
            else stats.get("top_copied_count", 0)
        )
        today_top_preview = stats.get("top_copied_preview", "")
        today_top_count = stats.get("top_copied_count", 0)

        self.lbl_total.setText(f"📦 Total: {total}")
        self.lbl_today.setText(f"📋 Today: {total_today}")
        self.lbl_copies.setText(f"⚡ Copies: {total_copies}")
        self.lbl_pinned.setText(f"📍 Pinned: {total_pinned}")
        if top_preview and top_count > 0:
            self.lbl_top.setText(f"🔥 Top: {top_preview} (×{top_count})")
            tooltip_parts = [f"All-time most copied: {top_preview} (×{top_count})"]
            if today_top_preview and today_top_count > 0:
                tooltip_parts.append(f"Today's top: {today_top_preview} (×{today_top_count})")
            self.lbl_top.setToolTip("\n".join(tooltip_parts))
        else:
            self.lbl_top.setText("🔥 Top: None")
            self.lbl_top.setToolTip("No copied clips yet")
