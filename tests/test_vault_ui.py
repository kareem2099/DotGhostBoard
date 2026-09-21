"""
tests/test_vault_ui.py
──────────────────────
Comprehensive unit and integration tests for Phase 7: The Vault UI subsystem.
Covers VaultController, SecretCard, VaultUnlockDialog, SecretDialog, VaultPanel,
and Dashboard coordination.
"""

from unittest.mock import MagicMock
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

import core.crypto as crypto
import core.security.vault.database as vdb
import core.storage as storage
from core.crypto import save_master_password
from core.security.vault import (
    VaultLockedError,
    VaultRepository,
    VaultService,
    init_vault_db,
)
from ui.vault import (
    SecretCard,
    SecretDialog,
    VaultController,
    VaultPanel,
    VaultUnlockDialog,
)


class InMemoryClipboard:
    def __init__(self):
        self._text = ""
        self._mime = None

    def text(self):
        return self._text

    def setText(self, val):
        self._text = str(val) if val is not None else ""

    def setMimeData(self, md):
        self._mime = md
        if md and hasattr(md, "text"):
            self._text = md.text()
        else:
            self._text = ""

    def mimeData(self):
        return self._mime

    def clear(self):
        self._text = ""
        self._mime = None


@pytest.fixture
def vault_ui_env(tmp_path, monkeypatch):
    """Sandbox configuration, salts, and vault database for UI tests."""
    vault_db_file = str(tmp_path / "vault_ui_test.db")
    ghost_db_file = str(tmp_path / "ghost_ui_test.db")

    monkeypatch.setattr(crypto, "_CFG_DIR", str(tmp_path))
    monkeypatch.setattr(crypto, "_SALT_FILE", str(tmp_path / "eclipse.salt"))
    monkeypatch.setattr(crypto, "_VERIFY_FILE", str(tmp_path / "eclipse.verify"))
    monkeypatch.setattr(vdb, "VAULT_DB_PATH", vault_db_file)
    monkeypatch.setattr(storage, "DB_PATH", ghost_db_file)

    mem_clip = InMemoryClipboard()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: mem_clip))

    storage.init_db()
    init_vault_db(vault_db_file)

    # Initialize master password for testing
    save_master_password("TestMasterPass123!")

    repo = VaultRepository(vault_db_file)
    service = VaultService(repository=repo)
    controller = VaultController(vault_service=service)

    return {
        "repo": repo,
        "service": service,
        "controller": controller,
        "vault_db": vault_db_file,
        "password": "TestMasterPass123!",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. VaultController Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_vault_controller_init(vault_ui_env):
    controller = vault_ui_env["controller"]
    assert not controller.is_unlocked
    assert controller.count() == 0


def test_vault_controller_unlock_success(vault_ui_env):
    controller = vault_ui_env["controller"]
    unlocked_events = []
    controller.vault_unlocked.connect(lambda: unlocked_events.append(True))

    success = controller.unlock(vault_ui_env["password"])
    assert success is True
    assert controller.is_unlocked is True
    assert len(unlocked_events) == 1


def test_vault_controller_unlock_failure(vault_ui_env):
    controller = vault_ui_env["controller"]
    success = controller.unlock("WrongPassword999!")
    assert success is False
    assert controller.is_unlocked is False


def test_vault_controller_lock(vault_ui_env):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    assert controller.is_unlocked is True

    locked_events = []
    controller.vault_locked.connect(lambda: locked_events.append(True))

    controller.lock()
    assert controller.is_unlocked is False
    assert len(locked_events) == 1


def test_vault_controller_idle_lock(vault_ui_env):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    assert controller.is_unlocked is True

    # Simulate idle timeout
    controller._idle_timer.timeout.emit()
    assert controller.is_unlocked is False


def test_vault_controller_reveal_and_copy_exception_handling(vault_ui_env, monkeypatch):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])

    # Mock service.get_secret to raise an unexpected SQLite / Decryption exception
    monkeypatch.setattr(controller.service, "get_secret", MagicMock(side_effect=RuntimeError("Corrupted SQLite record")))

    msgs = []
    controller.status_message.connect(lambda m: msgs.append(m))

    assert controller.reveal_secret(999) is None
    assert any("Decryption error" in m for m in msgs)

    assert controller.copy_secret(999) is False
    assert any("Decryption error" in m for m in msgs)


def test_vault_controller_add_and_list_secrets(vault_ui_env):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])

    item_id = controller.add_secret("Prod AWS Key", "AKIAIOSFODNN7EXAMPLE", category="token")
    assert item_id > 0

    item_id2 = controller.add_secret("Admin SSH Key", "ssh-ed25519 AAAAC3NzaC1", category="key")
    assert item_id2 > 0

    all_items = controller.list_secrets()
    assert len(all_items) == 2

    token_items = controller.list_secrets(category="token")
    assert len(token_items) == 1
    assert token_items[0].title == "Prod AWS Key"

    filtered = controller.list_secrets(search_query="Admin")
    assert len(filtered) == 1
    assert filtered[0].title == "Admin SSH Key"


def test_vault_controller_add_secret_locked_error(vault_ui_env):
    controller = vault_ui_env["controller"]
    with pytest.raises(VaultLockedError):
        controller.add_secret("Secret", "Payload")


def test_vault_controller_add_secret_validation(vault_ui_env):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])

    with pytest.raises(ValueError, match="title cannot be empty"):
        controller.add_secret("   ", "ValidPayload")

    with pytest.raises(ValueError, match="content cannot be empty"):
        controller.add_secret("ValidTitle", "")


def test_vault_controller_update_secret(vault_ui_env):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])

    item_id = controller.add_secret("Staging DB", "postgres://old_user:pass@host", category="password")
    success = controller.update_secret(item_id, title="Prod DB", secret_text="postgres://new_user:pass@host", category="password")
    assert success is True

    updated_secret = controller.reveal_secret(item_id)
    assert updated_secret == "postgres://new_user:pass@host"

    summaries = controller.list_secrets()
    assert summaries[0].title == "Prod DB"


def test_vault_controller_delete_secret(vault_ui_env):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])

    item_id = controller.add_secret("To Delete", "secret123")
    assert controller.count() == 1

    success = controller.delete_secret(item_id)
    assert success is True
    assert controller.count() == 0


def test_vault_controller_reveal_secret(vault_ui_env):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])

    item_id = controller.add_secret("Github PAT", "ghp_mockSecretToken42")
    revealed = controller.reveal_secret(item_id)
    assert revealed == "ghp_mockSecretToken42"


def test_vault_controller_reveal_secret_locked(vault_ui_env):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("Secret", "Value")
    controller.lock()

    assert controller.reveal_secret(item_id) is None


def test_vault_controller_copy_secret(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])

    item_id = controller.add_secret("CopyTest", "super_secret_copied_value")
    copied_signals = []
    controller.secret_copied.connect(lambda iid: copied_signals.append(iid))

    success = controller.copy_secret(item_id)
    assert success is True
    assert len(copied_signals) == 1
    assert copied_signals[0] == item_id
    assert QApplication.clipboard().text() == "super_secret_copied_value"


def test_vault_controller_find_duplicate(vault_ui_env):
    controller = vault_ui_env["controller"]

    # When locked, must return None
    assert not controller.is_unlocked
    assert controller.find_duplicate("my_secret_pass_123") is None

    controller.unlock(vault_ui_env["password"])
    assert controller.find_duplicate("my_secret_pass_123") is None

    # Add secret
    item_id = controller.add_secret("Gmail Account", "my_secret_pass_123", category="password")

    # Matching exact plaintext
    dup = controller.find_duplicate("my_secret_pass_123")
    assert dup is not None
    assert dup.id == item_id
    assert dup.title == "Gmail Account"

    # Non-matching plaintext
    assert controller.find_duplicate("other_pass_999") is None

    # Lock again -> returns None
    controller.lock()
    assert controller.find_duplicate("my_secret_pass_123") is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. SecretCard Component Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_secret_card_masked_by_default(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("AWS API Key", "super_secret_key", category="token")
    summary = controller.list_secrets()[0]

    card = SecretCard(summary, controller)
    assert card.title_label.text() == "AWS API Key"
    assert card.title_label.textFormat() == Qt.TextFormat.PlainText
    assert card.payload_label.text() == "••••••••••••••••"
    assert card.payload_label.textFormat() == Qt.TextFormat.PlainText
    assert card.payload_label.maximumHeight() == 120
    assert card.payload_label.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction
    assert not card.is_revealed
    assert "TOKEN" in card.cat_badge.text()


def test_secret_card_reveal_toggle(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("RevealCardTest", "decrypted_token_value", category="token")
    summary = controller.list_secrets()[0]

    card = SecretCard(summary, controller)

    # First click: Reveal
    card.reveal_btn.click()
    assert card.is_revealed is True
    assert card.payload_label.text() == "decrypted_token_value"
    assert card.reveal_btn.text() == "🙈 Hide"

    # Second click: Hide/Mask
    card.reveal_btn.click()
    assert card.is_revealed is False
    assert card.payload_label.text() == "••••••••••••••••"
    assert card.reveal_btn.text() == "👁️ Reveal"


def test_secret_card_scrub_on_vault_lock(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("ScrubTest", "must_be_scrubbed")
    summary = controller.list_secrets()[0]

    card = SecretCard(summary, controller)
    card.reveal_btn.click()
    assert card.payload_label.text() == "must_be_scrubbed"

    # Lock controller -> Card must immediately scrub revealed plaintext
    controller.lock()
    assert not card.is_revealed
    assert card.payload_label.text() == "••••••••••••••••"
    assert card._revealed_text is None


def test_secret_card_copy_button(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("CardCopy", "payload_to_copy")
    summary = controller.list_secrets()[0]

    card = SecretCard(summary, controller)
    card.copy_btn.click()
    assert QApplication.clipboard().text() == "payload_to_copy"
    assert card.copy_btn.text() == "✓ Copied!"


def test_secret_card_edit_and_delete_signals(vault_ui_env, qapp, monkeypatch):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("SignalTest", "val")
    summary = controller.list_secrets()[0]

    card = SecretCard(summary, controller)

    edit_signals = []
    card.edit_requested.connect(lambda iid: edit_signals.append(iid))
    card.edit_btn.click()
    assert edit_signals == [item_id]

    delete_signals = []
    card.delete_requested.connect(lambda iid: delete_signals.append(iid))

    # Mock user answering Yes to deletion confirmation
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    card.delete_btn.click()
    assert delete_signals == [item_id]


# ══════════════════════════════════════════════════════════════════════════════
# 3. VaultUnlockDialog & SecretDialog Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_vault_unlock_dialog_validation(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    dlg = VaultUnlockDialog(controller)

    # Empty password
    dlg.pw_input.setText("")
    dlg.submit_btn.click()
    assert "cannot be empty" in dlg.error_lbl.text()
    assert not controller.is_unlocked


def test_vault_unlock_dialog_submit_wrong_and_correct(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    dlg = VaultUnlockDialog(controller)

    # Wrong password
    dlg.pw_input.setText("WrongPass123!")
    dlg.submit_btn.click()
    assert "Incorrect" in dlg.error_lbl.text()
    assert not controller.is_unlocked

    # Correct password
    dlg.pw_input.setText(vault_ui_env["password"])
    dlg.submit_btn.click()
    assert controller.is_unlocked is True


def test_secret_dialog_add_mode_validation(qapp):
    dlg = SecretDialog()

    # Empty title
    dlg.title_input.setText("")
    dlg.secret_input.setPlainText("Some secret")
    dlg.save_btn.click()
    assert "Title cannot be empty" in dlg.error_lbl.text()

    # Empty payload in add mode
    dlg.title_input.setText("Valid Title")
    dlg.secret_input.setPlainText("")
    dlg.save_btn.click()
    assert "Secret payload cannot be empty" in dlg.error_lbl.text()

    # Valid
    dlg.secret_input.setPlainText("Valid secret text")
    dlg.save_btn.click()
    title, payload, category = dlg.get_data()
    assert title == "Valid Title"
    assert payload == "Valid secret text"
    assert category == "generic"


def test_secret_dialog_edit_mode(qapp):
    dlg = SecretDialog(title="Existing Key", category="key", item_id=42)
    assert dlg.title_input.text() == "Existing Key"
    assert dlg.cat_combo.currentData() == "key"

    # In edit mode, empty payload keeps original payload (returns None)
    dlg.save_btn.click()
    title, payload, category = dlg.get_data()
    assert title == "Existing Key"
    assert payload is None
    assert category == "key"


def test_secret_dialog_reject_scrubs_secret_input(qapp):
    dlg = SecretDialog()
    dlg.secret_input.setPlainText("SensitiveTokenXYZ")
    dlg.title_input.setText("SecretTitle")
    dlg.reject()
    assert dlg.secret_input.toPlainText() == ""
    assert dlg.title_input.text() == ""


def test_vault_unlock_dialog_accept_scrubs_pw_input(vault_ui_env, qapp):
    dlg = VaultUnlockDialog(controller=vault_ui_env["controller"])
    dlg.pw_input.setText(vault_ui_env["password"])
    dlg.accept()
    assert dlg.pw_input.text() == ""


# ══════════════════════════════════════════════════════════════════════════════
# 4. VaultPanel Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_vault_panel_toggle_visibility(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    panel = VaultPanel(controller)
    assert panel.objectName() == "VaultPanel"

    vis_events = []
    controller.panel_visibility_changed.connect(lambda v: vis_events.append(v))

    panel.show_panel()
    assert panel.isVisible()
    assert vis_events[-1] is True

    panel.hide_panel()
    assert not panel.isVisible()
    assert vis_events[-1] is False

    panel.toggle_panel()
    assert panel.isVisible()
    assert vis_events[-1] is True


def test_vault_panel_locked_state_render(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    panel = VaultPanel(controller)
    assert not controller.is_unlocked
    assert "Locked" in panel.badge_lbl.text()


def test_vault_panel_initial_badge_when_unlocked(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])

    panel = VaultPanel(controller)
    assert controller.is_unlocked
    assert "Unlocked" in panel.badge_lbl.text()
    assert panel.badge_lbl.property("unlocked") == "true"


def test_vault_panel_category_filter_switching(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    controller.add_secret("SSH Key", "ssh-rsa ...", category="key")
    controller.add_secret("Bank Password", "Pass123", category="password")

    panel = VaultPanel(controller)
    panel.show_panel()

    # 'all' category has 2 cards + 1 stretch = 3 items
    assert panel.cards_layout.count() - 1 == 2

    # Switch to 'password' category
    panel._on_category_selected("password")
    assert panel._active_category == "password"
    # Exactly 1 card shown in layout
    assert panel.cards_layout.count() - 1 == 1
    card = panel.cards_layout.itemAt(0).widget()
    assert isinstance(card, SecretCard)
    assert card.summary.title == "Bank Password"


def test_vault_panel_search_filtering(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    controller.add_secret("Production Database", "db_pass_1", category="password")
    controller.add_secret("Development Redis", "redis_pass_2", category="password")

    panel = VaultPanel(controller)
    panel.show_panel()

    panel.search_box.setText("Database")
    panel._apply_debounced_search()
    assert panel._search_query == "Database"
    assert panel.cards_layout.count() - 1 == 1
    card = panel.cards_layout.itemAt(0).widget()
    assert isinstance(card, SecretCard)
    assert card.summary.title == "Production Database"


def test_vault_panel_hide_scrubs_revealed_cards(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("RevealHideTest", "ephemeral_payload")

    panel = VaultPanel(controller)
    panel.show_panel()

    card = panel.cards_layout.itemAt(0).widget()
    card.reveal_btn.click()
    assert card.is_revealed is True
    assert card.payload_label.text() == "ephemeral_payload"

    # Hiding panel must scrub revealed plaintext from memory/card
    panel.hide_panel()
    assert not card.is_revealed
    assert card.payload_label.text() == "••••••••••••••••"
    assert card._revealed_text is None


def test_vault_panel_guarded_slot_exceptions(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    panel = VaultPanel(controller)

    # Calling a guarded function that raises VaultLockedError should not crash
    messages = []
    controller.status_message.connect(lambda m: messages.append(m))

    res = panel._guarded(controller.add_secret, "Title", "Payload")
    assert res is None
    assert any("Vault is locked" in m for m in messages)


def test_vault_panel_save_with_relock_retry(vault_ui_env, qapp, monkeypatch):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    panel = VaultPanel(controller)

    # Simulate: user opened add secret dialog while unlocked, but vault locked before saving
    controller.lock()
    assert not controller.is_unlocked

    # Mock prompt_unlock to simulate successful re-authentication
    monkeypatch.setattr(panel, "_prompt_unlock", lambda: controller.unlock(vault_ui_env["password"]))

    # Calling _save_with_relock_retry prompts unlock and successfully saves
    res = panel._save_with_relock_retry(controller.add_secret, "SavedAfterRelock", "my_val", category="generic")
    assert res is not None
    assert controller.is_unlocked is True
    assert any(s.title == "SavedAfterRelock" for s in controller.list_secrets())


def test_vault_panel_prompt_add_duplicate_secret(vault_ui_env, monkeypatch):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    panel = VaultPanel(controller)

    # First add
    first_id = controller.add_secret("Gmail Password", "secret_duplicate_candidate", category="password")

    # Second add with same secret payload via _prompt_add_secret
    from ui.vault.secret_dialog import SecretDialog
    monkeypatch.setattr(SecretDialog, "exec", lambda self: SecretDialog.DialogCode.Accepted)
    monkeypatch.setattr(SecretDialog, "get_data", lambda self: ("Password Gmail", "secret_duplicate_candidate", "password"))

    statuses = []
    controller.status_message.connect(statuses.append)

    ret_id = panel._prompt_add_secret(prefill_secret="secret_duplicate_candidate")
    assert ret_id == first_id, "Must return existing dup.id on duplicate"
    assert controller.count() == 1, "Must not create second item in vault database"
    assert any("Already saved as 'Gmail Password'" in s for s in statuses)


def test_vault_panel_event_filter_touches_idle_timer(vault_ui_env, qapp):
    panel = VaultPanel(controller=vault_ui_env["controller"])
    panel.controller.unlock(vault_ui_env["password"])
    panel.show_panel()

    touch_called = []
    panel.controller._idle_timer.start = lambda ms: touch_called.append(ms)

    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
    app = QApplication.instance()
    app.sendEvent(panel.search_box, key_event)

    assert len(touch_called) > 0
    panel.hide_panel()


def test_vault_panel_activity_filter_detects_dialog_keypress(vault_ui_env, qapp):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent

    panel = VaultPanel(controller=vault_ui_env["controller"])
    panel.controller.unlock(vault_ui_env["password"])
    panel.show_panel()

    spy_touch = MagicMock()
    panel.controller.touch = spy_touch

    dlg = SecretDialog(parent=panel)
    key_ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.NoModifier, "x")
    QApplication.sendEvent(dlg.title_input, key_ev)

    spy_touch.assert_called()
    dlg.deleteLater()
    panel.hide_panel()


def test_vault_controller_self_paste_announcement(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("SelfPasteTest", "dont_capture_me")

    announced = []
    controller.secret_copy_starting.connect(lambda: announced.append(True))

    controller.copy_secret(item_id)
    assert len(announced) == 1


def test_vault_controller_clipboard_auto_clear(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("AutoClearTest", "clear_after_timeout")

    controller.copy_secret(item_id, auto_clear_seconds=30)
    assert QApplication.clipboard().text() == "clear_after_timeout"
    assert controller._pending_clipboard_hash is not None

    # Trigger timeout callback directly
    controller._on_clipboard_scrub_timeout()
    assert QApplication.clipboard().text() == ""
    assert controller._pending_clipboard_hash is None


def test_clipboard_kept_if_user_copied_something_else(vault_ui_env, qapp):
    c = vault_ui_env["controller"]
    c.unlock(vault_ui_env["password"])
    iid = c.add_secret("X", "secret_val")
    c.copy_secret(iid)
    QApplication.clipboard().setText("something else")
    c._on_clipboard_scrub_timeout()
    assert QApplication.clipboard().text() == "something else"


def test_self_paste_announced_before_clipboard_write(vault_ui_env, qapp):
    c = vault_ui_env["controller"]
    c.unlock(vault_ui_env["password"])
    iid = c.add_secret("X", "secret_val")
    QApplication.clipboard().clear()
    seen = []
    c.secret_copy_starting.connect(lambda: seen.append(QApplication.clipboard().text()))
    c.copy_secret(iid)
    assert seen and seen[0] != "secret_val"


def test_vault_lock_scrubs_clipboard_immediately(vault_ui_env, qapp):
    c = vault_ui_env["controller"]
    c.unlock(vault_ui_env["password"])
    iid = c.add_secret("AutoWipe", "wipe_on_lock_now")
    c.copy_secret(iid)
    assert QApplication.clipboard().text() == "wipe_on_lock_now"

    # Locking vault immediately scrubs the secret without waiting for timer
    c.lock()
    assert QApplication.clipboard().text() == ""


def test_vault_lock_preserve_clipboard_when_flag_false(vault_ui_env, qapp):
    c = vault_ui_env["controller"]
    c.unlock(vault_ui_env["password"])
    iid = c.add_secret("KeepClip", "dont_wipe_on_hide")
    c.copy_secret(iid)
    assert QApplication.clipboard().text() == "dont_wipe_on_hide"

    # Locking vault with wipe_clipboard=False preserves clipboard for pasting
    c.lock(wipe_clipboard=False)
    assert not c.is_unlocked
    assert QApplication.clipboard().text() == "dont_wipe_on_hide"

    # When scrub timer expires, it wipes clipboard and announces "Clipboard cleared"
    statuses = []
    c.status_message.connect(statuses.append)
    c._on_clipboard_scrub_timeout()
    assert QApplication.clipboard().text() == ""
    assert "Clipboard cleared" in statuses


# ══════════════════════════════════════════════════════════════════════════════
# 5. Dashboard Vault Coordination Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_dashboard_vault_integration(mock_dashboard):
    dash = mock_dashboard
    assert hasattr(dash, "vault_controller")
    assert hasattr(dash, "vault_panel")
    assert hasattr(dash, "vault_shortcut")
    assert hasattr(dash.sidebar_widget, "vault_btn")
    assert hasattr(dash.topbar, "vault_btn")

    # Initially vault panel is hidden
    assert dash.vault_panel.isHidden()

    # Sidebar vault button toggles vault panel
    dash.sidebar_widget.vault_btn.click()
    assert not dash.vault_panel.isHidden()

    # Toggling again hides it
    dash._toggle_vault()
    assert dash.vault_panel.isHidden()

    # When window is visible, toggling panel expands and restores window width
    dash.show()
    orig_w = dash.width()
    dash._toggle_vault()
    assert not dash.vault_panel.isHidden()
    assert dash.width() >= orig_w + 300

    # Available width should exclude drawer width, keeping sidebar compact/hidden
    QApplication.processEvents()
    assert not dash.sidebar_widget.isVisible()

    dash._toggle_vault()
    assert dash.vault_panel.isHidden()
    assert dash.width() == orig_w


def test_dashboard_topbar_vault_button(mock_dashboard):
    dash = mock_dashboard
    assert dash.vault_panel.isHidden()

    dash.topbar.vault_btn.click()
    assert not dash.vault_panel.isHidden()

    dash.topbar.vault_btn.click()
    assert dash.vault_panel.isHidden()


def test_dashboard_secret_copy_marks_self_paste(mock_dashboard, monkeypatch):
    dash = mock_dashboard
    dash.watcher = MagicMock()

    # Emitting secret_copy_starting must invoke watcher.mark_self_paste
    dash.vault_controller.secret_copy_starting.emit()
    dash.watcher.mark_self_paste.assert_called_once()


def test_dashboard_session_lock_auto_locks_vault(mock_dashboard, monkeypatch):
    dash = mock_dashboard
    monkeypatch.setattr(VaultController, "is_unlocked", property(lambda self: True))
    spy = MagicMock()
    monkeypatch.setattr(dash.vault_controller, "lock", spy)

    dash._on_lock_state_changed(is_locked=True)
    spy.assert_called_once()


def test_dashboard_toggle_visibility_locks_vault(mock_dashboard):
    dash = mock_dashboard
    save_master_password("TestMasterPass123!")
    dash.vault_controller.unlock("TestMasterPass123!")
    assert dash.vault_controller.is_unlocked is True

    dash.show()
    assert dash.isVisible()

    # Toggling visibility when visible should lock the vault and hide
    dash.toggle_visibility()
    assert not dash.isVisible()
    assert dash.vault_controller.is_unlocked is False


def test_vault_panel_activity_filter_restored_after_dashboard_hide_show(mock_dashboard):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent

    dash = mock_dashboard
    dash.show()
    dash.vault_panel.show_panel()
    assert not dash.vault_panel.isHidden()
    assert dash.vault_panel.isVisible()

    # Hide and re-show dashboard
    dash.hide()
    dash.show()
    QApplication.processEvents()

    # Spy on vault_controller.touch
    spy_touch = MagicMock()
    dash.vault_controller.touch = spy_touch

    # Send key press to search_box
    key_ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
    QApplication.sendEvent(dash.vault_panel.search_box, key_ev)

    spy_touch.assert_called()


def test_vault_copy_sets_password_manager_mime_hint(vault_ui_env, qapp):
    controller = vault_ui_env["controller"]
    controller.unlock(vault_ui_env["password"])
    item_id = controller.add_secret("MimeTest", "mime_secret_data")

    controller.copy_secret(item_id)
    mime = QApplication.clipboard().mimeData()
    assert mime is not None
    assert mime.text() == "mime_secret_data"
    assert mime.hasFormat("x-kde-passwordManagerHint")
    assert bytes(mime.data("x-kde-passwordManagerHint")) == b"secret"


def test_qt_clipboard_backend_ignores_password_manager_hint(qapp):
    from core.clipboard.backends.qt_backend import QtClipboardBackend
    from PyQt6.QtCore import QMimeData

    backend = QtClipboardBackend()
    captured = []
    backend.set_on_event(lambda ev: captured.append(ev))

    md = QMimeData()
    md.setText("sensitive_password")
    md.setData("x-kde-passwordManagerHint", b"secret")
    QApplication.clipboard().setMimeData(md)

    backend._check_clipboard()
    assert len(captured) == 0

    # Positive control: verify normal clipboard content is captured
    md2 = QMimeData()
    md2.setText("plain_control")
    QApplication.clipboard().setMimeData(md2)
    backend._check_clipboard()
    assert [e.content for e in captured] == ["plain_control"]


def test_vault_copy_secret_ignored_by_watcher_integration(mock_dashboard):
    dash = mock_dashboard
    from PyQt6.QtTest import QTest
    from core.watcher import ClipboardWatcher

    dash.show()
    dash.activateWindow()
    QTest.qWait(600)

    dash.watcher = ClipboardWatcher()
    captured = []
    dash.watcher.new_text_captured.connect(lambda iid, text: captured.append(text))
    dash.watcher.start()
    QTest.qWait(600)

    save_master_password("TestMasterPass123!")
    dash.vault_controller.unlock("TestMasterPass123!")
    item_id = dash.vault_controller.add_secret("TokenA", "sensitive_vault_secret_987")

    try:
        QApplication.clipboard().setText("control_text_123")
        QTest.qWait(1500)
        if "control_text_123" not in captured:
            pytest.skip(f"watcher never captured control text (captured={captured!r})")
        dash.vault_controller.copy_secret(item_id)
        QTest.qWait(1500)
        assert "sensitive_vault_secret_987" not in captured
    finally:
        dash.watcher.stop()


def test_dashboard_line_count_under_500():
    from pathlib import Path
    dash_file = Path(__file__).resolve().parents[1] / "ui" / "dashboard.py"
    line_count = len(dash_file.read_text(encoding="utf-8").splitlines())
    assert line_count <= 500, f"ui/dashboard.py has {line_count} lines (must be <= 500)"


def test_dashboard_no_semicolon_chaining():
    import io
    import tokenize
    from pathlib import Path
    dash_file = Path(__file__).resolve().parents[1] / "ui" / "dashboard.py"
    content = dash_file.read_text(encoding="utf-8")
    tokens = tokenize.generate_tokens(io.StringIO(content).readline)
    semicolons = [tok for tok in tokens if tok.type == tokenize.OP and tok.string == ";"]
    assert len(semicolons) == 0, f"ui/dashboard.py has {len(semicolons)} semicolon-chained statements (E702)"
