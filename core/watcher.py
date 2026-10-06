"""
core/watcher.py
───────────────
Orchestrates clipboard monitoring by coordinating a ClipboardBackend,
a ClipboardPipeline (policy engine), and persistence/thumbnailing.
Emits Qt signals to the dashboard on new text, image, or video captures.
"""

import time
from PyQt6.QtCore import QObject, pyqtSignal, QThread
from core import storage, media
from core.clipboard import (
    ClipboardPipeline,
    ClipboardEvent,
    Action,
    ClipboardBackend,
    QtClipboardBackend,
)
from core.security.auto_tagger import apply_auto_tags


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
    known_secret_detected = pyqtSignal(object)
    vault_check_required = pyqtSignal(object)
    primary_fragment_replaced = pyqtSignal(int)   # (old_item_id)

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
        self._vault_check_pending: bool = False
        self._capture_sound_enabled: bool = False
        self._last_primary_id: int | None = None
        self._last_primary_text: str | None = None
        self._last_primary_time: float = 0.0

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
        self._last_primary_id = None

    def mark_self_paste(self):
        """Notify backend to avoid capturing the app's own paste action."""
        self._backend.mark_self_paste()

    def recheck_clipboard(self):
        if not self._vault_check_pending:
            return
        recheck = getattr(self._backend, "recheck_clipboard", None)
        if recheck:
            self._vault_check_pending = False
            recheck()

    def paste_item_to_clipboard(self, item: dict):
        """Restore item back to system clipboard via backend."""
        self._backend.paste_item(item)

    def set_monitor_primary(self, enabled: bool) -> None:
        """Enable or disable primary selection monitoring on the backend."""
        if not enabled:
            self._last_primary_id = None
        if hasattr(self._backend, "set_monitor_primary"):
            self._backend.set_monitor_primary(enabled)

    def set_sync_primary_to_clipboard(self, enabled: bool) -> None:
        """Configure whether primary mouse selection is synced to system CLIPBOARD (Ctrl+V)."""
        if hasattr(self._backend, "set_sync_primary_to_clipboard"):
            self._backend.set_sync_primary_to_clipboard(enabled)

    def set_capture_sound_enabled(self, enabled: bool) -> None:
        """Enable or disable subtle audio feedback on capture."""
        self._capture_sound_enabled = enabled

    # ─────────────────────────────────────────
    def _on_clipboard_event(self, event: ClipboardEvent) -> None:
        """Single processing funnel for all clipboard events."""
        decision = self._pipeline.process(event)
        self._vault_check_pending = decision.action == Action.VAULT_CHECK_REQUIRED

        if decision.action == Action.IGNORE:
            return

        if decision.action == Action.SECRET_CANDIDATE:
            self.secret_candidate_detected.emit(decision.payload)
            return
        if decision.action == Action.KNOWN_SECRET:
            self.known_secret_detected.emit(decision.payload)
            return
        if decision.action == Action.VAULT_CHECK_REQUIRED:
            self.vault_check_required.emit(decision.payload)
            return

        # Smart primary selection consolidation:
        # If user extended or refined an existing mouse selection within 3.0s, replace intermediate fragment.
        now = time.monotonic()
        is_primary = getattr(event, "source_app", "") == "primary_selection"

        # Only freshly inserted PRIMARY fragments belong to this drag. A content
        # match can return an older saved clip that must never be consolidated.
        existing = storage.get_item_by_content(event.content) if is_primary else None
        item_id = storage.add_item(
            event.content_type,
            event.content,
            preview=event.preview,
        )

        if is_primary and self._last_primary_id is not None and self._last_primary_id != item_id:
            if (
                (now - self._last_primary_time) < 3.0
                and self._last_primary_text
                and (
                    event.content.startswith(self._last_primary_text)
                    or event.content.endswith(self._last_primary_text)
                    or self._last_primary_text.startswith(event.content)
                )
            ):
                try:
                    if storage.delete_item(self._last_primary_id):
                        self.primary_fragment_replaced.emit(self._last_primary_id)
                except Exception:
                    pass

        if is_primary:
            self._last_primary_id = item_id if existing is None else None
            self._last_primary_text = event.content
            self._last_primary_time = now
            try:
                storage.add_tag(item_id, "mouse")
            except Exception:
                pass
        else:
            self._last_primary_id = None
            self._last_primary_text = None
            self._last_primary_time = 0.0

        if self._capture_sound_enabled:
            try:
                from core.audio import play_capture_sound
                play_capture_sound()
            except Exception:
                pass

        if event.content_type == "text":
            # Auto-tag new text items (non-blocking: runs in same thread, sub-ms)
            apply_auto_tags(item_id, event.content)
            # Auto-purge: respect the user's "Max history" setting from Settings → General
            try:
                from ui.settings._io import load_settings
                from core.constants import HISTORY_PURGE_CHUNK
                _max = load_settings().get("max_history", 500)
                storage.auto_purge_history(max_items=_max, chunk=HISTORY_PURGE_CHUNK)
            except Exception:
                pass  # never crash the capture pipeline over a purge failure
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
