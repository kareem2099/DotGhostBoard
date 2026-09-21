"""
tests/conftest.py
─────────────────
Global pytest configuration and shared fixtures for DotGhostBoard.
"""

import os
import shutil
import tempfile
from pathlib import Path

# Enforce global sandbox isolation before any core/ui modules are imported
_SESSION_SANDBOX = tempfile.mkdtemp(prefix="dotghost_test_env_")
_SESSION_CONFIG = os.path.join(_SESSION_SANDBOX, ".config")
_SESSION_DOTGHOST = os.path.join(_SESSION_CONFIG, "dotghostboard")
os.makedirs(_SESSION_DOTGHOST, exist_ok=True)

os.environ["HOME"] = _SESSION_SANDBOX
os.environ["XDG_CONFIG_HOME"] = _SESSION_CONFIG
os.environ["DOTGHOST_HOME"] = _SESSION_DOTGHOST

import pytest
from PyQt6.QtWidgets import QApplication


def pytest_sessionfinish(session, exitstatus):
    """Clean up temporary sandbox environment created for the session."""
    if os.path.exists(_SESSION_SANDBOX):
        shutil.rmtree(_SESSION_SANDBOX, ignore_errors=True)


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single persistent QApplication instance exists for Qt GUI tests."""
    app = QApplication.instance()
    if not app:
        app = QApplication(["DotGhostBoard-Tests"])
    return app


@pytest.fixture(autouse=True)
def isolate_user_environment(tmp_path, monkeypatch):
    """Guarantee tests never touch real ~/.config or ~/.config/dotghostboard/."""
    fake_config = tmp_path / ".config"
    fake_dotghost = fake_config / "dotghostboard"
    fake_dotghost.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_config))
    monkeypatch.setenv("DOTGHOST_HOME", str(fake_dotghost))


@pytest.fixture
def mock_dashboard(monkeypatch, qapp, tmp_path):
    """Fixture providing an isolated headless Dashboard instance."""
    from core import storage
    from ui.dashboard import Dashboard

    db_file = str(tmp_path / "test_dashboard_fixture.db")
    vault_file = str(tmp_path / "test_vault_fixture.db")
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    import core.security.vault.database as vdb
    monkeypatch.setattr(vdb, "VAULT_DB_PATH", vault_file)
    monkeypatch.setenv("DOTGHOST_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    import core.crypto as crypto
    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))
    monkeypatch.setattr(crypto, "_VERIFY_FILE", str(tmp_path / "eclipse.verify"))
    storage.init_db()
    vdb.init_vault_db(vault_file)

    monkeypatch.setattr("ui.settings.load_settings", lambda: {
        "max_history": 500,
        "max_captures": 100,
        "theme": "dark",
        "clear_on_exit": False,
        "multiselect_hint_dismissed": True,
        "auto_lock_minutes": 0,
        "stealth_mode": False,
        "app_filter_mode": "blacklist",
        "app_filter_list": [],
    })

    # Disable background network / timers / discovery during testing
    monkeypatch.setattr("ui.dashboard.Dashboard._start_watcher", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard._start_api_server", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard._start_discovery", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard._init_sync_engine", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard.check_for_updates", lambda self: None)
    monkeypatch.setattr("ui.dashboard.Dashboard._setup_tray", lambda self: None)

    # Disable network services in SyncController
    monkeypatch.setattr("ui.controllers.sync_controller.SyncController.start_all", lambda self, *a, **k: None)
    monkeypatch.setattr("ui.controllers.sync_controller.SyncController.start_discovery", lambda self, *a, **k: None)
    monkeypatch.setattr("ui.controllers.sync_controller.SyncController.start_api_server", lambda self, *a, **k: None)
    monkeypatch.setattr("ui.controllers.sync_controller.SyncController.init_sync_engine", lambda self, *a, **k: None)

    dash = Dashboard(startup_locked=False, active_key=b"1" * 32)
    yield dash

    if hasattr(dash, "sync_controller"):
        dash.sync_controller.stop_all(100)
    dash.close()
    dash.deleteLater()
