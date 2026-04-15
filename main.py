import sys
import os
import signal
import tempfile

# Suppress D-Bus warnings before any Qt import
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.dbus.*=false"
os.environ["QT_QPA_PLATFORM"]  = "xcb"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore    import Qt
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

def _cleanup_old_appimage():
    """If running as AppImage, check if there's a leftover .old file from an update and remove it."""
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        app_dir = os.path.dirname(os.path.abspath(appimage_path))
        for fname in os.listdir(app_dir):
            if fname.endswith(".AppImage.old"):
                old_file = os.path.join(app_dir, fname)
                try:
                    os.remove(old_file)
                    print(f"[Updater] Cleaned up old update file: {fname}")
                except Exception as e:
                    print(f"[Updater] Failed to remove {fname}: {e}")

# Absolute path forces AppImage, .deb, and source to share the exact same socket
# If DOTGHOST_HOME is used, we append a suffix to allow independent instances
_home_suffix = f"_{os.getenv('DOTGHOST_HOME', 'default').replace('/', '_')}"
SERVER_NAME  = os.path.join(tempfile.gettempdir(), f"dotghostboard_ipc{_home_suffix}.sock")


def main():
    _cleanup_old_appimage()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DotGhostBoard")
    app.setQuitOnLastWindowClosed(False)

    # ── IPC: single-instance check ─────────────────────────────────────────
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(500):
        # Another instance is running, send it a message to show the window and exit
        written = socket.write(b"show")
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        if written > 0:
            print("[Main] Another instance is running, sent show command and exiting.")
            sys.exit(0)
        else:
            # Stale socket — no real server behind it, clean up and continue
            print("[Main] Stale IPC socket detected, removing and continuing.")
            QLocalServer.removeServer(SERVER_NAME)

    QLocalServer.removeServer(SERVER_NAME)  # Clean up any stale server
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        print("[IPC] Could not start local server — continuing without IPC.")
        server = None

    # Ctrl+C cleanly exits the application without core dump
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    # ── Eclipse: startup lock ──────────────────────────────────────────────
    from core.crypto    import has_master_password
    from ui.lock_screen import LockScreen

    active_key = None
    if has_master_password():
        lock   = LockScreen(setup=False)
        result = lock.exec()
        if result != LockScreen.DialogCode.Accepted:
            sys.exit(0)   # Locked out → quit gracefully
        active_key = lock.get_key()

    # ── Dashboard ──────────────────────────────────────────────────────────
    from ui.dashboard import Dashboard

    window = Dashboard()
    if active_key is not None:
        window.set_active_key(active_key)
    window.show()

    # ── IPC: bring existing window to front on second launch ───────────────
    def handle_new_connection():
        client = server.nextPendingConnection()
        if client and client.waitForReadyRead(500):
            if client.readAll().data().decode() == "show":
                window.show_and_raise()
        client.disconnectFromServer()
        client.deleteLater()

    if server is not None:
        server.newConnection.connect(handle_new_connection)

    exit_code = app.exec()
    # Ensure threads are stopped before the interpreter starts destroying objects
    window.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()