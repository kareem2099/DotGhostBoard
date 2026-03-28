# 🛡️ Security Policy

## Supported Versions

We take the security of **DotGhostBoard** and the **DotSuite** ecosystem seriously. Currently, only the latest stable release receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| v1.4.x  | ✅ YES (Current)    |
| < v1.4.0| ❌ NO               |

---

## Security Philosophy (Eclipse Mode)

DotGhostBoard follows a **Zero-Cloud, Zero-Trust** local-first security model:
- **Local Storage:** All clipboard data is stored in a local SQLite database (`ghost.db`).
- **Eclipse Encryption:** Sensitive items are encrypted using **AES-256-GCM** (via Python's `cryptography` library).
- **No Telemetry:** The app does not connect to the internet. No data ever leaves your machine.
- **Master Password:** Session locking uses a salted SHA-256 hash to verify access without storing the actual password.

---

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

If you discover a security hole or a way to bypass the **Eclipse Master Lock**, please report it responsibly:

1. **Email:** Reach out directly to the maintainer at `kareem209907@gmail.com`.
2. **Details:** Include a detailed description of the vulnerability, steps to reproduce, and a Proof of Concept (PoC) if possible.
3. **Response:** You will receive an acknowledgment within **48 hours**. 
4. **Disclosure:** We ask that you do not disclose the issue publicly until a fix has been released.

---

## Best Practices for Users

To keep your clipboard data secure, we recommend:
- **Enable Master Lock:** Set a strong Master Password in settings.
- **Auto-Lock:** Configure the "Auto-lock on idle" timeout to prevent unauthorized access when you are away.
- **Database Backup:** If you manually back up `ghost.db`, ensure the backup location is also encrypted.
- **Clear on Exit:** For maximum privacy, enable "Clear unpinned on exit" in the Privacy settings.

---

## Security Tooling

We use the following tools to ensure the codebase stays clean:
- **Pytest:** Over 160+ tests covering encryption and storage logic.
- **Bandit:** Used for static analysis to find common security issues in Python code.
- **Safety:** Checks dependencies for known vulnerabilities.

---

*Thank you for helping keep the DotSuite ecosystem secure!* 💀🛡️