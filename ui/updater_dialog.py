import os
import tempfile
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.updater import download_update, apply_update
from core.config import APP_VERSION


# ─────────────────────────────────────────────
#  Background Worker
# ─────────────────────────────────────────────

class DownloadWorker(QThread):
    progress          = pyqtSignal(int)
    finished_download = pyqtSignal(str, str)   # (output_path, asset_url)
    error             = pyqtSignal(str)

    def __init__(self, asset_url: str):
        super().__init__()
        self.asset_url = asset_url

    def run(self):
        try:
            filename = self.asset_url.split("/")[-1]
            # Sanitise filename — keep only safe characters
            filename = "".join(c for c in filename if c.isalnum() or c in "._-")
            output_dir = os.path.expanduser("~/.local/share/dotghostboard/updates")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(
                output_dir, f"dotghostboard_update_{filename}"
            )
            download_update(self.asset_url, output_path, self.progress.emit)
            self.finished_download.emit(output_path, self.asset_url)
        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────
#  Dialog
# ─────────────────────────────────────────────

class UpdaterDialog(QDialog):
    def __init__(self, update_info: dict, asset_url: str, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.asset_url   = asset_url
        self.worker: DownloadWorker | None = None

        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.resize(500, 400)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)

        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel(f"🚀  New Update: {self.update_info['version']}")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00ff41;")
        root.addWidget(title)

        info = QLabel(f"You are currently running {APP_VERSION}.")
        info.setStyleSheet("color: #aaa;")
        root.addWidget(info)

        self.browser = QTextBrowser()
        self.browser.setMarkdown(self.update_info.get("body", "No changelog provided."))
        self.browser.setStyleSheet(
            "QTextBrowser {"
            "  background: #0a0a0a;"
            "  border: 1px solid #222;"
            "  border-radius: 6px;"
            "  padding: 10px;"
            "  color: #ddd;"
            "}"
        )
        root.addWidget(self.browser)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        # FIX #2 — Cancel stays enabled; its slot is swapped during download
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.download_btn = QPushButton("Download && Install")
        self.download_btn.setStyleSheet(
            "QPushButton {"
            "  background: #00ff4122;"
            "  color: #00ff41;"
            "  border: 1px solid #00ff41;"
            "  padding: 6px 16px;"
            "  border-radius: 4px;"
            "  font-weight: bold;"
            "} "
            "QPushButton:hover { background: #00ff4144; }"
        )
        self.download_btn.clicked.connect(self._start_download)
        btn_row.addWidget(self.download_btn)

        root.addLayout(btn_row)

    # ── Download flow ────────────────────────────────────────────────────────

    def _start_download(self):
        self.download_btn.setEnabled(False)
        self.progress_bar.show()

        # FIX #2 — rewire Cancel to abort the active download
        self.cancel_btn.setText("Cancel Download")
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self._cancel_download)

        self.worker = DownloadWorker(self.asset_url)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished_download.connect(self._on_download_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _cancel_download(self):
        """Stop the in-progress download and close the dialog cleanly."""
        self._stop_worker()
        self.reject()

    # ── Worker lifecycle ─────────────────────────────────────────────────────

    def _stop_worker(self):
        """Gracefully stop the worker thread if it is still running."""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(3000)

    # ── Slots ────────────────────────────────────────────────────────────────

    def _on_download_finished(self, output_path: str, asset_url: str):
        # FIX #3 — schedule worker for deletion to prevent memory leak
        self.worker.deleteLater()
        self.worker = None

        self.progress_bar.setValue(100)

        try:
            apply_update(output_path, asset_url)
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self, "Update Failed", f"Failed to apply update:\n{e}"
            )
            self.reject()

    def _on_error(self, message: str):
        # FIX #3 — cleanup worker on error path too
        self.worker.deleteLater()
        self.worker = None

        self.progress_bar.hide()
        self.download_btn.setEnabled(True)

        # Restore Cancel button to its original close-dialog behaviour
        self.cancel_btn.setText("Cancel")
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self.reject)

        QMessageBox.warning(
            self, "Download Error", f"Error during download:\n{message}"
        )

    # ── Window close (X button) ───────────────────────────────────────────────

    def closeEvent(self, event):
        # FIX #1 — stop the thread when the user closes the window mid-download
        self._stop_worker()
        super().closeEvent(event)