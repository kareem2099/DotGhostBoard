# Contributing to DotGhostBoard

First off — thank you for taking the time to contribute. Every bug report, suggestion, and pull request makes DotGhostBoard better.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Branch Naming](#branch-naming)
- [Commit Style](#commit-style)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Project Structure Quick Reference](#project-structure-quick-reference)

---

## Code of Conduct

This project follows our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

---

## How Can I Contribute?

### Report a Bug
Open an issue and include:
- Your OS and desktop environment (e.g. Kali Linux / XFCE)
- Python and PyQt6 version (`python3 --version`, `pip show PyQt6`)
- Steps to reproduce
- What you expected vs what happened
- Any error output or traceback

### Suggest a Feature
Open an issue with the label `enhancement`. Check the [`roadmap(v1.x).json`](roadmap(v1.x).json) first — your idea might already be planned.

### Fix a Bug / Implement a Feature
1. Open or find an existing issue
2. Comment that you're working on it
3. Fork → branch → code → PR

---

## Development Setup

```bash
# Fork and clone
git clone https://github.com/kareem2099/DotGhostBoard.git
cd DotGhostBoard

# Create virtual environment
python3 -m venv venv --system-site-packages
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python3 main.py
```

---

## Branch Naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/short-description` | `feat/global-hotkey` |
| Bug fix | `fix/short-description` | `fix/db-connection-leak` |
| Refactor | `refactor/short-description` | `refactor/watcher-thread` |
| Docs | `docs/short-description` | `docs/readme-update` |
| Tests | `test/short-description` | `test/storage-crud` |

---

## Commit Style

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]
```

### Types

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code change that doesn't fix or add |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `chore` | Build process, deps, config |
| `style` | Formatting, whitespace (no logic change) |

### Examples

```bash
git commit -m "feat(watcher): add global hotkey Ctrl+Shift+V"
git commit -m "fix(storage): prevent connection leak on exception"
git commit -m "docs(readme): add installation screenshot"
git commit -m "refactor(widgets): extract _build_content to separate method"
```

---

## Pull Request Process

1. Make sure your branch is up to date with `main`
2. Run the app and manually test your changes
3. Update `CHANGELOG.md` under `[Unreleased]`
4. If you added a new feature, update `todo_list(v1.0.0).json` accordingly
5. Open a PR with a clear title and description
6. Link the related issue with `Closes #issue_number`

### PR Title Format

```
feat(scope): what you did
fix(scope): what you fixed
```

---

## Code Style

- **Python 3.11+** — use type hints where practical
- **4 spaces** indentation — no tabs
- **Max line length**: 100 characters
- **Docstrings**: short single-line for simple functions, multi-line for complex ones
- **Error handling**: never let exceptions silently crash the UI — use `try/except` and `print(f"[Module] ...")`
- **No unused imports** — keep imports clean and at the top of the file
- **Context managers**: always use `with _db() as conn:` for database access — never open/close manually

### File Responsibility (don't mix concerns)

| File | Owns |
|------|------|
| `core/storage.py` | All DB queries |
| `core/watcher.py` | Clipboard polling logic only |
| `core/media.py` | File I/O for images and videos |
| `ui/dashboard.py` | Window layout + slot wiring |
| `ui/widgets.py` | Individual card appearance only |
| `ui/ghost.qss` | All visual styling |

---

## Project Structure Quick Reference

```
DotGhostBoard/
├── main.py          ← entry point, env setup, signal handlers
├── core/            ← business logic (no UI imports here)
├── ui/              ← PyQt6 widgets and stylesheet
├── data/            ← runtime files (gitignored)
└── ghost.db         ← SQLite database (gitignored)
```

---

Thank you for contributing to DotGhostBoard 👻
