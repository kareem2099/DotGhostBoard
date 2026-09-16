"""
core/security/vault/models.py
─────────────────────────────
Data models for The Vault subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from core.crypto import decrypt


@dataclass
class VaultItem:
    """Full record from vault_items table."""
    id: Optional[int]
    title: str
    category: str
    ciphertext: str
    metadata_encrypted: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def decrypt_payload(self, key: bytes) -> str:
        """Decrypt ciphertext using the domain-separated vault key."""
        return decrypt(self.ciphertext, key)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "ciphertext": self.ciphertext,
            "metadata_encrypted": self.metadata_encrypted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class VaultSummary:
    """Summary model for UI listings (metadata: title, category, timestamps without payload)."""
    id: int
    title: str
    category: str
    created_at: str
    updated_at: str
