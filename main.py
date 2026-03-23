import sys
import signal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DotGhostBoard")
    app.setQuitOnLastWindowClosed(False)

    # Ctrl+C cleanly exits the application without core dump
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    from ui.dashboard import Dashboard
    window = Dashboard()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()