"""
tests/test_primary_selection.py
───────────────────────────────
Test suite for Issue #2: PRIMARY mouse selection clipboard monitoring,
debouncing, settings persistence, and drag fragment consolidation.
"""

import time
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QMimeData

from core.clipboard.events import ClipboardEvent
from core.clipboard.backends.qt_backend import QtClipboardBackend
from core.watcher import ClipboardWatcher
from ui.settings import load_settings, save_settings, SettingsDialog
from ui.settings._io import _DEFAULTS


from core import storage

@pytest.fixture
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_primary.db")
    monkeypatch.setattr(storage, "DB_PATH", test_db)
    storage.init_db()
    return test_db


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    test_settings_path = str(tmp_path / "settings.json")
    monkeypatch.setattr("ui.settings._io.SETTINGS_PATH", test_settings_path)
    save_settings(dict(_DEFAULTS))
    return test_settings_path


# ── 1. Settings & Defaults Tests ──────────────────────────────────────────────

def test_default_settings_primary_selection_disabled(isolated_settings):
    """PRIMARY monitoring must be disabled by default (opt-in)."""
    settings = load_settings()
    assert "monitor_primary_selection" in settings
    assert settings["monitor_primary_selection"] is False


def test_settings_dialog_toggle_persists(qapp, isolated_settings):
    """Toggling the PRIMARY selection checkbox persists the preference."""
    dlg = SettingsDialog()
    assert hasattr(dlg, "_monitor_primary")
    assert dlg._monitor_primary.isChecked() is False

    # Check the box and simulate save
    dlg._monitor_primary.setChecked(True)
    dlg._save_and_close()

    updated = load_settings()
    assert updated["monitor_primary_selection"] is True


# ── 2. QtClipboardBackend Unit Tests ──────────────────────────────────────────

def test_qt_backend_set_monitor_primary(qapp):
    """Enabling/disabling primary monitoring starts/stops debounce timer."""
    backend = QtClipboardBackend()
    backend.start()
    assert backend._monitor_primary is False
    assert backend._primary_debounce_timer.isActive() is False

    backend.set_monitor_primary(True)
    assert backend._monitor_primary is True

    # Simulate selection changed
    backend.set_on_event(lambda ev: None)
    backend._on_selection_changed()
    assert backend._primary_debounce_timer.isActive() is True

    backend.set_monitor_primary(False)
    assert backend._monitor_primary is False
    assert backend._primary_debounce_timer.isActive() is False


def test_qt_backend_debounces_rapid_selection_events(qapp, monkeypatch):
    """Multiple rapid selectionChanged events trigger only one event after timeout."""
    backend = QtClipboardBackend()
    backend.start()
    backend.set_monitor_primary(True)

    events = []
    backend.set_on_event(events.append)

    # Mock selection support and text
    mock_clipboard = MagicMock()
    mock_clipboard.supportsSelection.return_value = True
    mock_clipboard.mimeData.return_value = QMimeData()
    mock_clipboard.text.return_value = "highlighted text"
    backend._clipboard = mock_clipboard

    # Trigger selection changed multiple times rapidly
    backend._on_selection_changed()
    backend._on_selection_changed()
    backend._on_selection_changed()

    # Before timeout, no events emitted
    assert len(events) == 0

    # Trigger timeout
    backend._on_primary_debounce_timeout()

    assert len(events) == 1
    assert events[0].content == "highlighted text"
    assert events[0].source_app == "primary_selection"


def test_qt_backend_ignores_single_character_and_empty(qapp):
    """Accidental 1-char clicks or whitespace are discarded."""
    backend = QtClipboardBackend()
    backend.start()
    backend.set_monitor_primary(True)

    events = []
    backend.set_on_event(events.append)

    mock_clipboard = MagicMock()
    mock_clipboard.supportsSelection.return_value = True
    mock_clipboard.mimeData.return_value = QMimeData()
    backend._clipboard = mock_clipboard

    # 1 character
    mock_clipboard.text.return_value = "a"
    backend._on_primary_debounce_timeout()
    assert len(events) == 0

    # Whitespace only
    mock_clipboard.text.return_value = "   \n  "
    backend._on_primary_debounce_timeout()
    assert len(events) == 0


def test_qt_backend_password_manager_secret_ignored(qapp):
    """Selections flagged with x-kde-passwordManagerHint == 'secret' are ignored."""
    backend = QtClipboardBackend()
    backend.start()
    backend.set_monitor_primary(True)

    events = []
    backend.set_on_event(events.append)

    mock_clipboard = MagicMock()
    mock_clipboard.supportsSelection.return_value = True
    mime = QMimeData()
    mime.setData("x-kde-passwordManagerHint", b"secret")
    mock_clipboard.mimeData.return_value = mime
    mock_clipboard.text.return_value = "SuperSecretPassword123"
    backend._clipboard = mock_clipboard

    backend._on_primary_debounce_timeout()
    assert len(events) == 0


# ── 3. Watcher & Fragment Consolidation Tests ─────────────────────────────────

def test_watcher_primary_fragment_consolidation(qapp, isolated_storage):
    """
    If user extends a mouse drag within 3.0s, the intermediate fragment
    is deleted from storage and signaled for removal from UI.
    """
    from core import storage

    watcher = ClipboardWatcher()
    watcher._running = True

    replaced_ids = []
    watcher.primary_fragment_replaced.connect(replaced_ids.append)

    # 1. User drags over 'Hello'
    ev1 = ClipboardEvent(
        content_type="text",
        content="Hello",
        source_app="primary_selection",
    )
    watcher._on_clipboard_event(ev1)

    items = storage.get_all_items()
    assert len(items) == 1
    first_id = items[0]["id"]
    assert items[0]["content"] == "Hello"

    # 2. User continues dragging to 'Hello World' within 3 seconds
    ev2 = ClipboardEvent(
        content_type="text",
        content="Hello World",
        source_app="primary_selection",
    )
    watcher._on_clipboard_event(ev2)

    # First fragment should have been replaced and deleted
    assert replaced_ids == [first_id]
    items_after = storage.get_all_items()
    assert len(items_after) == 1
    assert items_after[0]["content"] == "Hello World"
    assert storage.get_item_by_id(first_id) is None


def test_watcher_unrelated_primary_not_replaced(qapp, isolated_storage):
    """Unrelated primary selection does not replace previous clip."""
    from core import storage

    watcher = ClipboardWatcher()
    watcher._running = True

    replaced_ids = []
    watcher.primary_fragment_replaced.connect(replaced_ids.append)

    ev1 = ClipboardEvent(
        content_type="text",
        content="Selection Alpha",
        source_app="primary_selection",
    )
    watcher._on_clipboard_event(ev1)

    ev2 = ClipboardEvent(
        content_type="text",
        content="Selection Beta",
        source_app="primary_selection",
    )
    watcher._on_clipboard_event(ev2)

    assert len(replaced_ids) == 0
    items = storage.get_all_items()
    assert len(items) == 2


def test_watcher_delegates_set_monitor_primary(qapp):
    """ClipboardWatcher delegates set_monitor_primary to backend."""
    mock_backend = MagicMock()
    watcher = ClipboardWatcher(backend=mock_backend)

    watcher.set_monitor_primary(True)
    mock_backend.set_monitor_primary.assert_called_with(True)

    watcher.set_monitor_primary(False)
    mock_backend.set_monitor_primary.assert_called_with(False)


def test_watcher_backwards_and_recoil_consolidation(qapp, isolated_storage):
    """Test consolidation when dragging backwards or trimming boundaries."""
    from core import storage

    watcher = ClipboardWatcher()
    watcher._running = True

    replaced_ids = []
    watcher.primary_fragment_replaced.connect(replaced_ids.append)

    # 1. User selected with trailing dot
    ev1 = ClipboardEvent(
        content_type="text",
        content="DotGhostBoard is awesome.",
        source_app="primary_selection",
    )
    watcher._on_clipboard_event(ev1)
    items = storage.get_all_items()
    first_id = items[0]["id"]

    # 2. User recoils/trims the trailing dot within 3 seconds
    ev2 = ClipboardEvent(
        content_type="text",
        content="DotGhostBoard is awesome",
        source_app="primary_selection",
    )
    watcher._on_clipboard_event(ev2)

    assert replaced_ids == [first_id]
    items_after = storage.get_all_items()
    assert len(items_after) == 1
    assert items_after[0]["content"] == "DotGhostBoard is awesome"


def test_mouse_badge_rendered_on_card(qapp, isolated_storage):
    """Cards captured via mouse primary selection render the 🖱️ mouse badge."""
    from ui.widgets import ItemCard

    item_mouse = {
        "id": 1,
        "type": "text",
        "content": "Mouse selected text",
        "tags": "#mouse",
        "created_at": "2026-10-05T00:00:00",
    }
    card = ItemCard(item_mouse)
    assert hasattr(card, "_mouse_badge")
    assert "🖱️ mouse" in card._mouse_badge.text()

    # Normal clip copied via Ctrl+C should NOT have mouse badge
    item_normal = {
        "id": 2,
        "type": "text",
        "content": "Ctrl+C copied text",
        "tags": "",
        "created_at": "2026-10-05T00:00:00",
    }
    card_normal = ItemCard(item_normal)
    assert not hasattr(card_normal, "_mouse_badge")


def test_middle_click_copies_to_primary(qapp):
    """Middle-clicking a card puts its text into the PRIMARY selection buffer."""
    from ui.controllers.history_controller import HistoryController
    from PyQt6.QtGui import QClipboard

    service = MagicMock()
    service.get_item.return_value = {
        "id": 42,
        "type": "text",
        "content": "Quick middle click paste",
        "is_secret": 0,
    }
    hc = HistoryController(service=service, cards_layout=MagicMock())

    status_messages = []
    hc.status_message.connect(status_messages.append)

    mock_clipboard = MagicMock()
    mock_clipboard.supportsSelection.return_value = True

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(QApplication, "clipboard", lambda: mock_clipboard)
        hc.on_card_middle_clicked(42)

    mock_clipboard.setText.assert_called_with("Quick middle click paste", QClipboard.Mode.Selection)
    assert any("PRIMARY buffer" in msg for msg in status_messages)


def test_capture_sound_invoked_when_enabled(qapp, isolated_storage, monkeypatch):
    """When capture sound is enabled in settings/watcher, play_capture_sound is called."""
    watcher = ClipboardWatcher()
    watcher._running = True
    watcher.set_capture_sound_enabled(True)

    sound_played = []
    monkeypatch.setattr("core.audio.play_capture_sound", lambda: sound_played.append(True))

    ev = ClipboardEvent(
        content_type="text",
        content="Testing audio feedback",
        source_app="primary_selection",
    )
    watcher._on_clipboard_event(ev)

    assert len(sound_played) == 1


def test_primary_syncs_to_system_clipboard(qapp):
    """When sync_primary_to_clipboard is True, text is synced to QClipboard.Mode.Clipboard for Ctrl+V."""
    from PyQt6.QtGui import QClipboard

    backend = QtClipboardBackend()
    backend.start()
    backend.set_monitor_primary(True)
    backend.set_sync_primary_to_clipboard(True)

    events = []
    backend.set_on_event(events.append)

    mock_clipboard = MagicMock()
    mock_clipboard.supportsSelection.return_value = True
    mime = QMimeData()
    mock_clipboard.mimeData.return_value = mime
    mock_clipboard.text.return_value = "Selected for Ctrl+V"
    backend._clipboard = mock_clipboard

    backend._on_primary_debounce_timeout()

    assert len(events) == 1
    # Verify it updated the standard CLIPBOARD buffer for Ctrl+V
    mock_clipboard.setText.assert_called_with("Selected for Ctrl+V", QClipboard.Mode.Clipboard)
    assert backend._is_self_paste is False


def test_paste_item_syncs_both_clipboard_and_primary(qapp):
    """paste_item updates both CLIPBOARD (Ctrl+V) and PRIMARY (Middle-click) buffers."""
    from PyQt6.QtGui import QClipboard

    backend = QtClipboardBackend()
    backend.start()
    mock_clipboard = MagicMock()
    mock_clipboard.supportsSelection.return_value = True
    backend._clipboard = mock_clipboard

    backend.paste_item({"type": "text", "content": "Pasted anywhere"})

    mock_clipboard.setText.assert_any_call("Pasted anywhere")
    mock_clipboard.setText.assert_any_call("Pasted anywhere", QClipboard.Mode.Selection)


def test_validate_audio_file_rejects_long_or_large_files(tmp_path):
    """Ensure audio validator rejects long songs (like Umm Kulthum) and files > 1.5MB."""
    import wave
    import struct
    import shutil
    from core.audio import validate_audio_file, _wrap_timeout

    # 1. Bundled short UI pop is valid
    from core.paths import resource_path
    ghost_pop = resource_path("data", "assets", "sounds", "ghost_pop.wav")
    valid, msg = validate_audio_file(ghost_pop)
    assert valid is True
    assert msg == ""

    # 2. File longer than 2.0 seconds is rejected
    long_wav = str(tmp_path / "long_song.wav")
    with wave.open(long_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        # 4 seconds duration
        samples = bytearray(struct.pack("<h", 0) * (44100 * 4))
        w.writeframes(samples)

    valid_long, msg_long = validate_audio_file(long_wav)
    assert valid_long is False
    assert "too long" in msg_long

    # 3. Timeout wrapper guarantees command has a 1.5s execution cap
    cmd = _wrap_timeout(["paplay", long_wav])
    if shutil.which("timeout"):
        assert cmd[0] == "timeout"
        assert cmd[1] == "1.5s"


def test_primary_monitoring_stops_and_resumes(qapp, isolated_storage):
    from PyQt6.QtTest import QTest

    backend = QtClipboardBackend()
    clipboard = MagicMock()
    clipboard.supportsSelection.return_value = True
    clipboard.mimeData.return_value = QMimeData()
    clipboard.text.return_value = "Selection made while paused"
    backend._clipboard = clipboard
    backend._primary_debounce_timer.setInterval(10)
    backend.set_monitor_primary(True)
    watcher = ClipboardWatcher(backend=backend)
    watcher.start()
    backend._on_selection_changed()
    watcher.stop()
    backend._on_selection_changed()
    backend._on_primary_debounce_timeout()  # A queued timeout must also be harmless.
    QTest.qWait(30)
    assert storage.get_all_items() == []
    clipboard.setText.assert_not_called()

    watcher.start()
    backend._on_selection_changed()
    QTest.qWait(30)
    assert storage.get_item_by_content("Selection made while paused") is not None
    watcher.stop()


@pytest.mark.parametrize("poll_before_copy", [False, True])
def test_primary_sync_preserves_next_external_copy(qapp, poll_before_copy):
    from PyQt6.QtGui import QClipboard

    backend = QtClipboardBackend()
    clipboard = MagicMock()
    primary = QMimeData()
    primary.setText("Mouse selection")
    standard = QMimeData()
    clipboard.supportsSelection.return_value = True
    clipboard.text.return_value = primary.text()
    clipboard.mimeData.side_effect = lambda mode=None: (
        primary if mode == QClipboard.Mode.Selection else standard
    )
    clipboard.setText.side_effect = lambda text, mode: standard.setText(text)
    backend._clipboard = clipboard
    events = []
    backend.set_on_event(events.append)
    backend.set_monitor_primary(True)
    backend.start()
    backend._on_primary_debounce_timeout()
    if poll_before_copy:
        backend._check_clipboard()
    standard.setText("Next external Ctrl+C")
    backend._check_clipboard()
    backend._check_clipboard()
    assert [e.content for e in events] == ["Mouse selection", "Next external Ctrl+C"]
    backend.stop()


def test_consolidation_preserves_preexisting_clip(qapp, isolated_storage):
    item_id = storage.add_item("text", "Previously saved")
    storage.add_tag(item_id, "keep")
    watcher = ClipboardWatcher(backend=MagicMock())
    removed = []
    watcher.primary_fragment_replaced.connect(removed.append)
    for text in ("Previously saved", "Previously saved and extended"):
        watcher._on_clipboard_event(ClipboardEvent(
            content_type="text", content=text, source_app="primary_selection",
        ))
    assert storage.get_item_by_id(item_id) is not None
    assert removed == []
    assert len(storage.get_all_items()) == 2


def test_consolidation_keeps_newly_pinned_card_visible(qapp, isolated_storage):
    watcher = ClipboardWatcher(backend=MagicMock())
    removed = []
    watcher.primary_fragment_replaced.connect(removed.append)
    watcher._on_clipboard_event(ClipboardEvent(
        content_type="text", content="Pin this fragment", source_app="primary_selection",
    ))
    item_id = storage.get_item_by_content("Pin this fragment")["id"]
    storage.toggle_pin(item_id)
    watcher._on_clipboard_event(ClipboardEvent(
        content_type="text", content="Pin this fragment extended", source_app="primary_selection",
    ))
    assert storage.get_item_by_id(item_id)["is_pinned"]
    assert removed == []


def test_consolidation_saves_replacement_before_deleting(qapp, isolated_storage, monkeypatch):
    watcher = ClipboardWatcher(backend=MagicMock())
    watcher._on_clipboard_event(ClipboardEvent(
        content_type="text", content="Keep on failure", source_app="primary_selection",
    ))
    removed = []
    watcher.primary_fragment_replaced.connect(removed.append)
    monkeypatch.setattr(storage, "add_item", MagicMock(side_effect=RuntimeError("Write failed")))
    with pytest.raises(RuntimeError, match="Write failed"):
        watcher._on_clipboard_event(ClipboardEvent(
            content_type="text", content="Keep on failure extended", source_app="primary_selection",
        ))
    assert storage.get_item_by_content("Keep on failure") is not None
    assert removed == []
