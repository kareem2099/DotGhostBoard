"""
core/clipboard/backends
───────────────────────
Platform-specific clipboard listeners.
"""

from .qt_backend import QtClipboardBackend

__all__ = ["QtClipboardBackend"]
