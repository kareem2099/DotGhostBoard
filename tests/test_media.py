"""
tests/test_media.py
───────────────────
Unit tests for core/media.py

Run:
    pytest tests/test_media.py -v
"""

import os
import pytest
import tempfile
import shutil


# ════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════
@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    """
    Redirects all media directories to tmp_path
    so we don't write to the actual project directory.
    """
    import core.media as media
    monkeypatch.setattr(media, "CAPTURES_DIR", str(tmp_path / "captures"))
    monkeypatch.setattr(media, "PINS_DIR",     str(tmp_path / "pins"))
    monkeypatch.setattr(media, "VLOGS_DIR",    str(tmp_path / "v_logs"))

    os.makedirs(str(tmp_path / "captures"), exist_ok=True)
    os.makedirs(str(tmp_path / "pins"),     exist_ok=True)
    os.makedirs(str(tmp_path / "v_logs"),   exist_ok=True)

    return tmp_path


# ════════════════════════════════════════════
# is_video_path
# ════════════════════════════════════════════
class TestIsVideoPath:
    def test_valid_video_file(self, tmp_path):
        from core.media import is_video_path
        # Create a dummy video file
        video = tmp_path / "test.mp4"
        video.touch()
        assert is_video_path(str(video)) is True

    def test_mkv_extension(self, tmp_path):
        from core.media import is_video_path
        f = tmp_path / "clip.mkv"
        f.touch()
        assert is_video_path(str(f)) is True

    def test_avi_extension(self, tmp_path):
        from core.media import is_video_path
        f = tmp_path / "movie.avi"
        f.touch()
        assert is_video_path(str(f)) is True

    def test_text_file_is_not_video(self, tmp_path):
        from core.media import is_video_path
        f = tmp_path / "notes.txt"
        f.touch()
        assert is_video_path(str(f)) is False

    def test_nonexistent_path(self):
        from core.media import is_video_path
        assert is_video_path("/nonexistent/path/video.mp4") is False

    def test_empty_string(self):
        from core.media import is_video_path
        assert is_video_path("") is False

    def test_none_like_empty(self):
        from core.media import is_video_path
        assert is_video_path("   ") is False

    def test_all_supported_extensions(self, tmp_path):
        from core.media import is_video_path, VIDEO_EXTENSIONS
        for ext in VIDEO_EXTENSIONS:
            f = tmp_path / f"file{ext}"
            f.touch()
            assert is_video_path(str(f)) is True, f"Failed for {ext}"


# ════════════════════════════════════════════
# log_video_path
# ════════════════════════════════════════════
class TestLogVideoPath:
    def test_creates_log_file(self, tmp_data_dir):
        from core.media import log_video_path, VLOGS_DIR
        log_video_path("/home/user/video.mp4")
        log_file = os.path.join(VLOGS_DIR, "video_log.txt")
        assert os.path.exists(log_file)

    def test_log_contains_path(self, tmp_data_dir):
        from core.media import log_video_path, VLOGS_DIR
        log_video_path("/home/user/myvideo.mkv")
        log_file = os.path.join(VLOGS_DIR, "video_log.txt")
        content = open(log_file).read()
        assert "/home/user/myvideo.mkv" in content

    def test_returns_original_path(self, tmp_data_dir):
        from core.media import log_video_path
        result = log_video_path("/some/path.mp4")
        assert result == "/some/path.mp4"

    def test_appends_multiple_entries(self, tmp_data_dir):
        from core.media import log_video_path, VLOGS_DIR
        log_video_path("/video1.mp4")
        log_video_path("/video2.mp4")
        log_video_path("/video3.mp4")
        log_file = os.path.join(VLOGS_DIR, "video_log.txt")
        lines = [l for l in open(log_file).read().splitlines() if l.strip()]
        assert len(lines) == 3

    def test_handles_write_error_gracefully(self, monkeypatch, tmp_data_dir):
        """If write fails, don't raise an exception"""
        from core import media
        monkeypatch.setattr(media, "VLOGS_DIR", "/root/no_permission_dir")
        # Should not raise an exception
        result = media.log_video_path("/some/video.mp4")
        assert result == "/some/video.mp4"


# ════════════════════════════════════════════
# detect_content_type
# ════════════════════════════════════════════
class TestDetectContentType:
    """
    We'll mock QMimeData so we don't need
    to run Qt in tests.
    """

    def _make_mime(self, has_image=False, has_text=False, text=""):
        """Helper to create a simple mock object"""
        class FakeMime:
            def hasImage(self): return has_image
            def hasText(self):  return has_text
            def text(self):     return text
        return FakeMime()

    def test_none_returns_unknown(self):
        from core.media import detect_content_type
        assert detect_content_type(None) == "unknown"

    def test_image_mime(self):
        from core.media import detect_content_type
        mime = self._make_mime(has_image=True)
        assert detect_content_type(mime) == "image"

    def test_text_mime(self):
        from core.media import detect_content_type
        mime = self._make_mime(has_text=True, text="Hello World")
        assert detect_content_type(mime) == "text"

    def test_empty_text_returns_unknown(self):
        from core.media import detect_content_type
        mime = self._make_mime(has_text=True, text="   ")
        assert detect_content_type(mime) == "unknown"

    def test_video_path_in_text(self, tmp_path):
        from core.media import detect_content_type
        video = tmp_path / "clip.mp4"
        video.touch()
        mime = self._make_mime(has_text=True, text=str(video))
        assert detect_content_type(mime) == "video"

    def test_no_content_returns_unknown(self):
        from core.media import detect_content_type
        mime = self._make_mime(has_image=False, has_text=False)
        assert detect_content_type(mime) == "unknown"

    def test_image_takes_priority_over_text(self):
        """If mime has both image and text, image takes priority"""
        from core.media import detect_content_type
        mime = self._make_mime(has_image=True, has_text=True, text="some text")
        assert detect_content_type(mime) == "image"


# ════════════════════════════════════════════
# copy_image_to_pins
# ════════════════════════════════════════════
class TestCopyImageToPins:
    def test_copies_existing_file(self, tmp_data_dir):
        from core.media import copy_image_to_pins, PINS_DIR

        # Dummy source file
        src = tmp_data_dir / "captures" / "test_img.png"
        src.write_bytes(b"\x89PNG\r\n")

        dest = copy_image_to_pins(str(src))
        assert dest is not None
        assert os.path.exists(dest)
        assert os.path.basename(dest) == "test_img.png"

    def test_nonexistent_source_returns_none(self, tmp_data_dir):
        from core.media import copy_image_to_pins
        result = copy_image_to_pins("/nonexistent/image.png")
        assert result is None

    def test_none_returns_none(self, tmp_data_dir):
        from core.media import copy_image_to_pins
        result = copy_image_to_pins(None)
        assert result is None

    def test_does_not_overwrite_existing_pin(self, tmp_data_dir):
        from core.media import copy_image_to_pins, PINS_DIR

        src = tmp_data_dir / "captures" / "dup.png"
        src.write_bytes(b"original")

        # First copy
        copy_image_to_pins(str(src))

        # Change content and try again
        src.write_bytes(b"modified")
        copy_image_to_pins(str(src))

        pin_path = os.path.join(PINS_DIR, "dup.png")
        assert open(pin_path, "rb").read() == b"original"   # Hasn't changed


# ════════════════════════════════════════════
# cleanup_captures
# ════════════════════════════════════════════
class TestCleanupCaptures:
    def test_removes_old_files(self, tmp_data_dir):
        from core.media import cleanup_captures, CAPTURES_DIR

        # Create 5 files
        for i in range(5):
            (tmp_data_dir / "captures" / f"cap_{i}.png").write_bytes(b"x")

        cleanup_captures(keep_last=3)

        remaining = os.listdir(CAPTURES_DIR)
        assert len(remaining) == 3

    def test_keeps_all_if_under_limit(self, tmp_data_dir):
        from core.media import cleanup_captures, CAPTURES_DIR

        for i in range(3):
            (tmp_data_dir / "captures" / f"cap_{i}.png").write_bytes(b"x")

        cleanup_captures(keep_last=10)
        assert len(os.listdir(CAPTURES_DIR)) == 3

    def test_empty_dir_no_error(self, tmp_data_dir):
        from core.media import cleanup_captures
        cleanup_captures(keep_last=5)   # no exception
