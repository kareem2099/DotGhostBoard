# Changelog

All notable changes to DotGhostBoard are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] — 2026-10-02 — *Leviathan (Smart Auto-Tagging, Contextual Actions, Vault Backup & Expiry)*

> **Codename:** Leviathan — Power-User Productivity & Vault Intelligence Release
>
> This release introduces rules-based Smart Auto-Tagging (`#link`, `#code`, `#json`, `#secret`, `#email`, `#ip`, `#phone`, `#path`, `#hash`) using local regex and entropy heuristics with zero NLP/AI runtime overhead, contextual inline Smart Action buttons directly on item cards (Open Link, Format Pretty JSON, Compose Email, Copy IP, Send to Vault), an integrated secure Password & Token Generator within The Vault dialog featuring Shannon entropy bit calculation and visual strength meters, standalone AES-256-GCM encrypted Vault backup/restore (`.vault` format) with 100k-round PBKDF2 key derivation, Secret Expiry dates with visual countdown and expired status badges, cross-subsystem Vault-to-Dashboard history sweep to eliminate lingering plaintext duplicates, robust bracket and special-character preservation for complex passwords, and dynamic user-configured auto-purge history management. Automated test suite expanded to 522 passing tests.

### Added — Smart Auto-Tagging Engine (`core/security/auto_tagger.py`, `core/watcher.py`, `tests/test_auto_tagger.py`)

- **Rules-Based Auto-Tagging Engine (`core/security/auto_tagger.py`)**:
  - Pure local regex and Shannon entropy heuristics that automatically classify clipboard text upon capture without external dependencies or heavy background processes.
  - Automatically identifies and applies contextual tags:
    - `#link` — HTTP, HTTPS, and FTP URLs.
    - `#code` — Multi-line code snippets, programming language keywords (`def`, `class`, `function`, `public static`, `async/await`, etc.), and dense syntax structures.
    - `#json` — Valid JSON objects or arrays.
    - `#secret` — High-entropy credentials, API keys, JWT tokens, AWS access keys, GitHub PATs, and PEM private keys.
    - `#email` — Standard RFC email addresses.
    - `#ip` — IPv4 and IPv6 addresses.
    - `#phone` — Formatted telephone and mobile numbers.
    - `#path` — Unix absolute and Windows filesystem paths.
    - `#hash` — Cryptographic digests (MD5, SHA-1, SHA-256).
- **Clipboard Ingestion Pipeline Integration (`core/watcher.py`)**:
  - Auto-detected tags are seamlessly merged with user-defined tags during clipboard ingestion, enabling instant tag filtering and search matching right from the first copy.
- **Dedicated Test Suite (`tests/test_auto_tagger.py`)**:
  - 11 comprehensive unit tests covering all pattern heuristics, error handling, and storage persistence.

### Added — Contextual Smart Actions on Cards (`ui/widgets/item_card.py`)

- **Inline Smart Actions Toolbar**:
  - Contextual, non-intrusive action buttons appear dynamically beneath card content when recognizable patterns are present:
    - **🔗 Open Link**: Instantly opens detected URLs in the default desktop browser.
    - **{ } Format JSON**: Parses and re-formats minified JSON into indented, human-readable JSON copied directly back to the clipboard.
    - **✉ Compose**: Launches the system mail client with prefilled `mailto:` target.
    - **📡 Copy IP**: Extracts and copies clean IP address from noisy logs or text.
    - **🛡 → Vault**: One-click transition for detected credentials or high-entropy tokens to be securely stored into The Vault with envelope encryption.
- **Card Signal Routing (`sig_smart_action`)**: Emits structured action signals for telemetry and UI status responses.

### Added — Built-in Vault Password & Token Generator (`ui/vault/secret_dialog.py`, `tests/test_password_generator.py`)

- **Integrated Generator Modal (`ui/vault/secret_dialog.py`)**:
  - Added a dedicated `⚡ Generate` button and expandable generator section in the Add / Edit Secret dialog.
  - Generates cryptographically secure passwords or API tokens using Python's `secrets` CSPRNG.
  - Configurable length (8–64 chars), character pool toggles (lowercase, uppercase, digits, symbols), and token modes (`hex`, `uuid4`, `base64`, `bearer`, `urlsafe`).
- **Real-Time Entropy & Strength Meter**:
  - Real-time calculation of Shannon entropy bits (`_entropy_bits`).
  - Visual color-coded strength bar (Weak, Moderate, Strong, Fort Knox) with instantaneous dynamic feedback.
- **Unit Test Coverage (`tests/test_password_generator.py`)**:
  - 6 unit tests covering CSPRNG distribution, format validation, entropy calculations, and fallback behaviors.

### Added — Vault Password History & Safe Revert (`core/security/vault/`, `ui/vault/history_dialog.py`, `tests/test_vault_history.py`)

- **Automated Encrypted History Retention (`core/security/vault/repository.py`, `service.py`)**:
  - Automatically captures and retains up to 3 previous encrypted ciphertext versions (`vault_item_history`) whenever a secret payload is updated or rotated.
  - Strict FIFO pruning prevents unbounded database growth while ensuring the last 3 password states are preserved.
  - Zero-exposure: historical secrets remain fully encrypted with the per-database DEK envelope and are decrypted in-memory only upon explicit user request.
  - Cascading cleanup: deleting a Vault item permanently purges its associated history records.
- **Dedicated Password History Dialog (`ui/vault/history_dialog.py`)**:
  - Accessed via the `📜` history button on any `SecretCard`.
  - Displays version chronological index, creation timestamp, and masked (`••••••••`) payload.
  - Features in-memory `👁️ Reveal` / `🙈 Hide`, safe `📋 Copy` (with automatic 30s clipboard scrubbing), and a single-click `↺ Revert to this` button.
  - Reverting restores an older password as the active secret while archiving the current value into history, preventing accidental overwrites.
  - Memory-safe: immediately scrubs all plaintext buffers from memory when closed or when the Vault locks.
- **Comprehensive Test Suite (`tests/test_vault_history.py`)**:
  - 5 tests validating history capping, FIFO pruning, cascade deletion, service lifecycle, locked error protection, and UI dialog interactions.

### Added — Vault Encrypted Export & Import (.vault) (`core/security/vault/backup.py`, `ui/vault/vault_panel.py`, `ui/vault/vault_controller.py`, `tests/test_vault_backup.py`)

- **Cryptographic Backup Engine (`core/security/vault/backup.py`)**:
  - Standalone `.vault` binary package format: `b"DGBV" + version (1B) + salt (16B) + nonce (12B) + ciphertext + GCM auth tag (16B)`.
  - AES-256-GCM authenticated encryption paired with PBKDF2-HMAC-SHA256 key derivation (100,000 iterations) using an independent per-export salt.
  - Packages all secrets, categories, creation/updated timestamps, full 3-version historical entries, and expiration dates.
  - Zero disk leaks: encryption and decryption occur entirely in memory before writing to disk or populating the database.
- **Import & Duplicate Resolution Engine**:
  - Validates magic header, format version, and cryptographic authenticity; rejects wrong passphrases or truncated files cleanly without corrupting the active database.
  - Built-in duplicate skipping policy (`overwrite_existing=False`) preventing duplicate credential proliferation during backup restores.
- **Drawer Panel Export & Import Tooling (`ui/vault/vault_panel.py`, `ui/vault/vault_controller.py`)**:
  - Added dedicated `📤` (Export) and `📥` (Import) tool buttons directly in The Vault drawer header bar.
  - Password modal dialogs to capture and confirm backup passphrases with clear success and error feedback.
- **Dedicated Test Coverage (`tests/test_vault_backup.py`)**:
  - 6 unit tests covering format validation, plaintext confidentiality, roundtrip restore, corrupted file rejection, wrong passphrase handling, and duplicate skipping.

### Added — Secret Expiry Date & Visual Warning Badges (`core/security/vault/models.py`, `database.py`, `ui/vault/secret_dialog.py`, `secret_card.py`, `tests/test_vault_expiry.py`)

- **Database Expiration Column & Dynamic Migration (`core/security/vault/database.py`, `repository.py`)**:
  - Added `expires_at TIMESTAMP` to the `vault_items` table with backward-compatible dynamic migration in `init_vault_db`.
  - Query filtering and storage persistence across repository and service layers.
- **Expiry Computing Models (`core/security/vault/models.py`)**:
  - Added dynamic `@property is_expired` and `@property days_remaining` to both `VaultItem` and `VaultSummary` models for clean state checks.
- **SecretDialog Expiry Controls (`ui/vault/secret_dialog.py`)**:
  - Added optional `[ ] Set Expiration Date` checkbox with animated expand/collapse container.
  - Preset duration dropdown (`30 Days`, `90 Days`, `180 Days`, `1 Year`, `Custom...`) paired with an interactive `QDateEdit` calendar picker.
  - Backward-compatible `SecretData` tuple unpack allowing existing callers and tests unpacking 3 elements (`title, payload, cat = dlg.get_data()`) to function seamlessly without modification while exposing `.expires_at`.
- **SecretCard Visual Status Badges (`ui/vault/secret_card.py`)**:
  - Dynamic pill badges rendered in the top header row of each secret card:
    - `⛔ EXPIRED` — Red badge with tooltip indicating expiration date.
    - `⚠️ Xd left` — Yellow warning badge when expiration is within 7 days.
    - `⏳ YYYY-MM-DD` — Blue pill badge for long-term active secrets.
- **Dedicated Test Suite (`tests/test_vault_expiry.py`)**:
  - 5 tests covering property calculations, database persistence, dialog presets, custom dates, tuple unpacking, and visual badge rendering.

### Added — Vault-to-Dashboard History Sweep (`ui/vault/vault_controller.py`, `ui/vault/wiring.py`)

- **Coordinated Plaintext Purge**:
  - When a secret is deleted from The Vault, or scrubbed after transmission, any matching plaintext duplicates lingering in the unencrypted dashboard history are automatically swept and removed from the database and UI.
- **Safe Signal Decoupling**:
  - Emits `history_item_removed` signal across `ui/vault/wiring.py` to trigger UI card disposal in `HistoryController` without tight coupling between Vault and History subsystems.

### Fixed — Bracket & Special Character Password Preservation (`core/storage/repositories/clips.py`, `core/watcher.py`)

- **Complex Password Support**:
  - Resolved an issue where passwords containing brackets, parentheses, or syntax symbols (e.g. `tn)eT2sabF*P#hbRb`) were misinterpreted as expressions or dropped during storage verification.
- **Dashboard Visibility**:
  - Ensured that unencrypted passwords and credentials correctly populate the dashboard history when no Master Password is configured, preventing accidental capture loss.

### Improved — Configurable Auto-Purge History Limit (`core/storage/repositories/clips.py`, `core/constants.py`)

- **Settings Dynamic Integration**:
  - `auto_purge_history()` now directly reads and honors the user's "Max history" configuration from the Settings panel (defaulting to user settings, e.g. 2000 items), while falling back cleanly to `HISTORY_MAX_ITEMS` and maintaining `HISTORY_PURGE_CHUNK` batch sizing.
  - Prevents unbounded SQLite database growth on long-running instances while strictly preserving pinned cards.

### Improved — Vault Drawer UX & Empty State Onboarding (`ui/vault/vault_panel.py`, `core/constants.py`, `ui/ghost.qss`)

- **Two-Row Header Architecture (`ui/vault/vault_panel.py`)**:
  - Reorganized drawer top bar into two dedicated rows to prevent horizontal crowding and button clipping:
    - **Row 1:** Title (`🛡️ The Vault`), Status Badge (`🔒 Locked` / `🔓 Unlocked`), flexible stretch, and Close button (`✕`).
    - **Row 2 Toolbar:** Prominent `+ Add Secret` primary button on the left, flexible stretch, and utility action buttons on the right (`🔓 / 🔒` Lock Toggle, `📤` Export Backup, `📥` Import Backup, `❓` Quick Tips Guide).
  - Increased `VAULT_DRAWER_WIDTH` from 340px to 380px (`core/constants.py`) for improved typography and comfortable action spacing.
- **Vault Empty State Smart Tips Card (`ui/vault/vault_panel.py`, `ui/ghost.qss`)**:
  - When the Vault is unlocked but contains no secrets, users are greeted with an informative, styled onboarding card (`#VaultTipsCard`) highlighting core capabilities:
    - ⌨️ **Global Shortcut**: `Ctrl+Shift+V` to open or hide the Vault from anywhere.
    - ⏱️ **Automatic Clipboard Scrubbing**: Secrets copied to clipboard are wiped automatically after 30 seconds.
    - 📜 **Version History**: Up to 3 previous encrypted password versions are preserved for safe rollback.
    - ⏳ **Expiration Tracking**: Support for temporary tokens and credentials with proactive expiration warnings.

### Improved — Unified Password Input & Compact Lock Screens (`ui/widgets/password_input.py`, `ui/lock_screen.py`, `ui/vault/unlock_dialog.py`, `ui/ghost.qss`)

- **Reusable Composite Component (`ui/widgets/password_input.py`)**:
  - Introduced `PasswordInputWidget`, unifying password input across the application with an integrated `👁️ / 🙈` eye toggle button.
  - Automatically handles echo mode transitions (`Password` ↔ `Normal`), tooltip updates, and seamless property forwarding (`text()`, `setText()`, `clear()`, `returnPressed`, `setFocus()`).
- **UI & Design System Unification**:
  - Refactored both `LockScreen` (application session gatekeeper) and `VaultUnlockDialog` (vault subsystem authenticator) to use the shared `PasswordInputWidget`.
  - Removed duplicated hardcoded inline stylesheets from `ui/lock_screen.py` and consolidated styling centrally in `ui/ghost.qss`.
- **Proportional Compact Sizing & Layout Polish**:
  - Eliminated excessive vertical dead space (~80px gap) between the password field and the action button on `LockScreen`.
  - Reduced `LockScreen` fixed height to 235px (290px in first-time setup mode) with optimized margins `(32, 22, 32, 22)` and spacing (`10px`).
  - Adjusted `VaultUnlockDialog` to a matching compact height of 265px for a cohesive, balanced design.

### Improved — Vault Backup Dialog Usability & Security Guidance (`ui/vault/backup_dialog.py`, `ui/ghost.qss`)

- **Transparent Security Education**:
  - Enhanced `VaultBackupDialog` with explicit cryptographic transparency informing users that `.vault` backup packages are encrypted with AES-256-GCM authenticated encryption and 100,000-round PBKDF2-HMAC-SHA256 key derivation.
  - Clearly enumerates all backed-up items (all secrets, 3-version history, categories, timestamps, expiration dates).
  - Prominent amber warning notice (`#VaultBackupWarnDesc`, `#e3b341`) stressing that backup passphrases cannot be recovered if lost.
- **Layout & Typography Fixes**:
  - Expanded dialog width from 460px to 520px.
  - Replaced single multiline label with dedicated individual `QLabel` widgets for each bullet item, resolving Qt text measurement clipping and overlap.

---

## [2.0.1] — 2026-10-01 — *Cerberus (Maintenance & Tiling WM Support)*

> **Codename:** Cerberus — Tiling Window Manager Support & Security Hardening Release
>
> This maintenance release introduces native EWMH cross-workspace migration for X11 window managers (verified against Qtile and Openbox; designed for EWMH-compliant WMs like i3, bspwm, etc.), fixes cross-workspace toggle hiding behavior, guarantees dialog modality across workspaces, hardens desktop notification action handling, refines The Vault drawer UX (secret prefill, memory scrubbing, leak prevention), refactors the dashboard architecture into a modular mixin (449 LOC, 0 Flake8 errors), fixes updater process relaunching, and expands the automated test suite to 489 passing tests.
>
> **Special Thanks:** Heartfelt thanks to **[@knodalyte](https://github.com/knodalyte)** for reporting GitHub Issue [#1](https://github.com/kareem2099/DotGhostBoard/issues/1) and providing crucial diagnostic feedback on tiling window manager behavior!

### Added — Tiling Window Manager & EWMH Migration (`core/window_manager.py`, `ui/window_utils.py`)

- **Cross-Workspace Window Migration (`core/window_manager.py`)**:
  - Pure Python + `ctypes` (`libX11.so.6`) implementation with zero external runtime dependencies.
  - Context-managed single X11 connection (`x11_connection`) with persistent `XSetErrorHandler` to prevent fatal crashes on transient X11 errors.
  - Direct reading and writing of `_NET_CURRENT_DESKTOP` and `_NET_WM_DESKTOP`.
  - Pager-priority ClientMessages (`source=2`) for mapped window desktop relocation and `_NET_ACTIVE_WINDOW` focus activation.
- **Workspace-Aware Toggle & Summon (`ui/window_utils.py`, `ui/dashboard.py`)**:
  - Added `is_on_current_workspace(widget)`: resolves the X11 limitation where Qt reports `isVisible() == True` even when mapped to an inactive workspace.
  - When summoning via global shortcut (`Ctrl+Alt+V`), Spotlight (`Ctrl+Alt+Space`), or CLI (`dotghostboard --toggle`), if the window is open on another workspace/group, it now migrates to the active workspace and focuses instead of erroneously hiding.
- **Modal Dialog Workspace Preparation (`ui/window_utils.py`, throughout UI controllers)**:
  - Added `prepare_dialog_for_current_workspace(dlg)` to set `_NET_WM_DESKTOP` before `dlg.exec()`.
  - Universally integrated across all modal dialogs: `LockScreen`, `UpdaterDialog`, `UpdateLogScreen`, `SettingsDialog`, `TagManagerDialog`, `PairingDialog`, `PurgeEasterEggDialog`, `VaultUnlockDialog`, `SecretDialog`, `ImageViewer`, and confirmation `QMessageBox` dialogs.
  - Guarantees background notifications and modal dialogs appear on the user's active workspace with intact Qt modal event loops.
- **Robust Headless Qtile Integration Fixture (`tests/fixtures/qtile_test_config.py`, `tests/test_window_manager.py`)**:
  - Added dedicated Qtile test configuration fixture explicitly defining numeric groups `1` through `9`, Max layout, and screen.
  - Decoupled `test_real_qtile_and_qt_integration` from Qtile's built-in `default_config` (which varied group schemes like `asdfuiop` across releases), ensuring stable cross-platform and CI E2E validation.
- **EWMH Kill Switch & CLI Documentation (`main.py`, `README.md`)**:
  - Added `DOTGHOST_NO_EWMH=1` environment variable to bypass EWMH handling for setups desiring default window manager behavior.
  - Added `--help` / `-h` CLI flag and documented all flags and environment variables in `README.md`.
- **Interactive Xephyr Testing Tool (`scripts/demo_qtile_xephyr.sh`)**:
  - Automated launcher running Qtile and DotGhostBoard in a nested Xephyr X11 display for live manual and visual verification.

### Fixed — Desktop Notifications & Action Callbacks (`core/notifications.py`)

- **Interactive Notification Click Activation**:
  - Fixed desktop notification action callback triggering window summon when notification is clicked.
  - Bounded action listener wait duration with a grace period (`min((timeout_ms / 1000.0) + 2.0, 15.0)`).
  - Explicit termination and zombie drainage (`proc.kill()` and `proc.communicate()`) on dismissal or timeout to prevent lingering background `notify-send` sub-processes.

### Fixed — The Vault UI & Memory Safety (`ui/vault/`, `core/services/security_service.py`)

- **Secret Editing UX (`ui/vault/vault_panel.py`)**:
  - Pre-fills current decrypted secret plaintext when opening the Edit Secret dialog (`_prompt_edit_secret`), enabling seamless updates without requiring users to type complex credentials from scratch.
- **Safe Clipboard Scrubbing (`ui/vault/vault_controller.py`)**:
  - Removed redundant `clipboard.setText("")` following `clipboard.clear()`, preventing spurious empty MimeData instances from triggering clipboard re-captures.
  - Ensured pending clipboard hash is reliably reset when scrub timer fires regardless of external clipboard state.
- **Signal Leak Prevention (`ui/vault/secret_card.py`, `ui/vault/vault_panel.py`)**:
  - Used `Qt.ConnectionType.UniqueConnection` for `vault_locked` signal bindings on secret cards to prevent duplicate event delivery.
  - Explicitly disconnected signals prior to widget destruction in `refresh_list()`, preventing dangling signal handlers from attempting memory scrubs on deleted Qt objects.
- **Modal Workspace Preparation (`ui/vault/vault_panel.py`)**:
  - Prepared `VaultUnlockDialog` and `SecretDialog` with `prepare_dialog_for_current_workspace()` to ensure they appear centered and focused on active tiling window manager groups.
- **Key Derivation Architecture Documentation (`core/services/security_service.py`)**:
  - Documented domain separation between Eclipse session key and Vault KEK in `set_session_key()`.

### Fixed — Updater Lifecycle & Shutdown (`ui/update_log_screen.py`, `ui/updater_dialog.py`, `ui/ghost.qss`)

- Fixed `UpdateLogScreen._restart_or_close` to cleanly terminate old application processes (`closeAllWindows()`, `quit()`, `sys.exit(0)`) and execute new binary/AppImage instances without lingering zombie processes.
- Enhanced updater dialog buttons with dynamic progress tracking (`⏳ Downloading... {percent}%`, `⚙️ Installing...`).
- Consolidated updater styling in `ui/ghost.qss`.

### Refactored — Architecture & Flake8 Compliance (`ui/dashboard.py`, `ui/dashboard_compat.py`)

- Extracted backward compatibility properties and coordination shims into `ui/dashboard_compat.py` via `DashboardCompatibilityMixin`.
- Reduced `ui/dashboard.py` to **449 lines** (strictly adhering to the $\le 500$ LOC architectural limit).
- Achieved **100% clean Flake8 compliance** (0 errors or warnings) across all modified and new files.

### Testing & Verification (`tests/test_window_manager.py`)

- Added 19 comprehensive tests covering X11 struct sizes, client message payloads, kill switches, mock parent ordering, and live `Xvfb` integration tests against real **Openbox** and real **Qtile 0.36.0**.
- Total test suite expanded to **489 passing tests (100% green)**.

---

## [2.0.0] — 2026-09-21 — *Cerberus (General Availability)*

> **Codename:** Cerberus — Stable / Production Release
>
> This major milestone completes the transformation of DotGhostBoard into a full-fledged cryptographic clipboard security station. Features include the dedicated encrypted Vault UI subsystem, zero-log password & secret detection with Shannon entropy analysis, memory-safe deduplication, system-native FreeDesktop desktop notifications with click activation, universal engine-level secure deletion, and a modern responsive 2.0.0 cyber-stealth icon architecture with 470 passing tests.

### Added — The Vault UI Subsystem (`ui/vault/`)

- **The Vault Drawer Panel (`ui/vault/vault_panel.py`)**:
  - Sliding / toggleable drawer panel integrated into the Dashboard central layout (`340px` fixed width, `#VaultPanel`).
  - Accessible via sidebar button (`🛡️ The Vault` with tooltips) and global hotkey `Ctrl+Shift+V`.
  - Dynamic status indicator (`🔒 Locked` / `🔓 Unlocked`), Lock toggle tool button, `+ Add` secret action, and `✕` close button.
  - Real-time search filtering across secret titles and category pills (`All`, `Pass`, `Token`, `Key`, `Note`, `Gen`).
  - Rich locked state banner with inline unlock CTA, and empty state prompt.
- **Vault Controller (`ui/vault/vault_controller.py`)**:
  - Standalone `QObject` mediating between `VaultService` envelope encryption and UI components.
  - Manages session lifecycle (`unlock`, `lock`, `add_secret`, `update_secret`, `delete_secret`, `reveal_secret`, `copy_secret`).
  - In-memory constant-time duplicate detection (`find_duplicate`) using `hmac.compare_digest` with zero plaintext hashes stored in `vault.db`.
  - Dispatches Qt signals: `vault_unlocked`, `vault_locked`, `secrets_changed`, `secret_revealed`, `secret_copied`, `status_message`, `panel_visibility_changed`.
- **Secret Card (`ui/vault/secret_card.py`)**:
  - Masked by default (`••••••••••••••••`) to protect against shoulder surfing.
  - Ephemeral in-memory reveal (`👁️ Reveal` / `🙈 Hide`) displaying decrypted plaintext in monospace emerald font.
  - Immediate scrubbing of plaintext upon session lock via `vault_locked` signal.
  - Disabled mouse selection (`NoTextInteraction`) on sensitive payload labels to prevent accidental clipboard pollution.
  - 1-click clipboard copy (`📋 Copy`) with visual feedback (`✓ Copied!`), Edit dialog trigger (`✏️`), and confirmation-guarded Delete (`🗑️`).
- **Master Password Unlock Modal (`ui/vault/unlock_dialog.py`)**:
  - Frameless modal dialog matching Eclipse lock aesthetics for master password authentication.
- **Add / Edit Secret Dialog (`ui/vault/secret_dialog.py`)**:
  - Dual-mode modal for creating and updating secrets with title validation, category selector, and encrypted payload textarea.
- **Dashboard Integration (`ui/dashboard.py`)**:
  - Strict preservation of architectural line limit: `ui/dashboard.py` remains at **494 lines** (≤ 500 LOC).
  - Integrated hotkey `Ctrl+Shift+V` and auto-locking synchronization when main session locks.
- **Testing**:
  - Added `tests/test_vault_ui.py` with 27 comprehensive unit and integration tests.

### Added — Send to Vault, Deduplication & Zero-Log Protection

- **Send to Vault Action (`ui/vault/send_to_vault.py`, `ui/widgets/item_card.py`)**:
  - Added direct 🛡️ "Send to Vault" button on text item cards and in context menus (`🛡️ Send to Vault...`).
  - Automatically prefills the `SecretDialog` with secret payload and focuses directly on the title input.
  - Abort safety: dialog cancellation preserves item in history without deletion.
  - Decrypts Eclipse-encrypted items on the fly before passing plaintext to the Vault.
  - In-memory deduplication interception: if plaintext already exists in the Vault, displays transient 4-second auto-dismiss "Already Secured" banner instead of creating duplicate cards.
  - Globally enforced `PRAGMA secure_delete = ON` on all SQLite database connections, zeroing content columns and verifying WAL truncation on deletion.
- **Zero-Log Automatic Secret & Password Protection (`core/security/detector.py`, `ui/widgets/secret_toast.py`)**:
  - Precision detection combining Shannon entropy ($\ge 3.0$), character class analysis, and strict regex patterns.
  - Comprehensive negative heuristics: excludes paths, environment variables (e.g. `$PWD`), code function calls, package namespaces, git branches, ISO timestamps, MAC addresses, SSH commands, and multiline files with incidental keyword occurrences.
  - Zero character leakage: fixed-length mask (`••••••••••••`) without exposing leading or trailing plaintext chars.
  - Zero-Loss Timeout Fallback: when 60s TTL expires without user action, candidate is automatically encrypted with Eclipse (`is_secret = 1`) into history rather than discarded.
  - System Tray notification when Dashboard window is hidden in tray mode.
  - Dynamic toggle in Settings (`Security -> Zero-Log Password Protection`) evaluated in real-time.

### Added — Native Desktop Notifications & 2.0.0 Brand Identity

- **Native FreeDesktop Linux Notifications (`core/notifications.py`)**:
  - Dispatches native OS notifications via FreeDesktop `/usr/bin/notify-send` and session D-Bus.
  - Includes click action callback (`-A default="Open DotGhostBoard"`) routed through a thread-safe Qt dispatcher (`_NotificationDispatcher`) to bring the window to the foreground upon click.
  - Graceful fallback to `QSystemTrayIcon.showMessage` if external notification daemon is unavailable.
- **2.0.0 Cyber-Stealth Icon & Asset Pipeline (`scripts/generate_icon.py`)**:
  - Replaced legacy 8-bit Pac-Man ghost with sleek, modern Cyber-Stealth Phantom glyph featuring glowing neon green visor (`#00ff41`) on dark graphite matte squircle.
  - Pure brand mark free of transient text or version numbers for long-term brand longevity.
  - Automated high-quality downsampling pipeline with Lanczos resampling, contrast boost, and unsharp masking for crispness down to 16px and 32px.
  - Generates full icon suite: `icon_16.png`, `icon_32.png`, `icon_48.png`, `icon_64.png`, `icon_128.png`, `icon_256.png`, `icon_512.png`, and `icon.png`.
  - Unified system tray integration in `ui/components/tray_manager.py` using `icon_32.png`.

### Quality, Architecture & Testing

- **Architectural Line Limit Preserved**: `ui/dashboard.py` strictly held to **494 lines** ($\le 500$ LOC limit) with zero semicolons.
- **470 Tests Passing (100% Green)**: Comprehensive unit, integration, and security test suite covering cryptographic isolation, raw disk byte overwrite verification, IPC, UI controllers, and notifications.

## [2.0.0-beta.2] — 2026-09-18 — *Cerberus*

> **Codename:** Cerberus — Phase 5 & 6 Architecture Refactoring & Multi-Channel Updates
>
> This pre-release completes the full decomposition of `ui/settings.py` and `ui/dashboard.py` (down to ≤ 500 lines) with dedicated UI components and controllers, introduces the multi-channel update system (Stable, Beta, Alpha), and achieves 389/389 passing tests.

### Added — Multi-Channel Update System

- **Channel-Aware Release Engine (`core/updater.py`)**:
  - Implemented update channel selection (`stable`, `beta`, `alpha`) in **Settings → General**.
  - Filter GitHub releases by channel: Stable users receive stable releases only; Beta users receive stable, beta, and RC builds; Alpha users receive bleeding-edge releases.
  - Robust version normalization supporting PEP 440 and hyphenated pre-release tags (`v2.0.0-beta.2` ↔ `v2.0.0b2`).
  - Seamless propagation from Settings UI → Dashboard → `UpdateController` → `UpdateCheckerThread` → `core.updater`.

### Architecture — v2.0.0 Cerberus (Phase 6: Dashboard Final Decomposition)

- **Phase 6A: Decomposed Dashboard UI Layout into Isolated Components (`ui/components/`)**:
  - `ui/components/sidebar.py`: `SidebarWidget` (160px width, collections list, 140px devices list, collection create signal, collapsed mode).
  - `ui/components/topbar.py`: `TopBarWidget` (56px height, logo, update notification button, real-time stats label, Eclipse session lock button, settings button, clear history button, responsive compact mode).
  - `ui/components/cards_view.py`: `CardsView` (QScrollArea container, card widget placement, visibility filtering, and Drag & Drop visual feedback emitting `card_reordered(dragged_id, target_card_id)` with zero DB calls).
  - `ui/components/bulk_toolbar.py`: `BulkToolbar` (coordinating `HintStrip` and `BulkBar` frames directly without layout parent reparenting conflicts, managing selection threshold ≥2 and emitting semantic action signals `pin_all_requested`, `delete_all_requested`, `export_requested`, `add_tag_requested`, `cancel_requested`, `hint_dismissed`).
  - `ui/components/tray_manager.py`: `DashboardTrayManager` (QSystemTrayIcon lifecycle, neon ghost icon rendering, retry visibility loop, dynamic context menu, tooltips based on lock/pause state).
  - `ui/components/__init__.py`: Clean re-exports for all 5 UI components.
- **Phase 6B: Bulk Actions & Selection State Extraction (`HistoryController`)**:
  - Moved multi-select selection state (`selected_ids`, `_last_clicked_id`), bulk actions (`bulk_pin`, `bulk_delete`, `bulk_export`, `bulk_add_tag`, `clear_selection`, `clear_unpinned_history`), keyboard navigation (`handle_key_press`, `set_card_focus`), card reordering (`on_card_reordered`), and limit enforcement (`enforce_history_limit`, `clean_old_captures`) into `HistoryController`.
  - Preserved original interaction contract: normal click sets keyboard focus without selection, Ctrl+click toggles selection, and Shift+click selects range based on visual card layout order (`_visible_cards()`).
- **Phase 6C: Network Sync & Pairing Orchestration (`SyncController`)**:
  - Moved `APIServerThread`, `DotGhostDiscovery`, `SyncEngine` configuration, and `PairingDialog` lifecycle into `SyncController`.
  - Emits clean semantic signals `api_text_received` and `sync_received_signal`.
- **Phase 6D: Update Lifecycle Extraction (`UpdateController`)**:
  - Created `ui/controllers/update_controller.py` containing `UpdateCheckerThread` and `UpdateController(QObject)`.
  - Manages GitHub release checking, notification badges, and updater dialogs independently.
- **Phase 6E & 6F: Auto-Lock & Session Orchestration (`SecurityController`) & Compatibility Shims**:
  - Moved auto-lock timer, idle timeout tracking, and `auto_lock_triggered` signal into `SecurityController` (with clean single-trigger delegation avoiding double-locking).
  - Streamlined `ui/dashboard.py` down from 1,536 lines to **493 lines** (achieving the target **≤ 500 lines**).
  - Preserved 100% backward compatibility for all 25+ public attributes/properties and legacy monkeypatch targets (`_start_api_server`, `_start_discovery`, `check_for_updates`, `sidebar`, `collections_list`, `devices_list`, `clear_btn`, `lock_btn`, `update_btn`, `stats_label`, `scroll`, `cards_container`, `cards_layout`, `_hint_strip`, `_bulk_bar`, `_bulk_count_lbl`, `tray`, `_cards`, `active_collection_id`, `_active_key`, `_selected_ids`, `_auto_lock_timer`, etc.).
- **Testing & Verification**:
  - Added `tests/test_dashboard_components.py` (23 unit tests), `tests/test_sync_controller.py` (8 unit tests), `tests/test_update_controller.py` (3 unit tests), and expanded `tests/test_history_controller.py` (including normal click focus verification) and `tests/test_security_controller.py` (including single auto-lock trigger verification).
  - Full test suite expanded from 322 to **357 passed tests** with 0 regressions.

### Architecture — v2.0.0 Cerberus (Phase 5: Settings Decomposition)

- **Decomposed Monolithic `ui/settings.py` (1,324 LOC)** into a clean, modular package (`ui/settings/`) and standalone components:
  - `ui/settings/__init__.py`: 100% backward-compatible Facade re-exporting `SettingsDialog`, `load_settings`, `save_settings`, `TagManagerDialog`, `SETTINGS_PATH`, `_DEFAULTS`.
  - `ui/settings/_io.py`: File-based JSON settings persistence and default settings isolated from UI logic.
  - `ui/settings/dialog.py`: Reduced from 1,324 lines to a clean **189-line orchestrator shell** that builds tabs and manages save lifecycle.
  - `ui/settings/pages/`:
    - `general.py`: General settings tab builder (`build_general_tab`) and embedded `AppFilterEditor` (whitelist/blacklist app filtering).
    - `security.py`: Eclipse & Security tab builder (`build_security_tab`) and standalone password lifecycle functions (`setup_master_password`, `remove_master_password`, `refresh_eclipse_pw_ui`).
    - `api.py`: Local REST API configuration builder (`build_api_tab`).
    - `about.py`: About & system information tab builder (`build_about_tab`).
  - `ui/tag_manager.py`: Standalone `TagManagerDialog` extracted into an independent module.
- **Zero Regressions & Full Backward Compatibility**:
  - All existing callers (`ui/dashboard.py`, `ui/pairing_dialog.py`, tests) continue working without changes.
  - Test suite expanded from 306 to **322 tests** (+16 new tests in `tests/test_settings.py` covering backward-compatibility, `_io`, `AppFilterEditor`, tab builders, and password UI helpers).
  - All 322 tests passing with 0 regressions.

---

## [1.6.0] — 2026-09-16 — *Phantom*

> **Codename:** Phantom — Full v2.x Architecture Foundation
>
> This release completes the modular refactoring of DotGhostBoard's entire core and UI layer.
> Zero user-facing behavior changes. 306/306 tests passing.

### Architecture — v2.x Foundation (Phases 1–4)

#### Phase 1–3: Core Decomposition

- **Storage Engine Modularization (`core/storage/`)** — Decomposed the monolithic 1,100-line `core/storage.py` into a clean, decoupled package:
  - `database.py`: Context-managed SQLite connection layer with dynamic test path getters.
  - `migrations.py`: Versioned migration engine with legacy schema adoption, downgrade protection, and transactional rollbacks.
  - `repositories/clips.py`: CRUD, image deduplication, AES-256-GCM encryption, secure deletion, bulk operations.
  - `repositories/tags.py`: Tag extraction, normalization (`#tag`), global rename/delete.
  - `repositories/collections.py`: Categorization, item counts, unlink on delete.
  - `repositories/peers.py`: Trusted device credentials for LAN sync.
  - `repositories/stats.py`: Optimized metrics queries.
  - `__init__.py`: 100% backward-compatible facade — zero caller changes required.
- **Clipboard Pipeline & Backend Abstraction (`core/clipboard/`)** — GUI-independent decision pipeline with pluggable backends:
  - `events.py`: Frozen dataclasses (`ClipboardEvent`, `CaptureDecision`) and `Action` enum (`SAVE_NORMAL`, `IGNORE`, `SECRET_CANDIDATE`).
  - `pipeline.py`: Pure policy engine (validation → app filter → paranoia → secret detection → accept).
  - `backend.py`: `ClipboardBackend` Protocol — ready for Wayland (`wlr-data-control`) backends.
  - `backends/qt_backend.py`: Extracted Qt polling backend with hot-swap lifecycle.
  - `core/watcher.py`: Re-architected as Orchestrator delegating to Backend + Pipeline.
- **Service Layer (`core/services/`)** — Qt-free business logic boundaries:
  - `history_service.py` (`ClipService`): Pagination, search, tag manipulation, pin toggling, copy thresholds (`PIN_SUGGESTION_THRESHOLD = 5`, `AUTO_PIN_THRESHOLD = 10`), cleanup, export.
  - `collection_service.py`: Collection management, validation, item categorization.
  - `security_service.py`: Master password lifecycle, atomic password rotation (re-encrypts Eclipse items + re-wraps Vault DEK), safe removal guard.
  - `sync_service.py`: Peer trust coordination and broadcast delegation.
- **Security Domain (`core/security/`, `core/crypto.py`):**
  - HKDF-SHA256 domain-separated key derivation (`derive_key` vs `derive_vault_key`).
  - `secure_zero()` for best-effort in-memory key scrubbing.
  - `SecretDetector`: Sub-millisecond regex heuristics for SSH keys, GitHub tokens, AWS keys, JWTs, and high-entropy strings.
  - `vault/`: Physical database isolation (`vault.db`) with DEK/KEK envelope encryption enabling instant password rotation without re-encrypting vault items.

#### Phase 4: Dashboard Decomposition

- **Four Behavioral `QObject` Controllers (`ui/controllers/`)** — Decomposed the 2,353-line monolithic `Dashboard` class into focused, injection-based controllers:
  - `CollectionController`: Sidebar management, drag-and-drop targeting, collection CRUD dialogs, active filter state.
  - `SecurityController`: Session lock/unlock lifecycle, secret copy resolution, card-level Eclipse encrypt/decrypt — no direct widget manipulation.
  - `SyncController`: Peer list UI, pairing dialog invocation, device status styling, outbound broadcast.
  - `HistoryController`: Card lifecycle, infinite scroll pagination, debounced search & tag filtering, pin/copy/delete slots, signal wiring via `_connect_card_signals()`.
- **`PinSuggestionToast`** extracted into `ui/widgets/pin_toast.py`.
- **Dashboard reduced by 818 lines** (2,353 → 1,535 lines). Zero direct `storage.*` or `crypto.*` calls remain in `ui/dashboard.py`.
- **Strict signal boundaries enforced:**
  - Clipboard sync fires **only** from `watcher.new_text_captured` → `sync_controller.broadcast_text`. Manual copy never triggers sync.
  - Secret copy: `history_controller.secret_copy_requested` → `security_controller.handle_secret_copy` → `copy_payload_ready` → paste.

### Bug Fixes & Internal Quality

- **Encapsulation fix** (`SecurityService.set_session_key()`): `SecurityController` now uses a proper public API instead of directly mutating `_active_key` / `_is_locked` private attributes.
- **N-query fix** (`CollectionService.get_collection()`): Direct `get_collection_by_id()` DB lookup instead of fetching all collections and filtering in Python.
- **N+1 connection fix** (`clean_old_captures()`): Consolidated per-row `DELETE` statements into a single `DELETE WHERE id IN (...)` bulk transaction.
- **DRY fix** (`HistoryController._connect_card_signals()`): Extracted duplicated 9-line signal-wiring block into a shared helper used by both `add_card()` and `refresh_item()`.

### Test Coverage

- Test suite expanded from 220 → **306 passing tests** across 25 test modules.
- New test modules: `test_clipboard_pipeline`, `test_watcher_backend_integration`, `test_collection_controller`, `test_security_controller`, `test_sync_controller`, `test_history_controller`, `test_dashboard_coordination`, `test_crypto_domain`, `test_secret_detector`, `test_vault`, `test_services`, `test_storage_contract`.

---


## [1.5.7] — 2026-09-13 — *Nexus Hotfix V*

Critical packaging and CI headless stability hotfix: ensures `dotghost` CLI runtime dependencies are met across Debian and Arch, resolves Qt6/xcb CI headless crashes, and refines release automation pipelines.

### Fixed & Improved

- **CI / Headless Stability (`.github/workflows/tests.yml`, `tests/test_ipc_spotlight.py`)** — Fixed PyQt6 / xcb fatal abort (`SIGABRT / exit code 134`) on headless runners by installing `libgl1`, `libxkbcommon0`, `libxkbcommon-x11-0`, and `libxcb1`, while defaulting test executions in headless/CI environments to `QT_QPA_PLATFORM=offscreen`.
- **Packaging Dependencies (`scripts/build_deb.sh`, `scripts/build_arch.sh`)** — Added explicit `python3` dependency to `.deb` package (`DEBIAN/control`) and `python` to Arch package (`.PKGINFO` and `PKGBUILD`) to guarantee the `/usr/bin/dotghost` Python CLI companion has a system interpreter available.
- **CLI Companion Polish (`cli/dotghost.py`)** — Added `--help` / `-h` command-line flags, standardized terminal confirmation prints, and automatic detection/cleanup of stale UNIX socket endpoints.
- **Release Automation Alignment (`scripts/sign_and_upload.sh`)** — Unified release asset filenames and patterns (`*.pkg.tar.*`) to precisely match builder artifacts and SHA256 checksums.

---

## [1.5.6] — 2026-09-13 — *Nexus Global Hotkeys & UI Polish*

Per-user global desktop shortcuts (`Ctrl+Alt+V`, `Ctrl+Alt+Space`), decoupled floating Spotlight search overlay, Eclipse Lock security protection for quick search, major visual styling & typography overhaul, modular UI widgets architecture, and comprehensive test suite expansion to 219 passing tests.

### Added

- **Per-User Global Desktop Shortcuts (`core/shortcuts.py`)** — Added native desktop shortcuts for the logged-in user on GNOME (`gsettings`) and XFCE (`xfconf-query`):
  - `Ctrl+Alt+V`: Toggles DotGhostBoard main window visibility (show / hide) from any application.
  - `Ctrl+Alt+Space`: Opens the standalone floating Spotlight quick search overlay from any application.
  - Features intelligent desktop environment detection (`detect_desktop`), secure zero-`eval` parsing of GSettings lists (`ast.literal_eval`), multi-target command launcher resolving AppImage (`$APPIMAGE`), PyInstaller binary, and source virtualenv with `shlex.join()`.
- **Decoupled Spotlight Quick Search (`ui/spotlight.py`, `ui/dashboard.py`)** — Standalone floating search overlay accessible globally without opening or raising the main window. Features screen centering, real-time debounced search, keyboard navigation (`Up`/`Down`/`Enter`), and instant clipboard copy.
- **Single-Instance IPC Messaging (`main.py`)** — Extended local UNIX socket IPC server to support `--spotlight` (`-s`) and `--toggle` (`-t`) arguments, routing commands directly to the running instance without restarting or launching duplicate instances.
- **CLI Companion Subcommands (`cli/dotghost.py`)** — Added `dotghost spotlight` and `dotghost toggle` commands for terminal-driven workflows and custom window manager keybindings.
- **In-App Global Shortcut Configuration (`ui/settings.py`)** — Added `[ Configure Global Shortcuts ]` button in Settings → General with live desktop feedback banner and keybind legend for `.deb`, AppImage, and source installs.
- **In-Dashboard Search Shortcut (`ui/dashboard.py`)** — Added `Ctrl+F` shortcut inside Dashboard to quickly focus and select the search query input.
- **Modular UI Widgets Package (`ui/widgets/`)** — Split monolithic `widgets.py` into focused, maintainable modules (`item_card.py`, `stats_header.py`, `tag_chip.py`, `tag_input.py`, and `helpers.py`).
- **Comprehensive Test Suite Expansion (`tests/`)** — Added `tests/test_ipc_spotlight.py`, `tests/test_autostart.py`, and `tests/test_runtime_dir.py`, expanding the test suite to 219 passing tests.

### Security & Privacy

- **Eclipse Lock Protection for Spotlight (`ui/dashboard.py`)** — `show_spotlight()` strictly enforces Master Password authentication when Eclipse mode is locked. If unlocked via Spotlight, only Spotlight is presented—the main dashboard remains hidden and protected behind the lock screen.
- **Automatic Background Worker Re-arming** — Unlocking Eclipse on instances launched with `--startup` now automatically initializes the clipboard watcher, local REST API, mDNS peer discovery, and sync engine.
- **Safe GSettings Parsing** — Replaced insecure string evaluations with `ast.literal_eval` and safe `@as []` prefix stripping in shortcut detection.

### Changed & Polished

- **Modern Typography & Aesthetic Overhaul (`ui/ghost.qss`)**:
  - Replaced global monospace font with clean, modern sans-serif typography (`Inter`, `Noto Sans`, `Segoe UI`) across all headers, buttons, inputs, and dialogs. Monospace is preserved exclusively for item text, code blocks, and command-line snippets.
  - Refined slate & muted dark-green palette (`#0f1411`, `#151c17`, `#1d2820`, `#2bbf5c`, `#77dd98`) with subtle borders and smooth hover states.
  - Standardized `ItemCard` padding (14px / 10px) and compacted action buttons to 26×26px for enhanced information density.
  - Re-themed `PinSuggestionToast` and `New Update!` notification banner with the new muted palette.
  - Converted Settings dialog styling to reusable QSS classes (`SettingsDialog`, `SettingsTitle`, `SettingsSaveBtn`, `SettingsCancelBtn`).
- **Resolved Shortcut Collision** — Removed conflicting `Ctrl+Shift+F` window shortcut to prevent collision with IDEs and code editors (e.g., VS Code Global Search).
- **Resilient Installer Script (`scripts/install.sh`)** — Made shortcut setup non-fatal, allowing clean installations on custom or minimal desktop environments without aborting the install pipeline.
- **Profile Isolation (`cli/dotghost.py`)** — CLI now honors `DOTGHOST_HOME` environment variable for isolated profiles and testing.

### Fixed

- **Desktop Detection False Positives** — Fixed issue where XFCE environments with `gsettings` installed were mistakenly identified as GNOME.
- **Path Escaping with Spaces** — Fixed launch command generation using `shlex.join()` so executable paths containing spaces work reliably.
- **XFCE Keybind Idempotency** — Prevented duplicate or conflicting shortcut entries in `xfconf-query`.
- **System Tray Window Toggle** — Fixed tray icon click handler to toggle window visibility cleanly between active and minimized/hidden states.

---

## [1.5.5] — 2026-08-05 — *Nexus Polish & Spotlight*

UI state intelligence, quick Spotlight search overlay, relative time formatting, copy count reset, image deduplication, and search input debouncing.

### Added

- **Spotlight Quick Search Overlay** (`ui/spotlight.py`) — Frameless floating search popup accessible from the Dashboard via `Ctrl+Shift+F`. Provides real-time search, keyboard navigation (`Up`/`Down`/`Enter`), and instant copy/paste. Encrypted secret items are masked with `🔒 Secret Item (Encrypted)` preview for privacy.
- **Master Password Prompt for Secret Copying** (`ui/dashboard.py` — `_on_copy`) — Prompting for Master Password using `LockScreen` before copying secret items, decrypting content in-memory for pasting without saving plaintext back to DB or re-capturing as unencrypted cards.
- **Image SHA-256 Deduplication** (`core/storage.py` — `_get_file_hash`, `add_item`) — Identical image captures/screenshots are deduplicated via SHA-256 checksums, automatically moving the existing image card to top and incrementing `copy_count` while purging duplicate temporary files.
- **Search Input Debouncing** (`ui/dashboard.py`, `ui/spotlight.py`) — Added 200ms (Dashboard) and 150ms (Spotlight) `QTimer` search input debounce to prevent unnecessary SQL execution and UI rebuilds during rapid typing.
- **Dashboard Stats & State Header** (`ui/widgets.py` — `StatsHeaderCard`, `core/storage.py` — `get_today_stats`) — Live status bar banner displaying Today's Captures, Top Copied Clip created today (excluding secrets), and Pinned Items Count.
- **Relative Timestamp Formatting** (`ui/widgets.py` — `_format_time`) — Human relative timestamps ("just now", "5m ago", "2h ago", "3d ago") with a 60-second background `QTimer` UI refresh.

### Fixed

- **Duplicate `closeEvent` Method Override** (`ui/dashboard.py`) — Merged duplicate `closeEvent` definitions into a single method to restore system tray minimization on window close (`X`), `clear_on_exit` cleanup, and graceful thread shutdown.
- **Self-Paste Re-capture Prevention** (`core/watcher.py` — `_check_clipboard`) — Fixed `_last_content` update on self-paste to prevent app-pasted text/decrypted secrets from being re-captured as new cards in the DB.
- **`reset_copy_count` Return Type** (`core/storage.py`) — Updated `reset_copy_count(item_id)` to return `bool` (`True` when item count is reset, `False` when item is not found), with UI handling in Dashboard status bar.

---

## [1.5.4] — 2026-08-05 — *Nexus Hotfix IV*


Clipboard reliability fix + copy intelligence feature.
Resolves a 3-layer bug where repeated copies of the same text would silently stop being captured.
Introduces **Copy Count Badge** and **Auto-Pin Suggestion** for frequently-used items.

### Fixed

- **Clipboard capture stopping on repeated copies** — Three compounding root causes were identified and resolved:
  - **`core/storage.py` — `add_item()` silent no-op on duplicate:** When the same content already existed in the DB, `add_item()` returned the old ID without updating `updated_at` or emitting any signal, causing the UI to never refresh. Fixed to do a **"Move to Top"** (`UPDATE updated_at = NOW, copy_count += 1`) so the card floats up and the watcher signal fires correctly.
  - **`core/watcher.py` — self-paste blocks re-copy:** After the app pasted an item back to clipboard via the ⎘ button, `_is_self_paste` was cleared but `_last_content` still held the old text. Any subsequent manual copy of that same text would be silently skipped. Fixed by resetting `_last_content = None` on self-paste, allowing immediate re-capture.
  - **`ui/dashboard.py` — `_add_card()` ignores existing cards:** When the watcher emitted a signal for an already-seen item, `_add_card()` returned early without moving the card to the top of the list. Fixed to `removeWidget()` + `insertWidget(0, ...)` when `at_top=True`.

### Added

- **Copy Count Badge** (`ui/widgets.py`) — A pill badge on each `ItemCard` showing how many times the item has been copied. Hidden for first copies; appears from `×2` onwards with color tiers:
  - `↩ ×2–4` — Muted teal (mild)
  - `♻ ×5–9` — Orange (warm)
  - `🔥 ×10+` — Gold/red (hot)
  Badge updates live via `update_copy_count(count)` without rebuilding the card.

- **`copy_count` DB column** (`core/storage.py`) — New `INTEGER DEFAULT 0` column on `clipboard_items`. Automatic `ALTER TABLE` migration for existing databases. `add_item()` sets `copy_count = 1` on insert and increments on re-copy. New `increment_copy_count(item_id) → int` function for copy-button presses.

- **Pin Suggestion Toast** (`ui/dashboard.py` — `PinSuggestionToast`) — Non-blocking toast overlay at the bottom-left of the window, triggered when an item reaches `×5` copies. Shows item preview, a **Pin It** button and a **Dismiss** button. Auto-dismisses after 6 seconds.

- **Auto-Pin at ×10** (`ui/dashboard.py` — `_check_pin_suggestion()`) — Items copied 10 or more times are automatically pinned with a status bar notification: `📍 Auto-pinned! Copied ×10 times — keeping it safe.`

- **Badge + suggestion on keyboard copy** (`ui/dashboard.py` — `_on_new_text/image/video()`) — Badge refresh and pin suggestion now trigger for all copy paths (keyboard `Ctrl+C` via watcher, not just the ⎘ button in the UI).

---

## [1.5.3] — 2026-04-16 — *Nexus Hotfix III*

Critical rendering fix — resolves the blank/white window that appeared in **GitHub-built** `.deb` and AppImage releases.

### Root Cause
The GitHub Actions workflow (`.github/workflows/build.yml`) was missing `--add-data "ui/ghost.qss:ui"` from both the AppImage and DEB build steps. The local build scripts (`scripts/build_deb.sh`, `scripts/build_appimage.sh`) had it correctly, which is why local builds always worked. GitHub builds shipped without the stylesheet file entirely.

### Added
- **`core/paths.py`** — New `resource_path(*parts)` helper as a defensive measure that resolves bundled asset paths correctly in both dev and frozen (PyInstaller `sys._MEIPASS`) environments.

### Fixed
- **`.github/workflows/build.yml`** — Added `--add-data "ui/ghost.qss:ui"` to both the `linux-appimage` and `linux-deb` build steps. This was the actual cause of the white/unstyled window in all published GitHub releases.
- **`ui/dashboard.py`** — Switched `QSS_PATH` and tray icon path to use `resource_path()` as a secondary fix, making the code robust against this class of bundling bugs in the future.

---

## [1.5.2] — 2026-04-16 — *Nexus Hotfix II*


Stability & UX polish release — secures the update pipeline, adds a cinematic "Aura Check" easter egg for Clear History, and fixes database migration regressions.

### Added
- **Aura Check easter egg** — `_clear_history()` in `ui/dashboard.py` now requires the user to pass a two-stage confirmation: a styled `QMessageBox` Aura Check dialog (`QMessageBox.StandardButton.No` as default), followed by the Pigeon Doctor cinematic overlay.
- **Pigeon Doctor Purge Screen** (`ui/purge_easter_egg.py`) — Frameless, dark full-window overlay playing `pigeon_boss.gif` with a cinematic timeline: fade-in at `t=0`, DB purge fires in a `QThread` at `t=600ms`, sub-caption flips to `✓ Purge Complete` at `t=700ms`, fade-out at `t=2200ms`, dialog closes at `t=2700ms`. Purge is guaranteed complete via `worker.wait()` before `accept()`.
- **`get_asset_path(filename)`** in `core/config.py` — Bulletproof asset resolver that works in dev mode, PyInstaller bundles (`sys._MEIPASS`), and AppImage/DEB installs. Points to `data/assets/` relative to the project root.

### Fixed
- **Update directory security** — `core/updater.py` now saves downloaded `.deb`/`.AppImage` files to `~/.local/share/dotghostboard/updates/` instead of `/tmp/`, preventing TOCTOU attacks and surviving cross-session updates.
- **Self-cleanup after install** — The generated install script now removes both the downloaded asset and itself after `pkexec` completes, leaving no stale files.
- **`pkexec` error handling** — `ui/updater_dialog.py` now catches non-zero exit codes from `pkexec` and shows a user-friendly error dialog instead of silently failing or crashing.
- **Database migration regression** — `core/storage.py` migration guard (`PRAGMA user_version`) now correctly handles databases upgraded from v1.4.x without re-running migrations on clean v1.5.x installs.
- **Theme inconsistency hotfix** — QSS rules for `ItemCard` states (`focused`, `selected`, `droptarget`) are now applied consistently after stylesheet reload in `_load_stylesheet()`.

---

## [1.5.0] — 2026-04-13 — *Nexus*

The Sync & Connectivity release — introduces secure local network clipboard synchronization, a REST API for programmatic access, a CLI companion, and a secure device pairing system.

### Added
- **Local Network Sync (v1.5.0 flagship)** — End-to-End Encrypted (E2EE) clipboard synchronization between devices on the same network using AES-256-GCM and per-peer shared secrets.
- **mDNS Device Discovery** — Automatic zero-configuration discovery of other DotGhostBoard instances on the local network using Zeroconf (mDNS).
- **Secure Pairing Handshake** — X25519 (ECDH) based key exchange protected by a 6-digit PIN and dynamic salts, ensuring safe pairing even on public Wi-Fi.
- **REST API** — Background server (`core/api_server.py`) providing programmatic clipboard access. Includes endpoints for history retrieval, manual item pushing, and device pairing.
- **CLI Companion (`dotghost`)** — Command-line interface for pushing and popping clipboard data, integrated with the local API.
- **Sync Engine** — Multi-threaded background engine for pushing new captures to all trusted peers without blocking the main UI thread.
- **Rate Limiting & Security Hardening** — Integrated IP-based rate limiting (3 attempts/min) for pairing endpoints and dynamic salt generation for all handshakes.

### Fixed
- **API Server reachability** — Shifted server binding from `127.0.0.1` to `0.0.0.0` to enable cross-device communication.
- **Handshake Race Conditions** — Improved UI synchronization between the server thread and the pairing dialog to handle asynchronous key verification.
- **Resource Cleanup** — Ensured all background discovery and API threads are gracefully terminated on application exit.

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
- **About tab** — `ui/settings.py` `_build_about_tab()` with logo, version v1.4.0 Eclipse, author FreeRave, Apache 2.0 license, system info (Python/PyQt6/Qt/Platform/Arch), and social links organized in sections (Project, Articles, Social, Videos, Facebook)
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