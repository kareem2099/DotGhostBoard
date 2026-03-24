"""
tests/test_thumbnailer.py
─────────────────────────
Unit tests for core/thumbnailer.py (v1.2.0 S002).

Run:
    pytest tests/test_thumbnailer.py -v
"""

import os
import tempfile
import shutil
import pytest

from core import thumbnailer


@pytest.fixture
def tmp_thumb_dir(tmp_path):
    """Override THUMB_DIR to a temporary directory."""
    original = thumbnailer.THUMB_DIR
    thumbnailer.THUMB_DIR = str(tmp_path)
    yield str(tmp_path)
    thumbnailer.THUMB_DIR = original


# ════════════════════════════════════════════
# extract_video_thumb
# ════════════════════════════════════════════
class TestExtractVideoThumb:
    def test_returns_none_for_nonexistent_file(self, tmp_thumb_dir):
        result = thumbnailer.extract_video_thumb("/nonexistent/video.mp4", item_id=1)
        assert result is None

    def test_returns_none_for_empty_path(self, tmp_thumb_dir):
        result = thumbnailer.extract_video_thumb("", item_id=2)
        assert result is None

    def test_returns_none_when_ffmpeg_absent(self, tmp_thumb_dir, monkeypatch):
        """If ffmpeg is not on PATH, must return None without crashing."""
        import subprocess

        def fake_run(*args, **kwargs):
            raise FileNotFoundError("ffmpeg not found")

        monkeypatch.setattr(subprocess, "run", fake_run)

        # Create a fake file so path check passes
        fake_video = os.path.join(tmp_thumb_dir, "fake.mp4")
        with open(fake_video, "wb") as f:
            f.write(b"\x00" * 16)

        result = thumbnailer.extract_video_thumb(fake_video, item_id=3)
        assert result is None

    def test_returns_none_on_ffmpeg_timeout(self, tmp_thumb_dir, monkeypatch):
        """Ffmpeg timeout must return None without crashing."""
        import subprocess

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10)

        monkeypatch.setattr(subprocess, "run", fake_run)

        fake_video = os.path.join(tmp_thumb_dir, "fake.mp4")
        with open(fake_video, "wb") as f:
            f.write(b"\x00" * 16)

        result = thumbnailer.extract_video_thumb(fake_video, item_id=4)
        assert result is None

    def test_returns_thumb_path_on_success(self, tmp_thumb_dir, monkeypatch):
        """On ffmpeg success (returncode 0 + file exists), returns correct path."""
        import subprocess

        expected_out = os.path.join(tmp_thumb_dir, "99.png")

        def fake_run(cmd, **kwargs):
            # Simulate ffmpeg writing the output file
            with open(expected_out, "wb") as f:
                f.write(b"fake png")
            result = subprocess.CompletedProcess(cmd, returncode=0)
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        fake_video = os.path.join(tmp_thumb_dir, "real.mp4")
        with open(fake_video, "wb") as f:
            f.write(b"\x00" * 16)

        result = thumbnailer.extract_video_thumb(fake_video, item_id=99)
        assert result == expected_out


# ════════════════════════════════════════════
# get_thumb_path
# ════════════════════════════════════════════
class TestGetThumbPath:
    def test_returns_none_when_no_thumb(self, tmp_thumb_dir):
        result = thumbnailer.get_thumb_path(item_id=1)
        assert result is None

    def test_returns_path_when_thumb_exists(self, tmp_thumb_dir):
        path = os.path.join(tmp_thumb_dir, "42.png")
        with open(path, "wb") as f:
            f.write(b"fake png")
        result = thumbnailer.get_thumb_path(item_id=42)
        assert result == path


# ════════════════════════════════════════════
# delete_thumb
# ════════════════════════════════════════════
class TestDeleteThumb:
    def test_removes_existing_thumb(self, tmp_thumb_dir):
        path = os.path.join(tmp_thumb_dir, "7.png")
        with open(path, "wb") as f:
            f.write(b"fake png")
        thumbnailer.delete_thumb(item_id=7)
        assert not os.path.isfile(path)

    def test_no_error_when_thumb_missing(self, tmp_thumb_dir):
        thumbnailer.delete_thumb(item_id=9999)   # should not raise
