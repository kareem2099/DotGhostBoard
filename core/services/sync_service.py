"""
core/services/sync_service.py
─────────────────────────────
Service orchestrating peer trust, synchronization, and pairing notifications.
"""

from __future__ import annotations

import threading
from typing import Optional
from core import storage


class SyncService:
    """Business logic and network orchestration for peer synchronization."""

    def __init__(self, local_node_id: str = "", api_port: int = 9090, storage_mod=None):
        self._local_node_id = local_node_id
        self._api_port = api_port
        self._storage = storage_mod or storage
        self._sync_engine = None
        if local_node_id:
            self.configure(local_node_id, api_port)

    def configure(self, local_node_id: str, api_port: int = 9090) -> None:
        """Update node configuration and initialize or re-initialize SyncEngine."""
        self._local_node_id = local_node_id
        self._api_port = api_port
        if local_node_id:
            from core.sync_engine import SyncEngine
            self._sync_engine = SyncEngine(local_node_id=local_node_id, api_port=api_port)
        else:
            self._sync_engine = None

    def push_text(self, text: str) -> None:
        """Broadcast text item to connected trusted peers."""
        if self._sync_engine:
            self._sync_engine.push("text", text)

    def is_peer_trusted(self, node_id: str) -> bool:
        """Check whether node_id is in trusted peers."""
        return self._storage.is_peer_trusted(node_id)

    def get_trusted_peer(self, node_id: str) -> Optional[dict]:
        """Fetch trusted peer details."""
        return self._storage.get_trusted_peer(node_id)

    def get_trusted_peers(self) -> list[dict]:
        """Fetch list of all trusted peers."""
        return self._storage.get_all_trusted_peers()

    def remove_trusted_peer(self, node_id: str) -> bool:
        """Remove peer from trusted store."""
        return self._storage.remove_trusted_peer(node_id)

    def unpair_peer(self, node_id: str, notify: bool = True) -> bool:
        """
        Unpair trusted peer. Optionally dispatches background notification to the peer.
        """
        peer_info = self.get_trusted_peer(node_id)
        if not peer_info:
            return False

        if notify:
            self._notify_peer_unpair_async(peer_info)

        return self.remove_trusted_peer(node_id)

    def _notify_peer_unpair_async(self, peer_info: dict) -> None:
        """Send background HTTP notification to peer informing them of unpair."""
        def _target():
            try:
                import requests
                from core.sync_engine import _encrypt_for_peer

                shared_secret = peer_info.get("shared_secret")
                peer_url = peer_info.get("ip_address")
                if not peer_url or not shared_secret:
                    return

                payload = _encrypt_for_peer("unpair", shared_secret)
                requests.post(
                    f"{peer_url}/api/pair/unpair",
                    json={"node_id": self._local_node_id, "payload": payload},
                    timeout=3,
                )
            except Exception:
                pass  # Best effort unpair notice

        threading.Thread(target=_target, daemon=True).start()
