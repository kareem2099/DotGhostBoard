"""
core/storage/repositories/peers.py
──────────────────────────────────
Repository for trusted peer devices and sync credentials.
"""

from datetime import datetime
from ..database import _db


def add_trusted_peer(node_id: str, device_name: str, shared_secret: str, ip: str = None) -> None:
    """Store a newly paired peer and its shared encryption key."""
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO trusted_peers (node_id, device_name, shared_secret, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (node_id, device_name, shared_secret, ip, now))


def get_trusted_peer(node_id: str) -> dict | None:
    """Retrieve peer info and shared secret by node_id."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM trusted_peers WHERE node_id = ?", (node_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_trusted_peers() -> list[dict]:
    """Retrieve a list of all paired devices."""
    with _db() as conn:
        cursor = conn.execute("SELECT * FROM trusted_peers ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


def remove_trusted_peer(node_id: str) -> bool:
    """Un-pair a device."""
    with _db() as conn:
        cursor = conn.execute("DELETE FROM trusted_peers WHERE node_id = ?", (node_id,))
        return cursor.rowcount > 0


def is_peer_trusted(node_id: str) -> bool:
    """Fast check for paired status."""
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM trusted_peers WHERE node_id = ? LIMIT 1", (node_id,)
        ).fetchone()
        return bool(row)
