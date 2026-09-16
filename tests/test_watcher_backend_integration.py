"""
tests/test_watcher_backend_integration.py
─────────────────────────────────────────
Integration tests verifying that ClipboardWatcher properly orchestrates
ClipboardBackend and ClipboardPipeline, enforcing boundaries and ensuring
ignored / secret candidate events never touch persistent storage.
"""

import pytest
from core.clipboard.events import ClipboardEvent
from core.clipboard.pipeline import ClipboardPipeline
from core.watcher import ClipboardWatcher
from core import storage


class MockClipboardBackend:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.self_pasted = False
        self.pasted_items = []
        self._on_event = None

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def set_on_event(self, callback):
        self._on_event = callback

    def mark_self_paste(self):
        self.self_pasted = True

    def paste_item(self, item):
        self.pasted_items.append(item)

    def emit_event(self, event: ClipboardEvent):
        if self._on_event:
            self._on_event(event)


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    db_file = str(tmp_path / "watcher_test.db")
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    storage.init_db()
    return db_file


class TestWatcherBackendIntegration:
    def test_watcher_start_delegates_to_backend(self, isolated_storage):
        backend = MockClipboardBackend()
        watcher = ClipboardWatcher(backend=backend)
        assert not backend.started

        watcher.start()
        assert backend.started is True

    def test_watcher_stop_delegates_to_backend(self, isolated_storage):
        backend = MockClipboardBackend()
        watcher = ClipboardWatcher(backend=backend)
        assert not backend.stopped

        watcher.start()
        watcher.stop()
        assert backend.stopped is True

    def test_watcher_hot_swap_backend_while_running(self, isolated_storage):
        b1 = MockClipboardBackend()
        b2 = MockClipboardBackend()
        watcher = ClipboardWatcher(backend=b1)

        watcher.start()
        assert b1.started is True
        assert not b2.started

        # Hot-swap while running
        watcher.set_backend(b2)
        assert b1.stopped is True
        assert b2.started is True

    def test_watcher_mark_self_paste_and_paste_item_delegate(self, isolated_storage):
        backend = MockClipboardBackend()
        watcher = ClipboardWatcher(backend=backend)

        watcher.mark_self_paste()
        assert backend.self_pasted is True

        watcher.paste_item_to_clipboard({"type": "text", "content": "Hello"})
        assert backend.pasted_items == [{"type": "text", "content": "Hello"}]

    def test_backend_event_flows_through_pipeline_and_storage(self, isolated_storage):
        backend = MockClipboardBackend()
        pipeline = ClipboardPipeline()
        watcher = ClipboardWatcher(backend=backend, pipeline=pipeline)

        captured = []
        watcher.new_text_captured.connect(lambda item_id, text: captured.append((item_id, text)))

        # Simulate backend capturing text
        event = ClipboardEvent(content_type="text", content="First integration capture")
        backend.emit_event(event)

        assert len(captured) == 1
        item_id, text = captured[0]
        assert text == "First integration capture"

        # Verify item actually persisted in DB
        persisted = storage.get_item_by_id(item_id)
        assert persisted is not None
        assert persisted["content"] == "First integration capture"

    def test_ignored_decision_never_persists(self, isolated_storage):
        backend = MockClipboardBackend()
        # Pipeline configured with paranoia = True
        pipeline = ClipboardPipeline(paranoia_checker=lambda: True)
        watcher = ClipboardWatcher(backend=backend, pipeline=pipeline)

        captured = []
        watcher.new_text_captured.connect(lambda item_id, text: captured.append((item_id, text)))

        initial_count = len(storage.get_all_items())

        event = ClipboardEvent(content_type="text", content="Sensitive text during paranoia")
        backend.emit_event(event)

        # Nothing signaled
        assert len(captured) == 0
        # Nothing written to storage
        assert len(storage.get_all_items()) == initial_count

    def test_secret_candidate_never_hits_storage(self, isolated_storage):
        backend = MockClipboardBackend()
        # Secret detector flags strings starting with 'ghp_'
        pipeline = ClipboardPipeline(secret_detector=lambda text: text.startswith("ghp_"))
        watcher = ClipboardWatcher(backend=backend, pipeline=pipeline)

        secret_signals = []
        captured_signals = []
        watcher.secret_candidate_detected.connect(lambda payload: secret_signals.append(payload))
        watcher.new_text_captured.connect(lambda item_id, text: captured_signals.append((item_id, text)))

        initial_count = len(storage.get_all_items())

        secret_token = "ghp_superSecretToken123456789"
        event = ClipboardEvent(content_type="text", content=secret_token)
        backend.emit_event(event)

        # Signal emitted to UI for prompt/Vault redirection
        assert len(secret_signals) == 1
        assert secret_signals[0].content == secret_token

        # Standard capture signal NOT emitted
        assert len(captured_signals) == 0

        # CRITICAL SECURITY BOUNDARY: storage remains untouched!
        assert len(storage.get_all_items()) == initial_count
        assert storage.get_item_by_content(secret_token) is None
