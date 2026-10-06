"""Remove confirmed Vault duplicates from public history without copying Vault data."""

import logging

from core import storage
from core.crypto import decrypt

logger = logging.getLogger(__name__)


def remove_vault_history(dashboard, plaintext: str | None = None) -> None:
    # Snapshot before deleting so offsets cannot skip rows (including pinned cards).
    items = []
    offset = 0
    while True:
        page = storage.get_all_items(limit=200, offset=offset)
        items.extend(page)
        if len(page) < 200:
            break
        offset += len(page)
    key = dashboard.security_service.active_key
    controller = getattr(dashboard, "history_controller", None)
    removed = False
    for item in items:
        if item.get("type") != "text":
            continue
        value = item.get("content", "")
        if item.get("is_secret"):
            if key is None:
                continue
            try:
                value = decrypt(value, key)
            except Exception:
                continue
        try:
            matches = (
                value.strip() == plaintext.strip() if plaintext is not None
                else dashboard.security_service.vault.match_clipboard_secret(value) is True
            )
            if matches and storage.delete_item(item["id"], secure=True, force=True):
                removed = True
                if controller:
                    controller.remove_card(item["id"])
        except Exception:
            logger.warning("Could not remove a protected history entry", exc_info=True)
    if removed and controller:
        controller.refresh_stats()
