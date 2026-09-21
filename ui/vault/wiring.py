"""
ui/vault/wiring.py
──────────────────
Wires The Vault subsystem into the Dashboard window.
Unifies drawer resize handling, keyboard shortcuts, and signal routing.

v2.0.0 Cerberus — Phase 7 Vault UI Subsystem.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QBoxLayout

from core.constants import VAULT_DRAWER_WIDTH
from ui.vault.vault_controller import VaultController
from ui.vault.vault_panel import VaultPanel

if TYPE_CHECKING:
    from ui.dashboard import Dashboard


def attach_vault(dashboard: Dashboard, container_layout: QBoxLayout) -> tuple[VaultController, VaultPanel]:
    """
    Instantiate and attach The Vault controller, drawer panel, shortcut, and signals
    to the Dashboard window. Encapsulates drawer width adjustments on visibility change.
    """
    controller = VaultController(vault_service=dashboard.security_service.vault, parent=dashboard)
    controller.status_message.connect(dashboard.statusBar().showMessage)

    panel = VaultPanel(controller=controller, parent=dashboard)
    panel.hide()
    container_layout.addWidget(panel)

    shortcut = QShortcut(QKeySequence("Ctrl+Shift+V"), dashboard)

    def _toggle() -> None:
        panel.toggle_panel()

    def _on_visibility(shown: bool) -> None:
        if not dashboard.isVisible():
            return
        if dashboard.isMaximized() or dashboard.isFullScreen():
            dashboard.setMinimumWidth(400 + (VAULT_DRAWER_WIDTH if shown else 0))
            return
        if not shown:
            dashboard.setMinimumWidth(400)
        delta = VAULT_DRAWER_WIDTH if shown else -VAULT_DRAWER_WIDTH
        new_width = max(400, dashboard.width() + delta)
        dashboard.resize(new_width, dashboard.height())
        if shown:
            dashboard.setMinimumWidth(400 + VAULT_DRAWER_WIDTH)

    shortcut.activated.connect(_toggle)

    if hasattr(dashboard, "topbar") and dashboard.topbar:
        dashboard.topbar.vault_clicked.connect(_toggle)

    if hasattr(dashboard, "sidebar_widget") and dashboard.sidebar_widget:
        dashboard.sidebar_widget.vault_toggle_requested.connect(_toggle)

    controller.secret_copy_starting.connect(
        lambda: getattr(dashboard, "watcher", None) and dashboard.watcher.mark_self_paste()
    )
    controller.panel_visibility_changed.connect(_on_visibility)

    # Expose attributes on dashboard instance for backward compatibility and tests
    dashboard.vault_controller = controller
    dashboard.vault_panel = panel
    dashboard.vault_shortcut = shortcut
    dashboard._toggle_vault = _toggle
    dashboard._on_vault_visibility = _on_visibility

    return controller, panel
