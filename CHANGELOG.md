# Changelog

All notable changes to DotGhostBoard are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Global hotkey `Ctrl+Shift+V` to show/hide from anywhere
- Real app icon (SVG/PNG) replacing programmatic fallback
- Autostart on boot via `~/.config/autostart/`
- Settings panel (history limit, hotkey config, theme)
- Unit tests with `pytest` for `storage.py` and `media.py`

---

## [1.0.0] — 2026-03-23 — *Ghost*

First stable release of DotGhostBoard.

### Added
- **Clipboard monitor** — QTimer polling every 500ms via `core/watcher.py`
- **Text capture** — Detects and stores all copied text, deduplication built-in
- **Image capture** — Saves `QImage` from clipboard as `.png` in `data/captures/`
- **Video path detection** — Identifies copied file paths with video extensions (`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`, `.wmv`)
- **SQLite storage** — Full CRUD layer in `core/storage.py` with `@contextmanager` connection safety
- **Pin system** — `toggle_pin()` in DB; pinned items are immune to deletion
- **Item card widget** — Custom `QFrame` with Pin / Copy / Delete buttons and content preview
- **Dashboard window** — Main `QMainWindow` with scroll area, stats bar, and search
- **Real-time search** — Filters visible cards by text content as you type
- **Clear History** — Deletes all unpinned items; pinned items always survive
- **System tray** — Programmatic tray icon, right-click menu (Show / Quit), minimize-to-tray on window close
- **Dark Neon theme** — Full `ghost.qss` stylesheet (`#0f0f0f` bg, `#00ff41` accent, `#ffcc00` pin)
- **`self_paste` guard** — Prevents re-capturing items pasted from within the app itself

### Fixed
- **Critical segfault** — `qimage.bits().tobytes()` caused IOT instruction / core dump; replaced with safe `width x height x sizeInBytes` signature
- **DB connection leak** — Manual `conn.close()` replaced with `@contextmanager _db()` that always closes on exception
- **Timer not stopped on quit** — `closeEvent` now distinguishes tray-minimize (ignore) from real quit (stop watcher + hide tray)
- **Missing file validation** — `os.path.isfile()` guard added before loading images or videos in `widgets.py`
- **D-Bus warning** — `QT_LOGGING_RULES` env var set before Qt import to suppress `StatusNotifierWatcher` noise on non-KDE desktops
- **`mark_self_paste()` never called** — Now correctly called in `_on_copy()` before `paste_item_to_clipboard()`

### Security
- All data stored locally — no network calls, no telemetry
- `data/captures/` and `ghost.db` excluded from git via `.gitignore`

---

*Older versions will be listed here as the project grows.*
