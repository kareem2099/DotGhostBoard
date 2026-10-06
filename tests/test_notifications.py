"""Notification delivery, action routing, failure recovery and mute regressions."""
import threading
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QThread
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QSystemTrayIcon

import core.notifications as notifications
from ui.components.tray_manager import DashboardTrayManager


def wait_until(qapp, condition):
    for _ in range(100):
        qapp.processEvents()
        if condition():
            return
        QTest.qWait(10)
    assert condition()


@pytest.fixture
def dispatcher(qapp, monkeypatch):
    service = notifications._NotificationDispatcher()
    monkeypatch.setattr(notifications, '_dispatcher_instance', service)
    monkeypatch.setattr(service, '_connect_bus', lambda: False)
    monkeypatch.setattr(notifications.shutil, 'which', lambda name: None)
    yield service
    service.cancel()
    qapp.processEvents()
    service.deleteLater()
    qapp.processEvents()


def fake_native(dispatcher, monkeypatch, *, error=False):
    from PyQt6.QtDBus import QDBusMessage, QDBusPendingCall
    bus = MagicMock()
    method = QDBusMessage.createMethodCall('org.test.Service', '/test', 'org.test.Service', 'Notify')
    reply = method.createErrorReply('org.test.Error', 'Rejected') if error else method.createReply([77])
    bus.asyncCall.side_effect = lambda *args: QDBusPendingCall.fromCompletedCall(reply)
    dispatcher._bus = bus
    monkeypatch.setattr(dispatcher, '_connect_bus', lambda: True)
    return bus


def fake_cli(tmp_path, monkeypatch, body):
    executable = tmp_path / 'notify-send'
    executable.write_text('#!/bin/sh\n' + body + '\n')
    executable.chmod(0o700)
    monkeypatch.setattr(notifications.shutil, 'which', lambda name: str(executable))
    return executable


def test_icon_resolution(monkeypatch):
    assert notifications.get_default_icon_path()
    monkeypatch.setattr(notifications.os.path, 'exists', lambda path: False)
    assert notifications.get_default_icon_path('security') == 'dialog-password'
    assert notifications.get_default_icon_path('error') == 'dialog-error'


def test_callbacks_run_on_gui_thread_even_when_initialized_in_worker(qapp, monkeypatch):
    monkeypatch.setattr(notifications, '_dispatcher_instance', None)
    observed = []
    for _ in range(2):
        worker = threading.Thread(target=lambda: notifications._safe_dispatch_callback(
            lambda: observed.append(QThread.currentThread() == qapp.thread())
        ))
        worker.start()
        worker.join()
        qapp.processEvents()
    assert observed == [True, True]
    service = notifications._dispatcher_instance
    assert service.thread() == qapp.thread()
    service.deleteLater()
    qapp.processEvents()


def test_native_delivery_and_action_lifetime(qapp, dispatcher, monkeypatch):
    bus = fake_native(dispatcher, monkeypatch)
    results, clicks = [], []
    assert notifications.send_desktop_notification(
        'Secret', 'Masked <preview>', timeout_ms=0, sound=False,
        action_callback=lambda: clicks.append(QThread.currentThread() == qapp.thread()),
        on_result=results.append,
    )
    wait_until(qapp, lambda: results)
    assert results == [True]
    arguments = bus.asyncCall.call_args[0][0].arguments()
    assert arguments[4] == 'Masked &lt;preview&gt;'
    assert arguments[6]['suppress-sound'] is True
    assert arguments[7] == 0
    # There is no local expiry timer: actions remain until the daemon closes them.
    dispatcher._action(77, 'default')
    dispatcher._action(77, 'default')
    assert clicks == [True]


def test_native_close_discards_callback(qapp, dispatcher, monkeypatch):
    fake_native(dispatcher, monkeypatch)
    clicks, results = [], []
    notifications.send_desktop_notification('Title', 'Body', action_callback=lambda: clicks.append(1), on_result=results.append)
    wait_until(qapp, lambda: results)
    dispatcher._closed(77, 2)
    dispatcher._action(77, 'default')
    assert clicks == []


def test_native_failure_falls_back_to_cli(qapp, dispatcher, monkeypatch, tmp_path):
    fake_native(dispatcher, monkeypatch, error=True)
    fake_cli(tmp_path, monkeypatch, "printf '88\\ndefault\\n'")
    results, clicks = [], []
    notifications.send_desktop_notification('Title', 'Body', action_callback=lambda: clicks.append(1), on_result=results.append)
    wait_until(qapp, lambda: clicks and not dispatcher._processes)
    assert results == [True]
    assert clicks == [1]


@pytest.mark.parametrize('failure', ['missing', 'exit', 'launch'])
def test_native_and_cli_failures_are_reported(qapp, dispatcher, monkeypatch, tmp_path, failure):
    results = []
    if failure == 'exit':
        fake_cli(tmp_path, monkeypatch, 'exit 2')
    elif failure == 'launch':
        monkeypatch.setattr(notifications.shutil, 'which', lambda name: str(tmp_path / 'missing-program'))
    notifications.send_desktop_notification('Title', 'Body', on_result=results.append)
    wait_until(qapp, lambda: results)
    assert results == [False]


def test_cancel_drops_queued_delivery(qapp, dispatcher, monkeypatch):
    send_cli = MagicMock()
    monkeypatch.setattr(dispatcher, '_send_cli', send_cli)
    notifications.send_desktop_notification('Title', 'Body')
    notifications.cancel_desktop_notifications()
    qapp.processEvents()
    send_cli.assert_not_called()


def test_cancel_closes_native_and_disables_action(qapp, dispatcher, monkeypatch):
    bus = fake_native(dispatcher, monkeypatch)
    results, clicks = [], []
    notifications.send_desktop_notification('Title', 'Body', action_callback=lambda: clicks.append(1), on_result=results.append)
    wait_until(qapp, lambda: results)
    notifications.cancel_desktop_notifications()
    assert bus.asyncCall.call_args[0][0].member() == 'CloseNotification'
    dispatcher._action(77, 'default')
    assert clicks == []


def test_tray_fallback_after_async_failure_and_click(qapp, dispatcher, monkeypatch):
    manager = DashboardTrayManager()
    manager.tray = MagicMock()
    monkeypatch.setattr(QSystemTrayIcon, 'supportsMessages', lambda: True)
    clicks = []
    manager.show_message('Title', 'Body', action_callback=lambda: clicks.append(1))
    wait_until(qapp, lambda: manager.tray.showMessage.called)
    assert manager.tray.showMessage.call_args[0][:2] == ('Title', 'Body')
    manager._on_message_clicked()
    manager._on_message_clicked()
    assert clicks == [1]


def test_tray_setup_connects_message_click(qapp, monkeypatch):
    tray = MagicMock()
    monkeypatch.setattr('ui.components.tray_manager.QSystemTrayIcon', MagicMock(return_value=tray))
    manager = DashboardTrayManager()
    manager.setup_tray()
    tray.messageClicked.connect.assert_called_once_with(manager._on_message_clicked)


def test_disable_and_reenable_without_restart(qapp, dispatcher, monkeypatch):
    send = MagicMock(return_value=True)
    monkeypatch.setattr(notifications, 'send_desktop_notification', send)
    manager = DashboardTrayManager()
    manager.tray = MagicMock()
    manager.configure_notifications({'notifications_enabled': False})
    manager.show_message('Title', 'Body')
    send.assert_not_called()
    manager.tray.showMessage.assert_not_called()
    manager.configure_notifications({'notifications_enabled': True})
    manager.show_message('Title', 'Body')
    send.assert_called_once()


def test_muting_prevents_delayed_fallback_and_action(qapp, dispatcher, monkeypatch):
    send = MagicMock(return_value=True)
    monkeypatch.setattr(notifications, 'send_desktop_notification', send)
    manager = DashboardTrayManager()
    manager.tray = MagicMock()
    clicks = []
    manager.show_message('Title', 'Body', action_callback=lambda: clicks.append(1))
    callbacks = send.call_args.kwargs
    manager.configure_notifications({'notifications_enabled': False})
    callbacks['on_result'](False)
    callbacks['action_callback']()
    manager.tray.showMessage.assert_not_called()
    assert clicks == []


def test_categories_deduplication_and_sound(qapp, dispatcher, monkeypatch):
    send = MagicMock(return_value=True)
    monkeypatch.setattr(notifications, 'send_desktop_notification', send)
    manager = DashboardTrayManager()
    manager.configure_notifications({'notifications_security': False, 'notification_sound_enabled': False})
    manager.show_message('Security', 'Body', category='security')
    send.assert_not_called()
    for _ in range(2):
        manager.show_message('Background', 'Body', dedupe_key='background', once=True)
    assert send.call_count == 1
    assert send.call_args.kwargs['sound'] is False
    for _ in range(2):
        manager.show_message('Repeated', 'Body', dedupe_key='repeated', cooldown=30)
    assert send.call_count == 2
