"""
ui/components/__init__.py
─────────────────────────
Reusable UI components for DotGhostBoard Dashboard.

v2.0.0 Cerberus — Phase 6 Dashboard Decomposition.
"""

from ui.components.bulk_toolbar import BulkToolbar
from ui.components.cards_view import CardsView
from ui.components.sidebar import SidebarWidget
from ui.components.topbar import TopBarWidget
from ui.components.tray_manager import DashboardTrayManager

__all__ = [
    "SidebarWidget",
    "TopBarWidget",
    "CardsView",
    "BulkToolbar",
    "DashboardTrayManager",
]
