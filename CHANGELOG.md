# Changelog

All notable changes to DotGhostBoard are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned for v1.2.0 — *Specter*
- Image thumbnail previews with lazy loading
- Video thumbnail via ffmpeg first-frame extraction
- Auto-cleanup: keep last N captures (configurable)
- Image viewer popup on card click
- Copy image back to clipboard from saved .png
- Drag & drop cards to reorder pinned items

---

## [1.1.0] — 2026-03-24 — *Phantom*

Usability release — settings panel, keyboard navigation, double-click paste, standalone autostart, and real SVG icon source.

### Added
- **Settings panel** — `ui/settings.py` `SettingsDialog` opened via ⚙ button in the top bar; persists to `data/settings.json`
  - **Max history** — `QSpinBox` (10–5000, default 200); enforced on startup and on every new capture
  - **Clear history on exit** — privacy checkbox; wipes all unpinned items on app quit (pinned items always survive)
  - **Theme selector** — Dark Neon active; Light placeholder grayed out (v1.2.0+)
  - **Hotkey hint** — read-only label showing `Ctrl+Alt+V`
- **Keyboard navigation** — `Up`/`Down` arrows move focus between visible cards; `Enter`/`Space` copies the focused card; `Escape` clears focus; `scroll.ensureWidgetVisible()` keeps focused card in viewport automatically
- **Double-click to paste** — `mouseDoubleClickEvent` on any `ItemCard` emits `sig_copy` instantly — no need to click the copy button
- **Standalone autostart installer** — `scripts/setup_autostart.py`; pure-Python, supports `--remove` flag; writes `~/.config/autostart/DotGhostBoard.desktop` and `~/.local/share/applications/DotGhostBoard.desktop` without requiring bash
- **Ghost SVG icon** — `data/icons/ghost.svg`; neon ghost design (`#00ff41` / `#0f0f0f`); pixel-perfect source for all sizes; `generate_icon.py` remains the PNG renderer

### Changed
- **Dashboard top bar** — ⚙ settings button added between stats label and Clear History; `_load_history()` now respects `max_history` from settings
- **`closeEvent`** — on real quit, checks `clear_on_exit` setting before calling `watcher.stop()`
- **`ghost.qss`** — added `ItemCard[focused="true"]` rule (neon green border + dark green tint); added `ItemCard[pinned="true"][focused="true"]` combined rule; added `#SettingsBtn` styles

### Removed
- **`core/hotkey.py`** — deleted entirely; `pynput` keylogger approach (resource-heavy, Wayland-incompatible) replaced by the existing `QLocalServer` IPC + system-level `Ctrl+Alt+V` shortcut registered by `scripts/install.sh`

---

## [1.0.0] — 2026-03-24 — *Ghost*

First stable release of DotGhostBoard. 59/59 tests passing.

### Added
- **Clipboard monitor** — `QTimer` polling every 500ms via `core/watcher.py`
- **Text capture** — Detects and stores all copied text, deduplication built-in
- **Image capture** — Saves `QImage` from clipboard as `.png` in `data/captures/`
- **Video path detection** — Identifies copied file paths with extensions `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`, `.wmv`
- **SQLite storage** — Full CRUD layer in `core/storage.py` with `@contextmanager` connection safety
- **Pin system** — `toggle_pin()` in DB; pinned items are immune to all deletion
- **Item card widget** — Custom `QFrame` with Pin / Copy / Delete buttons and content preview
- **Dashboard window** — `QMainWindow` with scroll area, stats bar, and real-time search
- **Clear History** — Deletes all unpinned items; pinned items always survive
- **System tray** — Tray icon, right-click menu (Show / Quit), minimize-to-tray on close
- **IPC local server** — `QLocalServer` in `main.py`; `Ctrl+Alt+V` fires second instance that sends `b"SHOW"` and exits immediately — no Wayland conflicts, no root required
- **App icon generator** — `scripts/generate_icon.py` draws a neon ghost via Pillow at 16 / 32 / 48 / 64 / 128 / 256px; loaded by dashboard and tray automatically
- **Install script** — `scripts/install.sh` sets up autostart (`~/.config/autostart/`), `.desktop` app launcher, and `Ctrl+Alt+V` shortcut via `xfconf-query`
- **Dark Neon theme** — Full `ghost.qss` (`#0f0f0f` bg, `#00ff41` accent, `#ffcc00` pin highlight)
- **Unit tests** — 59 tests across `test_storage.py` (32) and `test_media.py` (27); all passing in 0.23s

### Fixed
- **Critical segfault** — `qimage.bits().tobytes()` caused IOT instruction / core dump on PyQt6; replaced with safe `f"{width}x{height}_{sizeInBytes()}"` signature
- **DB connection leak** — Manual `conn.close()` replaced with `@contextmanager _db()` that guarantees close on exception via `finally`
- **Timer not stopped on quit** — `closeEvent` now distinguishes tray-minimize (`event.spontaneous()`) from real quit; calls `watcher.stop()` on actual exit
- **Missing file validation** — `os.path.isfile()` guard added in `widgets.py` before loading any image or video path
- **D-Bus warning** — `QT_LOGGING_RULES` env var set at top of `main.py` before any Qt import to suppress `StatusNotifierWatcher` noise on non-KDE desktops
- **`mark_self_paste()` never called** — Now correctly called in `_on_copy()` before `paste_item_to_clipboard()` to prevent re-capturing pasted items
- **Wrong `QMimeData` import** — `from PyQt6.QtMimeData import QMimeData` → `from PyQt6.QtCore import QMimeData`
- **Dangerous `sed` XML fallback** — Removed; replaced with a safe manual instruction message to avoid corrupting XFCE keyboard shortcut config

### Security
- All data stored locally — zero network calls, zero telemetry
- `data/captures/`, `data/pins/`, `ghost.db` excluded from git via `.gitignore`
- Pinned items protected at DB level — `delete_item()` returns `False` without touching DB if `is_pinned = 1`

---

*Older versions will be listed here as the project grows.*