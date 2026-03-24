import sys
import os
import signal

# suppress D-Bus warnings before any Qt import
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.dbus.*=false"
os.environ["QT_QPA_PLATFORM"]  = "xcb"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

# Local server name
SERVER_NAME = "DotGhostBoard_IPC_Server"


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DotGhostBoard")
    app.setQuitOnLastWindowClosed(False)

    # ── 1. Check if the app is already running in the background ──
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(500):
        # Already running → send "SHOW" and exit immediately
        socket.write(b"SHOW")
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        sys.exit(0)

    # ── 2. First time running → set up the server ──
    QLocalServer.removeServer(SERVER_NAME)   # Cleanup if it was closed incorrectly before
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        print("[IPC] Could not start local server — continuing without IPC.")

    # Ctrl+C from terminal closes cleanly
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    from ui.dashboard import Dashboard
    window = Dashboard()
    window.show()

    # ── 3. Receive IPC messages ──
    def handle_connection():
        client = server.nextPendingConnection()
        if client and client.waitForReadyRead(500):
            msg = client.readAll().data()
            if msg == b"SHOW":
                window.show_and_raise()
        if client:
            client.disconnectFromServer()

    server.newConnection.connect(handle_connection)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()