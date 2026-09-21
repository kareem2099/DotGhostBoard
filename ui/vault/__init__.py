"""
ui/vault/__init__.py
────────────────────
The Vault UI subsystem package.

v2.0.0 Cerberus — Phase 7 Vault UI Subsystem.
"""

from ui.vault.secret_card import SecretCard
from ui.vault.secret_dialog import SecretDialog
from ui.vault.unlock_dialog import VaultUnlockDialog
from ui.vault.vault_controller import VaultController
from ui.vault.vault_panel import VaultPanel
from ui.vault.send_to_vault import attach_send_to_vault
from ui.vault.wiring import attach_vault

__all__ = [
    "SecretCard",
    "SecretDialog",
    "VaultController",
    "VaultPanel",
    "VaultUnlockDialog",
    "attach_vault",
    "attach_send_to_vault",
]
