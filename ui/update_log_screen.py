"""
ui/update_log_screen.py — Terminal-style update log screen
============================================================
Shown after download completes. Features:
  • Version banner  (current → new)
  • "What's New" release notes panel
  • File info bar   (name · size · SHA-256)
  • Live terminal log with colour-coded lines
  • Animated blinking cursor
  • Progress bar that advances with each log line
  • Auto-restart countdown on success
"""

import os
import sys
import hashlib
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTextEdit, QProgressBar,
    QSizePolicy, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QTextCursor, QFont


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _human_size(path: str) -> str:
    try:
        b = os.path.getsize(path)
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
    except OSError:
        return "unknown"


def _sha256(path: str) -> str:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return "error"


# ─────────────────────────────────────────────
#  Install Worker
# ─────────────────────────────────────────────

class InstallWorker(QThread):
    """Runs the install in background and streams log lines."""
    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)   # (success, error_msg)

    def __init__(self, downloaded_file: str, asset_url: str):
        super().__init__()
        self.downloaded_file = downloaded_file
        self.asset_url       = asset_url

    def run(self):
        import shlex, stat, shutil, subprocess

        def log(msg: str):
            self.log_line.emit(msg)

        ext = os.path.splitext(self.downloaded_file)[1].lower()

        try:
            # ── Verification ─────────────────────────────────────────────────
            log("► Verifying downloaded file…")
            if not os.path.isfile(self.downloaded_file):
                raise RuntimeError(f"File not found: {self.downloaded_file}")
            size = _human_size(self.downloaded_file)
            sha  = _sha256(self.downloaded_file)
            log(f"  Size   : {size}")
            log(f"  SHA-256: {sha[:32]}…")
            log(f"  Status : OK ✓")
            log("")

            # ── DEB ──────────────────────────────────────────────────────────
            if ext == ".deb" or self.asset_url.lower().endswith(".deb"):
                log("► Package type  : DEB (.deb)")
                log(f"► Package path  : {os.path.basename(self.downloaded_file)}")
                log("")
                log("► Writing install script…")

                safe_path  = shlex.quote(self.downloaded_file)
                script_dir = os.path.expanduser("~/.local/share/dotghostboard/updates")
                os.makedirs(script_dir, exist_ok=True)
                script_path = os.path.join(script_dir, "dotghostboard_install.sh")

                with open(script_path, "w") as f:
                    f.write("#!/bin/sh\n")
                    f.write(f"dpkg -i {safe_path}\n")
                    f.write(f"rm -f {safe_path}\n")
                    f.write('rm -f "$0"\n')
                os.chmod(script_path, 0o755)

                log(f"  Script : {script_path}")
                log("")
                log("► Requesting elevated privileges via pkexec…")
                log("  [A system authorisation dialog will appear]")
                log("")

                result = subprocess.run(
                    ["pkexec", script_path],
                    capture_output=True, text=True
                )

                if result.stdout:
                    for line in result.stdout.strip().splitlines():
                        log(f"  {line}")
                if result.stderr:
                    for line in result.stderr.strip().splitlines():
                        log(f"  [stderr] {line}")

                log("")
                if result.returncode == 0:
                    log("✓ Package installed successfully!")
                    log("✓ Temporary files removed.")
                    log("")
                    log("► System is ready — restart to activate the update.")
                    self.finished.emit(True, "")
                else:
                    msg = f"pkexec returned exit code {result.returncode}"
                    if result.returncode == 126:
                        msg += " (authorisation denied)"
                    elif result.returncode == 127:
                        msg += " (pkexec not found — run: sudo chmod 4755 /usr/bin/pkexec)"
                    log(f"✗ Installation failed: {msg}")
                    self.finished.emit(False, msg)

            # ── AppImage ─────────────────────────────────────────────────────
            elif ext == ".appimage" or self.asset_url.lower().endswith(".appimage"):
                log("► Package type : AppImage")
                log(f"► New binary   : {os.path.basename(self.downloaded_file)}")
                log("")

                current = os.environ.get("APPIMAGE")
                if not current:
                    raise RuntimeError("$APPIMAGE env var not set.")

                log(f"► Current path : {current}")
                old_file = current + ".old"
                if os.path.exists(old_file):
                    os.remove(old_file)
                    log(f"► Removed stale backup.")

                log("► Swapping binary…")
                os.rename(current, old_file)
                shutil.move(self.downloaded_file, current)

                st = os.stat(current)
                os.chmod(current, st.st_mode | stat.S_IEXEC)
                log("► Permissions set (+x)")
                log("")
                log("✓ AppImage updated successfully!")
                log("► Restarting application…")
                self.finished.emit(True, "")

            else:
                log(f"✗ Unknown file type: {ext}")
                self.finished.emit(False, f"Unknown update type: {ext}")

        except Exception as exc:
            log("")
            log(f"✗ Error: {exc}")
            self.finished.emit(False, str(exc))


# ─────────────────────────────────────────────
#  Update Log Screen
# ─────────────────────────────────────────────

_STYLE = """
QDialog {
    background: #0a0a0a;
    color: #00ff41;
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
}

/* ── Version banner ── */
QFrame#VersionBanner {
    background: #0d1a0d;
    border: 1px solid #1a3a1a;
    border-radius: 8px;
}
QLabel#OldVer  { color: #555;    font-size: 14px; font-weight: bold; }
QLabel#Arrow   { color: #00ff41; font-size: 18px; }
QLabel#NewVer  { color: #00ff41; font-size: 14px; font-weight: bold; }
QLabel#VerSub  { color: #444;    font-size: 10px; }

/* ── What's New panel ── */
QFrame#WhatsNewFrame {
    background: #0d0d0d;
    border: 1px solid #1a2a1a;
    border-radius: 6px;
}
QTextEdit#WhatsNewBox {
    background: transparent;
    color: #99dd99;
    border: none;
    font-size: 11px;
    selection-background-color: #00ff4122;
}

/* ── File info bar ── */
QLabel#FileInfo {
    color: #446644;
    font-size: 10px;
    font-family: 'Courier New', monospace;
}

/* ── Terminal ── */
QFrame#TermFrame {
    background: #050505;
    border: 1px solid #1a3a1a;
    border-radius: 8px;
}
QTextEdit#TermLog {
    background: transparent;
    color: #00ff41;
    border: none;
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    font-size: 11px;
    selection-background-color: #00ff4133;
}
QLabel#CursorLabel { color: #00ff41; font-size: 13px; }

/* ── Progress ── */
QProgressBar#InstallProgress {
    background: #0d1a0d;
    border: 1px solid #1a3a1a;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    color: transparent;
}
QProgressBar#InstallProgress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00ff41, stop:1 #00ccff);
    border-radius: 3px;
}

/* ── Buttons ── */
QPushButton#CloseBtn {
    background: #1a0a0a;
    color: #ff4444;
    border: 1px solid #ff222233;
    border-radius: 4px;
    padding: 6px 20px;
    font-size: 11px;
}
QPushButton#CloseBtn:hover   { background: #ff222222; border-color: #ff4444; }
QPushButton#CloseBtn:disabled { color: #333; border-color: #1a1a1a; }

QPushButton#RestartBtn {
    background: #0d1a0d;
    color: #00ff41;
    border: 1px solid #00ff41;
    border-radius: 4px;
    padding: 6px 24px;
    font-size: 11px;
    font-weight: bold;
}
QPushButton#RestartBtn:hover { background: #00ff4122; }

QLabel#TitleBar {
    color: #00ff41; font-size: 12px; font-weight: bold; letter-spacing: 1px;
}
"""


class UpdateLogScreen(QDialog):
    """Terminal-style install log screen shown after download completes."""

    def __init__(
        self,
        downloaded_file: str,
        asset_url: str,
        new_version: str,
        current_version: str = "",
        release_notes: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.downloaded_file = downloaded_file
        self.asset_url       = asset_url
        self.new_version     = new_version
        self.current_version = current_version or "current"
        self.release_notes   = release_notes or "_No release notes provided._"

        self._worker: InstallWorker | None = None
        self._cursor_visible = True
        self._done           = False
        self._log_count      = 0
        self._countdown      = 5

        self.setWindowTitle("DotGhostBoard — Installing Update")
        self.setModal(True)
        self.resize(720, 630)
        self.setMinimumSize(580, 500)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(_STYLE)

        self._build_ui()
        self._start_cursor_blink()
        QTimer.singleShot(500, self._start_install)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # ── macOS-style title bar ──
        header = QHBoxLayout()
        for col in ("#ff5f57", "#febc2e", "#28c840"):
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{col}; font-size:11px;")
            dot.setFixedWidth(16)
            header.addWidget(dot)
        header.addSpacing(8)
        title = QLabel("dotghostboard — system updater")
        title.setObjectName("TitleBar")
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        sep0 = self._separator()
        root.addWidget(sep0)

        # ── Version Banner ────────────────────────────────────────
        banner = QFrame()
        banner.setObjectName("VersionBanner")
        b_lay = QHBoxLayout(banner)
        b_lay.setContentsMargins(20, 14, 20, 14)
        b_lay.setSpacing(0)

        # Ghost icon
        ghost = QLabel("👻")
        ghost.setStyleSheet("font-size: 28px;")
        b_lay.addWidget(ghost)
        b_lay.addSpacing(14)

        # Left side: label + versions
        ver_col = QVBoxLayout()
        ver_col.setSpacing(4)
        lbl_updating = QLabel("UPDATING DOTGHOSTBOARD")
        lbl_updating.setStyleSheet(
            "color:#446644; font-size:9px; letter-spacing:2px; font-weight:bold;"
        )
        ver_col.addWidget(lbl_updating)

        ver_row = QHBoxLayout()
        ver_row.setSpacing(12)
        old = QLabel(self.current_version)
        old.setObjectName("OldVer")
        arrow = QLabel("──→")
        arrow.setObjectName("Arrow")
        new = QLabel(self.new_version)
        new.setObjectName("NewVer")
        ver_row.addWidget(old)
        ver_row.addWidget(arrow)
        ver_row.addWidget(new)
        ver_row.addStretch()
        ver_col.addLayout(ver_row)

        b_lay.addLayout(ver_col)
        b_lay.addStretch()

        # File info (right side)
        fname = os.path.basename(self.downloaded_file)
        fsize = _human_size(self.downloaded_file)
        file_info = QLabel(f"📦  {fname}\n💾  {fsize}")
        file_info.setObjectName("FileInfo")
        file_info.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        b_lay.addWidget(file_info)

        root.addWidget(banner)

        # ── What's New (collapsible-ish) ──────────────────────────
        wn_label = QLabel("▾  What's New")
        wn_label.setStyleSheet(
            "color:#446644; font-size:10px; letter-spacing:1px; padding-left:2px;"
        )
        root.addWidget(wn_label)

        wn_frame = QFrame()
        wn_frame.setObjectName("WhatsNewFrame")
        wn_lay = QVBoxLayout(wn_frame)
        wn_lay.setContentsMargins(10, 8, 10, 8)

        self.notes_box = QTextEdit()
        self.notes_box.setObjectName("WhatsNewBox")
        self.notes_box.setReadOnly(True)
        self.notes_box.setMarkdown(self.release_notes)
        self.notes_box.setFixedHeight(90)
        self.notes_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        wn_lay.addWidget(self.notes_box)
        root.addWidget(wn_frame)

        sep1 = self._separator()
        root.addWidget(sep1)

        # ── Terminal log ──────────────────────────────────────────
        term_frame = QFrame()
        term_frame.setObjectName("TermFrame")
        term_lay = QVBoxLayout(term_frame)
        term_lay.setContentsMargins(12, 8, 12, 8)
        term_lay.setSpacing(4)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("TermLog")
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Courier New", 10))
        term_lay.addWidget(self.log_box)

        cursor_row = QHBoxLayout()
        cursor_row.setContentsMargins(0, 0, 0, 0)
        self.cursor_label = QLabel("█")
        self.cursor_label.setObjectName("CursorLabel")
        cursor_row.addWidget(self.cursor_label)
        cursor_row.addStretch()
        term_lay.addLayout(cursor_row)

        root.addWidget(term_frame, stretch=1)

        # ── Progress bar ──────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setObjectName("InstallProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        # ── Status / button row ───────────────────────────────────
        btn_row = QHBoxLayout()
        self.status_lbl = QLabel("● Initializing…")
        self.status_lbl.setStyleSheet("color:#ffcc00; font-size:11px;")
        btn_row.addWidget(self.status_lbl)
        btn_row.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("CloseBtn")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)

        self.restart_btn = QPushButton("Restart Now")
        self.restart_btn.setObjectName("RestartBtn")
        self.restart_btn.setVisible(False)
        self.restart_btn.clicked.connect(self._restart_or_close)
        btn_row.addWidget(self.restart_btn)

        root.addLayout(btn_row)

        # Pre-fill terminal prompt
        self._append("┌──(dotghostboard㉿updater)-[~]", "#444")
        self._append(
            f"└─$ dotghostboard --install {self.new_version} --auto", "#444"
        )
        self._append("", "#00ff41")

    # ── Separator ─────────────────────────────────────────────────────────────

    @staticmethod
    def _separator() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("color:#1a3a1a; margin:0px;")
        return f

    # ── Cursor blink ──────────────────────────────────────────────────────────

    def _start_cursor_blink(self):
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_timer.start()

    def _blink(self):
        self._cursor_visible = not self._cursor_visible
        self.cursor_label.setText("█" if self._cursor_visible else " ")

    # ── Terminal helpers ───────────────────────────────────────────────────────

    def _append(self, text: str, color: str | None = None):
        """Append one styled line to the terminal."""
        if color is None:
            if text.startswith("✓"):
                color = "#00ff41"
            elif text.startswith("✗"):
                color = "#ff4444"
            elif text.startswith("►"):
                color = "#00ccff"
            elif text.startswith("  [stderr]"):
                color = "#ffaa00"
            elif text.startswith("  Size") or text.startswith("  SHA") or text.startswith("  Status") or text.startswith("  Script") or text.startswith("  ["):
                color = "#888888"
            elif text.startswith("┌") or text.startswith("└"):
                color = "#444"
            else:
                color = "#00cc33"

        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe = safe.replace(" ", "&nbsp;")
        self.log_box.insertHtml(
            f'<span style="color:{color}; font-family:monospace;">{safe}</span><br>'
        )
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum()
        )

        # Advance progress bar (max 80 before install completes)
        self._log_count += 1
        pct = min(80, self._log_count * 5)
        self.progress.setValue(pct)

    # ── Install flow ──────────────────────────────────────────────────────────

    def _start_install(self):
        self.status_lbl.setText("● Installing…")
        self._worker = InstallWorker(self.downloaded_file, self.asset_url)
        self._worker.log_line.connect(self._append)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, success: bool, error_msg: str):
        self._done = True
        self._blink_timer.stop()
        self.cursor_label.setText("█")
        self.progress.setValue(100)

        if success:
            self.status_lbl.setText("✓ Update complete")
            self.status_lbl.setStyleSheet("color:#00ff41; font-size:11px;")
            self.close_btn.setEnabled(True)
            self.restart_btn.setVisible(True)
            self._start_countdown()
        else:
            self.status_lbl.setText(f"✗ Failed: {error_msg}")
            self.status_lbl.setStyleSheet("color:#ff4444; font-size:11px;")
            self.close_btn.setEnabled(True)
            self.progress.setStyleSheet(
                "QProgressBar#InstallProgress::chunk { background: #ff4444; }"
            )

    # ── Countdown to auto-restart ─────────────────────────────────────────────

    def _start_countdown(self):
        self._countdown = 5
        self._update_countdown_label()
        self._cd_timer = QTimer(self)
        self._cd_timer.setInterval(1000)
        self._cd_timer.timeout.connect(self._tick_countdown)
        self._cd_timer.start()

    def _tick_countdown(self):
        self._countdown -= 1
        if self._countdown <= 0:
            self._cd_timer.stop()
            self._restart_or_close()
        else:
            self._update_countdown_label()

    def _update_countdown_label(self):
        self.restart_btn.setText(f"Restart Now  ({self._countdown})")

    # ── Restart / close ───────────────────────────────────────────────────────

    def _restart_or_close(self):
        if hasattr(self, "_cd_timer"):
            self._cd_timer.stop()
        appimage = os.environ.get("APPIMAGE")
        if appimage and os.path.isfile(appimage):
            os.execv(appimage, [appimage] + sys.argv[1:])
        else:
            self.accept()

    # ── Close guard ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
