# 👻 DotGhostBoard

> Advanced clipboard manager for Kali Linux — part of the **DotSuite** toolkit.

![Version](https://img.shields.io/badge/version-v1.0.0-00ff41?style=flat-square&labelColor=0f0f0f)
![Python](https://img.shields.io/badge/python-3.11+-00ff41?style=flat-square&labelColor=0f0f0f)
![PyQt6](https://img.shields.io/badge/PyQt6-6.6+-00ff41?style=flat-square&labelColor=0f0f0f)
![Platform](https://img.shields.io/badge/platform-Linux-00ff41?style=flat-square&labelColor=0f0f0f)
![Tests](https://img.shields.io/badge/tests-59%20passed-00ff41?style=flat-square&labelColor=0f0f0f)
![License](https://img.shields.io/badge/license-MIT-00ff41?style=flat-square&labelColor=0f0f0f)

---

## What is DotGhostBoard?

DotGhostBoard is a lightweight, privacy-first clipboard manager built natively for Linux. It runs silently in the background, capturing everything you copy — text, images, and video paths — and stores them locally in a SQLite database. No cloud. No telemetry. No Electron.

Think **Ditto** (Windows) or **CopyQ** (Linux) — but built for the DotSuite ecosystem with a Kali-native dark aesthetic.

<img src="data/assets/demo-ui.gif" width="100%" alt="DotGhostBoard UI Demo" />

<img src="data/assets/demo-capture.gif" width="100%" alt="DotGhostBoard UI Demo" />

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
- **App icon** — Auto-generated ghost icon via `scripts/generate_icon.py`
- **Dark Neon UI** — Custom QSS theme built for dark desktops

**Native Desktop Integration:**
DotGhostBoard integrates seamlessly with your desktop environment dock and app launcher.

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
│   └── media.py                 # Image/video handler
├── ui/
│   ├── dashboard.py             # Main window
│   ├── widgets.py               # Item card widget
│   └── ghost.qss                # Dark neon stylesheet
├── data/
│   ├── icons/                   # Generated app icons (all sizes)
│   ├── captures/                # Saved images (.png)
│   ├── pins/                    # Backup copies of pinned images
│   └── v_logs/                  # Video path log file
├── scripts/
│   ├── generate_icon.py         # Draws ghost icon at 16/32/48/64/128/256px
│   └── install.sh               # Autostart + shortcut + .desktop installer
├── tests/
│   ├── test_storage.py          # 32 tests — full CRUD coverage
│   └── test_media.py            # 27 tests — media detection & file ops
├── todo_list(v1.0.0).json
├── roadmap(v1.x).json
├── pytest.ini
├── requirements.txt
└── .gitignore
```

---

## Requirements

| Dependency | Version  |
|------------|----------|
| Python     | 3.11+    |
| PyQt6      | 6.6.0+   |
| Pillow     | 10.0.0+  |
| pytest     | 7.0.0+   |

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

### Option C — Full install (autostart + shortcut + icon)

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

This sets up autostart on login and registers the `Ctrl+Alt+V` shortcut via `xfconf-query`.

---

## Usage

| Action | How |
|--------|-----|
| Copy anything | Just use `Ctrl+C` anywhere — DotGhostBoard captures it automatically |
| Show window | Press `Ctrl+Alt+V` from anywhere |
| Pin an item | Click 📌 on any card |
| Unpin an item | Click 📍 on a pinned card |
| Copy back | Click ⎘ on any card to restore it to clipboard |
| Delete an item | Click ✕ — pinned items are protected |
| Search | Type in the search bar at the top |
| Clear history | Click "Clear History" — pinned items are never deleted |
| Minimize | Click X — the app stays alive in the system tray |
| Quit | Right-click the tray icon → Quit |

---

## Running Tests

```bash
python3 -m pytest
```

Expected output:
```
tests/test_media.py    ........................... 27 passed
tests/test_storage.py  ................................ 32 passed
59 passed in 0.23s
```

<img src="data/assets/tests-passed.png" width="100%" alt="Tests Output" />

---

## Roadmap

| Version | Codename | Goal |
|---------|----------|------|
| v1.0.0 | Ghost | Stable base ← **current** |
| v1.1.0 | Phantom | Settings panel, keyboard nav, double-click paste |
| v1.2.0 | Specter | Image thumbnails, video preview via ffmpeg |
| v1.3.0 | Wraith | Tags, collections, multi-select, export |
| v1.4.0 | Eclipse | AES-256 encryption, master lock, stealth mode |
| v1.5.0 | Nexus | Local network sync, CLI companion, plugin system |

Full details in [`roadmap(v1.x).json`](roadmap(v1.x).json)

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