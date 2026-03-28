"""
Secure File Deletion — Eclipse v1.4.0
──────────────────────────────────────
Overwrites file contents with random bytes before unlinking,
making recovery significantly harder than a simple os.remove().

Note: On SSDs/flash storage with wear-levelling, true forensic
destruction is not guaranteed by software alone. For maximum
security, full-disk encryption (LUKS) is recommended at the
system level. This module provides best-effort protection.
"""

from __future__ import annotations

import os


def secure_delete(path: str, passes: int = 3) -> bool:
    """
    Overwrite *path* with random bytes *passes* times, then delete it.

    Args:
        path:   Absolute path to the file to destroy.
        passes: Number of overwrite passes (default 3).
                More passes = slower but marginally more secure.

    Returns:
        True  — file was overwritten and deleted successfully.
        False — file did not exist (no-op).

    If an I/O error occurs during overwriting, the function falls back
    to a plain os.remove() so the file is at least unlinked.
    """
    if not os.path.isfile(path):
        return False

    try:
        size = os.path.getsize(path)
        if size > 0:
            with open(path, "r+b") as fh:
                for pass_num in range(passes):
                    fh.seek(0)
                    # Alternate: random → zeros → random for maximum confusion
                    if pass_num % 2 == 1:
                        fh.write(b"\x00" * size)
                    else:
                        fh.write(os.urandom(size))
                    fh.flush()
                    os.fsync(fh.fileno())
    except (OSError, IOError):
        pass  # Fall through to deletion regardless

    try:
        os.remove(path)
        return True
    except OSError:
        return False


def secure_delete_many(paths: list[str], passes: int = 3) -> dict[str, bool]:
    """
    Securely delete multiple files.

    Returns:
        dict mapping each path → True (deleted) / False (not found or failed).
    """
    return {p: secure_delete(p, passes) for p in paths}