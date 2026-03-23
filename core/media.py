import os
from datetime import datetime
from PyQt6.QtGui import QImage
from PyQt6.QtCore import QBuffer, QIODevice

# ─────────────────────────────────────────────
# Basic paths
# ─────────────────────────────────────────────
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

    # convert QImage → bytes → save
    buffer = QBuffer()
    buffer.open(QIODevice.OpenMode.ReadWrite)
    qimage.save(buffer, "PNG")
    buffer.seek(0)
    raw_bytes = bytes(buffer.data())
    buffer.close()

    with open(filepath, "wb") as f:
        f.write(raw_bytes)

    return filepath


def copy_image_to_pins(src_path: str) -> str | None:
    """
    When you pin an image, we create a copy in the pins folder
    so it remains available even if the original is deleted.
    """
    if not src_path or not os.path.exists(src_path):
        return None

    filename  = os.path.basename(src_path)
    dest_path = os.path.join(PINS_DIR, filename)

    if not os.path.exists(dest_path):
        import shutil
        shutil.copy2(src_path, dest_path)

    return dest_path


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
    timestamp = datetime.now().isoformat()
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {video_path}\n")
    return video_path


# ─────────────────────────────────────────────
# Content type detection
# ─────────────────────────────────────────────
def detect_content_type(mime_data) -> str:
    """
    Takes QMimeData and returns:
    'image' | 'video' | 'text' | 'unknown'
    """
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
        to_delete = files[:-keep_last] if len(files) > keep_last else []
        for f in to_delete:
            os.remove(f)
    except Exception:
        pass
