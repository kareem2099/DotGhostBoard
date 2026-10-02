"""
core/security
─────────────
Security subsystems: Secret detection, Vault zero-knowledge storage,
auto-tagging engine, and session policy.
"""

from core.security.detector import SecretDetector, SecretMatch
from core.security.auto_tagger import detect_tags, apply_auto_tags
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
    "detect_tags",
    "apply_auto_tags",
    "VaultService",
    "VaultRepository",
    "VaultItem",
    "VaultSummary",
    "VaultLockedError",
]
