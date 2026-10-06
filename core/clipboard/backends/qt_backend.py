"""
core/clipboard/backends/qt_backend.py
─────────────────────────────────────
Default Qt-based clipboard backend for X11 / Wayland environments.
Converts raw clipboard data into ClipboardEvent instances.
"""

import os
from typing import Callable, Any
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QClipboard

from ..events import ClipboardEvent
from core import media


class QtClipboardBackend(QObject):
    """
    Monitors QApplication.clipboard() every 500ms.
    Converts raw clipboard data into ClipboardEvent instances.
    Supports optional debounced PRIMARY mouse selection monitoring.
    """

    def __init__(self, parent=None, poll_interval_ms: int = 500):
        super().__init__(parent)
        self._clipboard = QApplication.clipboard()
        self._last_content: str | None = None
        self._last_primary_content: str | None = None
        self._monitor_primary: bool = False
        self._sync_primary_to_clipboard: bool = True
        self._is_self_paste: bool = False
        self._on_event: Callable[[ClipboardEvent], None] | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self._check_clipboard)

        self._primary_debounce_timer = QTimer(self)
        self._primary_debounce_timer.setSingleShot(True)
        self._primary_debounce_timer.setInterval(450)
        self._primary_debounce_timer.timeout.connect(self._on_primary_debounce_timeout)

        try:
            self._clipboard.selectionChanged.connect(self._on_selection_changed)
        except Exception:
            pass

    def set_on_event(self, callback: Callable[[ClipboardEvent], None]) -> None:
        self._on_event = callback

    def set_monitor_primary(self, enabled: bool) -> None:
        self._monitor_primary = enabled
        if not enabled:
            self._primary_debounce_timer.stop()

    def set_sync_primary_to_clipboard(self, enabled: bool) -> None:
        self._sync_primary_to_clipboard = enabled

    def _on_selection_changed(self) -> None:
        if not self._timer.isActive() or not self._monitor_primary or self._on_event is None:
            return
        self._primary_debounce_timer.start()

    def _on_primary_debounce_timeout(self) -> None:
        if not self._timer.isActive() or not self._monitor_primary or self._on_event is None:
            return
        try:
            if not self._clipboard.supportsSelection():
                return

            mime = self._clipboard.mimeData(QClipboard.Mode.Selection)
            if mime is None:
                return

            if mime.hasFormat("x-kde-passwordManagerHint"):
                hint = bytes(mime.data("x-kde-passwordManagerHint")).decode("utf-8", errors="ignore").strip().lower()
                if hint == "secret":
                    return

            text = self._clipboard.text(QClipboard.Mode.Selection).strip()
            if not text or len(text) < 2:
                return

            if text == self._last_primary_content or text == self._last_content:
                return

            self._last_primary_content = text

            if self._sync_primary_to_clipboard:
                # The synced text is already known. Normal content deduplication
                # suppresses it without swallowing the next external copy.
                self._is_self_paste = False
                self._last_content = text
                self._clipboard.setText(text, QClipboard.Mode.Clipboard)

            event = ClipboardEvent(
                content_type="text",
                content=text,
                source_app="primary_selection",
            )
            self._on_event(event)
        except Exception as e:
            print(f"[QtClipboardBackend] Primary Selection Error: {e}")

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._primary_debounce_timer.stop()

    def mark_self_paste(self) -> None:
        self._is_self_paste = True

    def recheck_clipboard(self) -> None:
        """Re-evaluate previously blocked text after Vault verification becomes available."""
        self._last_content = None
        self._last_primary_content = None
        if self._monitor_primary:
            self._on_selection_changed()

    def paste_item(self, item: dict[str, Any]) -> None:
        self._is_self_paste = True
        item_type = item.get("type")
        content = item.get("content", "")

        if item_type == "text":
            self._clipboard.setText(content)
            if self._clipboard.supportsSelection():
                self._clipboard.setText(content, QClipboard.Mode.Selection)
        elif item_type == "image":
            image = QImage(content)
            if not image.isNull():
                self._clipboard.setImage(image)
            else:
                self._clipboard.setText(content)
        elif item_type == "video":
            self._clipboard.setText(content)

    def _check_clipboard(self) -> None:
        if self._on_event is None:
            return

        try:
            mime = self._clipboard.mimeData()
            if mime is None:
                return

            # Ignore clipboard if password manager hint is present
            if mime.hasFormat("x-kde-passwordManagerHint"):
                hint = bytes(mime.data("x-kde-passwordManagerHint")).decode("utf-8", errors="ignore").strip().lower()
                if hint == "secret":
                    self._is_self_paste = False
                    if mime.hasText():
                        self._last_content = mime.text().strip()
                    return

            if self._is_self_paste:
                if mime.hasText():
                    current = mime.text().strip()
                    if current == self._last_content:
                        return  # Pending clipboard change hasn't arrived yet
                    self._is_self_paste = False
                    self._last_content = current
                    return
                self._is_self_paste = False
                if mime.hasUrls():
                    urls = mime.urls()
                    if urls:
                        self._last_content = urls[0].toLocalFile()
                elif mime.hasImage():
                    qimage = self._clipboard.image()
                    if not qimage.isNull():
                        self._last_content = f"{qimage.width()}x{qimage.height()}_{qimage.sizeInBytes()}"
                return

            # 1. Images
            if mime.hasImage():
                qimage = self._clipboard.image()
                if not qimage.isNull():
                    img_sig = f"{qimage.width()}x{qimage.height()}_{qimage.sizeInBytes()}"
                    if img_sig != self._last_content:
                        self._last_content = img_sig
                        file_path = media.save_image_from_qimage(qimage)
                        if file_path:
                            event = ClipboardEvent(
                                content_type="image",
                                content=file_path,
                                preview=file_path,
                            )
                            self._on_event(event)
                    return

            # 2. URLs / File Manager Copies
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
                            event = ClipboardEvent(
                                content_type="image",
                                content=local_path,
                                preview=local_path,
                            )
                            self._on_event(event)
                            return
                        elif low_path.endswith(vid_exts):
                            event = ClipboardEvent(
                                content_type="video",
                                content=local_path,
                            )
                            self._on_event(event)
                            return

            # 3. Plain Text / Path Strings
            if mime.hasText():
                text = mime.text().strip()
                if not text:
                    return

                if text == self._last_content:
                    return
                self._last_content = text

                clean_path = text.replace("file://", "").strip()
                if os.path.isfile(clean_path):
                    img_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
                    vid_exts = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv")
                    low_p = clean_path.lower()

                    if low_p.endswith(img_exts):
                        event = ClipboardEvent(
                            content_type="image",
                            content=clean_path,
                            preview=clean_path,
                        )
                        self._on_event(event)
                        return
                    elif low_p.endswith(vid_exts):
                        event = ClipboardEvent(
                            content_type="video",
                            content=clean_path,
                        )
                        self._on_event(event)
                        return

                event = ClipboardEvent(
                    content_type="text",
                    content=text,
                )
                self._on_event(event)
                return

        except Exception as e:
            print(f"[QtClipboardBackend] Error: {e}")
