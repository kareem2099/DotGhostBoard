"""
ui/components/tray_manager.py
─────────────────────────────
System tray icon & context menu manager for DotGhostBoard Dashboard.

v2.0.0 Cerberus — Phase 6 Dashboard Decomposition.
Owns system tray icon rendering, context menu actions, retry loops,
and tooltip formatting. Communicates with Dashboard via semantic signals.
"""

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QMenu,
    QSystemTrayIcon,
)


class DashboardTrayManager(QObject):
    """
    Manages the QSystemTrayIcon lifecycle, context menu, and tooltips.
    """

    toggle_visibility_requested = pyqtSignal()
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

    @staticmethod
    def make_tray_icon() -> QIcon:
        """Create a stylized neon ghost icon for the system tray."""
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
        menu = QMenu(self._parent_widget)

        show_action = QAction("👻 Open DotGhostBoard", menu)
        show_action.triggered.connect(self.toggle_visibility_requested.emit)
        menu.addAction(show_action)

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

            settings_action = QAction("⚙ Settings", menu)
            settings_action.triggered.connect(self.open_settings_requested.emit)
            menu.addAction(settings_action)

        menu.addSeparator()

        if has_password:
            if is_locked:
                lock_action = QAction("🔓 Unlock DotGhostBoard", menu)
                lock_action.triggered.connect(self.unlock_requested.emit)
            else:
                lock_action = QAction("🔒 Lock", menu)
                lock_action.triggered.connect(self.lock_requested.emit)
            menu.addAction(lock_action)
            menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)

    def _on_tray_click(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visibility_requested.emit()

    def show_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        timeout: int = 2000,
    ):
        if self.tray and self.tray.isVisible():
            self.tray.showMessage(title, message, icon, timeout)

    def hide(self):
        if self.tray:
            self.tray.hide()
