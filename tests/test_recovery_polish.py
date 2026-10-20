"""Recovery UI stays responsive and bulk selection preserves hidden choices."""

import threading
from types import SimpleNamespace
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QDialog
import pytest

from ui.vault.recovery_selection import RecoverySelectionDialog
from ui.vault.recovery_task import run_recovery_task


def test_bulk_selection_only_changes_search_results(qapp):
    summaries = [SimpleNamespace(id=i, title=name) for i, name in enumerate(
        ['Mail personal', 'Mail work', 'Bank account'])]
    dialog = RecoverySelectionDialog(summaries, [2])
    dialog.search.setText('MAIL')
    dialog.select_all.click()
    assert dialog.selected_ids() == [0, 1, 2]
    dialog.clear_all.click()
    assert dialog.selected_ids() == [2]
    dialog.search.clear()
    dialog.select_all.click()
    assert dialog.selected_ids() == [0, 1, 2]
    dialog.search.setText('no matches')
    assert not dialog.select_all.isEnabled()
    assert '0 of 3 shown' in dialog.status.text()
    dialog.items.clear()
    dialog.deleteLater()


def test_progress_runs_work_off_gui_thread_and_blocks_reentry(qapp):
    owner = QDialog()
    ready, release = threading.Event(), threading.Event()
    main_thread = threading.get_ident()
    ticks, duplicates = [], []

    def work():
        ready.set()
        assert release.wait(3), 'GUI event loop did not respond during recovery'
        return threading.get_ident()

    def heartbeat():
        if not ready.is_set():
            return
        ticks.append(True)
        assert owner.property('recoveryBusy')
        owner.close()
        try:
            run_recovery_task(owner, 'Duplicate', lambda: None)
        except RuntimeError:
            duplicates.append(True)
        release.set()

    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(heartbeat)
    timer.start()
    try:
        assert run_recovery_task(owner, 'Test recovery', work) != main_thread
        assert ticks and duplicates
        assert not owner.property('recoveryBusy')
    finally:
        release.set()
        timer.stop()
        owner.deleteLater()


def test_worker_failure_clears_busy_state_and_resumes_timers(qapp):
    owner = QDialog()
    idle = QTimer(owner)
    idle.setTimerType(Qt.TimerType.PreciseTimer)
    idle.setSingleShot(True)
    idle.start(60_000)
    owner.vault_controller = SimpleNamespace(_idle_timer=idle)

    def fail():
        assert not idle.isActive()
        raise ValueError('Destination unavailable')

    with pytest.raises(ValueError, match='Destination unavailable'):
        run_recovery_task(owner, 'Test failure', fail)
    assert not owner.property('recoveryBusy')
    assert idle.isActive()
    assert 0 < idle.remainingTime() <= 60_000
    idle.stop()
    owner.deleteLater()


def test_settings_cancel_is_ignored_during_recovery(mock_dashboard):
    from ui.settings import SettingsDialog
    dialog = SettingsDialog(parent=mock_dashboard)
    dialog._recovery_page.new_password.setText('temporary test input')
    dialog.setProperty('recoveryBusy', True)
    dialog.reject()
    assert dialog._recovery_page.new_password.text() == 'temporary test input'
    dialog.setProperty('recoveryBusy', False)
    dialog.reject()
    assert dialog._recovery_page.new_password.text() == ''
    dialog.deleteLater()
