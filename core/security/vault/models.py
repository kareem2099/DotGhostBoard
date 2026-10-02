"""
core/security/vault/models.py
─────────────────────────────
Data models for The Vault subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from core.crypto import decrypt


# ── Shared expiry logic ───────────────────────────────────────────────────────

class _ExpiryMixin:
    """Mixin that provides expiry helpers for models carrying an `expires_at` field."""

    expires_at: Optional[str]  # declared on the concrete class

    @property
    def is_expired(self) -> bool:
        """Return True if the item's expiry date is in the past."""
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            now = datetime.now(exp.tzinfo) if exp.tzinfo else datetime.now()
            return now > exp
        except Exception:
            return False

    @property
    def days_remaining(self) -> Optional[int]:
        """Return the number of whole days until expiry, or None if no expiry is set."""
        if not self.expires_at:
            return None
        try:
            exp = datetime.fromisoformat(self.expires_at)
            now = datetime.now(exp.tzinfo) if exp.tzinfo else datetime.now()
            return (exp - now).days
        except Exception:
            return None


# ── Models ────────────────────────────────────────────────────────────────────

@dataclass
class VaultItem(_ExpiryMixin):
    """Full record from vault_items table."""
    id: Optional[int]
    title: str
    category: str
    ciphertext: str
    metadata_encrypted: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None

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
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class VaultSummary(_ExpiryMixin):
    """Summary model for UI listings (metadata: title, category, timestamps without payload)."""
    id: int
    title: str
    category: str
    created_at: str
    updated_at: str
    expires_at: Optional[str] = None
