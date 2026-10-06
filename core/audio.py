"""
core/audio.py
─────────────
Non-blocking subtle audio feedback for DotGhostBoard clipboard capture events.
Plays custom DotGhost sound or user-configured sound file.
"""

import os
import shutil
import subprocess
from core.paths import resource_path


def validate_audio_file(file_path: str, max_duration: float = 2.0, max_size_mb: float = 1.5) -> tuple[bool, str]:
    """
    Validates whether an audio file is suitable as a short UI feedback click.
    Rejects long songs or massive audio files.
    """
    if not os.path.isfile(file_path):
        return False, "File does not exist."

    # 1. File size check
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > max_size_mb:
        return False, f"File is too large ({size_mb:.1f} MB). UI feedback sounds must be under {max_size_mb} MB."

    # 2. Duration check
    duration = None
    if file_path.lower().endswith(".wav"):
        try:
            import wave
            with wave.open(file_path, "rb") as w:
                rate = w.getframerate()
                if rate > 0:
                    duration = w.getnframes() / float(rate)
        except Exception:
            pass

    if duration is None and shutil.which("ffprobe"):
        try:
            res = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", file_path],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode == 0 and res.stdout.strip():
                duration = float(res.stdout.strip())
        except Exception:
            pass

    if duration is not None and duration > max_duration:
        return False, (
            f"Audio duration is too long ({duration:.1f}s). "
            f"Clipboard feedback sounds must be short clicks under {max_duration:.1f} seconds."
        )

    return True, ""


def _wrap_timeout(cmd: list[str], max_sec: float = 1.5) -> list[str]:
    """Wrap command with system timeout to guarantee it cannot play forever."""
    if shutil.which("timeout"):
        return ["timeout", f"{max_sec}s"] + cmd
    return cmd


_active_player_proc: subprocess.Popen | None = None


def _spawn_player(args: list[str]) -> None:
    """Spawns an audio player process, terminating any previous player to prevent pileup."""
    global _active_player_proc
    try:
        if _active_player_proc is not None and _active_player_proc.poll() is None:
            _active_player_proc.terminate()
    except Exception:
        pass
    try:
        _active_player_proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def play_capture_sound(custom_sound_path: str | None = None) -> None:
    """Play a subtle click/pop sound asynchronously without blocking the UI thread."""
    try:
        target_path = custom_sound_path
        if not target_path:
            try:
                from ui.settings._io import load_settings
                target_path = load_settings().get("custom_sound_path")
            except Exception:
                pass

        # Default bundled DotGhostBoard "ghost_pop.wav"
        if not target_path or not os.path.isfile(target_path):
            bundled = resource_path("data", "assets", "sounds", "ghost_pop.wav")
            if os.path.isfile(bundled):
                target_path = bundled

        # Play via pw-play, paplay, aplay, or mpv
        if target_path and os.path.isfile(target_path):
            # Guard against massive files (> 2 MB) at runtime
            if os.path.getsize(target_path) > 2 * 1024 * 1024:
                return

            ext = os.path.splitext(target_path)[1].lower()
            if ext == ".mp3":
                for player, args in [
                    ("mpv", ["mpv", "--no-video", "--volume=65", "--end=1.5", target_path]),
                    ("pw-play", _wrap_timeout(["pw-play", target_path])),
                    ("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-t", "1.5", target_path]),
                ]:
                    if shutil.which(player):
                        _spawn_player(args)
                        return

            if shutil.which("pw-play"):
                _spawn_player(_wrap_timeout(["pw-play", target_path]))
                return
            if shutil.which("paplay"):
                _spawn_player(_wrap_timeout(["paplay", target_path]))
                return
            if shutil.which("aplay"):
                _spawn_player(_wrap_timeout(["aplay", "-q", target_path]))
                return

        # Fallback to freedesktop theme or Qt system beep
        if shutil.which("canberra-gtk-play"):
            _spawn_player(["canberra-gtk-play", "-i", "audio-volume-change"])
            return

        from PyQt6.QtWidgets import QApplication
        QApplication.beep()
    except Exception:
        pass
