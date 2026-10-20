"""Run recovery I/O and password derivation without blocking the Qt event loop."""

import time
from PyQt6.QtCore import QEvent, QEventLoop, QObject, QThread, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout


class _Worker(QThread):
    def __init__(self, work):
        super().__init__()
        self.work, self.value, self.error = work, None, None

    def run(self):
        try:
            self.value = self.work()
        except Exception as exc:
            self.error = exc
        finally:
            self.work = None


class _Progress(QDialog):
    def __init__(self, owner, message):
        super().__init__(owner)
        self.setWindowTitle('Vault Recovery')
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)

    def reject(self):
        pass  # A running database replacement must finish before closing.


class _CloseGuard(QObject):
    def __init__(self, widgets):
        super().__init__()
        self.widgets = widgets

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Quit or (
                event.type() == QEvent.Type.Close and watched in self.widgets):
            event.ignore()
            return True
        return False


def run_recovery_task(owner, message, work):
    """Return a worker result, propagating errors on the GUI thread.

    A modal progress window prevents duplicate actions. Suspend the UI's idle and
    recovery timers while the worker owns the Vault; elapsed idle time is deducted
    when resuming. No QWidget is read or mutated by the worker.
    """
    widgets, widget = [], owner
    while widget is not None:
        widgets.append(widget)
        widget = widget.parentWidget()
    if any(w.property('recoveryBusy') for w in widgets):
        raise RuntimeError('A recovery operation is already running.')
    timers = []
    for widget in widgets:
        for controller_name, names in (
                ('security_controller', ('_auto_lock_timer',)),
                ('vault_controller', ('_idle_timer', '_recovery_timer'))):
            controller = getattr(widget, controller_name, None)
            for name in names:
                timer = getattr(controller, name, None)
                if timer is not None and timer.isActive():
                    timers.append((timer, timer.remainingTime(), timer.interval()))
                    timer.stop()
    for widget in widgets:
        widget.setProperty('recoveryBusy', True)
    app = QApplication.instance()
    guard = _CloseGuard(widgets)
    app.installEventFilter(guard)
    progress = _Progress(owner, message)
    worker = _Worker(work)
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    started = time.monotonic()
    try:
        progress.show()
        worker.start()
        loop.exec()
        worker.wait()
        if worker.error is not None:
            raise worker.error
        return worker.value
    finally:
        app.removeEventFilter(guard)
        progress.hide()
        progress.deleteLater()
        worker.deleteLater()
        for widget in widgets:
            widget.setProperty('recoveryBusy', False)
        elapsed = int((time.monotonic() - started) * 1000)
        for timer, remaining, interval in timers:
            if timer.isSingleShot():
                timer.start(max(0, remaining - elapsed))
            else:
                timer.start(interval)
