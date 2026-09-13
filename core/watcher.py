"""
core/watcher.py
───────────────
Orchestrates clipboard monitoring by coordinating a ClipboardBackend,
a ClipboardPipeline (policy engine), and persistence/thumbnailing.
Emits Qt signals to the dashboard on new text, image, or video captures.
"""

from PyQt6.QtCore import QObject, pyqtSignal, QThread
from core import storage, media
from core.clipboard import (
    ClipboardPipeline,
    ClipboardEvent,
    Action,
    ClipboardBackend,
    QtClipboardBackend,
)


# ──────────────────────────────────────────────────────────
# S002: Background thread for video thumbnail extraction
# ──────────────────────────────────────────────────────────
class _ThumbWorker(QThread):
    """Runs ffmpeg in a background thread — never blocks the UI."""
    done = pyqtSignal(int, str)   # (item_id, thumb_path)

    def __init__(self, video_path: str, item_id: int):
        super().__init__()
        self._video_path = video_path
        self._item_id    = item_id

    def run(self):
        try:
            from core.thumbnailer import extract_video_thumb
            thumb = extract_video_thumb(self._video_path, self._item_id)
            if thumb:
                self.done.emit(self._item_id, thumb)
        except Exception as e:
            print(f"[ThumbWorker] {e}")


# ──────────────────────────────────────────────────────────
class ClipboardWatcher(QObject):
    """
    Orchestrator for clipboard events:
    Receives events from ClipboardBackend, validates through ClipboardPipeline,
    persists accepted clips, and signals the UI.
    """

    new_text_captured  = pyqtSignal(int, str)   # (id, text)
    new_image_captured = pyqtSignal(int, str)   # (id, file_path)
    new_video_captured = pyqtSignal(int, str)   # (id, video_path)
    thumb_ready        = pyqtSignal(int, str)   # (id, thumb_path)
    secret_candidate_detected = pyqtSignal(object) # ClipboardEvent candidate

    def __init__(
        self,
        parent=None,
        pipeline: ClipboardPipeline | None = None,
        backend: ClipboardBackend | None = None,
    ):
        super().__init__(parent)
        self._pipeline = pipeline or ClipboardPipeline()
        self._backend = backend or QtClipboardBackend(self)
        self._backend.set_on_event(self._on_clipboard_event)
        self._thumb_workers: list = []       # keep refs so GC doesn't kill threads
        self._running: bool = False

    @property
    def pipeline(self) -> ClipboardPipeline:
        return self._pipeline

    def set_pipeline(self, pipeline: ClipboardPipeline) -> None:
        self._pipeline = pipeline

    @property
    def backend(self) -> ClipboardBackend:
        return self._backend

    def set_backend(self, backend: ClipboardBackend) -> None:
        was_running = self._running
        if was_running:
            self._backend.stop()

        self._backend = backend
        self._backend.set_on_event(self._on_clipboard_event)

        if was_running:
            self._backend.start()

    @property
    def _is_self_paste(self) -> bool:
        """Backward-compatible access for tests inspecting self paste flag."""
        return getattr(self._backend, "_is_self_paste", False)

    @_is_self_paste.setter
    def _is_self_paste(self, value: bool) -> None:
        if hasattr(self._backend, "_is_self_paste"):
            self._backend._is_self_paste = value

    # ─────────────────────────────────────────
    def start(self):
        if self._running:
            return
        storage.init_db()
        self._backend.start()
        self._running = True

    def stop(self):
        if not self._running:
            return
        self._backend.stop()
        self._running = False

    def mark_self_paste(self):
        """Notify backend to avoid capturing the app's own paste action."""
        self._backend.mark_self_paste()

    def paste_item_to_clipboard(self, item: dict):
        """Restore item back to system clipboard via backend."""
        self._backend.paste_item(item)

    # ─────────────────────────────────────────
    def _on_clipboard_event(self, event: ClipboardEvent) -> None:
        """Single processing funnel for all clipboard events."""
        decision = self._pipeline.process(event)

        if decision.action == Action.IGNORE:
            return

        if decision.action == Action.SECRET_CANDIDATE:
            self.secret_candidate_detected.emit(decision.payload)
            return

        # Action.SAVE_NORMAL
        item_id = storage.add_item(
            event.content_type,
            event.content,
            preview=event.preview,
        )

        if event.content_type == "text":
            self.new_text_captured.emit(item_id, event.content)
        elif event.content_type == "image":
            self.new_image_captured.emit(item_id, event.content)
        elif event.content_type == "video":
            self.new_video_captured.emit(item_id, event.content)
            media.log_video_path(event.content)
            self._start_thumb_worker(event.content, item_id)

    # ─────────────────────────────────────────
    # S002: Video thumbnail
    # ─────────────────────────────────────────
    def _start_thumb_worker(self, video_path: str, item_id: int):
        worker = _ThumbWorker(video_path, item_id)
        worker.done.connect(self._on_thumb_done)
        worker.finished.connect(
            lambda: self._thumb_workers.remove(worker)
            if worker in self._thumb_workers else None
        )
        self._thumb_workers.append(worker)
        worker.start()

    def _on_thumb_done(self, item_id: int, thumb_path: str):
        storage.update_preview(item_id, thumb_path)
        self.thumb_ready.emit(item_id, thumb_path)