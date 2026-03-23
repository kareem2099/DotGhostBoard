# 👻 DotGhostBoard

> Advanced clipboard manager for Kali Linux — part of the **DotSuite** toolkit.

![Version](https://img.shields.io/badge/version-v1.0.0-00ff41?style=flat-square&labelColor=0f0f0f)
![Python](https://img.shields.io/badge/python-3.11+-00ff41?style=flat-square&labelColor=0f0f0f)
![PyQt6](https://img.shields.io/badge/PyQt6-6.6+-00ff41?style=flat-square&labelColor=0f0f0f)
![Platform](https://img.shields.io/badge/platform-Linux-00ff41?style=flat-square&labelColor=0f0f0f)
![License](https://img.shields.io/badge/license-MIT-00ff41?style=flat-square&labelColor=0f0f0f)

---

## What is DotGhostBoard?

DotGhostBoard is a lightweight, privacy-first clipboard manager built natively for Linux. It runs silently in the background, capturing everything you copy — text, images, and video paths — and stores them locally in a SQLite database. No cloud. No telemetry. No Electron.

Think **Ditto** (Windows) or **CopyQ** (Linux) — but built for the DotSuite ecosystem with a Kali-native dark aesthetic.

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
- **Dark Neon UI** — Custom QSS theme built for dark desktops

---

## Project Structure

```
DotGhostBoard/
├── main.py                  # Entry point
├── ghost.db                 # SQLite database (auto-created)
├── core/
│   ├── watcher.py           # Clipboard monitor (QTimer-based)
│   ├── storage.py           # Database CRUD layer
│   └── media.py             # Image/video handler
├── ui/
│   ├── dashboard.py         # Main window
│   ├── widgets.py           # Item card widget
│   └── ghost.qss            # Dark neon stylesheet
├── data/
│   ├── captures/            # Saved images (.png)
│   ├── pins/                # Backup copies of pinned images
│   └── v_logs/              # Video path log file
├── todo_list(v1.0.0).json
├── roadmap(v1.x).json
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

# Run
python3 main.py
```

---

## Usage

| Action | How |
|--------|-----|
| Copy anything | Just use Ctrl+C anywhere — DotGhostBoard captures it automatically |
| Pin an item | Click the 📌 button on any card |
| Unpin an item | Click the 📍 button on a pinned card |
| Copy back | Click ⎘ on any card to restore it to clipboard |
| Delete an item | Click ✕ (pinned items are protected) |
| Search | Type in the search bar at the top |
| Clear history | Click "Clear History" (pinned items are never deleted) |
| Minimize | Click X — the app stays alive in the system tray |
| Quit | Right-click the tray icon → Quit |

---

## Roadmap

| Version | Codename | Goal |
|---------|----------|------|
| v1.0.0 | Ghost | Stable base ← **current** |
| v1.1.0 | Phantom | Global hotkey, autostart, settings panel |
| v1.2.0 | Specter | Image thumbnails, video preview |
| v1.3.0 | Wraith | Tags, collections, multi-select |
| v1.4.0 | Eclipse | Encryption, master lock, stealth mode |
| v1.5.0 | Nexus | Sync, CLI companion, plugin system |

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

---

*Built with 💀 on Kali Linux*
