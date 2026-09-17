"""
tests/test_security_controller.py
─────────────────────────────────
Tests for SecurityController state machine and cryptographic signal contracts.
"""

from unittest.mock import MagicMock, patch
import pytest

from PyQt6.QtWidgets import QDialog
from core.services.security_service import SecurityService
from ui.controllers.security_controller import SecurityController


@pytest.fixture
def fake_sec_service():
    service = MagicMock(spec=SecurityService)
    service.is_locked = True
    service.has_master_password.return_value = True
    service.active_key = None
    service._active_key = None
    service._is_locked = True

    def lock_side_effect():
        service.is_locked = True
        service._is_locked = True
        service.active_key = None
        service._active_key = None
    service.lock.side_effect = lock_side_effect

    return service


def test_lock_state_signal(qapp, fake_sec_service):
    controller = SecurityController(service=fake_sec_service)

    signals = []
    controller.lock_state_changed.connect(signals.append)

    # Set active key -> unlocked
    fake_sec_service.is_locked = False
    controller.set_active_key(b"test_key_32_bytes_long_12345678")
    assert len(signals) == 1
    assert signals[-1] is False

    # Call lock() -> locked
    controller.lock()
    fake_sec_service.lock.assert_called_once()
    assert len(signals) == 2
    assert signals[-1] is True


def test_secret_copy_when_unlocked(qapp, fake_sec_service):
    fake_sec_service.is_locked = False
    fake_sec_service.decrypt_clip_for_view.return_value = "decrypted_secret_data"

    controller = SecurityController(service=fake_sec_service)

    payloads = []
    controller.copy_payload_ready.connect(lambda item_id, payload: payloads.append((item_id, payload)))

    item_data = {"id": 99, "content": "ciphertext", "is_secret": 1}
    controller.handle_secret_copy(99, item_data)

    fake_sec_service.decrypt_clip_for_view.assert_called_once_with(99)
    assert len(payloads) == 1
    assert payloads[0][0] == 99
    assert payloads[0][1]["content"] == "decrypted_secret_data"


def test_secret_copy_when_locked_prompt_accept(qapp, fake_sec_service):
    fake_sec_service.is_locked = True
    controller = SecurityController(service=fake_sec_service)

    payloads = []
    controller.copy_payload_ready.connect(lambda item_id, payload: payloads.append((item_id, payload)))

    mock_dialog = MagicMock()
    mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
    mock_dialog.get_key.return_value = b"valid_key_32_bytes_long_1234567"

    def unlock_action(key):
        fake_sec_service.is_locked = False
        fake_sec_service.active_key = key
    controller.set_active_key = MagicMock(side_effect=unlock_action)

    fake_sec_service.decrypt_clip_for_view.return_value = "unlocked_secret_text"

    with patch("ui.controllers.security_controller.LockScreen", return_value=mock_dialog):
        controller.handle_secret_copy(101, {"id": 101, "content": "enc", "is_secret": 1})

    controller.set_active_key.assert_called_once_with(b"valid_key_32_bytes_long_1234567")
    assert len(payloads) == 1
    assert payloads[0][1]["content"] == "unlocked_secret_text"


def test_secret_copy_when_locked_prompt_reject(qapp, fake_sec_service):
    fake_sec_service.is_locked = True
    controller = SecurityController(service=fake_sec_service)

    payloads = []
    failures = []
    controller.copy_payload_ready.connect(lambda item_id, payload: payloads.append((item_id, payload)))
    controller.secret_copy_failed.connect(lambda item_id, reason: failures.append((item_id, reason)))

    mock_dialog = MagicMock()
    mock_dialog.exec.return_value = QDialog.DialogCode.Rejected

    with patch("ui.controllers.security_controller.LockScreen", return_value=mock_dialog):
        controller.handle_secret_copy(102, {"id": 102, "content": "enc", "is_secret": 1})

    assert len(payloads) == 0
    assert len(failures) == 1
    assert failures[0][0] == 102
    fake_sec_service.decrypt_clip_for_view.assert_not_called()


def test_encrypt_item_emits_security_changed(qapp, fake_sec_service):
    fake_sec_service.is_locked = False
    fake_sec_service.encrypt_clip.return_value = True

    controller = SecurityController(service=fake_sec_service)

    changed_items = []
    controller.item_security_changed.connect(changed_items.append)

    res = controller.encrypt_item(55)
    assert res is True
    fake_sec_service.encrypt_clip.assert_called_once_with(55)
    assert changed_items == [55]


def test_decrypt_item_emits_security_changed(qapp, fake_sec_service):
    fake_sec_service.is_locked = False
    fake_sec_service.decrypt_clip_permanent.return_value = True

    controller = SecurityController(service=fake_sec_service)

    changed_items = []
    controller.item_security_changed.connect(changed_items.append)

    res = controller.decrypt_item(77, confirm=False)
    assert res is True
    fake_sec_service.decrypt_clip_permanent.assert_called_once_with(77)
    assert changed_items == [77]


def test_auto_lock_timeout_emits_trigger_without_locking(qapp):
    service = MagicMock(spec=SecurityService)
    controller = SecurityController(service=service)

    triggered = []
    controller.auto_lock_triggered.connect(lambda: triggered.append(True))

    controller._on_auto_lock_timeout()

    assert triggered == [True]
    service.lock.assert_not_called()
