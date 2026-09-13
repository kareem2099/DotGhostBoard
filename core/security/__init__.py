"""
core/security
─────────────
Security subsystems: Secret detection, Vault zero-knowledge storage, and session policy.
"""

from core.security.detector import SecretDetector, SecretMatch
from core.security.vault import (
    VaultService,
    VaultRepository,
    VaultItem,
    VaultSummary,
    VaultLockedError,
)

__all__ = [
    "SecretDetector",
    "SecretMatch",
    "VaultService",
    "VaultRepository",
    "VaultItem",
    "VaultSummary",
    "VaultLockedError",
]
