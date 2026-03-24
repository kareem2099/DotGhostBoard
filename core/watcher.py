"""
core/watcher.py
───────────────
Monitors the system clipboard every 500ms.
Emits Qt signals to the dashboard on new text, image, or video captures.
Waterfall logic: Image (Pixels) -> URLs (File Manager) -> Text (Path Check).
"""

import os
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage
from core import storage, media


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
    Monitors the clipboard every 500ms.
    Emits signals to the Dashboard when new content is detected.
    """

    new_text_captured  = pyqtSignal(int, str)   # (id, text)
    new_image_captured = pyqtSignal(int, str)   # (id, file_path)
    new_video_captured = pyqtSignal(int, str)   # (id, video_path)
    thumb_ready        = pyqtSignal(int, str)   # (id, thumb_path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clipboard      = QApplication.clipboard()
        self._last_content   = None          # last seen content signature/signature
        self._is_self_paste  = False         # ignore our own paste events
        self._thumb_workers: list = []       # keep refs so GC doesn't kill threads

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._check_clipboard)

    # ─────────────────────────────────────────
    def start(self):
        storage.init_db()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def mark_self_paste(self):
        """Call before pasting from within the app to avoid re-capture."""
        self._is_self_paste = True

    # ─────────────────────────────────────────
    def _check_clipboard(self):
        try:
            if self._is_self_paste:
                self._is_self_paste = False
                return

            mime = self._clipboard.mimeData()
            if mime is None:
                return

            # ──────────────────────────────────────────────────────────
            # 1. Image Data (Screenshots / Pixels)
            # ──────────────────────────────────────────────────────────
            if mime.hasImage():
                qimage = self._clipboard.image()
                if not qimage.isNull():
                    img_sig = f"{qimage.width()}x{qimage.height()}_{qimage.sizeInBytes()}"
                    if img_sig != self._last_content:
                        self._last_content = img_sig
                        file_path = media.save_image_from_qimage(qimage)
                        if file_path:
                            item_id = storage.add_item("image", file_path, preview=file_path)
                            self.new_image_captured.emit(item_id, file_path)
                    return  # Image pixel data is high priority

            # ──────────────────────────────────────────────────────────
            # 2. Files/URLs (Copies from File Manager like Thunar)
            # ──────────────────────────────────────────────────────────
            if mime.hasUrls():
                urls = mime.urls()
                if urls:
                    local_path = urls[0].toLocalFile()
                    if local_path and os.path.isfile(local_path):
                        if local_path == self._last_content:
                            return
                        self._last_content = local_path
                        
                        img_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
                        vid_exts = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv")
                        
                        low_path = local_path.lower()
                        if low_path.endswith(img_exts):
                            item_id = storage.add_item("image", local_path, preview=local_path)
                            self.new_image_captured.emit(item_id, local_path)
                            return
                        elif low_path.endswith(vid_exts):
                            item_id = storage.add_item("video", local_path)
                            self.new_video_captured.emit(item_id, local_path)
                            media.log_video_path(local_path)
                            self._start_thumb_worker(local_path, item_id)
                            return
                        # If it's a file but not media, treat path as text below

            # ──────────────────────────────────────────────────────────
            # 3. Text content (Plain text or Manual path strings)
            # ──────────────────────────────────────────────────────────
            if mime.hasText():
                text = mime.text().strip()
                if not text or text == self._last_content:
                    return
                self._last_content = text

                # Quick path check (some apps copy path as text, not URL)
                clean_path = text.replace("file://", "").strip()
                if os.path.isfile(clean_path):
                    img_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
                    vid_exts = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv")
                    low_p = clean_path.lower()
                    
                    if low_p.endswith(img_exts):
                        item_id = storage.add_item("image", clean_path, preview=clean_path)
                        self.new_image_captured.emit(item_id, clean_path)
                        return
                    elif low_p.endswith(vid_exts):
                        item_id = storage.add_item("video", clean_path)
                        self.new_video_captured.emit(item_id, clean_path)
                        self._start_thumb_worker(clean_path, item_id)
                        return

                # Normal text
                item_id = storage.add_item("text", text)
                self.new_text_captured.emit(item_id, text)
                return

        except Exception as e:
            print(f"[Watcher] Error: {e}")

    # ─────────────────────────────────────────
    # S002: Video thumbnail
    # ─────────────────────────────────────────
    def _start_thumb_worker(self, video_path: str, item_id: int):
        worker = _ThumbWorker(video_path, item_id)
        worker.done.connect(self._on_thumb_done)
        worker.finished.connect(lambda: self._thumb_workers.remove(worker)
                                if worker in self._thumb_workers else None)
        self._thumb_workers.append(worker)
        worker.start()

    def _on_thumb_done(self, item_id: int, thumb_path: str):
        storage.update_preview(item_id, thumb_path)
        self.thumb_ready.emit(item_id, thumb_path)

    # ─────────────────────────────────────────
    # S005: Paste item back to clipboard
    # ─────────────────────────────────────────
    def paste_item_to_clipboard(self, item: dict):
        """Restore item to clipboard."""
        self._is_self_paste = True
        if item["type"] == "text":
            self._clipboard.setText(item["content"])
        elif item["type"] == "image":
            image = QImage(item["content"])
            if not image.isNull():
                self._clipboard.setImage(image)
            else:
                self._clipboard.setText(item["content"])
        elif item["type"] == "video":
            self._clipboard.setText(item["content"])