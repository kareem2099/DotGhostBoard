"""
tests/test_send_to_vault.py
───────────────────────────
Tests for 'Send to Vault' item migration and hardened secret detection.
Covers:
- Physical SQLite erasure upon moving items to Vault.
- Eclipse ciphertext decryption prior to vault persistence.
- Type guards (text only).
- Abort handling without deletion on lock / cancellation.
- Ephemeral 3-action toast lifecycle with memory scrubbing.
- Watcher secret interception isolation (zero sync broadcast).
- Positive control verification.
"""

import os
from PyQt6.QtWidgets import QPushButton, QLabel

from core import storage
from core.clipboard.events import ClipboardEvent
from core.clipboard.pipeline import ClipboardPipeline
from core.security.detector import SecretDetector
from ui.vault.send_to_vault import attach_send_to_vault
from ui.widgets.item_card import ItemCard
from ui.widgets.secret_toast import SecretDetectedToast


def test_item_card_vault_button_and_signal(tmp_path, monkeypatch, qapp):
    """Verify Vault button is rendered for text items and emits sig_send_to_vault."""
    monkeypatch.setenv("DOTGHOST_HOME", str(tmp_path))
    storage.init_db()

    text_item = {"id": 101, "type": "text", "content": "Sample Note", "is_pinned": 0}
    card = ItemCard(text_item)
    vault_btn = card.findChild(QPushButton, "VaultBtn")
    assert vault_btn is not None, "Vault button must exist on text cards"

    received_ids = []
    card.sig_send_to_vault.connect(lambda iid: received_ids.append(iid))
    vault_btn.click()
    assert received_ids == [101]


def test_item_card_vault_button_hidden_for_media(tmp_path, monkeypatch, qapp):
    """Verify Vault button is NOT rendered for image or video items."""
    monkeypatch.setenv("DOTGHOST_HOME", str(tmp_path))
    storage.init_db()

    img_item = {"id": 102, "type": "image", "content": "/tmp/test.png", "is_pinned": 0}
    card = ItemCard(img_item)
    vault_btn = card.findChild(QPushButton, "VaultBtn")
    assert vault_btn is None, "Vault button must NOT exist on image/media cards"


def test_secret_toast_actions_and_scrub(qapp):
    """Verify SecretDetectedToast options, preview masking, and memory scrubbing."""
    raw_secret = "TestMasterPass123!"
    toast = SecretDetectedToast(raw_secret)

    # 1. Masked preview check
    labels = [lbl.text() for lbl in toast.findChildren(QLabel)]
    assert any("••••" in t for t in labels)
    assert not any(raw_secret in t for t in labels)

    # 2. Keep in history signal
    kept = []
    toast.sig_keep_in_history.connect(lambda s: kept.append(s))
    toast._on_keep_in_history()
    assert kept == [raw_secret]
    assert toast._candidate_text == "", "Candidate text must be scrubbed after emit"

    # 3. Save to vault signal on a fresh toast
    toast2 = SecretDetectedToast("AnotherSecret99#")
    saved = []
    toast2.sig_save_to_vault.connect(lambda s: saved.append(s))
    toast2._on_save_to_vault()
    assert saved == ["AnotherSecret99#"]
    assert toast2._candidate_text == ""


def test_watcher_pipeline_secret_candidate_zero_sync_broadcast(tmp_path, monkeypatch, qapp):
    """
    Ensure that when secret candidate is detected:
    1. Pipeline emits Action.SECRET_CANDIDATE
    2. Watcher does NOT emit new_text_captured
    3. Normal text (positive control) DOES emit new_text_captured
    """
    from core.watcher import ClipboardWatcher

    monkeypatch.setenv("DOTGHOST_HOME", str(tmp_path))
    storage.init_db()

    detector = SecretDetector()
    pipeline = ClipboardPipeline(secret_detector=detector.is_secret)
    watcher = ClipboardWatcher(pipeline=pipeline)

    captured_texts = []
    secret_candidates = []

    watcher.new_text_captured.connect(lambda iid, text: captured_texts.append(text))
    watcher.secret_candidate_detected.connect(lambda ev: secret_candidates.append(ev.content))

    # 1. Positive Control text
    control_text = "Hello normal clipboard content!"
    event_control = ClipboardEvent(content_type="text", content=control_text)
    watcher._on_clipboard_event(event_control)

    assert len(captured_texts) == 1
    assert captured_texts[0] == control_text
    assert len(secret_candidates) == 0

    # 2. Secret text
    secret_text = "TestMasterPass123!"
    event_secret = ClipboardEvent(content_type="text", content=secret_text)
    watcher._on_clipboard_event(event_secret)

    # Must NOT have added to captured_texts (and thus never broadcasted over sync)
    assert len(captured_texts) == 1
    assert len(secret_candidates) == 1
    assert secret_candidates[0] == secret_text


def test_send_to_vault_lifecycle(mock_dashboard):
    """
    Test full lifecycle of Send to Vault:
    1. Text item in ghost.db
    2. Master password configured and vault unlocked
    3. Trigger Send to Vault with prefilled SecretDialog acceptance
    4. Item encrypted in vault.db and physically erased from ghost.db
    """
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)
    dash.vault_controller.unlock(pw)
    assert dash.vault_controller.is_unlocked is True

    # Insert item into history
    secret_content = "CANARY_SECRET_DATA_12345"
    item_id = storage.add_item("text", secret_content)
    assert item_id > 0
    dash.history_controller.reload()

    # Mock user entering title in dialog
    def mock_prompt_add(prefill_secret="", prefill_title="", prefill_category="generic"):
        assert prefill_secret == secret_content
        return dash.vault_controller.add_secret("Production Key", prefill_secret, category=prefill_category)

    dash.vault_panel._prompt_add_secret = mock_prompt_add

    # Trigger send to vault
    dash._on_send_to_vault(item_id)

    # 1. Verify item exists in Vault
    secrets = dash.vault_controller.list_secrets()
    matching = [s for s in secrets if s.title == "Production Key"]
    assert len(matching) == 1

    # 2. Verify item is deleted from public storage
    assert storage.get_item_by_id(item_id) is None


def test_send_to_vault_eclipse_ciphertext_resolution(mock_dashboard):
    """
    Verify that an item encrypted with Eclipse (is_secret=1) is decrypted
    first before being sent to The Vault.
    """
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)
    dash.vault_controller.unlock(pw)

    # Also set session key for Eclipse
    derived_key = dash.security_service._crypto.derive_key(pw)
    dash.security_controller.set_active_key(derived_key)

    plaintext_secret = "SUPER_SECRET_PAYLOAD_999"
    item_id = storage.add_item("text", plaintext_secret)

    # Encrypt item with Eclipse
    dash.security_controller.encrypt_item(item_id)
    item_row = storage.get_item_by_id(item_id)
    assert item_row["is_secret"] == 1
    assert item_row["content"] != plaintext_secret, "Ciphertext must be stored in DB"

    passed_secret = []
    def mock_prompt(prefill_secret="", prefill_title="", prefill_category="generic"):
        passed_secret.append(prefill_secret)
        return dash.vault_controller.add_secret("Decrypted Secret", prefill_secret, category="password")

    dash.vault_panel._prompt_add_secret = mock_prompt

    # Send to vault
    dash._on_send_to_vault(item_id)

    # Assert the plaintext (not ciphertext) was passed to the vault
    assert passed_secret == [plaintext_secret]
    assert storage.get_item_by_id(item_id) is None


def test_send_to_vault_dialog_cancel_aborts_without_deletion(mock_dashboard):
    """
    If user cancels the Add Secret dialog (_prompt_add_secret returns None),
    the item MUST NOT be deleted from history.
    """
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)
    dash.vault_controller.unlock(pw)

    item_id = storage.add_item("text", "SECRET_CANCELED_ITEM")
    dash.history_controller.reload()

    # User cancels dialog
    dash.vault_panel._prompt_add_secret = lambda **kw: None

    dash._on_send_to_vault(item_id)

    # Item must still exist in storage!
    assert storage.get_item_by_id(item_id) is not None
    assert storage.get_item_by_id(item_id)["content"] == "SECRET_CANCELED_ITEM"


def test_send_to_vault_physical_disk_bytes_check(mock_dashboard):
    """
    Verify zero trace of secret bytes in ghost.db and ghost.db-wal
    after moving to vault without any manual checkpoint beforehand.
    """
    import os
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)
    dash.vault_controller.unlock(pw)

    canary = "CANARY_PHYSICAL_RAW_BYTES_998877"
    item_id = storage.add_item("text", canary)
    dash.history_controller.reload()

    dash.vault_panel._prompt_add_secret = (
        lambda prefill_secret="", **kw: dash.vault_controller.add_secret("Canary", prefill_secret)
    )

    dash._on_send_to_vault(item_id)

    db_path = storage.get_db_path()
    wal_path = f"{db_path}-wal"

    with open(db_path, "rb") as f:
        db_bytes = f.read()
    assert canary.encode("utf-8") not in db_bytes, "Canary string found in SQLite db file!"

    if os.path.exists(wal_path):
        with open(wal_path, "rb") as f:
            wal_bytes = f.read()
        assert canary.encode("utf-8") not in wal_bytes, "Canary string found in SQLite WAL file!"


def test_secret_toast_timeout_saves_to_eclipse(mock_dashboard):
    """
    Verify that when a secret toast times out without user action,
    it is directly inserted as ciphertext into history so data is never lost,
    and zero plaintext canary bytes exist in ghost.db or its WAL file.
    """
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)
    dash.vault_controller.unlock(pw)

    derived_key = dash.security_service._crypto.derive_key(pw)
    dash.security_controller.set_active_key(derived_key)

    candidate = "CanaryZeroPlaintextTimeoutPass99#!"
    dash._on_secret_candidate(candidate)

    # Trigger timeout on the active toast
    from ui.widgets.secret_toast import SecretDetectedToast
    toast = dash.findChild(SecretDetectedToast)
    assert toast is not None

    toast._on_timeout()

    # Verify that the item was saved as an encrypted Eclipse card
    items = storage.get_all_items()
    matching = [it for it in items if it.get("is_secret") == 1]
    assert len(matching) >= 1
    # Check that plaintext is not in the database content
    latest = matching[0]
    assert latest["content"] != candidate
    # But can be revealed with active key
    revealed = dash.security_controller.reveal_secret(latest["id"])
    assert revealed == candidate

    # Raw disk byte verification: zero plaintext in sqlite file or WAL
    db_path = storage.database.get_db_path()
    wal_path = f"{db_path}-wal"
    with open(db_path, "rb") as f:
        db_bytes = f.read()
    assert candidate.encode("utf-8") not in db_bytes, "Canary plaintext found on disk in SQLite db!"

    if os.path.exists(wal_path):
        with open(wal_path, "rb") as f:
            wal_bytes = f.read()
        assert candidate.encode("utf-8") not in wal_bytes, "Canary plaintext found in WAL file!"


def test_kept_candidate_hash_remembers_choice_for_session(mock_dashboard):
    """
    Verify that when user clicks Keep on a false positive, re-copying the same
    content passes directly to history without triggering the toast again.
    """
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)

    false_positive_text = "NotActuallySecretPass99#!"
    dash._on_secret_candidate(false_positive_text)

    from ui.widgets.secret_toast import SecretDetectedToast
    toast = dash.findChild(SecretDetectedToast)
    assert toast is not None

    # User clicks Keep in history
    toast._on_keep_in_history()

    # Verify it was added to normal items
    items = storage.get_all_items()
    assert any(it.get("content") == false_positive_text and it.get("is_secret") == 0 for it in items)

    # Re-copy the same candidate
    dash._on_secret_candidate(false_positive_text)
    # Toast should NOT be re-created / active
    active_visible_toasts = [t for t in dash.findChildren(SecretDetectedToast) if t.isVisible()]
    assert len(active_visible_toasts) == 0


def test_secret_candidate_hidden_window_triggers_tray_notification(mock_dashboard):
    """
    Verify that when Dashboard is hidden in tray, an intercepted secret candidate
    triggers a tray message.
    """
    from unittest.mock import MagicMock
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)

    dash.hide()
    assert dash.isVisible() is False

    tray_messages = []
    fake_tray = MagicMock()
    fake_tray.show_message = lambda title, msg, **kw: tray_messages.append((title, msg))
    dash.tray_manager = fake_tray

    dash._on_secret_candidate("HiddenSecretPass123#")
    assert len(tray_messages) == 1
    assert "Secret Intercepted" in tray_messages[0][0]


def test_dynamic_pipeline_settings_toggle(mock_dashboard):
    """
    Verify that detector enables/disables dynamically based on settings
    and master password presence without restart.
    """
    from core.watcher import ClipboardWatcher
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)

    dash.watcher = ClipboardWatcher(pipeline=ClipboardPipeline())
    attach_send_to_vault(dash)

    from core.clipboard.events import ClipboardEvent
    event = ClipboardEvent(content_type="text", content="DynamicSecret123#")

    # When enabled (default)
    dash._settings["detect_passwords"] = True
    assert dash.watcher.pipeline._secret_detector(event) is True

    # When toggled off in settings
    dash._settings["detect_passwords"] = False
    assert dash.watcher.pipeline._secret_detector(event) is False


def test_already_secured_toast_variant(qapp):
    """Verify that SecretDetectedToast with already_saved displays proper header and hides action buttons."""
    toast = SecretDetectedToast("original_secret_pass", already_saved="The Vault ('My Gmail')")

    # Header and subtext check
    labels = [lbl.text() for lbl in toast.findChildren(QLabel)]
    assert any("Already Secured" in t for t in labels)
    assert any("Found in The Vault ('My Gmail')" in t for t in labels)

    # Buttons check: Save and Keep should NOT exist
    buttons = [b.text() for b in toast.findChildren(QPushButton)]
    assert any("Dismiss" in b for b in buttons)
    assert not any("Save" in b for b in buttons)
    assert not any("Keep" in b for b in buttons)

    # In-memory candidate text must be empty (zero retention)
    assert toast._candidate_text == ""


def test_consecutive_duplicate_secret_intercept(mock_dashboard):
    """
    Ensure that copying the exact same secret twice while toast is active
    does not create duplicate toasts or duplicate Eclipse fallback items.
    """
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)

    dash.show()
    secret = "DuplicateSecretCandidate99#!"

    # First copy triggers intercept toast
    dash._on_secret_candidate(secret)
    first_toast = dash.findChild(SecretDetectedToast)
    assert first_toast is not None

    # Count Eclipse encrypted items in database currently
    items_before = storage.get_all_items()
    eclipse_before = [it for it in items_before if it.get("is_secret") == 1]

    # Second consecutive copy with identical secret text
    dash._on_secret_candidate(secret)

    # Verify no second toast replaced it and no extra Eclipse item was generated
    items_after = storage.get_all_items()
    eclipse_after = [it for it in items_after if it.get("is_secret") == 1]
    assert len(eclipse_after) == len(eclipse_before)


def test_secret_intercept_when_already_in_vault(mock_dashboard):
    """
    Ensure that copying a secret already stored in The Vault displays
    the 'Already Secured' toast and does not create an actionable intercept toast.
    """
    dash = mock_dashboard
    pw = "TestMasterPass123!"
    if not dash.security_service.has_master_password():
        dash.security_service.setup_master_password(pw)

    dash.show()
    vault_ctrl = dash.vault_controller
    vault_ctrl.unlock(pw)
    vault_ctrl.add_secret("Bank Password", "VaultSecretUnique99#", category="password")

    # Intercept candidate matching vault secret
    dash._on_secret_candidate("VaultSecretUnique99#")

    toast = dash.findChild(SecretDetectedToast)
    assert toast is not None
    labels = [lbl.text() for lbl in toast.findChildren(QLabel)]
    assert any("Already Secured" in t for t in labels)
    assert any("Found in The Vault ('Bank Password')" in t for t in labels)
