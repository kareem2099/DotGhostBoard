import sys
import os
import signal

#suppress D-Bus warnings before any Qt import
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.dbus.*=false"
os.environ["QT_QPA_PLATFORM"]  = "xcb"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "DotGhostBoard_IPC_Server"

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DotGhostBoard")
    app.setQuitOnLastWindowClosed(False)

    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(500):
        # Another instance is running, send it a message to show the window and exit
        socket.write(b"show")
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        print("[Main] Another instance is running, sent show command and exiting.")
        sys.exit(0)

    QLocalServer.removeServer(SERVER_NAME)  # Clean up any stale server
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        print("[IPC] Could not start local server — continuing without IPC.")
        sys.exit(1)

    # Ctrl+C cleanly exits the application without core dump
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    from ui.dashboard import Dashboard
    window = Dashboard()
    window.show()

    def handle_new_connection():
        client = server.nextPendingConnection()
        if client and client.waitForReadyRead(500):
            message = client.readAll().data().decode()
            if message == "show":
                window.show_and_raise()
        client.disconnectFromServer()
        client.deleteLater()

    server.newConnection.connect(handle_new_connection)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()