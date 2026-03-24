"""
scripts/generate_doc_assets.py
──────────────────────────────
Programmatically generates visualization assets for DotGhostBoard documentation
using PyQt6's QPainter. Ensures 100% theme match.
"""

import os
import sys
from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QBrush
from PyQt6.QtCore import Qt, QRectF, QPointF

# Add project root to sys.path to allow imports from core/ui
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# ── Theme Definition (Matches ghost.qss) ──────────────────────────────────────
NEON_GREEN = QColor("#00ff41")
NEON_GREEN_FADE = QColor("#00ff4122")
BG_COLOR = QColor("#0f0f0f")
CARD_BG = QColor("#161616")
TEXT_COLOR = QColor("#e0e0e0")
META_TEXT = QColor("#444")
FONT_FAMILY = "JetBrains Mono"

ASSETS_DIR = os.path.join(BASE_DIR, "data", "assets")

def ensure_assets_dir():
    os.makedirs(ASSETS_DIR, exist_ok=True)

# ── Asset #2: Architecture Diagram (Clipboard Loop) ──────────────────────────
def generate_architecture_diagram():
    """Generates the QTimer -> detect -> save -> emit diagram."""
    print("[DocAssets] Generating Architecture Diagram (placeholder #2)...")
    ensure_assets_dir()

    # Create a clean canvas
    width, height = 800, 450
    px = QPixmap(width, height)
    px.fill(BG_COLOR)

    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Pens and Brushes
    glow_pen = QPen(NEON_GREEN, 2)
    meta_pen = QPen(META_TEXT, 1)
    text_font = QFont(FONT_FAMILY, 12)
    title_font = QFont(FONT_FAMILY, 14, QFont.Weight.Bold)

    painter.setFont(text_font)

    # 1. Draw Nodes (Watcher, DB, Media, Dashboard)
    watcher_rect = QRectF(50, 150, 180, 80)
    db_rect = QRectF(300, 50, 180, 80)
    media_rect = QRectF(300, 250, 180, 80)
    dash_rect = QRectF(570, 150, 180, 80)

    nodes = [
        (watcher_rect, "Clipboard\nWatcher", "QObject"),
        (db_rect, "SQLite\nStorage", "Database"),
        (media_rect, "Media\nProcessor", "ffmpeg"),
        (dash_rect, "Main\nDashboard", "UI Thread"),
    ]

    for rect, title, subtitle in nodes:
        # Draw Box (Card Style)
        painter.setPen(meta_pen)
        painter.setBrush(QBrush(CARD_BG))
        painter.drawRoundedRect(rect, 8, 8)

        # Draw Title
        painter.setPen(QPen(TEXT_COLOR))
        painter.setFont(title_font)
        painter.drawText(
            rect.adjusted(10, 10, -10, -10),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            title
        )

        # Draw Subtitle
        painter.setPen(meta_pen)
        painter.setFont(QFont(FONT_FAMILY, 10))
        painter.drawText(
            rect.adjusted(10, 50, -10, -10),
            Qt.AlignmentFlag.AlignCenter,
            subtitle
        )

    # 2. Draw Connections (Glowing Lines)
    painter.setPen(glow_pen)
    painter.setFont(QFont(FONT_FAMILY, 9))

    # Watcher -> DB
    painter.drawLine(QPointF(230, 190), QPointF(270, 100))
    painter.drawText(230, 120, "1. save_text()")

    # Watcher -> Media
    painter.drawLine(QPointF(230, 190), QPointF(270, 270))
    painter.drawText(230, 250, "1. save_media()")

    # DB -> Dashboard
    painter.drawLine(QPointF(480, 100), QPointF(570, 170))
    painter.drawText(500, 120, "2. get_item()")

    # Media -> Dashboard
    painter.drawLine(QPointF(480, 270), QPointF(570, 170))
    painter.drawText(500, 250, "2. thumb_ready()")

    painter.end()

    # Save
    out_path = os.path.join(ASSETS_DIR, "demo-architecture.png")
    px.save(out_path)
    print(f"[DocAssets] Diagram saved: {out_path}")


if __name__ == "__main__":
    # QPainter needs a QApplication context
    app = QApplication(sys.argv)
    
    generate_architecture_diagram()
    # Add functions here for #1 (UI), #3 (Lazy), #4 (Video), #5 (Pytest)

    # Do not exit app context until painter is done