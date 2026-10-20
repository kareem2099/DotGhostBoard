# Vault security model (v2.1.3, prepared locally)

This describes the current source, including changes made after the published
v2.1.2 packages. Updating this document does not update those packages. No claim
of an independent security audit or protection against every attack is made.

## Encryption and password modes

Vault records use AES-256-GCM with a random 256-bit data encryption key (DEK),
random 96-bit nonces, and 128-bit authentication tags. Titles, categories, expiry,
and secret content live in the encrypted record payload. Previous secret values
are separately encrypted. Authenticated associated data binds each payload to its
record ID, and each history entry to both its parent record ID and history ID.
The wrapped DEK authenticates the credential mode and KDF configuration.

The DEK is wrapped with one current password-derived key:

| Mode | Wrapping key | Authentication |
| --- | --- | --- |
| Shared (default) | PBKDF2-HMAC-SHA256, 600,000 rounds, per-profile 32-byte salt; HKDF-SHA256 context `dotghostboard:vault:v2` | One Dashboard password opens both stores. |
| Independent (optional) | Argon2id, 65,536 KiB memory, 3 passes, 1 lane, random 16-byte salt, 32-byte output | Dashboard password, then Vault password immediately; capture waits for both. |

Independent mode does not retain a second wrapper derived from the Dashboard
password. Knowing that password or its derived session key does not by itself
unwrap the independent Vault. The independent password must differ from the
Dashboard password; that check also applies when changing the Dashboard password.
This is password separation, not multifactor authentication.

New Dashboard passwords, independent Vault passwords, and backup passphrases must
contain at least 12 characters and cannot consist only of whitespace. Existing
short Dashboard passwords and legacy backup passphrases remain readable; changing
them applies the new policy. There is no password-reset bypass for forgotten
credentials. Longer, unpredictable passphrases remain important against offline
guessing; a KDF cannot make an easily guessed password strong.

The independent mode is configured in **Settings → Eclipse → Vault Password**.
Enabling it checks the Dashboard password and confirms the new Vault password.
Changing it or returning to shared mode checks both current passwords. These
changes take effect immediately, even if the Settings dialog is later cancelled.
They rewrap the same DEK, preserving secrets and history.

## Locking and clipboard protection

Successful authentication initializes secret recognition before capture resumes.
Cancelling the independent-password prompt keeps the application locked. Vault
idle lock remains separate from the optional Dashboard idle lock. Dashboard
auto-lock defaults to disabled, with 5-minute, 30-minute, and 1-hour options.

After Vault idle lock, an in-memory HMAC index recognizes stored values without
retaining a plaintext index or writing password digests to disk. CSV password
components are indexed as well as full records. This index survives locks within
the process and ends with that process. Unknown or changed encrypted records
cannot be classified while locked; capture fails closed for those checks.

Locking the Vault clears its mutable DEK buffer and revealed UI. In shared mode,
the still-unlocked Dashboard key can derive the Vault wrapping key: Vault idle
lock is a UI/access boundary, not independent protection against process-memory
access. Independent mode removes that derivation path. Python and GUI libraries
can retain immutable copies; key scrubbing is best effort. Malware, debugging,
swap, core dumps, screenshots, or access to a fully unlocked process remain outside
the at-rest encryption guarantee. Clipboard contents can be read by other software
with clipboard access until cleared.

## Migration, recovery, and backups

Legacy record payloads, metadata, and histories are validated and migrated after
successful unlock. Record rewrites use a SQLite transaction. Live old pages are
cleaned with secure deletion, WAL checkpointing, and vacuuming after migration.
This cannot erase older external copies, filesystem snapshots, or storage-device
remnants. SQLite schema version 2 prevents older app builds from silently opening
the upgraded database. Keep a complete pre-upgrade profile backup if downgrade is
needed; never mix files from different profile states.

Missing, malformed, or unauthenticatable Vault key/configuration data is reported
without resetting existing secrets. Missing or malformed Dashboard salts are not
silently regenerated when a verifier exists. Failed authentication does not delete
data. Changing the Dashboard password rotates Eclipse items and the shared Vault
envelope through SecurityService; an independent envelope stays unchanged. Settings
cannot remove the Dashboard password while Vault items remain. Verifier replacement
is atomic, and ordinary verifier-write failures roll back store changes. Rotation
spans separate SQLite stores and a verifier file: it is not a crash-atomic transaction
across all three. Keep a recoverable backup before password changes or migrations.

For complete profile recovery, preserve `ghost.db`, `vault.db`, `eclipse.salt`, and
`eclipse.verify` together from a consistent, closed application state. Copying only
`vault.db` is insufficient in shared mode. An exported `.vault` backup is independent
of those profile files but requires its own export passphrase.

New `.vault` exports use format 2: AES-256-GCM, Argon2id (64 MiB, 3 passes, 1 lane),
a fresh 16-byte salt and 12-byte nonce, and an authenticated full header. They include
every record, up to three previous values, private metadata, expiry, and an export
timestamp. Export aborts if encrypted content cannot be read. Version 1 backups
(PBKDF2-HMAC-SHA256, 100,000 rounds) remain importable, including older short
passphrases. Exporting a new backup does not strengthen existing backup files.

## Visible information and remaining limits

Automatic recovery is available in Settings → Recovery: select specific records or
all current/future records with Auto Sync, keep an immediately updated latest copy,
and retain daily/weekly/monthly versions separately from safety/manual copies.
Archives have their own Argon2id-protected key envelope and remain recoverable after
the original profile is lost. The locally stored archive key is encrypted with the
Vault DEK and cleared on lock. Scheduled work requires the application and Vault to
be unlocked; overdue work resumes on unlock. Recovery requires a readable archive
and its passphrase and cannot recreate data after every copy has been lost.

Restoration validates data before replacement, preserves old database/sidecars and
credential copies, and can create a new profile without the original Dashboard/Vault
passwords. Source record IDs and creation/history timestamps are recreated. Automatic
backup settings must be reviewed after replacing the Vault. See the complete
[recovery setup and restore guide](vault-recovery.md), including selection, retention,
failure behavior, and archive encryption details.

SQLite structure, record/history counts and IDs, ciphertext lengths, creation/update
timestamps, credential mode, and KDF parameters remain visible. This is encrypted
application data, not full-file SQLCipher encryption. AES-GCM detects modified
authenticated ciphertext; it does not prevent deletion, replay of an old complete
database, or manipulation of unauthenticated listing timestamps. Full-disk encryption
and secure device access complement this model.

Argon2id requires `cryptography>=44` with a backend that supports it. Stored KDF
parameters are restricted to the supported profile before derivation, avoiding
unbounded memory/CPU requests from modified configurations.

Implementation: `core/security/passwords.py`, `core/security/vault/credentials.py`,
`core/security/vault/protected_records.py`, `core/security/vault/service.py`,
`core/security/vault/backup.py`, and `core/services/security_service.py`.
Regression coverage includes password-mode transitions, startup/cancel flows,
rotation failures, legacy migration/import, private metadata, and ciphertext swaps.

Verified on 20 October 2026: the full suite passed 694 tests in 335.61 seconds,
including 36 recovery regressions.
Qt tests ran headlessly; local API and Openbox/Qtile integration ran with the
permissions required for loopback and temporary X11 displays. Final Settings
password-field cleanup and selection-dialog adjustments also passed focused UI checks.
