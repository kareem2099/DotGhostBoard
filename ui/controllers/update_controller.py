"""
ui/controllers/update_controller.py
───────────────────────────────────
Controller managing background update checking, release asset resolution,
and the updater modal dialog lifecycle.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class UpdateCheckerThread(QThread):
    """Background worker querying GitHub releases for newer application versions."""
    update_found = pyqtSignal(dict, str)  # update_info, asset_url

    def __init__(self, channel: str = "stable", parent=None):
        super().__init__(parent)
        self._channel = channel

    def run(self):
        from core.config import APP_VERSION
        from core.updater import check_for_updates, identify_platform_asset

        update_info = check_for_updates(APP_VERSION, self._channel)
        if update_info:
            asset_url = identify_platform_asset(update_info["assets"])
            if asset_url:
                self.update_found.emit(update_info, asset_url)


class UpdateController(QObject):
    """
    Behavioral controller orchestrating update checks and user prompt dialogues.
    """
    update_found = pyqtSignal(dict, str)  # update_info, asset_url
    status_message = pyqtSignal(str)

    def __init__(
        self,
        parent_window: Optional[QWidget] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._parent_window = parent_window
        self._update_thread: Optional[UpdateCheckerThread] = None
        self._pending_update_info: Optional[dict] = None
        self._pending_asset_url: Optional[str] = None

    @property
    def update_thread(self) -> Optional[UpdateCheckerThread]:
        return self._update_thread

    @property
    def pending_update_info(self) -> Optional[dict]:
        return self._pending_update_info

    @property
    def pending_asset_url(self) -> Optional[str]:
        return self._pending_asset_url

    def check_for_updates(self, channel: str = "stable") -> None:
        """Spawn background check thread if not already running."""
        if self._update_thread and self._update_thread.isRunning():
            return
        self._update_thread = UpdateCheckerThread(channel=channel, parent=self)
        self._update_thread.update_found.connect(self._on_update_found)
        self._update_thread.finished.connect(self._on_thread_finished)
        self._update_thread.start()

    def _on_thread_finished(self) -> None:
        if self._update_thread:
            self._update_thread.deleteLater()
            self._update_thread = None

    def _on_update_found(self, update_info: dict, asset_url: str) -> None:
        self._pending_update_info = update_info
        self._pending_asset_url = asset_url
        self.update_found.emit(update_info, asset_url)

    def show_updater_dialog(self, parent_widget: Optional[QWidget] = None) -> None:
        """Display the modal UpdaterDialog with release notes and action buttons."""
        if not self._pending_update_info or not self._pending_asset_url:
            return
        from ui.updater_dialog import UpdaterDialog

        dlg_parent = parent_widget or self._parent_window
        dialog = UpdaterDialog(self._pending_update_info, self._pending_asset_url, dlg_parent)
        dialog.exec()

    def cleanup(self) -> None:
        """Terminate update thread on application exit."""
        try:
            if self._update_thread and self._update_thread.isRunning():
                self._update_thread.terminate()
                self._update_thread.wait(1000)
        except RuntimeError:
            pass
