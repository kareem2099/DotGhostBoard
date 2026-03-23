from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication
from core import storage, media


class ClipboardWatcher(QObject):
    """
    A watcher that monitors the clipboard every 500ms.
    When it detects new content, it sends a signal to the UI.
    """

    # Signals — sends data to the Dashboard
    new_text_captured  = pyqtSignal(int, str)        # (id, text)
    new_image_captured = pyqtSignal(int, str)        # (id, file_path)
    new_video_captured = pyqtSignal(int, str)        # (id, video_path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clipboard      = QApplication.clipboard()
        self._last_content   = None          # last captured content (text or image signature or video path)
        self._is_self_paste  = False         # to ignore clipboard changes caused by our own pasting actions

        # Timer to check clipboard every 500ms 
        self._timer = QTimer(self)
        self._timer.setInterval(500)         # every 500ms
        self._timer.timeout.connect(self._check_clipboard)

    # ─────────────────────────────────────────
    def start(self):
        storage.init_db()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def mark_self_paste(self):
        """Call this when you paste from the application itself"""
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

            content_type = media.detect_content_type(mime)

            if content_type == "unknown":
                return

            # ── Text ────────────────────────────
            if content_type == "text":
                text = mime.text().strip()
                if text and text != self._last_content:
                    self._last_content = text
                    item_id = storage.add_item("text", text)
                    self.new_text_captured.emit(item_id, text)

            # ── Image ──────────────────────────
            elif content_type == "image":
                qimage = self._clipboard.image()
                if qimage is None or qimage.isNull():
                    return
                # Safe hash: without tobytes() which can cause segfault
                img_sig = f"{qimage.width()}x{qimage.height()}_{qimage.sizeInBytes()}"
                if img_sig != self._last_content:
                    self._last_content = img_sig
                    file_path = media.save_image_from_qimage(qimage)
                    if file_path:
                        item_id = storage.add_item("image", file_path, preview=file_path)
                        self.new_image_captured.emit(item_id, file_path)

            # ── Video ─────────────────────────
            elif content_type == "video":
                video_path = mime.text().strip()
                if video_path and video_path != self._last_content:
                    self._last_content = video_path
                    media.log_video_path(video_path)
                    item_id = storage.add_item("video", video_path)
                    self.new_video_captured.emit(item_id, video_path)

        except Exception as e:
            print(f"[Watcher] Error: {e}")

    # ─────────────────────────────────────────
    def paste_item_to_clipboard(self, item: dict):
        """
        When the user clicks on an item in the list,
        we restore its content to the Clipboard.
        """
        self._is_self_paste = True
        if item["type"] == "text":
            self._clipboard.setText(item["content"])
        elif item["type"] == "image":
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap(item["content"])
            if not pixmap.isNull():
                self._clipboard.setPixmap(pixmap)
        elif item["type"] == "video":
            self._clipboard.setText(item["content"])