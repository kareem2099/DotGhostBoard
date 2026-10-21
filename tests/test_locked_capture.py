"""Dashboard privacy locks must not silently stop protected clipboard capture."""

from unittest.mock import MagicMock

import pytest
from core import crypto, storage
from core.clipboard.events import ClipboardEvent
from core.watcher import ClipboardWatcher
from ui.dashboard import Dashboard
from ui.lock_screen import LockScreen
from ui.vault.send_to_vault import attach_send_to_vault
from ui.widgets.secret_toast import SecretDetectedToast

PASSWORD = "LockedCaptureDashboard2026!"
VAULT_PASSWORD = "IndependentCaptureVault2026!"
KNOWN = "simple"
START_WATCHER = Dashboard._start_watcher


class ManualBackend:
    """Deliver clipboard changes only while monitoring is running."""
    def __init__(self):
        self.running = False
        self.callback = None
        self.on_start = None

    def set_on_event(self, callback):
        self.callback = callback

    def start(self):
        self.running = True
        if self.on_start:
            self.on_start()

    def stop(self):
        self.running = False

    def emit(self, text, primary=False):
        if self.running:
            self.callback(ClipboardEvent(
                "text", text, source_app="primary_selection" if primary else None,
            ))

    def set_monitor_primary(self, enabled):
        pass

    def set_sync_primary_to_clipboard(self, enabled):
        pass


def attach_backend(dash, monkeypatch, backend=None):
    backend = backend or ManualBackend()
    monkeypatch.setattr("ui.dashboard.ClipboardWatcher", lambda: ClipboardWatcher(backend=backend))
    START_WATCHER(dash)
    attach_send_to_vault(dash)
    dash.capture_controller.refresh()
    return backend


@pytest.fixture
def protected_dashboard(mock_dashboard):
    dash = mock_dashboard
    dash.security_service.setup_master_password(PASSWORD)
    dash.vault_controller.add_secret("Stored password", KNOWN)
    from core.security.vault.csv_importer import CsvEntry
    entry = CsvEntry(title="Imported account", username="user", password="imported-simple",
                     url="https://example.test")
    dash.vault_controller.add_secret(entry.title, entry.vault_secret_text, category="password")
    dash.security_controller.set_active_key(crypto.derive_key(PASSWORD))
    return dash


@pytest.mark.parametrize("independent", [False, True])
@pytest.mark.parametrize("primary", [False, True])
@pytest.mark.parametrize("automatic", [False, True])
def test_capture_survives_manual_and_idle_lock_with_secrets_excluded(
    protected_dashboard, monkeypatch, independent, primary, automatic,
):
    dash = protected_dashboard
    if independent:
        dash.security_service.vault.configure_password(PASSWORD, VAULT_PASSWORD)
    backend = attach_backend(dash, monkeypatch)
    dash._settings["detect_passwords"] = False  # Known values cannot depend on heuristics.
    prompt = MagicMock()
    monkeypatch.setattr(dash, "_show_lock_screen", prompt)
    dash._settings["auto_lock_minutes"] = 5
    dash._reset_auto_lock()
    dash.show()
    dash.spotlight_dialog.show()
    old_key = dash.security_service._active_key
    old_dek = dash.security_service.vault._vault_dek
    baseline_cards = set(dash.history_controller.cards)
    outgoing = MagicMock()
    monkeypatch.setattr(dash.sync_controller, "broadcast_text", outgoing)

    if automatic:
        dash.security_controller.auto_lock_timer.timeout.emit()
    else:
        dash._lock()

    assert dash._is_locked() and backend.running
    assert not dash.isVisible() and not dash.spotlight_dialog.isVisible()
    assert dash.security_service.active_key is None
    assert dash.security_service.vault._vault_dek is None
    assert not any(old_key) and not any(old_dek)
    prompt.assert_not_called()  # Idle lock must not steal focus.
    for text in ("First note copied while the Dashboard is locked", KNOWN, "imported-simple",
                 "Second note copied while the Dashboard is locked"):
        backend.emit(text, primary)
    assert storage.get_item_by_content(KNOWN) is None
    assert storage.get_item_by_content("imported-simple") is None
    assert storage.get_item_by_content("First note copied while the Dashboard is locked")
    assert storage.get_item_by_content("Second note copied while the Dashboard is locked")
    assert set(dash.history_controller.cards) == baseline_cards
    outgoing.assert_not_called()
    assert dash.findChild(SecretDetectedToast) is None

    def authenticate(dialog):
        dialog.pw_input.setText(PASSWORD)
        dialog._on_submit()
        return dialog.result()

    monkeypatch.setattr(LockScreen, "exec", authenticate)
    if independent:
        monkeypatch.setattr(dash.vault_panel, "_prompt_unlock",
                            lambda: dash.vault_controller.unlock(VAULT_PASSWORD))
    assert dash.security_controller.prompt_unlock()
    for text in ("First note copied while the Dashboard is locked",
                 "Second note copied while the Dashboard is locked"):
        item = storage.get_item_by_content(text)
        assert item["id"] in dash.history_controller.cards
    assert dash.vault_controller.is_unlocked


def test_pause_remains_explicit_and_can_resume_while_locked(protected_dashboard, monkeypatch):
    dash = protected_dashboard
    backend = attach_backend(dash, monkeypatch)
    dash._pause_monitoring()
    dash.security_controller.lock()
    backend.emit("Paused clipboard value")
    assert not backend.running
    assert storage.get_item_by_content("Paused clipboard value") is None
    dash._resume_monitoring()
    assert dash._is_locked() and backend.running
    backend.emit("Resumed without exposing the Dashboard")
    backend.emit(KNOWN)
    assert storage.get_item_by_content("Resumed without exposing the Dashboard")
    assert storage.get_item_by_content(KNOWN) is None


def test_cold_start_cannot_capture_before_authentication(protected_dashboard, monkeypatch):
    from ui.controllers.capture_controller import CaptureController
    dash = protected_dashboard
    dash.security_controller.lock()
    # Model a fresh process, with neither authorization nor a warm recognition index.
    from core.services import SecurityService
    dash.security_service = SecurityService()
    dash.security_controller._service = dash.security_service
    dash._startup_locked = True
    dash.capture_controller = CaptureController(dash)
    backend = attach_backend(dash, monkeypatch)
    dash._resume_monitoring()
    assert not backend.running and not dash.capture_controller.authorized
    backend.emit("Copied before first authentication")
    assert storage.get_item_by_content("Copied before first authentication") is None


def test_locked_candidates_and_unavailable_recognition_never_save_plaintext(
    protected_dashboard, monkeypatch,
):
    dash = protected_dashboard
    backend = attach_backend(dash, monkeypatch)
    dash.tray_manager = MagicMock()
    dash.security_controller.lock()
    candidate = "ghp_" + "A9b8C7d6" * 5
    backend.emit(candidate)
    assert storage.get_item_by_content(candidate) is None
    assert dash.findChild(SecretDetectedToast) is None
    assert dash.tray_manager.show_message.call_args.kwargs["dedupe_key"] == "locked_secret_excluded"
    # An external writer changes the Vault while its key is unavailable.
    item = dash.security_service.vault._repo.list_items()[0]
    dash.security_service.vault._repo.update_item(item.id, ciphertext="changed")
    backend.emit("Cannot classify this with a stale recognition index")
    assert storage.get_item_by_content("Cannot classify this with a stale recognition index") is None
    assert dash.tray_manager.show_message.call_args.kwargs["dedupe_key"] == "vault_check_required"


def test_secret_checker_is_installed_before_first_backend_event(protected_dashboard, monkeypatch):
    dash = protected_dashboard
    backend = ManualBackend()
    backend.on_start = lambda: backend.emit(KNOWN)
    attach_backend(dash, monkeypatch, backend)
    assert backend.running
    assert storage.get_item_by_content(KNOWN) is None


def test_warm_independent_reauthentication_stays_private_until_both_passwords_pass(
    protected_dashboard, monkeypatch,
):
    dash = protected_dashboard
    dash.security_service.vault.configure_password(PASSWORD, VAULT_PASSWORD)
    backend = attach_backend(dash, monkeypatch)
    dash.security_controller.lock()
    baseline = set(dash.history_controller.cards)

    def second_password():
        assert dash._is_locked()
        backend.emit("Ordinary text while the second password dialog is open")
        backend.emit(KNOWN)
        assert set(dash.history_controller.cards) == baseline
        assert storage.get_item_by_content(KNOWN) is None
        return dash.vault_controller.unlock(VAULT_PASSWORD)

    dash.security_controller.vault_unlock_callback = second_password
    assert dash.security_controller.set_active_key(crypto.derive_key(PASSWORD))
    assert not dash._is_locked()
    item = storage.get_item_by_content("Ordinary text while the second password dialog is open")
    assert item["id"] in dash.history_controller.cards


def test_locked_tray_distinguishes_monitoring_pause_and_first_unlock(qapp):
    from ui.components import DashboardTrayManager
    manager = DashboardTrayManager()
    manager.setup_tray()
    for paused, ready, status in [(False, True, "Monitoring clipboard"),
                                  (True, True, "Monitoring paused"),
                                  (False, False, "Unlock once")]:
        manager.update_menu_and_tooltip(True, paused, True, capture_ready=ready)
        assert status in manager.tray.toolTip()
        actions = [action.text() for action in manager.tray.contextMenu().actions()]
        assert any("Resume" in action or "Pause" in action for action in actions) is ready
        assert not any("Settings" in action for action in actions)
    manager.hide()


def test_real_qt_clipboard_timer_keeps_capturing_after_lock(protected_dashboard, monkeypatch, qapp):
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    dash = protected_dashboard
    monkeypatch.setattr("ui.dashboard.ClipboardWatcher", ClipboardWatcher)
    START_WATCHER(dash)
    attach_send_to_vault(dash)
    dash.capture_controller.refresh()
    dash.security_controller.lock()
    clipboard = QApplication.clipboard()
    try:
        clipboard.setText("Real Qt clipboard copied while locked")
        QTest.qWait(1200)
        assert storage.get_item_by_content("Real Qt clipboard copied while locked")
        clipboard.setText(KNOWN)
        QTest.qWait(1200)
        assert storage.get_item_by_content(KNOWN) is None
        assert not dash.isVisible() and dash._is_locked()
    finally:
        dash.watcher.stop()
        clipboard.clear()
