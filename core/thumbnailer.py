"""
core/thumbnailer.py
───────────────────
Extracts video thumbnails using ffmpeg.
Fails gracefully if ffmpeg is not installed — never crashes the app.
"""

import os
import subprocess

_USER_DATA = os.path.join(os.path.expanduser("~"), ".config", "dotghostboard")
THUMB_DIR  = os.path.join(_USER_DATA, "thumbnails")


def _ensure_thumb_dir():
    os.makedirs(THUMB_DIR, exist_ok=True)


def extract_video_thumb(video_path: str, item_id: int) -> str | None:
    """
    Extract the first frame of a video as a PNG thumbnail.

    Returns:
        Path to data/thumbnails/<item_id>.png on success.
        None if ffmpeg is absent or extraction fails.
    """
    if not video_path or not os.path.isfile(video_path):
        return None

    _ensure_thumb_dir()
    out_path = os.path.join(THUMB_DIR, f"{item_id}.png")

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-ss", "0",
                "-i", video_path,
                "-frames:v", "1",
                "-vf", "scale=300:-1",    # max-width 300px, keep aspect ratio
                out_path,
                "-y",                     # overwrite if exists
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        if result.returncode == 0 and os.path.isfile(out_path):
            print(f"[Thumbnailer] Thumbnail saved: {out_path}")
            return out_path
    except FileNotFoundError:
        # ffmpeg not installed — silent fail
        print("[Thumbnailer] ffmpeg not found — video thumbnails disabled")
    except subprocess.TimeoutExpired:
        print(f"[Thumbnailer] Timeout extracting thumbnail for: {video_path}")
    except Exception as e:
        print(f"[Thumbnailer] Error: {e}")

    return None


def get_thumb_path(item_id: int) -> str | None:
    """Return thumbnail path if it exists on disk, else None."""
    path = os.path.join(THUMB_DIR, f"{item_id}.png")
    return path if os.path.isfile(path) else None


def delete_thumb(item_id: int) -> None:
    """Remove thumbnail file if it exists (called during cleanup)."""
    path = os.path.join(THUMB_DIR, f"{item_id}.png")
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
