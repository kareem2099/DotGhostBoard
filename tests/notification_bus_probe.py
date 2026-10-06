"""Run with: QT_QPA_PLATFORM=offscreen dbus-run-session -- venv/bin/python tests/notification_bus_probe.py

Uses an isolated fake notification daemon; never contacts the real desktop.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QTimer, QThread, pyqtClassInfo
from PyQt6.QtDBus import QDBusConnection
from core.notifications import send_desktop_notification
app=QApplication([])
@pyqtClassInfo('D-Bus Interface', 'org.freedesktop.Notifications')
class Server(QObject):
    ActionInvoked=pyqtSignal('uint', str)
    NotificationClosed=pyqtSignal('uint', 'uint')
    @pyqtSlot(str, 'uint', str, str, str, 'QStringList', 'QVariantMap', int, result='uint')
    def Notify(self, appname, replaces, icon, title, body, actions, hints, expiry):
        print('RECEIVED', appname, body, actions, hints, expiry, flush=True)
        QTimer.singleShot(2300, lambda: self.ActionInvoked.emit(77, 'default'))
        return 77
    @pyqtSlot('uint')
    def CloseNotification(self, nid):
        self.NotificationClosed.emit(nid, 3)
server=Server()
bus=QDBusConnection.sessionBus()
assert bus.registerService('org.freedesktop.Notifications')
assert bus.registerObject('/org/freedesktop/Notifications', server, QDBusConnection.RegisterOption.ExportAllSlots | QDBusConnection.RegisterOption.ExportAllSignals)
results=[]
clicks=[]
def clicked():
    clicks.append(QThread.currentThread()==app.thread())
    app.quit()
send_desktop_notification('Test', 'Private <text>', timeout_ms=0, sound=False, action_callback=clicked, on_result=results.append)
QTimer.singleShot(5000, app.quit)
app.exec()
print('RESULTS',results,'CLICK MAIN',clicks)
assert results==[True] and clicks==[True]
