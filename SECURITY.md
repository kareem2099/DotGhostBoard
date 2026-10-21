# Security Policy

## Supported versions

Only the latest stable release receives security fixes. As of 21 October 2026,
that release is **v2.1.4**. When a new stable release is published, update to it.

| Version | Security maintenance |
| --- | --- |
| v2.1.4 (latest stable) | Supported |
| Earlier versions | Upgrade to the latest stable release |

## Reporting a vulnerability

Please report security vulnerabilities privately to **kareem209907@gmail.com**.
Do not include working passwords, API tokens, personal clipboard history, or a
real Vault database in public issues or reports.

Include the affected version and installation format, operating system, reproduction
steps, expected impact, and a minimal example using synthetic data. The maintainer
aims to acknowledge reports within 48 hours; investigation and fixes depend on severity
and reproducibility. Coordinate public disclosure after a fix is available.

## Storage and encryption

DotGhostBoard stores data locally in separate SQLite databases:

- **Dashboard (`ghost.db`):** ordinary clipboard history is not encrypted by default.
  Eclipse-protected items use AES-256-GCM with a password-derived session key.
- **Vault (`vault.db`):** a random 256-bit data key encrypts secrets, titles,
  categories, expiry, and secret history with AES-256-GCM. Authentication binds
  encrypted records and history to their IDs. Database structure, counts,
  timestamps, and ciphertext lengths remain visible; this is not full-file encryption.
- **Dashboard password:** PBKDF2-HMAC-SHA256 with 600,000 iterations and a random
  32-byte profile salt derives the session key. Authentication decrypts a known
  verifier with that key; it is not a plain salted SHA-256 password hash.
- **Shared Vault password (default):** an HKDF-SHA256 key derived from the Dashboard
  session key wraps the Vault data key. Vault idle-lock does not provide independent
  cryptographic protection from an unlocked Dashboard session.
- **Independent Vault password (optional):** Argon2id with 64 MiB memory, three
  passes, one lane, and a random 16-byte salt protects the Vault key without a
  Dashboard-key fallback. Password separation is not multifactor authentication.

New passwords and backup passphrases require at least 12 characters. Legacy
credentials remain readable. The [security model](docs/security-model.md) documents
the implementation, migration rules, remaining visible metadata, and memory limits.

## Network behavior and privacy

The application has no built-in analytics or telemetry service. It does make
network connections for the following features:

- Update checks contact GitHub Releases; installing an update downloads its asset.
- Enabled Nexus discovery and pairing exchange local-network device information;
  paired clipboard sync encrypts text sent between trusted peers.
- The optional API listens on its configured port on all IPv4 interfaces
  (`0.0.0.0`), rather than only loopback. Dashboard API requests require its Bearer
  token; pairing and peer sync use their separate PIN/trust mechanisms.

Vault databases are not synchronized by the Dashboard LAN sync feature. Recovery
writes encrypted files to the chosen folder; the app does not itself provide cloud
backup hosting. External software synchronizing that folder has its own network behavior.
Review update and API/network settings when controlling connectivity.

## Locks, backups, and recovery

Dashboard auto-lock is optional and disabled by default. Vault idle-lock is separate.
Normal clipboard capture initializes Vault secret recognition before resuming;
recognized Vault values and imported CSV password components are excluded from
Dashboard capture. A locked Vault retains a process-local keyed recognition index. After the first
successful authentication in a process, Dashboard locking also keeps protected local
capture active while clearing decryption keys and hiding Dashboard/Spotlight. API and
LAN sync stop while locked. Suspected new secrets are excluded without plaintext
fallback or a review popup; unlock and copy again to review. Capture stays stopped
before initial authentication or when explicitly paused. Unavailable membership checks
never authorize a save.

New `.vault` exports and `.dgb-recovery` archives use authenticated AES-256-GCM
encryption and Argon2id passphrase protection. Recovery requires a readable archive
and its backup passphrase. It cannot reconstruct data after every usable copy is lost.
Scheduled recovery work requires the application and Vault to be unlocked.

For a complete profile backup, close the application and preserve the whole profile
directory, including `ghost.db`, `vault.db`, `eclipse.salt`, `eclipse.verify`, and any
recovery configuration. Never mix credential and database files from different
profile states. A readable encrypted export or recovery archive can instead restore
Vault contents independently of those original files.

Legacy Vault records migrate after successful unlock. Older application versions
cannot open the upgraded schema. Preserve a consistent pre-upgrade copy if a
downgrade is needed. See the [recovery guide](docs/vault-recovery.md) for selection,
retention, restoration, and backup failure behavior.

## Scope and security checks

Encryption protects stored authenticated payloads, not a compromised or fully
unlocked device. Malware, debuggers, screenshots, swap, and other applications with
clipboard access can expose plaintext. Key clearing is best effort in Python/Qt.
Use an appropriate device security policy and a strong, unpredictable passphrase.

The project uses pytest regression coverage, GitHub Actions, CodeQL, Dependabot
security updates, and GitHub secret scanning with push protection. These checks
are not an independent security audit or a guarantee against every attack.

The v2.1.4 release tag and commit are OpenPGP-signed. Its official Linux builds
include SHA-256 checksums and detached OpenPGP signatures. Match the signing
fingerprint in the release notes and verify signatures and checksums before installing.
