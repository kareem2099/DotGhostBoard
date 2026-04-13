# 🗺️ DotGhostBoard Roadmap — v1.x

> **Project:** DotGhostBoard  
> **Author:** FreeRave / DotSuite  
> **Created:** 2026-03-23

---

## 🧱 Principles

- 🔒 **Privacy first** — no telemetry, no external calls by default
- 🐉 **Kali-native** — runs lean, no heavy Electron/browser runtime
- 🎨 **DotSuite brand** — consistent dark/neon aesthetic across all tools
- 🔁 **Backwards compatible** — v1.x never breaks `ghost.db` schema

---

## ✅ v1.0.0 — Ghost `[Released: 2026-03-24]`

> **Goal:** Stable base — clipboard monitor, pin system, dark UI, SQLite storage

### Features
- Text capture from clipboard
- Image capture → saved as `.png`
- Video path detection + logging
- Pin / Unpin with DB persistence
- SQLite CRUD with connection safety
- Item cards (Pin / Copy / Delete)
- Real-time search / filter
- Clear History (keeps pinned)
- System tray (minimize + quit)
- Dark Neon QSS theme
- IPC local server (`Ctrl+Alt+V` via `QLocalServer`)
- App icon generator (`scripts/generate_icon.py`)
- Install script (autostart + `.desktop` + shortcut)
- 59 unit tests — 100% passing (`test_storage.py` + `test_media.py`)

### Known Issues
- ⚠️ D-Bus `StatusNotifierWatcher` warning on non-KDE desktops *(cosmetic only)*
- ⚠️ No real app icon yet *(programmatic QPainter fallback)*

---

## ✅ v1.1.0 — Phantom `[Released: 2026-03-24]`

> **Goal:** Usability — global hotkey, autostart, real icon, settings panel, keyboard nav

### Features
- Global hotkey `Ctrl+Shift+V` to show/hide window from anywhere
- Autostart on boot via `~/.config/autostart/` `.desktop` file
- Real app icon (SVG/PNG) replacing QPainter fallback
- Settings panel: max history limit, hotkey config, theme toggle
- Keyboard navigation inside the cards list (Up / Down / Enter)
- Double-click card to paste directly

---

## ✅ v1.2.0 — Specter `[Released: 2026-03-25]`

> **Goal:** Media — image thumbnails, video preview, capture cleanup

### Features
- Image thumbnail previews with lazy loading
- Video thumbnail via `ffmpeg` first-frame extraction
- Auto-cleanup: keep last 100 captures *(configurable)*
- Image viewer popup on card click
- Copy image back to clipboard from saved `.png`
- Drag & drop cards to reorder pinned items

---

## ✅ v1.3.0 — Wraith `[Released: 2026-03-26]`

> **Goal:** Power features — tags, collections, multi-select

### Features
- Tag system: assign custom tags to items (`#code`, `#link`, `#pass`)
- Filter by tag in search bar
- Collections: group pinned items into named folders
- Multi-select: `Ctrl+Click` to select multiple cards
- Bulk delete / bulk pin selected items
- Export selected items to `.txt` or `.json`

---

## ✅ v1.4.0 — Eclipse `[Released: 2026-03-28]`

> **Goal:** Security — encryption, master lock, stealth mode

### Features
- AES-256 encryption for sensitive items *(marked as secret)*
- Master password lock on startup *(optional)*
- Stealth mode: hide window from taskbar + alt-tab
- Auto-lock after N minutes of inactivity
- Secure delete *(overwrite file bytes before removal)*
- Exclude specific apps from being monitored *(whitelist/blacklist)*

---

## 🔮 v1.5.0 — Nexus `[Target: 2026-10-01]`

> **Goal:** Sync & sharing — cross-device, cloud optional

### Features
- Local network sync between devices *(same WiFi)*
- Optional cloud backup via user-provided S3 / Rclone config
- QR code share: scan from phone to get clipboard item
- REST API mode: expose clipboard over localhost for scripts
- CLI companion: `dotghost push` / `dotghost pop` from terminal
- Plugin system: allow community extensions

---

*DotSuite — built for the shadows* 👻
