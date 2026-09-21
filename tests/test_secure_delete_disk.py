"""
tests/test_secure_delete_disk.py
─────────────────────────────────
Physical byte verification for secure item deletion from SQLite ghost.db.
Ensures zero byte traces of secret plaintext remain in SQLite DB pages or WAL.
"""

import os
from core import storage
from core.storage.repositories import clips


def test_physical_sqlite_byte_erasure(tmp_path, monkeypatch):
    """
    Verify that secure=True in delete_item physically zeroes out and purges
    the plaintext bytes from ghost.db and ghost.db-wal.
    """
    monkeypatch.setenv("DOTGHOST_HOME", str(tmp_path))
    storage.init_db()

    canary = "CANARY_ULTRA_SECURE_TOKEN_998877_ABCXYZ!"
    item_id = clips.add_item("text", canary)
    assert item_id > 0

    db_path = storage.get_db_path()
    wal_path = db_path + "-wal"

    # Flush WAL to ensure canary is physically written to disk
    with storage._db() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    bytes_before = b""
    with open(db_path, "rb") as f:
        bytes_before += f.read()
    if os.path.exists(wal_path):
        with open(wal_path, "rb") as f:
            bytes_before += f.read()

    assert canary.encode("utf-8") in bytes_before, "Canary must physically exist on disk before deletion"

    # Secure deletion
    deleted = clips.delete_item(item_id, secure=True, force=True)
    assert deleted is True

    bytes_after = b""
    with open(db_path, "rb") as f:
        bytes_after += f.read()
    if os.path.exists(wal_path):
        with open(wal_path, "rb") as f:
            bytes_after += f.read()

    assert canary.encode("utf-8") not in bytes_after, (
        "Canary plaintext bytes MUST NOT exist anywhere in ghost.db or WAL after secure deletion"
    )
