# Changelog

All notable changes to DotGhostBoard are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned for v1.5.0 — *Nexus*
- Cloud sync via local-network peer
- Plugin API for custom item types
- Light theme

---

## [Unreleased]

### Planned for v1.5.0 — *Nexus*
- Cloud sync via local-network peer
- Plugin API for custom item types
- Light theme

---

## [1.4.1] — 2026-04-13 — *Memory & Performance Optimization*

Performance stability & Update architecture release — major memory optimizations, lazy loading for GUI rendering, fixed IPC crashes, and a complete built-in GitHub updater.

### Added
- **Built-in Auto-Updater** — `ui/updater_dialog.py` handles parsing GitHub releases natively, downloads the correct platform asset (AppImage/DEB) using a background `QThread` inside `core/updater.py`, displays progress sequentially, and uses `os.rename` logic to backup currently executing binaries in place.
- **Image optimization via QImageReader** — Memory efficiency fix for large media loading bounds using `reader.setScaledSize()` before buffer injection preventing complete RAM exhaustion on high-res loads.
- **Lazy history loading (Infinite scroll)** — Limit-offset pagination bound to a vertical scrollbar in the dashboard instead of locking the GUI thread rendering 200 elements instantly on boot.

### Fixed
- **AppImage IPC Crash** — Single-instance local sockets shifted from relative path bounds to a strict absolute `tempfile.gettempdir()` bypassing X11 duplicate window spawns.
- **Memory Leaks and DB Overhead** — Removed dynamic array loading from `_clean_captures()` logic. Connected proper `worker.deleteLater()` tracking to active Python wrappers avoiding backend memory leaks after update checks.
- **Unpinned files storage leaks** — Media attachments (`.png`/`.mkv` previews) are now physically purged from `.config/dotghostboard/` using native `os.remove` checks during mass "Clear History" deletion sweeps, not just unregistered from DB schema.
- **Stealth Mode xprop failures** — Replaced direct subsystem calls targeting X11 `_NET_WM_STATE` with strict `Qt.WindowType.Tool` GUI flags making background running universal across Wayland and Windows.

---

## [1.4.0] — 2026-03-28 — *Eclipse*

Security & encryption release — AES-256 encryption for sensitive items, master password lock, auto-lock, stealth mode, secure delete, app filter, right-click context menu for per-item encryption, and About tab with social links.

### Added
- **AES-256-GCM encryption engine** — `core/crypto.py` with `encrypt()`, `decrypt()`, `derive_key()` using PBKDF2-SHA256 (600K iterations) + per-install random salt stored in `~/.config/dotghostboard/eclipse.salt`; master password verifier via encrypted sentinel token in `eclipse.verify`; `save_master_password()`, `verify_password()`, `remove_master_password()` for full lifecycle
- **Secret item schema** — `is_secret INTEGER DEFAULT 0` column added to `clipboard_items` via migration in `core/storage.py`; `mark_secret()`, `encrypt_item()`, `decrypt_item()`, `decrypt_item_permanent()`, `get_secret_items()`, `encrypt_all_text_items()`, `decrypt_all_secret_items()` for opt-in per-item encryption
- **Right-click context menu** — `_on_card_context_menu()` in `ui/dashboard.py`; "🔐 Mark as Secret" for plain text items, "🔓 Remove Encryption" for secret items (with confirmation); only shown when master password is set; card rebuilds in-place at same position after encrypt/decrypt
- **Lock Screen UI** — `ui/lock_screen.py` `LockScreen` QDialog; frameless, modal, always-on-top; dark neon theme; setup mode (first-time) and unlock mode; error shake on wrong password; `get_key()` returns derived AES key after success; Escape key blocked; close prevented until unlocked
- **Master password in Settings** — Eclipse tab in `ui/settings.py` with Set/Change/Remove password buttons; verifies current password before changes; info message guides user to right-click cards for per-item encryption
- **Auto-lock timer** — `auto_lock_minutes` setting (0–480, default 0 = disabled); `QTimer` resets on any user interaction (mouse, key); fires `_lock()` when idle exceeds threshold; requires master password
- **Stealth mode** — `stealth_mode` boolean setting; uses `xprop` to set `_NET_WM_STATE_SKIP_TASKBAR,_NET_WM_STATE_SKIP_PAGER` X11 hints; window accessible only via tray icon or global hotkey; responsive resize (400px compact)
- **Secure delete** — `core/secure_delete.py` with `secure_delete(path, passes=3)`; overwrites file bytes with random→zeros→random in 3 passes with `fsync`; integrated in `storage.delete_item(secure=True)` for image/video items
- **App filter** — `core/app_filter.py` `AppFilter` class; blacklist/whitelist modes; detects active window via `xdotool` + `/proc/<pid>/comm` + `xprop WM_CLASS`; substring matching; fail-open when detection unavailable; Settings UI with mode selector and app list editor
- **About tab** — `ui/settings.py` `_build_about_tab()` with logo, version v1.4.0 Eclipse, author FreeRave, MIT license, system info (Python/PyQt6/Qt/Platform/Arch), and social links organized in sections (Project, Articles, Social, Videos, Facebook)
- **Unit tests** — `tests/test_eclipse.py` with 27+ tests across 4 classes: `TestCrypto` (encrypt/decrypt roundtrip, wrong key, tampered ciphertext, unicode, master password flow, PBKDF2 determinism, salt persistence), `TestSecureDelete` (file gone, nonexistent, overwrite, batch, empty), `TestAppFilter` (blacklist/whitelist, match/unmatch, fail-open, hot-reload, substring), `TestStorageEclipse` (mark_secret, encrypt_item, decrypt_item, wrong key, get_secret_items, already encrypted, image rejection, permanent decrypt)

### Changed
- **`ui/dashboard.py`** — `_add_card()` connects `sig_reveal_requested` and `customContextMenuRequested`; `_on_card_context_menu()` builds menu with Copy/Pin/Encrypt/Decrypt/Delete; `_encrypt_card()` and `_decrypt_card()` use `_rebuild_card_in_place()` to keep card position; `_lock()`, `_show_lock_screen()`, `_reset_auto_lock()`, `_set_stealth()`, `_on_reveal_requested()` for Eclipse state management; `_active_key` tracks session key; `setContextMenuPolicy(CustomContextMenu)` on every card
- **`ui/widgets.py`** — `ItemCard` detects `is_secret` property; shows 🔐 badge and 👁 Reveal button; `_overlay_widget` + `_revealed_label` visibility toggle (no QStackedWidget); `reveal_content()` shows decrypted text, `_lock_content()` hides it; `on_session_locked()` re-hides revealed secrets; `setMaximumHeight` removed — QVBoxLayout handles sizing naturally
- **`core/storage.py`** — `init_db()` migration adds `is_secret` column; `delete_item(secure=True)` integrates secure delete for image/video items; `mark_secret()`, `encrypt_item()`, `decrypt_item()`, `decrypt_item_permanent()`, `get_secret_items()`, `encrypt_all_text_items()`, `decrypt_all_secret_items()` added
- **`ui/settings.py`** — Eclipse tab with master password (set/change/remove), auto-lock spinner, stealth checkbox, app filter editor; About tab with version/license/system/social; `_setup_master_password()` shows opt-in info message instead of auto-encrypting all items

### Security
- All encryption done locally — AES-256-GCM with PBKDF2 key derivation (600K iterations)
- Master password never stored — only encrypted verifier token on disk
- Session key cleared from memory on lock
- Secure delete overwrites file bytes 3 times before unlinking
- App filter prevents clipboard capture from password managers (keepassxc, bitwarden, etc.)

---

## [1.3.0] — 2026-03-26 — *Wraith*

Tags, Collections, Multi-Select & Export release — a complete tagging system with autocomplete and global tag manager, named collections with sidebar panel and drag-to-organize, multi-select with Ctrl+Click and Shift+Click, bulk actions toolbar, and export to .txt/.json.

### Added
- **Tag system** — `tags TEXT DEFAULT ''` column added to `clipboard_items` via migration; tags stored as comma-separated `#tag1,#tag2` string; `add_tag()`, `remove_tag()`, `get_tags()`, `get_items_by_tag()` in `core/storage.py`; four-pattern `LIKE` query prevents false positives (e.g. `#py` won't match `#python`); `get_all_tags()` returns deduplicated sorted list; `rename_tag()` and `delete_tag()` for global tag operations
- **Tag input widget on cards** — `TagInputRow` (`ui/widgets.py`) shows existing tags as colored `TagChip` pills (rotating 6-palette color scheme); inline `QLineEdit` with `QCompleter` autocomplete from existing DB tags; `returnPressed` emits signal; signal chain: `TagInputRow.sig_tag_added` → `ItemCard.sig_tag_added` → `Dashboard._on_tag_added()` → `storage.add_tag()` → `card.on_tag_added()` (UI confirm)
- **Combined text + tag search** — `_on_search()` in `ui/dashboard.py` parses mixed queries like `"python #code"`; tag-only filter works on all item types (images, video, text); `storage.search_items(query, tag_filter)` extended with four-pattern LIKE join
- **Collections system** — `collections` table with `id`, `name`, `created_at`, `updated_at`; `clipboard_items.collection_id` nullable FK (NULL = Uncategorized); `create_collection()`, `delete_collection()`, `get_collections()`, `move_to_collection()`, `get_items_by_collection()` in `core/storage.py`; `get_collections()` uses `LEFT JOIN` to include item counts
- **Collections sidebar panel** — `QListWidget` on left side (`ui/dashboard.py`); "❖ All Items" default entry; click to filter, right-click to rename/delete, `+` button to create; drag card onto collection name to move via `application/x-dotghost-card-id` MIME data
- **Multi-select cards** — `_selected_ids: set[int]` tracks selection; `_last_clicked_id` enables Shift+Click range selection; `ItemCard.sig_clicked(item_id, modifiers)` emits keyboard modifiers; Ctrl+Click toggles single, Shift+Click selects range, plain click clears; `set_selected()` toggles Qt property + shows/hides neon green `✓` overlay badge
- **One-time hint strip** — `QFrame#HintStrip` below search bar shows multi-select keyboard shortcuts; "✕ got it" dismisses and persists `multiselect_hint_dismissed` in settings; re-shows on first Ctrl+Click if not yet dismissed
- **Drag & drop visual feedback** — `QGraphicsOpacityEffect` dims source card to 35% opacity during drag; ghost pixmap is 72% opaque with neon green rounded-rect border; `set_drop_target()` highlights valid drop targets with dashed green border + green background
- **Bulk actions toolbar** — `_bulk_bar` `QFrame` shows when 2+ cards selected; buttons: Pin All, Unpin All, Add Tag, Export, Delete All, Cancel; `_update_bulk_bar()` toggles visibility based on selection count; bulk delete shows confirmation dialog and skips pinned items
- **Export to .txt / .json** — `storage.export_items(item_ids, fmt)` in `core/storage.py`; `.json` format includes `id`, `type`, `content`, `created_at`, `tags` (as list); `.txt` format has timestamped blocks with separator lines; `_bulk_export()` shows format picker dialog then save file dialog via `QFileDialog`
- **Global tag manager** — `TagManagerDialog` in `ui/settings.py`; accessible from ⚙ Settings → "🏷 Manage Tags…"; lists all tags with item counts; rename (global via `storage.rename_tag()`) and delete (global via `storage.delete_tag()`); empty state message when no tags exist
- **Unit tests** — `tests/test_storage_v130.py` with 20+ tests covering tag CRUD, collection CRUD, four-pattern LIKE queries, tag rename/delete, export, and edge cases (partial tag name false positives, tag position in list, uncategorized items after collection deletion)

### Changed
- **`core/storage.py`** — `init_db()` migration adds `tags` column and `collections` table + `collection_id` FK; new functions: `get_all_tags()`, `rename_tag()`, `delete_tag()`, `export_items()`, `export_items_txt()`, `export_items_json()`, `create_collection()`, `delete_collection()`, `get_collections()`, `get_collection_by_id()`, `rename_collection()`, `move_to_collection()`, `get_items_by_collection()`; `search_items()` extended with optional `tag_filter` parameter
- **`ui/dashboard.py`** — `_build_ui()` adds collections sidebar, hint strip, and bulk actions toolbar; `_on_card_clicked()` handles Ctrl+Click, Shift+Click, plain click with `_update_bulk_bar()`; `_clear_selection()` resets `_last_clicked_id` and hides bulk bar; new methods: `_bulk_pin()`, `_bulk_delete()`, `_bulk_export()`, `_bulk_add_tag()`, `_update_bulk_bar()`, `_dismiss_hint()`, `_refresh_sidebar()`, `_create_collection()`, `_on_collection_selected()`, `_sidebar_drop_event()`; `QFileDialog` added to imports
- **`ui/widgets.py`** — `ItemCard._build_ui()` adds `TagInputRow` and `✓` check overlay; `set_selected()` shows/hides overlay; `set_drop_target()` for drag visual feedback; `_do_drag()` uses ghost pixmap with `QPainter` (72% opacity + neon border) and `QGraphicsOpacityEffect` (35% dim on source); imports updated with `QGraphicsOpacityEffect`, `QPainter`, `QPen`, `QColor`
- **`ui/ghost.qss`** — added styles for: `ItemCard[selected="true"]` (neon green border), `ItemCard[droptarget="true"]` (dashed green), `QFrame#BulkBar` (green-tinted toolbar), `QLabel#BulkCountLabel`, `QPushButton#BulkBtn` / `#BulkBtnDanger` / `#BulkBtnCancel`, `QFrame#HintStrip`, `QLabel#HintText`, `QPushButton#HintDismissBtn`, `ItemCard[selected="true"] #DragHandle` (green)
- **`ui/settings.py`** — "🏷 Manage Tags…" button added to settings form; `_open_tag_manager()` opens `TagManagerDialog`

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