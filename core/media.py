import os
import shutil
from datetime import datetime
from PyQt6.QtGui import QImage
from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtCore import QMimeData  # type hint

BASE_DIR      = os.path.dirname(os.path.dirname(__file__))
CAPTURES_DIR  = os.path.join(BASE_DIR, "data", "captures")
PINS_DIR      = os.path.join(BASE_DIR, "data", "pins")
VLOGS_DIR     = os.path.join(BASE_DIR, "data", "v_logs")

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"}


def _ensure_dirs():
    for d in [CAPTURES_DIR, PINS_DIR, VLOGS_DIR]:
        os.makedirs(d, exist_ok=True)

_ensure_dirs()


# ─────────────────────────────────────────────
# Images
# ─────────────────────────────────────────────
def save_image_from_qimage(qimage: QImage) -> str | None:
    """
    Takes a QImage from the Clipboard and saves it as .png.
    Returns the full path of the saved file.
    """
    if qimage is None or qimage.isNull():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename  = f"capture_{timestamp}.png"
    filepath  = os.path.join(CAPTURES_DIR, filename)

    try:
        if qimage.save(filepath, "PNG"):
            return filepath
        else:
            print("[Media] Failed to save image to disk")
            return None

    except Exception as e:
        print(f"[Media] Unexpected error saving image: {e}")
        return None


def copy_image_to_pins(src_path: str) -> str | None:
    """
    When you pin an image, we create a copy in the pins folder
    so it remains available even if the original is deleted.
    """
    if not src_path or not os.path.exists(src_path):
        return None

    filename  = os.path.basename(src_path)
    dest_path = os.path.join(PINS_DIR, filename)
    try:
        if not os.path.exists(dest_path):
            shutil.copy2(src_path, dest_path)
        return dest_path
    except OSError as e:
        print(f"[Media] Failed to copy to pins: {e}")
        return None


# ─────────────────────────────────────────────
# Video
# ─────────────────────────────────────────────
def is_video_path(text: str) -> bool:
    """
    Is the copied text a video file path?
    """
    if not text:
        return False
    text = text.strip()
    # a real path that exists on the system
    if os.path.isfile(text):
        _, ext = os.path.splitext(text.lower())
        return ext in VIDEO_EXTENSIONS
    return False


def log_video_path(video_path: str) -> str:
    """
    Save the video path to a text log file.
    Returns the path as is (for saving in DB).
    """
    log_file = os.path.join(VLOGS_DIR, "video_log.txt")
    try:
        timestamp = datetime.now().isoformat()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {video_path}\n")
    except OSError as e:
        print(f"[Media] Failed to log video path: {e}")
    return video_path


# ─────────────────────────────────────────────
# Content type detection
# ─────────────────────────────────────────────
# FIX #8: type hint for parameter
def detect_content_type(mime_data: "QMimeData") -> str:
    """
    Takes QMimeData and returns:
    'image' | 'video' | 'text' | 'unknown'
    """
    if mime_data is None:
        return "unknown"
    if mime_data.hasImage():
        return "image"
    if mime_data.hasText():
        text = mime_data.text().strip()
        if is_video_path(text):
            return "video"
        if text:
            return "text"
    return "unknown"


# ─────────────────────────────────────────────
# Cleanup folders (optional)
# ─────────────────────────────────────────────
def cleanup_captures(keep_last: int = 100):
    """
    Keep only the last N images in captures
    to prevent disk space issues.
    """
    try:
        files = sorted(
            [os.path.join(CAPTURES_DIR, f) for f in os.listdir(CAPTURES_DIR)],
            key=os.path.getmtime
        )
        for f in files[:-keep_last] if len(files) > keep_last else []:
            os.remove(f)
    except Exception as e:
        print(f"[Media] Cleanup error: {e}")