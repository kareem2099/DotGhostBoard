# Vault Backup & Recovery

Recovery was introduced in v2.1.3 and remains available in v2.1.4. Earlier packages
have not been replaced. Recovery requires an existing, readable backup and its passphrase.

## Set up recovery copies

1. Unlock Dashboard and Vault, then open **Settings → Recovery**.
2. Enable **encrypted recovery copies**.
3. Choose **specific items**, then check the Vault entries to include (search and
   **Select all results / Deselect all results** apply only to visible matches and
   preserve choices hidden by the search); or choose
   **All items — Auto Sync** to include every current entry and future additions.
4. Choose an existing backup folder. An external drive or a folder you already
   synchronize elsewhere protects against losing the profile's disk. The app does
   not set up a cloud account or upload to a remote service itself.
5. Choose **Daily**, **Weekly**, or **Monthly**, and how many versions to retain.
6. Set and confirm a backup passphrase of at least 12 characters. Keep it safe;
   use a different password from Dashboard if independent backup protection is needed.
7. Click **Apply backup settings**, or use the Settings dialog's **Save** button.

The latest copy updates immediately after Vault changes. In selected-item mode,
only selected records appear in it; future entries require selection. Auto Sync
includes new entries automatically. Both modes include secret content, title,
category, expiry, and up to three prior secret values for each included record.
Changing the selection affects future copies; historical copies keep their original
selection. Before narrowing the selection or changing its passphrase in the same
folder, the previous latest copy is preserved as a safety version.

The schedule retains dated snapshots in addition to the latest copy. Safety
snapshots are also taken before editing, deletion, password changes, import, and
migration while recovery is enabled. Bulk imports update the latest copy once
after the batch, rather than writing a complete archive for every imported row.
Safety copies follow the same item selection; excluded entries are not added
automatically by a safety checkpoint.

The retention count applies separately to scheduled versions and safety/manual
versions. The default keeps up to 10 of each, plus the latest copy. Frequent edits
therefore do not evict the monthly or weekly timeline. **Back up now** creates a
manual version. Applying settings or making a manual copy takes effect immediately;
cancelling the surrounding Settings dialog does not undo those actions.

Scheduling runs while the application and Vault are unlocked. A minute timer checks
for due work; overdue work and failed synchronization are retried on the next Vault
unlock. No background system service runs while the application is closed. Vault
auto-lock clears the in-memory recovery key along with the Vault's data key.

Manual setup, copying, verification, and restoration run in background workers.
A modal progress window prevents duplicate actions and closing halfway through an
operation. Idle timers resume afterwards with elapsed time deducted.

## Understand backup status and failures

The Recovery page shows the last successful copy, included item count, enabled
state, and errors. A same-filesystem notice reminds you that losing the disk can
also lose local backups. Recovery failures also generate a security notification
when those notifications are enabled; messages omit item names and secrets.

A missing or changed destination directory/drive is rejected instead of silently
recreating it on another filesystem. Reconnect the drive; if its identity changed,
select the folder again and apply settings. Existing copies remain available.

An addition can still be saved to Vault if its backup fails; status records that
the copy is pending. Destructive changes and imports require their safety checkpoint
to succeed. If necessary, explicitly disable recovery in Settings to proceed without
that protection. Disabling backups does not delete existing archive files.

If entries disappear outside the application's deletion flow, synchronization
keeps the last successful copy and reports the unexpected loss. It checks record
IDs as well as counts, so adding another item cannot hide a missing record merely
by restoring the previous total. Open Recovery to restore, or explicitly review
the backup selection to establish a new baseline.

## Restore

Open **Settings → Recovery → Browse versions / Restore**. If the original Vault is
missing or unreadable at startup, the recovery screen is offered before Dashboard
starts. The login screen also has **Restore from backup**, and `--recover` opens
recovery directly (including through the running application's local IPC).

1. Select a dated version or the latest copy. **Choose backup file** also accepts
   `.dgb-recovery` files and manually exported `.vault` packages, including legacy ones.
2. Enter that file's backup passphrase and choose **Verify and preview**. The dialog
   authenticates the file and lists its item titles and count before enabling restore.
3. Choose the destination:
   - **Current profile:** enter its current Dashboard password. Restore replaces the
     active Vault with the version's contents, including when the version contains
     only selected items. Entries outside that version will not appear in the active
     Vault. Dashboard clipboard data and its credential files are not reset.
   - **New profile:** choose an empty folder and create/confirm a new Dashboard
     password. This works even if every original profile file or its passwords are
     unavailable. The recovered profile opens separately; the original stays intact.
4. For an archive created with independent Vault mode, choose and confirm a new
   independent Vault password. Shared-mode archives can also restore into independent
   mode. Independent passwords must differ from Dashboard.
5. Confirm restoration. The exact encrypted version previewed is frozen for restore,
   so a safety checkpoint updating the live "latest" file cannot replace that input.

Restore validates data and builds a fresh encrypted database before installing it.
It preserves the previous database, any WAL/SHM sidecars, and copies of the Dashboard
salt/verifier with a `.before-recovery-...` suffix. Those preserved files are not
automatically pruned. Restore does not merge versions; create a new profile if you
want to inspect an older state without replacing the current Vault.

Record IDs and creation/history timestamps are recreated during logical restoration;
secret values, history values, titles, categories, and expiry are restored. After
replacement, automatic recovery is disabled until its folder, selection, and passphrase
settings are reviewed. This prevents old record IDs or local keys from backing up the
wrong selection. Old archive files remain readable with their own backup passphrases.

## Encryption and durability

Recovery archives use a random 256-bit archive key, AES-256-GCM with random 96-bit
nonces and authenticated headers, and an Argon2id password envelope (64 MiB, 3 passes,
1 lane, random 16-byte salt). The archive carries its own key envelope, so it does not
need `vault.db`, `eclipse.salt`, or `eclipse.verify` to be decrypted. It does not contain
the original Vault data key or give access to unselected records in the original Vault.

To automate copies without retaining a plaintext passphrase, local recovery settings
hold the archive key encrypted with the Vault DEK. Unlocking the Vault makes that key
available; locking clears the mutable buffer. Changing the backup passphrase protects
future copies with a new key; older copies still need their previous passphrase.

Snapshots read items and history in a single SQLite read transaction. Only encrypted
archives are written to disk, using private temporary files, file fsync, atomic replace,
and parent-directory fsync. Copies are authenticated before success is published;
retention only removes this profile's version files after the new copy is saved.
Recovery files have a 128 MiB / 100,000-entry limit; KDF parameters are bounded before derivation.

Headers expose copy time, count, reason, profile ID, and KDF settings. This is at-rest
encryption, with the memory/device limits in [the security model](security-model.md).
No password or recovery code can reconstruct data after every usable copy is lost.

Implementation lives in `core/security/vault/recovery*.py`,
`ui/settings/pages/recovery.py`, and `ui/vault/recovery_dialog.py`.

Verified on 20 October 2026: 36 recovery regressions passed as part of the full
694-test suite (335.61 seconds). Coverage includes item selection and Auto Sync,
calendar schedules, separate retention, lost/corrupt profiles, cancelled and verified
restoration, destination failures, passphrase changes, and unexpected item loss.
