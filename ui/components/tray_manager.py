"""
ui/components/tray_manager.py
─────────────────────────────
System tray icon & context menu manager for DotGhostBoard Dashboard.

v2.0.0 Cerberus — Phase 6 Dashboard Decomposition.
Owns system tray icon rendering, context menu actions, retry loops,
and tooltip formatting. Communicates with Dashboard via semantic signals.
"""

from typing import Callable, Optional
import time
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QMenu,
    QSystemTrayIcon,
)


class DashboardTrayManager(QObject):
    """
    Manages the QSystemTrayIcon lifecycle, context menu, and tooltips.
    """

    toggle_visibility_requested = pyqtSignal()
    show_requested = pyqtSignal()  # Always shows (never hides) — for notification callbacks
    pause_monitoring_requested = pyqtSignal()
    resume_monitoring_requested = pyqtSignal()
    open_settings_requested = pyqtSignal()
    lock_requested = pyqtSignal()
    unlock_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_widget = parent
        self._tray_retry_count: int = 0
        self.tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._actions: list[QAction] = []
        self._notification_settings = {}
        self._notice_times: dict[str, float] = {}
        self._notification_generation = 0
        self._tray_callback = None

    def configure_notifications(self, settings: dict) -> None:
        preferences = {key: settings.get(key, True) for key in (
            "notifications_enabled", "notifications_security", "notifications_updates",
            "notification_sound_enabled",
        )}
        if preferences == self._notification_settings:
            return
        self._notification_settings = preferences
        self._notification_generation += 1
        self._tray_callback = None
        if not settings.get("notifications_enabled", True):
            from core.notifications import cancel_desktop_notifications
            cancel_desktop_notifications()

    def _notifications_allowed(self, category: str) -> bool:
        settings = self._notification_settings
        return settings.get("notifications_enabled", True) and settings.get(
            f"notifications_{category}", True,
        )

    def _on_message_clicked(self):
        callback, self._tray_callback = self._tray_callback, None
        if callback:
            callback()

    @staticmethod
    def make_tray_icon() -> QIcon:
        """Create a stylized neon ghost icon for the system tray."""
        import os
        from core.paths import resource_path
        icon_path = resource_path("data", "icons", "icon_32.png")
        if os.path.isfile(icon_path):
            return QIcon(icon_path)
        px = QPixmap(32, 32)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#00ff41"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.setPen(QColor("#000000"))
        f = QFont("monospace", 14, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "G")
        p.end()
        return QIcon(px)

    def setup_tray(self):
        """Initialize the QSystemTrayIcon and attach signal handlers."""
        self.tray = QSystemTrayIcon(self.make_tray_icon(), self)
        self.tray.activated.connect(self._on_tray_click)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self._menu = QMenu(self._parent_widget)
        self.tray.setContextMenu(self._menu)
        self.ensure_tray_visible()

    def ensure_tray_visible(self):
        """Ensure the tray icon shows once system tray becomes available."""
        if not self.tray:
            return
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        else:
            if self._tray_retry_count < 10:
                self._tray_retry_count += 1
                delay = min(500 * self._tray_retry_count, 3000)
                QTimer.singleShot(delay, self.ensure_tray_visible)

    def update_menu_and_tooltip(
        self,
        is_locked: bool,
        is_monitoring_paused: bool,
        has_password: bool,
    ):
        """Reconstruct context menu and tooltip based on application state."""
        if not self.tray:
            return

        # ── Tooltip ──
        if is_locked:
            self.tray.setToolTip("DotGhostBoard — 🔒 Locked (Click to unlock)")
        elif is_monitoring_paused:
            self.tray.setToolTip("DotGhostBoard — ⏸ Monitoring paused")
        else:
            self.tray.setToolTip("DotGhostBoard — Monitoring clipboard")

        # ── Context Menu ──
        if self._menu is None:
            self._menu = QMenu(self._parent_widget)
            self.tray.setContextMenu(self._menu)

        menu = self._menu
        menu.clear()
        self._actions.clear()

        show_action = QAction("👻 Open DotGhostBoard", menu)
        show_action.triggered.connect(self.toggle_visibility_requested.emit)
        menu.addAction(show_action)
        self._actions.append(show_action)

        if not is_locked:
            if is_monitoring_paused:
                toggle_monitor_action = QAction("▶ Resume Monitoring", menu)
                toggle_monitor_action.triggered.connect(
                    self.resume_monitoring_requested.emit
                )
            else:
                toggle_monitor_action = QAction("⏸ Pause Monitoring", menu)
                toggle_monitor_action.triggered.connect(
                    self.pause_monitoring_requested.emit
                )
            menu.addAction(toggle_monitor_action)
            self._actions.append(toggle_monitor_action)

            settings_action = QAction("⚙ Settings", menu)
            settings_action.triggered.connect(
                self.open_settings_requested.emit
            )
            menu.addAction(settings_action)
            self._actions.append(settings_action)

        menu.addSeparator()

        if has_password:
            if is_locked:
                lock_action = QAction("🔓 Unlock DotGhostBoard", menu)
                lock_action.triggered.connect(self.unlock_requested.emit)
            else:
                lock_action = QAction("🔒 Lock", menu)
                lock_action.triggered.connect(self.lock_requested.emit)
            menu.addAction(lock_action)
            self._actions.append(lock_action)
            menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)
        self._actions.append(quit_action)

        self.tray.setContextMenu(menu)

    def _on_tray_click(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visibility_requested.emit()

    def show_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = (
            QSystemTrayIcon.MessageIcon.Information
        ),
        timeout: int = 2000,
        action_callback: Optional[Callable[[], None]] = None,
        *,
        category: str = "general",
        action_label: str = "Open DotGhostBoard",
        dedupe_key: str | None = None,
        cooldown: float = 0,
        once: bool = False,
    ):
        """
        Display a desktop notification.
        First attempts native OS / FreeDesktop notification with
        click-to-activate callback.
        Falls back to QSystemTrayIcon.showMessage if native is unavailable.
        """
        from core.notifications import (
            get_default_icon_path,
            send_desktop_notification,
        )

        if not self._notifications_allowed(category):
            return
        now = time.monotonic()
        if dedupe_key in self._notice_times:
            if once or now - self._notice_times[dedupe_key] < cooldown:
                return
        if dedupe_key:
            self._notice_times[dedupe_key] = now
        generation = self._notification_generation

        icon_path = get_default_icon_path(category)
        # Use show_requested (not toggle) so clicking a notification always
        # brings the window up — never accidentally hides it.
        def callback():
            if generation == self._notification_generation and self._notifications_allowed(category):
                (action_callback or self.show_requested.emit)()

        def delivered(success):
            if generation != self._notification_generation or not self._notifications_allowed(category):
                return
            if success:
                return
            if self.tray and self.tray.isVisible() and QSystemTrayIcon.supportsMessages():
                # Tray balloons have no notification ID: route clicks to the latest balloon.
                self._tray_callback = callback
                self.tray.showMessage(title, message, icon, timeout)
            elif dedupe_key:
                self._notice_times.pop(dedupe_key, None)

        sent = send_desktop_notification(
            title=title,
            message=message,
            icon=icon_path,
            timeout_ms=timeout,
            action_callback=callback,
            action_label=action_label,
            sound=self._notification_settings.get("notification_sound_enabled", True),
            on_result=delivered,
        )

        if not sent:
            delivered(False)

    def hide(self):
        if self.tray:
            self.tray.hide()
