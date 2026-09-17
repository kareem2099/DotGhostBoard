# 🗺️ DotGhostBoard — v2.x Master Roadmap (Post Phantom)

> **Baseline:** v1.6.0 "Phantom" — Modular Architecture Foundation complete.
> **Branch Strategy:** Each release starts from a feature branch → PR → merge to `main` → tag.
> **Rule:** Never ship new features and architecture refactors in the same commit.

---

## ✅ What v1.6.0 "Phantom" Delivered (Foundations)

| Layer | Done |
|---|---|
| `core/storage/` — Repository Pattern + Facade | ✅ |
| `core/clipboard/` — Headless Pipeline + Protocol Backends | ✅ |
| `core/services/` — HistoryService, CollectionService, SecurityService, SyncService | ✅ |
| `core/security/` — SecretDetector, Vault (DEK/KEK envelope encryption) | ✅ |
| `core/crypto.py` — PBKDF2 + HKDF-SHA256 two-tier key derivation | ✅ |
| `ui/controllers/` — 4 behavioral QObject controllers extracted from Dashboard | ✅ |
| `ui/dashboard.py` — Reduced from 2,353 → 1,535 lines | ✅ |
| Test suite — 220 → 306 tests across 25 modules | ✅ |

---

## 🚧 What Is NOT Done Yet (Still Required Before v2.0)

| Component | Status | Notes |
|---|---|---|
| `ui/settings.py` — Decomposed into `ui/settings/` | ✅ | Completed in Phase 5 (1,324 LOC → modular package) |
| `ui/dashboard.py` — Streamlined to 493 lines (≤ 500) | ✅ | Completed in Phase 6 (Components & Controllers extracted) |
| Multi-Channel Update System (Stable, Beta, Alpha) | ✅ | Completed in v2.0.0-beta.2 |
| `core/security/vault/` — VaultService wired to UI | ⬜ | Vault panel UI integration |
| Wayland backend (`wlr-data-control`) | ⬜ | Planned for v2.1 Leviathan |
| `core/api_server.py` — 14,765 bytes REST API server | ⬜ | Needs service layer integration |

---

## 📅 Release Plan

```
v2.0.0 "Cerberus"   — Phase 5 + Vault Panel + Smart Detection
v2.1.0 "Leviathan"  — Wayland + Spotlight + System Tray Dash
v2.2.0 "Chimera"    — Local OCR + Smart Actions + Auto-Tagging
v2.3.0 "Oracle"     — Predictive UX + Workflows + Ephemeral
```

---

## 🔵 v2.0.0 — "Cerberus"

> **Codename:** Cerberus — The Vault Gatekeeper
> **Goal:** Complete architecture + ship Vault as a first-class feature.

### Phase 5: Settings Decomposition

> `ui/settings.py` (1,324 lines) needs the same treatment the Dashboard received.

**Target structure:**
```
ui/settings/
├── __init__.py          # Re-exports SettingsDialog
├── dialog.py            # Main shell (≤ 200 lines)
├── pages/
│   ├── general.py       # Appearance, language, startup
│   ├── clipboard.py     # Capture filters, media settings
│   ├── security.py      # Password policy, Eclipse, auto-lock
│   ├── sync.py          # Device management, trusted peers
│   ├── vault.py         # Vault settings and danger zone
│   └── about.py         # Version, licenses, update channel
└── tag_manager.py       # Tag CRUD panel (extracted from settings)
```

**Key rules:**
- Settings pages call `SettingsService` / `SecurityService` — no raw disk I/O.
- No direct `QSettings` calls inside pages; all persistence goes through a `SettingsRepository`.
- Backward compatible: existing `from ui.settings import SettingsDialog` still works.

**Git commits:**
```
feat(settings): extract SettingsRepository for QSettings isolation
refactor(settings): decompose into pages/ package
refactor(settings): extract TagManagerPanel into ui/settings/tag_manager.py
test(settings): add page-level unit tests (target: 15 new tests)
```

**Definition of Done:**
- [ ] `ui/settings/dialog.py` ≤ 200 lines.
- [ ] Each settings page ≤ 150 lines.
- [ ] All 306 existing tests still pass.
- [ ] New: ≥ 15 tests for settings pages.

---

### Phase 6: Dashboard Final Decomposition (Target ≤ 500 lines)

> Current: 1,535 lines. Target: ≤ 500 lines pure orchestrator.

**Remaining to extract:**
```
ui/components/
├── cards_view.py         # Infinite scroll cards layout
├── sidebar.py            # Collection sidebar widget
├── topbar.py             # Search bar + filter chips + stats
└── bulk_toolbar.py       # Multi-select bulk actions
```

**Dashboard becomes:**
```python
class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self._load_settings()
        self._build_ui()           # Assembles components
        self._create_services()    # Injects services
        self._create_controllers() # Injects controllers
        self._connect_signals()    # Wires component signals
        self._restore_state()      # Restores last session
```

**Git commits:**
```
refactor(ui): extract CardsView component from dashboard
refactor(ui): extract SidebarWidget from dashboard
refactor(ui): extract TopBarWidget from dashboard
refactor(ui): extract BulkToolbar from dashboard
refactor(dashboard): reduce to pure orchestrator ≤ 500 lines
```

**Definition of Done:**
- [ ] `ui/dashboard.py` ≤ 500 lines.
- [ ] Zero direct `storage.*` calls remain in dashboard.
- [ ] Zero direct `crypto.*` calls remain in dashboard.
- [ ] All signals flow through controllers.
- [ ] Existing 306 tests + Phase 5 tests pass.

---

### Phase 7: Vault Panel (First-Class Feature)

> The encrypted Vault is already implemented at the service layer (`core/security/vault/`).
> This phase surfaces it as a polished first-class UI panel.

**New files:**
```
ui/vault/
├── __init__.py
├── vault_panel.py        # Slide-in/drawer panel integrated into Dashboard
├── unlock_dialog.py      # Master password prompt
├── secret_card.py        # Encrypted item card widget
└── vault_settings.py     # Change/remove master password
```

**Features:**
- Vault panel opens via sidebar button or `Ctrl+Shift+V`.
- Unlock via master password (uses `SecurityService.unlock_vault()`).
- Items shown as masked cards; tap to reveal in-memory (no plaintext written to disk).
- Auto-lock vault after configurable timeout (default: 5 minutes).
- "Move to Vault" action surfaced on regular clip cards when `SecretDetector` fires.

**Git commits:**
```
feat(vault): add VaultPanel drawer widget
feat(vault): add UnlockDialog with password field
feat(vault): add SecretCard masked display widget
feat(vault): integrate Ctrl+Shift+V keyboard shortcut
test(vault): add vault panel interaction tests
```

**Definition of Done:**
- [ ] Vault panel opens, locks, and unlocks correctly.
- [ ] Items survive app restart (encrypted in `vault.db`).
- [ ] Password rotation works (re-wraps DEK, no item re-encryption).
- [ ] Auto-lock after timeout fires correctly.
- [ ] ≥ 20 new tests for vault UI interactions.

---

### Phase 8: Secret Detection UX

> `SecretDetector` (sub-millisecond regex engine) is in `core/security/detector.py`.
> This phase adds the user-facing prompts and workflow around it.

**Features:**
- When `SecretDetector` fires `SECRET_CANDIDATE`, show a non-intrusive toast:
  ```
  🔐 Secret detected. Move to Vault?   [Move]  [Keep]  [Ignore]
  ```
- "Auto-Clear" mode: automatically wipe a pasted secret from clipboard 30s after paste.
- "Paranoia Mode" toggle in quick settings: prevents ALL new items from being saved to DB.
- Secret patterns supported: JWT, `ghp_`, `AKIA`, SSH private keys, high-entropy hex (32–64 chars).

**Git commits:**
```
feat(security): add SecretDetectionToast widget
feat(security): wire toast to ClipboardPipeline SECRET_CANDIDATE action
feat(security): add Auto-Clear 30s timer on vault paste
feat(security): add Paranoia Mode toggle to quick settings
test(security): add toast trigger and auto-clear tests
```

**Definition of Done:**
- [ ] Toast appears within 200ms of a secret being captured.
- [ ] "Move to Vault" correctly encrypts and removes from regular history.
- [ ] Auto-Clear timer fires and wipes clipboard content.
- [ ] Paranoia Mode prevents DB writes while active.

---

## 🟣 v2.1.0 — "Leviathan"

> **Codename:** Leviathan — Wayland Native + Power-User UX
> **Goal:** Support modern Linux environments + keyboard-first power users.

### Wayland Backend
- Implement `WaylandClipboardBackend` using `wlr-data-control` Wayland protocol.
- Auto-detect compositor: if Wayland session detected, use `WaylandClipboardBackend`; else fall back to `QtClipboardBackend`.
- Target compositors: **Hyprland**, **Sway**, **GNOME Wayland**, **KDE Plasma (Wayland)**.

### Spotlight Upgrade (Global Search Overlay)
- Current `ui/spotlight.py` works but needs polish.
- New features:
  - Fuzzy search across clips, tags, and vault items (vault items shown as `[Vault] ****`).
  - `Ctrl+Shift+F` global hotkey.
  - Up/Down navigation + Enter to copy + `Ctrl+Enter` to paste.
  - Animated fade-in/out.

### System Tray Mini-Dash
- Quick-access panel from system tray icon.
- Shows last 5 clips + Vault quick-unlock + Paranoia Mode toggle.
- Right-click: Open full dashboard / Settings / Quit.

---

## 🟡 v2.2.0 — "Chimera"

> **Codename:** Chimera — Local OCR + Smart Regex Actions
> **Goal:** Extract value from captured content without cloud dependencies.

### Local OCR (Tesseract)
- Text extraction from image clips using **Tesseract** (fully offline).
- Extracted text stored alongside the image clip, instantly searchable.
- Show "OCR text" badge on image cards.

### Regex Smart Actions
Context-aware action buttons that appear on cards based on content pattern:
| Detected Pattern | Action Button |
|---|---|
| URL (`https://...`) | `Open Link` |
| IP Address | `Ping` |
| Valid JSON | `Format JSON` |
| Phone Number | `Copy to Dialer` |
| Email | `Send Email` |
| Secret (high-entropy) | `Move to Vault` |

### Auto-Tagging (Rules-Based)
Automatic tag assignment without NLP:
- `#link` — URL detected
- `#code` — multi-line code block detected
- `#secret` — high entropy / token pattern
- `#json` — valid JSON payload
- `#image` — image clip

---

## 🟠 v2.3.0 — "Oracle"

> **Codename:** Oracle — Predictive & Context-Aware
> **Goal:** Always one step ahead of the user.

### Scheduled Self-Destruct (Ephemeral Items)
- Clips can be marked as ephemeral: vanish after N pastes or after X minutes.
- UI: each card gets a "self-destruct" timer badge when set.

### Context-Aware Paste (Pasty)
- Surfaces the most relevant clip based on the **active window**.
- Example: password manager detected → Vault items bubbled to top.
- Example: IDE detected → code clips bubbled to top.
- Driven by `wmctrl`/`xdotool` window class detection. No AI.

### Workflow Automation
- User-defined rules: "If clip matches regex X → run command Y".
- Example: Error log detected → open StackOverflow search in browser.
- Rules defined in YAML format inside settings.

---

## 📐 Architecture Completion Targets

| Target | v1.6.0 Now | v2.0.0 Goal |
|---|---|---|
| `ui/dashboard.py` LOC | 1,535 | **≤ 500** |
| `ui/settings.py` LOC | 1,324 | **Decomposed into pages/** |
| Direct SQL in UI layer | 0 | 0 |
| Direct crypto in UI layer | 0 | 0 |
| Test count | 306 | **≥ 400** |
| Wayland support | 0% | Phase 7 ready → **v2.1** |
| Vault UI | Service ready, no UI | **Full panel** |

---

## 🧱 Architecture Principles (Unchanged from Phantom)

> These rules apply to **every** v2.x commit.

1. **Controllers coordinate UI.** Services own business rules. Repositories own persistence. Backends own platform integration.
2. **`core` never imports `ui`.** One-way dependency arrow only.
3. **One concern per commit.** Never mix refactor + new feature + schema change.
4. **Facade before breaking change.** Keep old import paths alive during extraction.
5. **Tests first on risky extractions.** Regression tests before moving a function.

---

## 🌿 Branch Strategy

```
main
 ├── feature/v2.0-cerberus-settings-decomp    → Phase 5
 ├── feature/v2.0-cerberus-dashboard-final    → Phase 6
 ├── feature/v2.0-cerberus-vault-panel        → Phase 7
 ├── feature/v2.0-cerberus-secret-detection   → Phase 8
 ├── feature/v2.1-leviathan-wayland           → Wayland backend
 └── feature/v2.1-leviathan-spotlight         → Spotlight upgrade
```

---

## 🧪 v2.0 Exit Criteria

Before tagging `v2.0.0`:

- [ ] `ui/dashboard.py` ≤ 500 lines.
- [ ] `ui/settings.py` decomposed into `ui/settings/` package.
- [ ] Vault Panel fully functional (create, unlock, auto-lock, rotate password).
- [ ] Secret detection toast wired end-to-end.
- [ ] Test suite ≥ 380 tests (all passing).
- [ ] CHANGELOG.md `[2.0.0]` entry complete.
- [ ] `pyproject.toml` version bumped to `2.0.0`.
- [ ] `core/config.py` — `APP_VERSION = "v2.0.0"`, `APP_CODENAME = "Cerberus"`.
- [ ] All build artifacts generated by CI (AppImage, .deb, .pkg.tar.zst).
- [ ] Signed tag `v2.0.0` pushed to GitHub.

---

*DotSuite v2 — Ghosting boundaries, securely.* 👻