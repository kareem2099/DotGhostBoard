"""
core/clipboard/pipeline.py
──────────────────────────
Pure decision engine for evaluating clipboard capture events.
Free of Qt GUI dependencies and suitable for headless execution and unit tests.
"""

from typing import Callable, Any
from .events import ClipboardEvent, CaptureDecision, Action


class ClipboardPipeline:
    """
    Evaluates ClipboardEvents through configured policy interceptors:
    1. Validation & Empty Check
    2. App Policy (AppFilter)
    3. Paranoia Mode (Zero-Logging short-circuit)
    4. Secret Candidate Detection (Future v2.0 hook)
    5. Persistence Acceptance (SAVE_NORMAL)
    """

    def __init__(
        self,
        app_filter_checker: Callable[[str | None], bool] | None = None,
        paranoia_checker: Callable[[], bool] | None = None,
        secret_detector: Callable[[str], bool] | None = None,
    ):
        self._app_filter_checker = app_filter_checker
        self._paranoia_checker = paranoia_checker
        self._secret_detector = secret_detector

    def set_app_filter_checker(self, checker: Callable[[str | None], bool] | None) -> None:
        self._app_filter_checker = checker

    def set_paranoia_checker(self, checker: Callable[[], bool] | None) -> None:
        self._paranoia_checker = checker

    def set_secret_detector(self, detector: Callable[[str], bool] | None) -> None:
        self._secret_detector = detector

    def process(self, event: ClipboardEvent) -> CaptureDecision:
        """
        Evaluate a single event and return a deterministic decision.
        """
        # 1. Validation
        if event.content_type == "text":
            if not isinstance(event.content, str) or not event.content.strip():
                return CaptureDecision(action=Action.IGNORE, reason="empty_text")

        # 2. App Filter Policy
        if self._app_filter_checker is not None:
            if not self._app_filter_checker(event.source_app):
                return CaptureDecision(action=Action.IGNORE, reason="app_filter")

        # 3. Paranoia Mode (Strict early-exit: no OCR, no secret detection, no DB)
        if self._paranoia_checker is not None and self._paranoia_checker():
            return CaptureDecision(action=Action.IGNORE, reason="paranoia_mode")

        # 4. Secret Candidate Detection (v2.0 insertion point)
        if (
            self._secret_detector is not None
            and event.content_type == "text"
            and isinstance(event.content, str)
            and self._secret_detector(event.content)
        ):
            return CaptureDecision(
                action=Action.SECRET_CANDIDATE,
                reason="secret_detected",
                payload=event,
            )

        # 5. Default Acceptance
        return CaptureDecision(
            action=Action.SAVE_NORMAL,
            reason="valid_capture",
            payload=event,
        )
