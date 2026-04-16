"""
ui/purge_easter_egg.py
──────────────────────
The Pigeon Doctor Purge Screen 🐦⬛

Cinematic timeline
──────────────────
  t=0      → dark overlay fades in, GIF starts
  t=600ms  → purge_fn() is called (runs actual DB deletion)
  t=700ms  → sub-caption flips to "✓ Purge Complete" in green
  t=2200ms → fade-out begins (500 ms)
  t=2700ms → dialog closes, control returns to caller
"""

from typing import Callable

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QGraphicsOpacityEffect
from PyQt6.QtCore    import Qt, QTimer, QPropertyAnimation, QEasingCurve, QThread, pyqtSignal
from PyQt6.QtGui     import QMovie, QColor, QPalette, QFont

from core.config import get_asset_path


# ── Background worker ──────────────────────────────────────────────────────
class _PurgeWorker(QThread):
    """Runs purge_fn() off the main thread so the UI stays alive."""
    done = pyqtSignal()

    def __init__(self, purge_fn: Callable):
        super().__init__()
        self._purge_fn = purge_fn

    def run(self):
        try:
            self._purge_fn()
        finally:
            self.done.emit()


# ── Dialog ─────────────────────────────────────────────────────────────────
class PurgeEasterEggDialog(QDialog):
    """
    Frameless, dark overlay that plays pigeon_boss.gif while the purge runs.

    Parameters
    ----------
    purge_fn : callable
        Zero-argument function that performs the actual data deletion.
        It is called ~600 ms after the dialog is shown, in a background thread.
    parent : QWidget, optional

    Usage
    -----
        def do_purge():
            storage.delete_unpinned_items()

        dialog = PurgeEasterEggDialog(purge_fn=do_purge, parent=self)
        dialog.exec()   # blocks; purge is guaranteed done when this returns
    """

    # ── Timing constants (all in ms) ─────────────────────────────────────
    _T_PURGE_START  = 600   # when to kick off the background purge
    _T_DONE_LABEL   = 700   # when to show "Purge Complete" (after purge fires)
    _T_FADE_OUT     = 2200  # when to start fading out
    _FADE_IN_MS     = 400
    _FADE_OUT_MS    = 500

    def __init__(self, purge_fn: Callable, parent=None):
        super().__init__(parent)
        self._purge_fn = purge_fn
        self._worker: _PurgeWorker | None = None

        # ── Window chrome ───────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        if parent:
            self.setFixedSize(parent.size())
        else:
            self.setFixedSize(520, 680)

        # ── Dark backdrop ───────────────────────────────────────
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(10, 10, 10, 230))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # ── Layout ──────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── GIF ─────────────────────────────────────────────────
        self.gif_label = QLabel()
        self.gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gif_label.setStyleSheet("background: transparent;")

        gif_path = get_asset_path("pigeon_boss.gif")
        self.movie = QMovie(gif_path)

        if self.movie.isValid():
            self.movie.setScaledSize(
                self.movie.currentImage().size().scaled(
                    380, 340, Qt.AspectRatioMode.KeepAspectRatio
                )
            )
        self.gif_label.setMovie(self.movie)

        # ── Main caption ────────────────────────────────────────
        self.caption = QLabel("🐦⬛  The Pigeon Doctor is on duty…")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.caption.setStyleSheet(
            "color: #00ff41; background: transparent; letter-spacing: 1px;"
        )

        # ── Sub-caption (will change after purge) ───────────────
        self.sub_caption = QLabel("Purging all mortal clipboard data…")
        self.sub_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_caption.setFont(QFont("Segoe UI", 10))
        self.sub_caption.setStyleSheet("color: #888; background: transparent;")

        layout.addStretch(1)
        layout.addWidget(self.gif_label)
        layout.addSpacing(16)
        layout.addWidget(self.caption)
        layout.addSpacing(4)
        layout.addWidget(self.sub_caption)
        layout.addStretch(1)

        # ── Opacity effect ──────────────────────────────────────
        self._opacity_fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_fx)

        self._anim_in = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._anim_in.setDuration(self._FADE_IN_MS)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # ── Timers ──────────────────────────────────────────────
        self._timer_purge = QTimer(self)
        self._timer_purge.setSingleShot(True)
        self._timer_purge.timeout.connect(self._start_purge)

        self._timer_done_label = QTimer(self)
        self._timer_done_label.setSingleShot(True)
        self._timer_done_label.timeout.connect(self._show_done_label)

        self._timer_fade_out = QTimer(self)
        self._timer_fade_out.setSingleShot(True)
        self._timer_fade_out.timeout.connect(self._begin_fade_out)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self.movie.start()
        self._anim_in.start()

        # Fire the timed sequence
        self._timer_purge.start(self._T_PURGE_START)
        self._timer_done_label.start(self._T_PURGE_START + self._T_DONE_LABEL - self._T_PURGE_START)
        self._timer_fade_out.start(self._T_FADE_OUT)

    def _start_purge(self):
        """Kick off the purge in a background QThread."""
        self._worker = _PurgeWorker(self._purge_fn)
        self._worker.start()

    def _show_done_label(self):
        """Flip the sub-caption to the green 'Purge Complete' message."""
        self.sub_caption.setText("✓ Purge Complete")
        self.sub_caption.setStyleSheet(
            "color: #00ff41; background: transparent; font-weight: bold;"
        )

    def _begin_fade_out(self):
        """Start the 500 ms fade-out, then close."""
        self._anim_out = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._anim_out.setDuration(self._FADE_OUT_MS)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim_out.finished.connect(self._safe_close)
        self._anim_out.start()

    def _safe_close(self):
        """Wait for the worker to finish before accepting (safety guard)."""
        if self._worker and self._worker.isRunning():
            # Give it up to 2 extra seconds; if still busy, accept anyway
            self._worker.wait(2000)
        self.accept()

    def closeEvent(self, event):
        self.movie.stop()
        if self._worker and self._worker.isRunning():
            self._worker.wait(1000)
        super().closeEvent(event)
