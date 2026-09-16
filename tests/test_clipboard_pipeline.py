"""
tests/test_clipboard_pipeline.py
────────────────────────────────
Unit tests for ClipboardPipeline decision engine and event evaluation.
Runs purely in memory with zero GUI dependencies.
"""

import pytest
from core.clipboard.events import ClipboardEvent, CaptureDecision, Action
from core.clipboard.pipeline import ClipboardPipeline


class TestClipboardPipeline:
    def test_normal_text_event_is_accepted(self):
        pipeline = ClipboardPipeline()
        event = ClipboardEvent(content_type="text", content="print('hello')")
        decision = pipeline.process(event)

        assert decision.action == Action.SAVE_NORMAL
        assert decision.reason == "valid_capture"
        assert decision.payload == event

    def test_empty_or_whitespace_text_is_ignored(self):
        pipeline = ClipboardPipeline()
        for empty_val in ["", "   ", "\n\t"]:
            event = ClipboardEvent(content_type="text", content=empty_val)
            decision = pipeline.process(event)
            assert decision.action == Action.IGNORE
            assert decision.reason == "empty_text"

    def test_media_events_accepted(self):
        pipeline = ClipboardPipeline()
        img_event = ClipboardEvent(content_type="image", content="/path/to/shot.png", preview="/path/to/shot.png")
        assert pipeline.process(img_event).action == Action.SAVE_NORMAL

        vid_event = ClipboardEvent(content_type="video", content="/path/to/rec.mp4")
        assert pipeline.process(vid_event).action == Action.SAVE_NORMAL

    def test_app_filter_blocking(self):
        # App filter blocks if app name contains 'keepass'
        checker = lambda app: app != "keepassxc"
        pipeline = ClipboardPipeline(app_filter_checker=checker)

        allowed_event = ClipboardEvent(content_type="text", content="normal text", source_app="gedit")
        assert pipeline.process(allowed_event).action == Action.SAVE_NORMAL

        blocked_event = ClipboardEvent(content_type="text", content="password123", source_app="keepassxc")
        decision = pipeline.process(blocked_event)
        assert decision.action == Action.IGNORE
        assert decision.reason == "app_filter"

    def test_paranoia_mode_short_circuit(self):
        paranoia_state = {"enabled": True}
        checker = lambda: paranoia_state["enabled"]
        pipeline = ClipboardPipeline(paranoia_checker=checker)

        event = ClipboardEvent(content_type="text", content="secret or normal text")
        decision = pipeline.process(event)
        assert decision.action == Action.IGNORE
        assert decision.reason == "paranoia_mode"

        # Turn paranoia off
        paranoia_state["enabled"] = False
        decision = pipeline.process(event)
        assert decision.action == Action.SAVE_NORMAL

    def test_secret_detection_hook(self):
        # Detector flags tokens starting with 'ghp_'
        detector = lambda text: text.startswith("ghp_")
        pipeline = ClipboardPipeline(secret_detector=detector)

        normal_event = ClipboardEvent(content_type="text", content="Hello world")
        assert pipeline.process(normal_event).action == Action.SAVE_NORMAL

        secret_event = ClipboardEvent(content_type="text", content="ghp_1234567890abcdef")
        decision = pipeline.process(secret_event)
        assert decision.action == Action.SECRET_CANDIDATE
        assert decision.reason == "secret_detected"
        assert decision.payload == secret_event

    def test_paranoia_takes_precedence_over_secret_detection(self):
        # Paranoia must exit early before secret detector is even consulted
        detector_called = []

        def spy_detector(text):
            detector_called.append(text)
            return True

        pipeline = ClipboardPipeline(
            paranoia_checker=lambda: True,
            secret_detector=spy_detector,
        )

        event = ClipboardEvent(content_type="text", content="ghp_token")
        decision = pipeline.process(event)
        assert decision.action == Action.IGNORE
        assert decision.reason == "paranoia_mode"
        # Secret detector was never evaluated
        assert len(detector_called) == 0
