"""
ui/controllers package
──────────────────────
Stateful behavioral controllers for DotGhostBoard UI components.
"""

from .collection_controller import CollectionController
from .security_controller import SecurityController
from .sync_controller import SyncController
from .history_controller import HistoryController
from .update_controller import UpdateController
from .coordination import wire_dashboard_controllers

__all__ = [
    "CollectionController",
    "SecurityController",
    "SyncController",
    "HistoryController",
    "UpdateController",
    "wire_dashboard_controllers",
]

