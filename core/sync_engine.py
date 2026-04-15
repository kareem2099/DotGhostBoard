"""
SyncEngine — E2EE Clipboard Push for DotGhostBoard v1.5.0
───────────────────────────────────────────────────────────
When a new clipboard item is captured, SyncEngine pushes it to all
trusted peers over HTTP using AES-256-GCM encryption with the
per-peer shared_secret established during pairing.

Wire format for POST /api/sync:
    {
        "node_id":   "<local node id>",
        "item_type": "text",
        "payload":   "<base64url: [12b nonce][ciphertext+16b GCM tag]>"
    }
"""
from __future__ import annotations

import os
import base64
import threading
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ── Encryption helpers ─────────────────────────────────────────────────────

def _encrypt_for_peer(plaintext: str, shared_secret_hex: str) -> str:
    """
    AES-256-GCM encrypt plaintext using the peer's shared secret.
    Returns base64-encoded  [12b nonce][ciphertext+tag].
    """
    key = bytes.fromhex(shared_secret_hex)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_from_peer(payload: str, shared_secret_hex: str) -> Optional[str]:
    """
    Decrypt a payload received from a trusted peer.
    Returns plaintext string, or None on failure (wrong key / tampered).
    """
    try:
        raw = base64.b64decode(payload)
        nonce, ct = raw[:12], raw[12:]
        key = bytes.fromhex(shared_secret_hex)
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        return None


# ── Sync Engine ────────────────────────────────────────────────────────────

class SyncEngine:
    """
    Pushes new clipboard items to all trusted peers in background threads.
    Thread-safe: push() can be called from any thread.
    """

    def __init__(self, local_node_id: str, api_port: int):
        self.local_node_id = local_node_id
        self.api_port = api_port

    def push(self, item_type: str, content: str) -> None:
        """
        Encrypt and push a clipboard item to every trusted peer.
        Each peer gets its own background thread so one slow/dead peer
        does not block the others.
        """
        if item_type not in ("text",):
            # Only text sync for now; image sync in a future phase
            return

        from core import storage
        peers = storage.get_all_trusted_peers()
        if not peers:
            return

        for peer in peers:
            t = threading.Thread(
                target=self._push_to_peer,
                args=(peer, item_type, content),
                daemon=True,
            )
            t.start()

    # ── Internal ───────────────────────────────────────────────────────────

    def _push_to_peer(self, peer: dict, item_type: str, content: str) -> None:
        """Send one encrypted item to a single peer (runs in daemon thread)."""
        import requests

        node_id = peer.get("node_id", "")
        # ip_address might be a full URL (e.g. "http://x.x.x.x:port") or a plain IP
        ip_raw = peer.get("ip_address", "")
        shared_secret = peer.get("shared_secret", "")

        if not ip_raw or not shared_secret or not node_id:
            return

        # Normalize: build the base URL
        if ip_raw.startswith("http"):
            # Strip old port if embedded, replace with current api_port
            base = ip_raw.rstrip("/")
        else:
            base = f"http://{ip_raw}:{self.api_port}"

        try:
            payload = _encrypt_for_peer(content, shared_secret)
            resp = requests.post(
                f"{base}/api/sync",
                json={
                    "node_id":   self.local_node_id,
                    "item_type": item_type,
                    "payload":   payload,
                },
                timeout=5,
            )
            if resp.status_code == 201:
                print(f"[Sync] ✓ Pushed to {node_id} ({base})")
            else:
                print(f"[Sync] ✗ Peer {node_id} returned {resp.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"[Sync] ✗ Peer {node_id} unreachable at {base}")
        except Exception as exc:
            print(f"[Sync] ✗ Error pushing to {node_id}: {exc}")
