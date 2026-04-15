# 👻 DotGhostBoard

> Advanced clipboard manager for Kali Linux — part of the **DotSuite** toolkit.

![Version](https://img.shields.io/badge/version-v1.5.0-00ff41?style=flat-square&labelColor=0f0f0f)
![Codename](https://img.shields.io/badge/codename-Nexus-00ff41?style=flat-square&labelColor=0f0f0f)
![Python](https://img.shields.io/badge/python-3.11+-00ff41?style=flat-square&labelColor=0f0f0f)
![PyQt6](https://img.shields.io/badge/PyQt6-6.6+-00ff41?style=flat-square&labelColor=0f0f0f)
![Platform](https://img.shields.io/badge/platform-Linux-00ff41?style=flat-square&labelColor=0f0f0f)
![Tests](https://img.shields.io/badge/tests-178%20passed-00ff41?style=flat-square&labelColor=0f0f0f)
![License](https://img.shields.io/badge/license-MIT-00ff41?style=flat-square&labelColor=0f0f0f)

---

## What is DotGhostBoard?

DotGhostBoard is a lightweight, privacy-first clipboard manager built natively for Linux. It runs silently in the background, capturing everything you copy — text, images, and video paths — and stores them locally in a SQLite database. No cloud. No telemetry. No Electron.

Think **Ditto** (Windows) or **CopyQ** (Linux) — but built for the DotSuite ecosystem with a Kali-native dark aesthetic.

<img src="data/assets/demo-ui.gif" width="100%" alt="DotGhostBoard UI Demo" />

<img src="data/assets/demo-capture.gif" width="100%" alt="DotGhostBoard Capture Demo" />

---

## Features

- **Text capture** — Every text you copy is saved instantly
- **Image capture** — Screenshots and copied images saved as `.png`
- **Video path detection** — Detects copied file paths for `.mp4`, `.mkv`, `.avi`, and more
- **Pin system** — Pin important items; they are protected from deletion forever
- **Persistent storage** — SQLite database survives reboots
- **Real-time search** — Filter your clipboard history instantly
- **Clear history** — Wipe unpinned items in one click (pinned items always stay)
- **System tray** — Lives quietly in your tray, always available
- **IPC shortcut** — `Ctrl+Alt+V` shows the window from anywhere via local socket
- **App icon** — Auto-generated neon ghost icon via `scripts/generate_icon.py`
- **Dark Neon UI** — Custom QSS theme built for dark desktops
- **Settings panel** — ⚙ Max history limit, privacy clear-on-exit, theme toggle
- **Keyboard navigation** — `↑`/`↓` to move between cards, `Enter` to copy, `Esc` to clear focus
- **Double-click to paste** — Double-click any card to copy it instantly
- **Standalone autostart** — `scripts/setup_autostart.py` sets up boot entry without bash
- **Image thumbnail previews** — Lazy-loaded thumbnails capped at 300×180px; deferred rendering via `QTimer.singleShot`
- **Video thumbnails via ffmpeg** — First-frame extraction from video files; background thread processing; graceful fallback if ffmpeg unavailable
- **Auto-cleanup** — Configurable `max_captures` limit (default 100); oldest unpinned captures deleted from disk on startup
- **Image viewer popup** — Full-size image preview with smooth scaling; `Ctrl+C` to copy image; `Escape` to close
- **Copy image to clipboard** — Image items now copy actual image data (not file path) back to clipboard
- **Drag & drop reorder** — Pinned cards show drag handle; reorder persists via `sort_order` in database
- **Tag system** — Assign custom `#tags` to any item; colored chip display with rotating 6-palette colors; inline autocomplete from existing tags

<img src="data/assets/1.3.0-tag.gif" width="100%" alt="Tag System Demo" />

- **Combined search** — Search by text and tag simultaneously (e.g. `"python #code"`); tag-only filter works on all item types
- **Collections & Drag-and-Drop** — Group items into named folders; sidebar panel with click-to-filter, right-click to rename/delete. Features intuitive drag-and-drop interface for organizing items.

<img src="data/assets/demo-drag-and-drop.gif" width="100%" alt="Drag and Drop Collections Demo" />

- **Multi-select** — `Ctrl+Click` to toggle, `Shift+Click` for range selection; neon green `✓` overlay on selected cards

<img src="data/assets/1.3.0-Multi-Select.gif" width="100%" alt="Multi-Select Demo" />

- **Local Encryption (Eclipse Mode)** — Secure sensitive clipboard items using AES-256 encryption. Items are hidden and locked behind a Secret Overlay until explicitly revealed.

<img src="data/assets/demo-eclipse-encryption.gif" width="100%" alt="Local Encryption Demo" />

- **Session Lock & Master Password** — Protect your entire dashboard with a Master Password. Features automatic timeout locking and a stylish blurred lock screen.

<img src="data/assets/demo-session-lock.gif" width="100%" alt="Session Lock Demo" />

- **Advanced Settings & Pro UI** — Comprehensive control over Stealth Mode, App Filters, Auto-lock timeouts, and a beautiful DotSuite licensing/about page.

<img src="data/assets/demo-settings-and-about.gif" width="100%" alt="Settings and About Demo" />

- **Bulk actions toolbar** — Appears when 2+ selected: Pin All, Unpin All, Add Tag, Export, Delete All, Cancel
- **Export** — Export selected items to `.txt` (timestamped blocks) or `.json` (structured data with tags)
- **Global tag manager** — ⚙ Settings → "Manage Tags…"; rename or delete tags across all items in one click
- **Drag & drop visual feedback** — Ghost pixmap with neon border while dragging; source card dims to 35%; drop targets highlight with dashed green border

- **E2EE Local Network Sync (Nexus)** — End-to-end encrypted clipboard synchronization across your local network. AES-256-GCM protection with X25519 (ECDH) handshakes.
- **mDNS Auto-Discovery** — Zero-config discovery of peers on the same WiFi.
- **REST API** — Programmatic access to history and pushing through a local localhost server.
- **CLI Companion** — `dotghost push` and `dotghost pop` from your terminal for seamless shell workflow.
- **Secure Device Pairing** — PIN-protected handshakes to ensure unauthorized devices can't intercept your sync data.

**Native Desktop Integration:**
DotGhostBoard integrates seamlessly with desktop environment dock and app launcher.

<img src="data/assets/dock-icon.png" width="100%" alt="Kali Dock Integration" />

---

## Project Structure

```
DotGhostBoard/
├── main.py                      # Entry point + IPC local server
├── ghost.db                     # SQLite database (auto-created)
├── core/
│   ├── watcher.py               # Clipboard monitor (QTimer-based)
│   ├── storage.py               # Database CRUD layer
│   ├── crypto.py                # AES-256 encryption engine (Eclipse)
│   ├── sync_engine.py           # E2EE background push worker (Nexus)
│   ├── network_discovery.py     # Zeroconf mDNS peer discovery (Nexus)
│   ├── api_server.py            # Local REST API & Handshake handler (Nexus)
│   ├── pairing.py               # PIN-based ECDH handshake logic (Nexus)
│   ├── updater.py               # GitHub auto-updater engine (v1.4.1)
│   ├── app_filter.py            # App whitelist/blacklist (Eclipse)
│   └── media.py                 # Image/video handler
├── ui/
│   ├── dashboard.py             # Main window + keyboard nav + settings wiring
│   ├── widgets.py               # Item card widget (double-click, focus)
│   ├── settings.py              # Settings dialog with About tab
│   ├── pairing_dialog.py        # Device pairing UI (Nexus)
│   ├── lock_screen.py           # Master password lock screen (Eclipse)
│   ├── updater_dialog.py        # GUI for GitHub updates
│   └── ghost.qss                # Dark neon stylesheet
├── cli/
│   └── dotghost.py              # Command-line companion (Nexus)
├── data/
│   ├── icons/                   # Generated app icons + ghost.svg source
│   ├── captures/                # Saved images (.png)
│   ├── assets/                  # GIFs, screenshots, demo media
│   └── settings.json            # User settings
├── scripts/
│   ├── generate_icon.py         # Draws ghost icon at 16/32/48/64/128/256px
│   ├── install.sh               # Autostart + shortcut + CLI symlinker
│   ├── build_appimage.sh        # AppImage builder
│   └── setup_autostart.py       # Standalone Python autostart installer
├── tests/
│   ├── test_api.py              # REST API & Sync tests (178 total passed)
│   ├── test_eclipse.py          # Encryption & Security tests
│   ├── test_storage.py          # Database CRUD tests
│   └── test_media.py            # Media detection tests
├── roadmap(v1.x).md
├── CHANGELOG.md
├── requirements.txt
├── pytest.ini
└── .gitignore
```

---

## Requirements

| Dependency | Version  |
|------------|----------|
| Python     | 3.11+    |
| PyQt6      | 6.6.0+   |
| Pillow     | 10.0.0+  |
| cryptography | 41.0.0+ |
| pytest     | 7.0.0+   |

---

## 📥 Download

**Download for your platform:**

- 🐧 [AppImage (Linux)](https://github.com/kareem2099/DotGhostBoard/releases/latest)
- 📦 [DEB (Ubuntu/Debian)](https://github.com/kareem2099/DotGhostBoard/releases/latest)
- 🪟 [EXE (Windows)](https://github.com/kareem2099/DotGhostBoard/releases/latest)
- 🍎 [DMG (macOS)](https://github.com/kareem2099/DotGhostBoard/releases/latest)

---

## Installation

### Option A — System Python (Kali Linux)

PyQt6 and Pillow are usually pre-installed on Kali:

```bash
git clone https://github.com/kareem2099/DotGhostBoard.git
cd DotGhostBoard
python3 main.py
```

### Option B — Virtual Environment (Recommended)

```bash
git clone https://github.com/kareem2099/DotGhostBoard.git
cd DotGhostBoard

# Create isolated environment
python3 -m venv venv --system-site-packages
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Generate app icon (run once)
python3 scripts/generate_icon.py

# Run
python3 main.py
```

### Option C — pip install (PyPI)

```bash
pip install dotghostboard
dotghostboard
```

### Option D — AppImage (Portable)

Download the `.AppImage` from [Releases](https://github.com/kareem2099/DotGhostBoard/releases), then:

```bash
chmod +x DotGhostBoard-*.AppImage
./DotGhostBoard-*.AppImage
```

No installation needed — runs on ANY Linux distro.

### Option E — Full install (autostart + shortcut + icon)

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

This sets up autostart on login and registers the `Ctrl+Alt+V` shortcut via `xfconf-query`.

### Option F — Build AppImage from source

```bash
pip install pyinstaller
chmod +x scripts/build_appimage.sh
./scripts/build_appimage.sh
```

### Option G — DEB Package (Debian/Ubuntu/Kali)

**Quick install from Releases:**

```bash
# Download the latest .deb from GitHub Releases
wget https://github.com/kareem2099/DotGhostBoard/releases/latest/download/dotghostboard_1.5.0_amd64.deb

# Install with dpkg
sudo dpkg -i dotghostboard_*.deb

# Fix any missing dependencies (if needed)
sudo apt-get install -f

# Run
dotghostboard
```

**Or build locally:**

```bash
# Clone and build
git clone https://github.com/kareem2099/DotGhostBoard.git
cd DotGhostBoard

# Build the .deb package
chmod +x scripts/build_deb.sh
./scripts/build_deb.sh

# Install
sudo dpkg -i dotghostboard_*.deb

# Run
dotghostboard
```

**Uninstall:**

```bash
sudo apt remove dotghostboard
```

**Installed locations:**
- Binary: `/opt/dotghostboard/`
- Launcher: `/usr/bin/dotghostboard`
- Desktop entry: `/usr/share/applications/dotghostboard.desktop`
- Icon: `/usr/share/icons/hicolor/256x256/apps/dotghostboard.png`

---

## Usage

| Action | How |
|--------|-----|
| Copy anything | Just use `Ctrl+C` anywhere — DotGhostBoard captures it automatically |
| Show window | Press `Ctrl+Alt+V` from anywhere |
| Pin an item | Click 📌 on any card |
| Unpin an item | Click 📍 on a pinned card |
| Copy back | Click ⎘ on any card — or **double-click** the card |
| Delete an item | Click ✕ — pinned items are protected |
| Search | Type in the search bar at the top |
| Keyboard navigation | Press `↑` / `↓` to move focus; `Enter` or `Space` to copy; `Esc` to clear |
| Clear history | Click "Clear History" — pinned items are never deleted |
| Settings | Click ⚙ in the top bar — adjust history limit, privacy options |
| Minimize | Click X — the app stays alive in the system tray |
| Quit | Right-click the tray icon → Quit |

---

## Running Tests

```bash
python3 -m pytest
```

Expected output:
```
tests/test_api.py .....                                    [  3%]
tests/test_eclipse.py .................................    [ 21%]
tests/test_media.py ...........................            [ 37%]
tests/test_settings.py ............                       [ 44%]
tests/test_storage.py ................................    [ 62%]
tests/test_storage_v130.py ................................................. [ 90%]
tests/test_thumbnailer.py .........                       [ 95%]
tests/test_updater_core.py ...........                    [100%]

178 passed in 9.07s
```

<img src="data/assets/tests-passed.png" width="100%" alt="Tests Output" />

---

## Roadmap

| Version | Codename | Status | Goal |
|---------|----------|--------|------|
| v1.0.0 | Ghost | ✅ Released | Stable base — clipboard, pin system, dark UI, SQLite |
| v1.1.0 | Phantom | ✅ Released | Settings panel, keyboard nav, double-click paste, SVG icon |
| v1.2.0 | Specter | ✅ Released | Image thumbnails, video preview via ffmpeg, auto-cleanup, image viewer |
| v1.3.0 | Wraith | ✅ Released | Tags, collections, multi-select, bulk actions, export |
| v1.4.0 | Eclipse | ✅ Released | AES-256 encryption, master lock, stealth mode, pro UI |
| v1.4.1 | Mem & Perf | ✅ Released | Memory optimizations, GitHub auto-updater, IPC/Wayland bug fixes |
| v1.5.0 | Nexus | ✅ Released | E2EE Network Sync, mDNS Discovery, REST API, CLI Companion |
| v2.0.0 | Cerberus | 🔭 Planned | The Password Vault, Smart Secret Detection, Paranoia Mode |

Full details in [`roadmap(v2.x).md`](roadmap(v2.x).md)

---

## Contributing

Contributions are welcome. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before submitting a pull request.

---

## License

MIT — see [`LICENSE`](LICENSE) for details.

---

## Part of DotSuite

DotGhostBoard is one tool in the **DotSuite** collection — a set of lightweight, privacy-focused productivity tools built for Linux power users.

> DotEnv · DotCommand · DotSense · DotFetch · DotShare · DotScramble · **DotGhostBoard**

---

*Built with 💀 on Kali Linux*