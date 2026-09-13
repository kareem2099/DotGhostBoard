"""
core/clipboard/events.py
────────────────────────
Dataclasses and Action Enums for clipboard capture events and pipeline decisions.
Zero GUI framework dependencies.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time


class Action(str, Enum):
    SAVE_NORMAL = "SAVE_NORMAL"
    IGNORE = "IGNORE"
    SECRET_CANDIDATE = "SECRET_CANDIDATE"


@dataclass(frozen=True)
class ClipboardEvent:
    """
    Represents a raw or normalized clipboard capture event.
    """
    content_type: str            # "text", "image", "video"
    content: Any                 # text string or file path
    preview: str | None = None
    source_app: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class CaptureDecision:
    """
    Result of evaluating a ClipboardEvent through the decision pipeline.
    """
    action: Action
    reason: str | None = None
    payload: Any | None = None
