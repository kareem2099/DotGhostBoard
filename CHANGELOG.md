# Changelog

All notable changes to DotGhostBoard are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned for v1.3.0 — *Wraith*
- Tag system: assign custom tags to items (#code, #link, #pass)
- Filter by tag in search bar
- Collections: group pinned items into named folders
- Multi-select: Ctrl+Click to select multiple cards
- Bulk delete / bulk pin selected items
- Export selected items to .txt or .json

---

## [1.2.0] — 2026-03-25 — *Specter*

Media & preview release — lazy image thumbnails, video first-frame extraction via ffmpeg, auto-cleanup, full-size image viewer, clipboard image copy, and drag-to-reorder pinned items.

### Added
- **Image thumbnail previews (lazy loading)** — `ItemCard._load_thumbnail()` in `ui/widgets.py`; uses `QTimer.singleShot(0, ...)` to defer pixel loading until after the card is painted; caps thumbnails at 300×180px; QPixmap stored on label to avoid re-loading on every repaint
- **Video thumbnail via ffmpeg** — `core/thumbnailer.py` runs `ffmpeg -ss 0 -frames:v 1 -vf scale=300:-1` in a subprocess to extract the first frame as `.png` into `~/.config/dotghostboard/thumbnails/<item_id>.png`; `_ThumbWorker` QThread in `core/watcher.py` runs extraction in background; `thumb_ready` signal updates the card when done; graceful fallback if ffmpeg is not installed
- **Auto-cleanup of old captures** — `storage.clean_old_captures(keep=N)` deletes the oldest unpinned image/video items beyond the limit, removes their `.png` files from `data/captures/` and `data/thumbnails/`, and deletes DB rows; called on startup via `Dashboard._clean_captures()`; configurable via `max_captures` setting (default 100) with QSpinBox in settings dialog
- **Image viewer popup** — `ui/image_viewer.py` `ImageViewer` QDialog; shows full-size image with smooth scaling in a scrollable viewport; "Copy Image" button and "Close" button; keyboard shortcuts: `Escape` to close, `Ctrl+C` to copy; opens on single-click on any image/video thumbnail in a card
- **Copy image back to clipboard** — `ImageViewer._copy_image()` loads the `.png` into `QImage` and puts it on `QClipboard` as image data (not text path); `ClipboardWatcher.paste_item_to_clipboard()` now sets `QImage` directly for image items instead of copying the file path as text
- **Drag & drop to reorder pinned cards** — `ItemCard` shows a `⠿` drag handle on pinned cards; `mousePressEvent` / `mouseMoveEvent` initiate `QDrag` with `application/x-dotghost-card-id` MIME data; `Dashboard._drop_event` reorders pinned cards in the layout and persists `sort_order` via `storage.update_sort_order()`; DB migration adds `sort_order INTEGER DEFAULT 0` column

### Changed
- **`ui/widgets.py`** — `ItemCard._build_content()` now handles `video` type: shows thumbnail if `preview` path exists, falls back to path text; `_on_image_click()` opens `ImageViewer` on thumbnail single-click; `update_video_thumb()` called by dashboard when `thumb_ready` fires
- **`ui/dashboard.py`** — `_start_watcher()` connects `thumb_ready` signal to `_on_thumb_ready()` slot; `_on_thumb_ready()` calls `card.update_video_thumb()`; `_clean_captures()` runs on startup and after settings change; `_drag_enter`, `_drag_move`, `_drop_event` handlers added for S006 reorder
- **`core/watcher.py`** — `_ThumbWorker` QThread added for background ffmpeg extraction; `_start_thumb_worker()` spawns worker and tracks it; `_on_thumb_done()` stores preview path in DB and emits `thumb_ready`; `paste_item_to_clipboard()` now handles image type by loading `QImage` instead of setting text path
- **`core/storage.py`** — `clean_old_captures(keep=100)` function added; `update_preview(item_id, preview_path)` stores thumbnail path; `update_sort_order(item_id, order)` persists drag order; `sort_order` column added via migration
- **`ui/settings.py`** — `max_captures` spinbox (10–2000, default 100) added to form; tooltip explains auto-cleanup behavior

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