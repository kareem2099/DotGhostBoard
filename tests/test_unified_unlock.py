"""One authentication opens Dashboard and Vault, with independent Vault auto-lock."""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QDialog

from core import crypto, storage
from core.clipboard.events import ClipboardEvent
from core.constants import VAULT_IDLE_TIMEOUT_SECONDS
from core.security.vault import VaultService
from core.watcher import ClipboardWatcher
from ui.dashboard import Dashboard
from ui.lock_screen import LockScreen
from ui.vault.send_to_vault import attach_send_to_vault
from ui.widgets.secret_toast import SecretDetectedToast

PASSWORD = "UnifiedUnlockMaster123!"
KNOWN_SECRET = "simple"  # Must be protected even though heuristics do not flag it.


def seed_locked_vault(dash):
    crypto.save_master_password(PASSWORD)
    seed = VaultService()
    assert seed.unlock(PASSWORD)
    item_id = seed.add_secret("Existing secret", KNOWN_SECRET)
    seed.lock()
    dash.security_controller.lock()
    assert not dash.vault_controller.is_unlocked
    assert dash.security_service.vault.match_clipboard_secret(KNOWN_SECRET) is None
    return item_id


def submit_password(dialog):
    dialog.pw_input.setText(PASSWORD)
    dialog._on_submit()
    return dialog.result()


@pytest.mark.parametrize("timeout", [0, 5, 30, 60])
def test_startup_key_opens_existing_vault_and_starts_idle_timer(mock_dashboard, monkeypatch, timeout):
    item_id = seed_locked_vault(mock_dashboard)
    lock = LockScreen(setup=False)
    submit_password(lock)
    assert lock.result() == QDialog.DialogCode.Accepted
    assert lock.pw_input.text() == ""
    assert lock.confirm_input.text() == ""
    settings = dict(mock_dashboard._settings, auto_lock_minutes=timeout)
    monkeypatch.setattr("ui.dashboard.load_settings", lambda: settings)

    # Same handoff used by main.py, with a fresh service and no password in Dashboard.
    window = Dashboard(active_key=lock.get_key())
    try:
        assert not window._is_locked()
        assert window.vault_controller.is_unlocked
        assert window.vault_controller.service.get_secret(item_id) == KNOWN_SECRET
        assert window.vault_panel.badge_lbl.property("unlocked") == "true"
        assert window.vault_controller._idle_timer.isActive()
        assert window.vault_controller._idle_timer.interval() == VAULT_IDLE_TIMEOUT_SECONDS * 1000
        assert window.vault_panel.isHidden()  # No drawer needs to be opened to initialize it.
        assert window.security_controller.auto_lock_timer.isActive() is (timeout > 0)
        if timeout:
            assert window.security_controller.auto_lock_timer.interval() == timeout * 60_000
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("primary", [False, True])
def test_one_password_unlocks_both_before_capture_and_preserves_vault_auto_lock(
    mock_dashboard, monkeypatch, primary,
):
    dash = mock_dashboard
    seed_locked_vault(dash)
    dash._startup_locked = True  # Also exercise background/autostart authentication.
    dash._settings["detect_passwords"] = False
    backend = MagicMock()
    dash.watcher = ClipboardWatcher(backend=backend)
    dash.watcher.new_text_captured.connect(dash.history_controller.on_text_captured)
    captured, candidates = [], []
    dash.watcher.new_text_captured.connect(lambda iid, text: captured.append(text))
    dash.watcher.secret_candidate_detected.connect(candidates.append)
    attach_send_to_vault(dash)
    starts = []
    backend.start.side_effect = lambda: starts.append((
        not dash._is_locked(), dash.vault_controller.is_unlocked,
        dash.security_service.vault.match_clipboard_secret(KNOWN_SECRET),
    ))
    dialogs = []

    def authenticate(dialog):
        dialogs.append(dialog)
        return submit_password(dialog)

    monkeypatch.setattr(LockScreen, "exec", authenticate)
    assert dash._show_lock_screen(show_dashboard=False)
    assert len(dialogs) == 1
    assert starts == [(True, True, True)]
    assert dash.vault_controller._idle_timer.isActive()
    assert dash.vault_panel.badge_lbl.property("unlocked") == "true"

    source = "primary_selection" if primary else None
    text = "Ordinary text copied immediately after DotGhostBoard unlock"
    dash.watcher._on_clipboard_event(ClipboardEvent("text", text, source_app=source))
    item = storage.get_item_by_content(text)
    assert item is not None and item["id"] in dash.history_controller.cards
    dash.watcher._on_clipboard_event(ClipboardEvent("text", KNOWN_SECRET, source_app=source))
    assert storage.get_item_by_content(KNOWN_SECRET) is None
    assert captured == [text]  # The outbound sync signal never includes the secret.
    assert candidates == []
    assert dash.findChild(SecretDetectedToast) is None

    # Vault expires independently; Dashboard stays usable and recognition survives.
    dash.vault_controller._idle_timer.timeout.emit()
    assert not dash.vault_controller.is_unlocked
    assert dash.security_service.vault._vault_dek is None
    assert not dash.vault_controller._idle_timer.isActive()
    assert dash.vault_panel.badge_lbl.property("unlocked") == "false"
    assert not dash._is_locked()
    dash.watcher._on_clipboard_event(ClipboardEvent("text", KNOWN_SECRET, source_app=source))
    after_lock = "Ordinary note after the Vault idle timeout"
    dash.watcher._on_clipboard_event(ClipboardEvent("text", after_lock, source_app=source))
    assert storage.get_item_by_content(KNOWN_SECRET) is None
    assert storage.get_item_by_content(after_lock) is not None
    assert captured == [text, after_lock]

    # Locking/re-authenticating the whole app opens both again with one password.
    dash.security_controller.lock()
    assert dash.security_service.active_key is None
    assert dash._is_locked()
    assert dash._show_lock_screen(show_dashboard=False)
    assert len(dialogs) == 2
    assert dash.vault_controller.is_unlocked
    assert dash.vault_controller._idle_timer.isActive()


def test_session_lock_stops_vault_timers_and_scrubs_revealed_ui(mock_dashboard, monkeypatch):
    dash = mock_dashboard
    item_id = seed_locked_vault(dash)
    monkeypatch.setattr(LockScreen, "exec", submit_password)
    assert dash.security_controller.prompt_unlock()
    service = dash.security_service
    old_session_key, old_dek = service._active_key, service.vault._vault_dek
    dash.vault_controller.reveal_secret(item_id)
    scrub_ui = MagicMock()
    dash.vault_panel.scrub_all_revealed = scrub_ui
    dash.vault_controller._clipboard_scrub_timer.start(30_000)

    dash.security_controller.lock()

    assert service.is_locked and not dash.vault_controller.is_unlocked
    assert service.active_key is None and service.vault._vault_dek is None
    assert not any(old_session_key) and not any(old_dek)
    assert not dash.vault_controller._idle_timer.isActive()
    assert not dash.vault_controller._clipboard_scrub_timer.isActive()
    assert scrub_ui.called
    assert dash.vault_panel.badge_lbl.property("unlocked") == "false"


def test_wrong_or_cancelled_authentication_does_not_open_either(mock_dashboard, monkeypatch):
    dash = mock_dashboard
    seed_locked_vault(dash)

    def wrong_password(dialog):
        dialog.pw_input.setText("WrongPassword99!")
        dialog._on_submit()
        assert dialog.get_key() is None
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(LockScreen, "exec", wrong_password)
    assert not dash._show_lock_screen(show_dashboard=False)
    monkeypatch.setattr(LockScreen, "exec", lambda dialog: QDialog.DialogCode.Rejected)
    assert not dash._show_lock_screen(show_dashboard=False)
    assert dash._is_locked() and not dash.vault_controller.is_unlocked
    assert not dash.vault_controller._idle_timer.isActive()
    assert dash.security_service.active_key is None


def test_failed_vault_unwrap_does_not_publish_an_unlocked_dashboard(mock_dashboard, monkeypatch):
    dash = mock_dashboard
    seed_locked_vault(dash)
    dash.security_service.vault._repo.set_metadata("wrapped_dek", "corrupted-envelope")
    monkeypatch.setattr(LockScreen, "exec", submit_password)
    warning = MagicMock()
    monkeypatch.setattr("ui.controllers.security_controller.QMessageBox.warning", warning)
    states = []
    dash.security_controller.lock_state_changed.connect(states.append)

    assert not dash._show_lock_screen(show_dashboard=False)
    assert states == [True]
    assert dash._is_locked() and not dash.vault_controller.is_unlocked
    assert dash.security_service.active_key is None
    assert dash.security_service.vault._vault_dek is None
    assert not dash.vault_controller._idle_timer.isActive()
    warning.assert_called_once()
    assert "has not been reset or deleted" in warning.call_args.args[2]


@pytest.mark.parametrize("corruption", ["corrupt-envelope", None, "invalid-dek"])
def test_startup_reports_vault_key_failure_without_resetting_data(mock_dashboard, monkeypatch, corruption):
    import base64
    from main import _create_dashboard
    from core.security.vault import VaultRepository

    seed_locked_vault(mock_dashboard)
    repo = VaultRepository()
    if corruption is None:
        repo.delete_metadata("wrapped_dek")
    else:
        if corruption == "invalid-dek":
            corruption = crypto.encrypt(
                base64.urlsafe_b64encode(b"short-key").decode("ascii"),
                crypto.derive_vault_key(PASSWORD),
            )
        repo.set_metadata("wrapped_dek", corruption)
    before = [(item.id, item.ciphertext) for item in repo.list_items()]
    message = MagicMock()
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.critical", message)
    create_ui = MagicMock()
    monkeypatch.setattr(Dashboard, "_build_ui", create_ui)

    assert _create_dashboard(startup_locked=False, active_key=crypto.derive_key(PASSWORD)) is None

    create_ui.assert_not_called()
    message.assert_called_once()
    assert "has not been reset or deleted" in message.call_args.args[2]
    assert repo.get_metadata("wrapped_dek") == corruption
    assert [(item.id, item.ciphertext) for item in repo.list_items()] == before


def test_dashboard_idle_lock_resets_while_typing_in_search(mock_dashboard, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    dash = mock_dashboard
    seed_locked_vault(dash)
    dash._settings['auto_lock_minutes'] = 5
    monkeypatch.setattr(LockScreen, 'exec', submit_password)
    assert dash._show_lock_screen(show_dashboard=False)
    timer = dash.security_controller.auto_lock_timer
    timer.start(10_000)  # Simulate an almost-expired idle period without sleeping.
    QTest.keyClick(dash.search_box, Qt.Key.Key_A)
    assert timer.isActive() and timer.remainingTime() > 200_000
    assert dash.search_box.text() == 'a'

    dash._settings['auto_lock_minutes'] = 0
    dash._reset_auto_lock()
    assert not timer.isActive()
    assert dash.vault_controller._idle_timer.isActive()
