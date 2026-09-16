"""
core/clipboard
──────────────
Architecture layer for clipboard ingestion, backend abstraction, and policy pipelines.
"""

from .events import Action, ClipboardEvent, CaptureDecision
from .backend import ClipboardBackend
from .pipeline import ClipboardPipeline
from .backends.qt_backend import QtClipboardBackend

__all__ = [
    "Action",
    "ClipboardEvent",
    "CaptureDecision",
    "ClipboardBackend",
    "ClipboardPipeline",
    "QtClipboardBackend",
]
