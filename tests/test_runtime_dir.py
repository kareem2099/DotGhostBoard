import os
import stat
import tempfile
import pytest
from unittest.mock import patch

from main import _get_runtime_dir


def test_xdg_runtime_dir_valid(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))

    assert _get_runtime_dir() == str(runtime)


def test_xdg_runtime_dir_rejects_regular_file(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.write_text("not a directory")

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))

    with pytest.raises(RuntimeError, match="not a directory"):
        _get_runtime_dir()


def test_xdg_runtime_dir_rejects_symlink(monkeypatch, tmp_path):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)

    link = tmp_path / "runtime"
    link.symlink_to(real)

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(link))

    with pytest.raises(RuntimeError, match="not a directory"):
        _get_runtime_dir()


def test_xdg_runtime_dir_rejects_wrong_owner(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))

    real_stat = os.lstat(runtime)
    fake_stat = type("MockStat", (), {
        "st_mode": real_stat.st_mode,
        "st_uid": os.getuid() + 9999,
    })()

    with patch("os.lstat", return_value=fake_stat):
        with pytest.raises(RuntimeError, match="owned by another user"):
            _get_runtime_dir()


def test_fallback_creates_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    expected_path = str(tmp_path / f"dotghostboard-run-{os.getuid()}")
    assert not os.path.exists(expected_path)

    res = _get_runtime_dir()
    assert res == expected_path
    assert os.path.isdir(res)
    mode = stat.S_IMODE(os.stat(res).st_mode)
    assert mode == 0o700


def test_fallback_reuses_valid_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    target = tmp_path / f"dotghostboard-run-{os.getuid()}"
    target.mkdir(mode=0o755)

    res = _get_runtime_dir()
    assert res == str(target)
    # Ensure it restricted permissions to 0o700
    assert stat.S_IMODE(os.stat(res).st_mode) == 0o700


def test_fallback_rejects_symlink(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    real_dir = tmp_path / "some_real_dir"
    real_dir.mkdir()

    symlink_path = tmp_path / f"dotghostboard-run-{os.getuid()}"
    os.symlink(str(real_dir), str(symlink_path))

    with pytest.raises(RuntimeError, match="not a directory"):
        _get_runtime_dir()


def test_fallback_rejects_different_owner(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    target = tmp_path / f"dotghostboard-run-{os.getuid()}"
    target.mkdir(mode=0o700)

    # Mock os.lstat to return a different st_uid
    real_lstat = os.lstat(str(target))
    mock_stat = type("MockStat", (), {
        "st_mode": real_lstat.st_mode,
        "st_uid": os.getuid() + 9999,
    })()

    with patch("os.lstat", return_value=mock_stat):
        with pytest.raises(RuntimeError, match="owned by another user"):
            _get_runtime_dir()
