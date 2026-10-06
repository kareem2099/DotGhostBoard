"""Media cleanup must never accept a sibling merely sharing a root's name."""

import pytest

from core.storage.repositories import clips


@pytest.mark.parametrize("via_symlink", [False, True])
def test_media_helpers_reject_sibling_directory(tmp_path, monkeypatch, via_symlink):
    allowed = tmp_path / "captures"
    sibling = tmp_path / "captures-backup"
    allowed.mkdir()
    sibling.mkdir()
    outside = sibling / "image.png"
    outside.write_bytes(b"keep this file")
    monkeypatch.setattr(clips, "_get_allowed_media_roots", lambda: [str(allowed)])
    candidate = outside
    if via_symlink:
        candidate = allowed / "outside.png"
        candidate.symlink_to(outside)

    assert clips._is_path_in_allowed_roots(str(candidate)) is None
    assert clips._get_safe_image_path(str(candidate)) is None
    assert clips._get_file_hash(str(candidate)) is None
    assert clips._safe_remove_file(str(candidate)) is False
    assert outside.read_bytes() == b"keep this file"


def test_media_helpers_accept_files_inside_root(tmp_path, monkeypatch):
    allowed = tmp_path / "captures"
    allowed.mkdir()
    inside = allowed / "image.png"
    inside.write_bytes(b"temporary capture")
    monkeypatch.setattr(clips, "_get_allowed_media_roots", lambda: [str(allowed)])
    assert clips._get_safe_image_path(str(inside)) == str(inside)
    assert clips._get_file_hash(str(inside)) is not None
    assert clips._safe_remove_file(str(inside)) is True
    assert not inside.exists()
