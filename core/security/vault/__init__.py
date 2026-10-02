"""
core/security/vault
───────────────────
The Vault package: zero-knowledge encrypted credential repository (vault.db).
"""

from core.security.vault.database import get_vault_db_path, init_vault_db
from core.security.vault.models import VaultItem, VaultSummary
from core.security.vault.repository import VaultRepository
from core.security.vault.service import VaultService, VaultLockedError
from core.security.vault.backup import export_vault_package, import_vault_package

__all__ = [
    "get_vault_db_path",
    "init_vault_db",
    "VaultItem",
    "VaultSummary",
    "VaultRepository",
    "VaultService",
    "VaultLockedError",
    "export_vault_package",
    "import_vault_package",
]
