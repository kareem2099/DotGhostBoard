import sys
import os
import signal
import tempfile
import hashlib

import stat

# Suppress D-Bus warnings before any Qt import
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.dbus.*=false"
if os.getenv("DOTGHOST_FORCE_X11") == "1":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore    import Qt, QLockFile, QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

def _cleanup_old_appimage():
    """If running as AppImage, check if this specific executable has a leftover .old file and remove it."""
    appimage_path = os.environ.get("APPIMAGE")
    if not appimage_path:
        return

    old_file = os.path.abspath(appimage_path) + ".old"
    if os.path.isfile(old_file):
        try:
            os.remove(old_file)
            print(f"[Updater] Cleaned up old update file: {old_file}")
        except OSError as exc:
            print(f"[Updater] Failed to remove old update file: {exc}")

# Secure, per-user, profile-isolated runtime paths
_uid = os.getuid() if hasattr(os, "getuid") else "shared"


def _get_runtime_dir() -> str:
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        path = os.path.abspath(xdg_runtime)

        try:
            st = os.lstat(path)
        except OSError as exc:
            raise RuntimeError(
                f"Invalid XDG_RUNTIME_DIR: {path}: {exc}"
            ) from exc

        if not stat.S_ISDIR(st.st_mode):
            raise RuntimeError(
                f"Invalid XDG_RUNTIME_DIR: {path} is not a directory"
            )

        if hasattr(os, "getuid") and st.st_uid != os.getuid():
            raise RuntimeError(
                f"Invalid XDG_RUNTIME_DIR: {path} is owned by another user"
            )

        return path

    path = os.path.join(
        tempfile.gettempdir(),
        f"dotghostboard-run-{_uid}",
    )

    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        # lstat intentionally does NOT follow symlinks.
        st = os.lstat(path)

        if not stat.S_ISDIR(st.st_mode):
            raise RuntimeError(
                f"Insecure runtime path: {path} is not a directory"
            )

        if hasattr(os, "getuid") and st.st_uid != os.getuid():
            raise RuntimeError(
                f"Insecure runtime path: {path} is owned by another user"
            )

        # Safe now: verified real directory + correct owner.
        os.chmod(path, 0o700)
    except OSError as exc:
        raise RuntimeError(
            f"Unable to create secure runtime directory: {path}: {exc}"
        ) from exc

    return path


_runtime_dir = _get_runtime_dir()

_profile = os.path.realpath(
    os.getenv("DOTGHOST_HOME")
    or os.path.join(os.path.expanduser("~"), ".config", "dotghostboard")
)
_profile_hash = hashlib.sha256(_profile.encode("utf-8")).hexdigest()[:12]

SERVER_NAME = os.path.join(_runtime_dir, f"dotghostboard-{_uid}-{_profile_hash}.sock")
LOCK_FILE_PATH = os.path.join(_runtime_dir, f"dotghostboard-{_uid}-{_profile_hash}.lock")


def main():
    _cleanup_old_appimage()

    # ── Startup flags ──────────────────────────────────────────────────────
    startup_flags = ("--startup", "--background", "--minimized", "--tray", "-m")
    is_startup_mode = any(arg in sys.argv for arg in startup_flags)
    is_spotlight_mode = any(arg in sys.argv for arg in ("--spotlight", "-s", "spotlight"))
    is_toggle_mode = any(arg in sys.argv for arg in ("--toggle", "-t", "toggle"))
    is_show_mode = any(arg in sys.argv for arg in ("--show", "show"))

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DotGhostBoard")
    app.setQuitOnLastWindowClosed(False)

    # ── Single Instance Guard: QLockFile authority + QLocalServer IPC ─────
    lock_file = QLockFile(LOCK_FILE_PATH)
    # Long-lived application lock: Qt explicitly recommends 0 so time-based stale
    # detection is disabled, and Qt relies strictly on OS PID/process check.
    lock_file.setStaleLockTime(0)

    if not lock_file.tryLock(100):
        if is_startup_mode:
            # An active instance is already running and monitoring in background
            sys.exit(0)

        # Forward command over IPC socket: 'spotlight', 'toggle', or default 'show'
        if is_spotlight_mode:
            cmd = b"spotlight"
        elif is_toggle_mode:
            cmd = b"toggle"
        else:
            cmd = b"show"

        socket = QLocalSocket()
        for _ in range(4):
            socket.abort()
            socket.connectToServer(SERVER_NAME)
            if socket.waitForConnected(250):
                socket.write(cmd)
                socket.waitForBytesWritten(500)
                socket.disconnectFromServer()
                print(f"[Main] Another instance is running, sent {cmd.decode()} command and exiting.")
                sys.exit(0)

        print("[Main] Instance lock is held, but IPC server is unavailable.")
        sys.exit(1)

    # Primary instance acquired lock: initialize IPC server
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(SERVER_NAME):
        print(f"[IPC] Could not start local server on {SERVER_NAME} — continuing without IPC.")
        server = None

    window = None
    exit_code = 0
    try:
        # Unix signal handling:
        # Python signal handlers run on the main interpreter thread.
        # While Qt's native event loop is idle, Python may not regain control promptly.
        # This lightweight timer periodically returns control to Python so SIGINT/SIGTERM
        # handlers can call app.quit() and perform a graceful shutdown.
        sig_timer = QTimer(app)
        sig_timer.setInterval(250)
        sig_timer.timeout.connect(lambda: None)
        sig_timer.start()

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: app.quit())

        # Clean up any leftover legacy autostart entries
        from core.autostart import migrate_legacy_entries
        migrate_legacy_entries()

        # ── Eclipse: startup lock ──────────────────────────────────────────
        from core.crypto    import has_master_password
        from ui.lock_screen import LockScreen

        active_key = None
        startup_locked = False

        if has_master_password():
            if is_startup_mode:
                # On system boot/autostart, do not block login with a modal window.
                # Start dashboard in locked state; unlocking happens on demand.
                startup_locked = True
            else:
                lock   = LockScreen(setup=False)
                result = lock.exec()
                if result != LockScreen.DialogCode.Accepted:
                    sys.exit(0)   # Locked out → quit gracefully (finally block runs)
                active_key = lock.get_key()

        # ── Dashboard ──────────────────────────────────────────────────────
        from ui.dashboard import Dashboard

        window = Dashboard(startup_locked=startup_locked, active_key=active_key)

        if is_spotlight_mode:
            window.show_spotlight()
        elif not is_startup_mode:
            window.show()

        # ── IPC: handle show / spotlight / toggle commands from subsequent launches ───
        def handle_new_connection():
            client = server.nextPendingConnection()
            if client is None:
                return

            try:
                if client.waitForReadyRead(500):
                    message = bytes(client.readAll()).decode("utf-8", errors="replace").strip()
                    if message == "show":
                        window.show_and_raise()
                    elif message == "spotlight":
                        window.show_spotlight()
                    elif message == "toggle":
                        window.toggle_visibility()
            finally:
                client.disconnectFromServer()
                client.deleteLater()

        if server is not None:
            server.newConnection.connect(handle_new_connection)

        exit_code = app.exec()
    finally:
        # Ensure threads are stopped before the interpreter starts destroying objects
        if window is not None:
            window.close()
        if server is not None:
            server.close()
            QLocalServer.removeServer(SERVER_NAME)
        if lock_file.isLocked():
            lock_file.unlock()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()