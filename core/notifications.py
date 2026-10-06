"""Asynchronous desktop notifications with actions owned by the Qt event loop.

Qt D-Bus is the primary transport; notify-send is a fallback. A return value of
True means queued, not delivered: on_result reports transport acceptance. The
caller may use a tray balloon if both native transports fail.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import logging
import os
import shutil
import threading
from typing import Callable

from PyQt6.QtCore import QObject, QProcess, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)
_SERVICE = "org.freedesktop.Notifications"
_PATH = "/org/freedesktop/Notifications"


def _dbus_value(value, value_type):
    from PyQt6.QtCore import QMetaType, QVariant
    variant = QVariant(value)
    variant.convert(QMetaType(value_type.value))
    return variant


def get_default_icon_path(category: str = "general") -> str:
    from core.paths import resource_path
    icon = resource_path("data", "icons", "icon_128.png")
    if os.path.exists(icon):
        return icon
    if category in ("secret", "password", "security"):
        return "dialog-password"
    if category in ("warning", "alert"):
        return "dialog-warning"
    if category in ("error", "critical"):
        return "dialog-error"
    return "dialog-information"


def _invoke(callback, *args):
    if callback:
        try:
            callback(*args)
        except Exception:
            logger.exception("Notification callback failed")


@dataclass
class _Request:
    title: str
    message: str
    app_name: str
    icon: str
    timeout_ms: int
    urgency: str
    action_label: str
    action_callback: Callable | None
    sound: bool
    on_result: Callable | None
    generation: int = 0


class _NotificationDispatcher(QObject):
    sig_request = pyqtSignal(object)
    sig_action = pyqtSignal(object)
    sig_cancel = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.moveToThread(QApplication.instance().thread())
        self.sig_request.connect(self._send, Qt.ConnectionType.QueuedConnection)
        self.sig_action.connect(self._handle_action, Qt.ConnectionType.QueuedConnection)
        self.sig_cancel.connect(self.cancel, Qt.ConnectionType.AutoConnection)
        self._generation = 0
        self._bus = None
        self._service_watcher = None
        self._actions = {}
        self._processes = set()

    @pyqtSlot(object)
    def _handle_action(self, callback):
        _invoke(callback)

    def _connect_bus(self):
        if self._bus is not None:
            return self._bus.isConnected()
        try:
            from PyQt6.QtDBus import QDBusConnection, QDBusServiceWatcher
            bus = QDBusConnection.sessionBus()
            if not bus.isConnected():
                return False
            actions = bus.connect(_SERVICE, _PATH, _SERVICE, "ActionInvoked", self._action)
            closed = bus.connect(_SERVICE, _PATH, _SERVICE, "NotificationClosed", self._closed)
            if not actions or not closed:
                bus.disconnect(_SERVICE, _PATH, _SERVICE, "ActionInvoked", self._action)
                bus.disconnect(_SERVICE, _PATH, _SERVICE, "NotificationClosed", self._closed)
                return False
            self._bus = bus
            self._service_watcher = QDBusServiceWatcher(
                _SERVICE, bus, QDBusServiceWatcher.WatchModeFlag.WatchForOwnerChange, self,
            )
            self._service_watcher.serviceOwnerChanged.connect(self._owner_changed)
            return True
        except (ImportError, RuntimeError):
            return False

    @pyqtSlot(str, str, str)
    def _owner_changed(self, service, old_owner, new_owner):
        self._actions.clear()

    @pyqtSlot('uint', str)
    def _action(self, notification_id, action):
        if action == "default":
            _invoke(self._actions.pop(notification_id, None))

    @pyqtSlot('uint', 'uint')
    def _closed(self, notification_id, reason):
        self._actions.pop(notification_id, None)

    @pyqtSlot(object)
    def _send(self, request):
        if request.generation != self._generation:
            return
        generation = self._generation
        if not self._connect_bus():
            self._send_cli(request, generation)
            return
        from PyQt6.QtCore import QMetaType
        from PyQt6.QtDBus import QDBusMessage, QDBusPendingCallWatcher
        message = QDBusMessage.createMethodCall(_SERVICE, _PATH, _SERVICE, "Notify")
        actions = ["default", request.action_label] if request.action_callback else []
        hints = {
            "urgency": _dbus_value(
                {"low": 0, "normal": 1, "critical": 2}.get(request.urgency, 1),
                QMetaType.Type.UChar,
            ),
            "suppress-sound": not request.sound,
        }
        message.setArguments([
            request.app_name, _dbus_value(0, QMetaType.Type.UInt),
            request.icon, request.title, escape(request.message),
            _dbus_value(actions, QMetaType.Type.QStringList), hints, request.timeout_ms,
        ])
        watcher = QDBusPendingCallWatcher(self._bus.asyncCall(message, 3000), self)

        def finished(call):
            from PyQt6.QtDBus import QDBusPendingReply
            reply = QDBusPendingReply(call)
            call.deleteLater()
            if reply.isError():
                logger.debug("D-Bus notification failed: %s", reply.error().message())
                if generation == self._generation:
                    self._send_cli(request, generation)
                return
            notification_id = int(reply.argumentAt(0))
            if generation != self._generation:
                self._close_native(notification_id)
                return
            self._actions[notification_id] = request.action_callback
            _invoke(request.on_result, True)

        watcher.finished.connect(finished)

    def _close_native(self, notification_id):
        if self._bus:
            from PyQt6.QtCore import QMetaType
            from PyQt6.QtDBus import QDBusMessage
            message = QDBusMessage.createMethodCall(
                _SERVICE, _PATH, _SERVICE, "CloseNotification",
            )
            message.setArguments([_dbus_value(notification_id, QMetaType.Type.UInt)])
            self._bus.asyncCall(message, 1000)

    def _send_cli(self, request, generation):
        executable = shutil.which("notify-send")
        if not executable:
            _invoke(request.on_result, False)
            return
        args = [
            "-p", "-a", request.app_name, "-i", request.icon,
            "-t", str(request.timeout_ms), "-u", request.urgency,
            "-h", f"boolean:suppress-sound:{str(not request.sound).lower()}",
        ]
        if request.action_callback:
            args += ["-A", f"default={request.action_label}"]
        args += ["--", request.title, escape(request.message)]
        process = QProcess(self)
        self._processes.add(process)
        timer = QTimer(process)
        timer.setSingleShot(True)
        accepted = False
        completed = False
        action_handled = False
        output = ""

        def report(success):
            nonlocal completed
            if not completed and generation == self._generation:
                completed = True
                _invoke(request.on_result, success)

        def read_output():
            nonlocal output, accepted, action_handled
            output += bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
            while "\n" in output:
                line, output = output.split("\n", 1)
                line = line.strip()
                if line.isdigit() and int(line) > 0:
                    accepted = True
                    timer.stop()  # Wait for action/close, not an arbitrary expiry estimate.
                    report(True)
                elif (line == "default" and accepted and not action_handled
                      and generation == self._generation):
                    action_handled = True
                    _invoke(request.action_callback)

        def cleanup():
            timer.stop()
            self._processes.discard(process)
            process.deleteLater()

        def finished(code, status):
            read_output()
            if not accepted:
                report(False)
            cleanup()

        def failed(error):
            if not accepted:
                report(False)
            if error == QProcess.ProcessError.FailedToStart:
                cleanup()

        def no_reply():
            report(False)
            process.kill()

        process.readyReadStandardOutput.connect(read_output)
        process.finished.connect(finished)
        process.errorOccurred.connect(failed)
        timer.timeout.connect(no_reply)
        process.start(executable, args)
        timer.start(5000)  # Delivery handshake only; never limits action lifetime.

    @pyqtSlot()
    def cancel(self):
        self._generation += 1
        for notification_id in self._actions:
            self._close_native(notification_id)
        self._actions.clear()
        for process in list(self._processes):
            process.kill()


_dispatcher_instance = None
_dispatcher_lock = threading.Lock()


def _get_dispatcher():
    global _dispatcher_instance
    if QApplication.instance() is None:
        return None
    with _dispatcher_lock:
        if _dispatcher_instance is None:
            _dispatcher_instance = _NotificationDispatcher()
            QApplication.instance().aboutToQuit.connect(_dispatcher_instance.cancel)
    return _dispatcher_instance


def _safe_dispatch_callback(callback):
    dispatcher = _get_dispatcher()
    if dispatcher:
        dispatcher.sig_action.emit(callback)


def cancel_desktop_notifications():
    if _dispatcher_instance:
        _dispatcher_instance.sig_cancel.emit()


def send_desktop_notification(
    title: str, message: str, app_name: str = "DotGhostBoard", icon: str | None = None,
    timeout_ms: int = 5000, urgency: str = "normal", action_label: str | None = None,
    action_callback: Callable | None = None, *, sound: bool = True,
    on_result: Callable | None = None,
) -> bool:
    """Queue delivery. on_result(bool) reports acceptance/failure on the GUI thread."""
    dispatcher = _get_dispatcher()
    if dispatcher is None:
        return False
    dispatcher.sig_request.emit(_Request(
        title, message, app_name, icon or get_default_icon_path(), timeout_ms,
        urgency, action_label or "Open DotGhostBoard", action_callback, sound, on_result,
        dispatcher._generation,
    ))
    return True
