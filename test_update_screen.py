"""
Quick local test for UpdateLogScreen.
Run: python test_update_screen.py
"""
import sys
import os
import tempfile

# ── Bootstrap Qt ──────────────────────────────────────────────────────────────
os.environ["QT_QPA_PLATFORM"]  = "xcb"
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.dbus.*=false"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

app = QApplication(sys.argv)
app.setApplicationName("DotGhostBoard")

# ── Create a fake .deb file so size + SHA work ────────────────────────────────
fake_deb = tempfile.NamedTemporaryFile(suffix=".deb", delete=False)
fake_deb.write(b"\x00" * 1024 * 512)   # 512 KB fake payload
fake_deb.close()

RELEASE_NOTES = """\
## What's New in v1.5.4

### Fixed
- **Blank white window** in `.deb` / AppImage — missing `ghost.qss` in GitHub Actions build.
- **`pkexec` SUID** automatically repaired on install via `DEBIAN/postinst`.

### Added
- **Terminal-style update log** — live streaming install steps with colour-coded output,
  SHA-256 verification, progress bar, and auto-restart countdown.
- **`core/paths.py`** — `resource_path()` helper for PyInstaller-safe asset resolution.
"""

# ── Open the screen ───────────────────────────────────────────────────────────
from ui.update_log_screen import UpdateLogScreen

dlg = UpdateLogScreen(
    downloaded_file=fake_deb.name,
    asset_url="https://example.com/dotghostboard_1.5.4_amd64.deb",
    new_version="v1.5.4",
    current_version="v1.5.3",
    release_notes=RELEASE_NOTES,
)
dlg.exec()

# cleanup
os.unlink(fake_deb.name)
sys.exit(0)
