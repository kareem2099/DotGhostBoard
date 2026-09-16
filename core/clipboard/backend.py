"""
core/clipboard/backend.py
─────────────────────────
Protocol for low-level clipboard monitoring backends (Qt, Wayland wlr-data-control, etc.).
"""

from typing import Protocol, Callable, Any
from .events import ClipboardEvent


class ClipboardBackend(Protocol):
    """
    Minimal protocol for monitoring system clipboard.
    Backends produce ClipboardEvent instances and deliver them to a registered callback.
    """

    def start(self) -> None:
        """Start listening to clipboard events."""
        ...

    def stop(self) -> None:
        """Stop listening to clipboard events."""
        ...

    def set_on_event(self, callback: Callable[[ClipboardEvent], None]) -> None:
        """Register the consumer callback for captured events."""
        ...

    def mark_self_paste(self) -> None:
        """Notify backend to ignore subsequent self-paste actions."""
        ...

    def paste_item(self, item: dict[str, Any]) -> None:
        """Restore item back to the system clipboard."""
        ...
