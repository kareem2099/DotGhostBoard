# 🗺️ DotGhostBoard Roadmap — v2.x

> **Project:** DotGhostBoard  
> **Author:** FreeRave / DotSuite  
> **Created:** 2026-04-14

---

## 🧱 Principles for v2.x

- 🛡️ **Zero-Trust Local** — No data leaves the machine. Secrets are fully isolated.
- 🧠 **Regex-Brained** — Pattern-based intelligence (Heuristics), no heavy AI models — stays lean on RAM.
- 🚀 **Wayland Ready** — Full support for modern Linux environments.
- 🎨 **DotSuite Consistency** — Refining the Dark Neon aesthetic with fluid animations.

---

## 📅 v2.0.0 — Cerberus `[Planned]`

> **Goal:** The Password Vault & Secret Detection

### Features
- **The Vault:** An isolated, encrypted side-panel protected by a separate Master Password (Zero-Knowledge). Stored in a dedicated `vault.db`, completely separate from `ghost.db`.
- **Smart Secret Detection (Regex):** Pattern-based detection for API Keys, Tokens, and high-entropy strings — not keyword matching. Prompts the user: *"Move to Vault?"*
  ```
  Patterns: JWT, AWS keys (AKIA...), GitHub tokens (ghp_...), hex secrets (32-64 chars), high-entropy strings
  ```
- **Auto-Clear:** Automatically wipes a password from the regular clipboard 30 seconds after pasting from the Vault.
- **Zero-Logging Mode:** A "Paranoia Mode" toggle that temporarily prevents any new items from being written to the DB.

---

## 📅 v2.1.0 — Leviathan `[Planned]`

> **Goal:** Architecture & Modern Linux Support

### Features
- **Wayland Native:** Full clipboard monitoring for modern Wayland compositors (Hyprland, Sway, GNOME Wayland) via `wlr-data-control`.
- **Global Search Overlay:** A spotlight-like popup (similar to KRunner) for searching and pasting directly without opening the main dashboard.
- **System Tray Mini-Dash:** Quick-access panel from the tray for the Vault and recent items.
- **Code Syntax Highlighting:** Auto-detected language highlighting for code snippets directly in the cards.

---

## 📅 v2.2.0 — Chimera `[Planned]`

> **Goal:** Local OCR & Smart Actions (No AI Bloat)

### Features
- **Local OCR:** Text extraction from saved images using Tesseract — lightweight and fully offline. Extracted text is instantly searchable.
- **Regex Smart Actions:** Context buttons that appear based on content pattern — `Ping` if an IP is detected, `Format JSON` for valid JSON, `Open Link` for URLs.
- **Auto-Tagging (Rules-based):** Tags like `#link`, `#crypto`, `#code` assigned by pattern matching, not NLP.
- **Image Compression:** Configurable auto-compression for heavy image payloads before saving.

---

## 📅 v2.3.0 — Oracle `[Planned]`

> **Goal:** Predictive UX — Always one step ahead

### Features
- **Scheduled Self-Destruct:** Ephemeral items that vanish after a set number of pastes or after X minutes.
- **Workflow Automation:** Run scripts or fire webhooks when a specific clip is matched (e.g., *if regex matches an Error Log, auto-open a StackOverflow search*).
- **Context-Aware Pasty:** Surfaces the most relevant clip based on the active window (passwords near login screens, code near IDEs) — driven by window class detection, no AI.

---

*DotSuite v2 — Ghosting boundaries, securely.* 👻