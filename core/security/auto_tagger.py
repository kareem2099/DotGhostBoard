"""
core/security/auto_tagger.py
─────────────────────────────
Rules-based auto-tagging engine for clipboard items.
Assigns tags automatically based on content patterns — no AI or NLP.

v2.1.0 "Leviathan" — Smart Auto-Tagging.

Tags assigned:
    #link     — URL (http/https/ftp)
    #code     — multi-line code block or common code patterns
    #json     — valid JSON payload
    #secret   — high-entropy token / credential pattern
    #email    — email address
    #ip       — IPv4 / IPv6 address
    #phone    — phone number (international format)
    #path     — filesystem path
    #hash     — hex hash (MD5/SHA family)
"""

from __future__ import annotations

import json
import re
import math
import string

# ─────────────────────────────────────────────────────────────
# Compiled patterns (module-level for performance)
# ─────────────────────────────────────────────────────────────

_RE_URL = re.compile(
    r"https?://[^\s\"'<>]{3,}|ftp://[^\s\"'<>]{3,}",
    re.IGNORECASE,
)

_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

_RE_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)

_RE_IPV6 = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b"
)

_RE_PHONE = re.compile(
    r"(?:\+\d{1,3}[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{3,4}(?:[\s\-]?\d{1,4})?"
)

_RE_PATH = re.compile(
    r"(?:/[a-zA-Z0-9_.~\-]+){2,}|"             # Unix absolute
    r"[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\?)+"   # Windows absolute
)

_RE_HEX_HASH = re.compile(
    r"\b[0-9a-fA-F]{32,64}\b"   # MD5 (32) to SHA-256 (64)
)

# High-entropy secret patterns (JWT, API keys, tokens)
_RE_SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),                         # GitHub PAT
    re.compile(r"ghs_[A-Za-z0-9]{36,}"),                         # GitHub server token
    re.compile(r"github_pat_[A-Za-z0-9_]{82,}"),                 # GitHub fine-grained
    re.compile(r"AKIA[0-9A-Z]{16}"),                              # AWS Access Key
    re.compile(r"sk-[A-Za-z0-9]{32,}"),                          # OpenAI / Stripe
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),                # Slack tokens
    re.compile(r"eyJ[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}"), # JWT
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), # PEM keys
]

# Code heuristics: at least one of these patterns in a multi-line text
_CODE_KEYWORDS = re.compile(
    r"\b(?:def |class |import |from |function |const |let |var |return |if |else |for |while |"
    r"printf|cout|System\.out|#include|public static|async |await |lambda |->|=>)\b"
)

_CODE_BRACKETS = re.compile(r"[\{\}\[\];]{3,}")  # dense brackets/semicolons


# ─────────────────────────────────────────────────────────────
# Entropy helper (same as in secret_dialog.py)
# ─────────────────────────────────────────────────────────────

def _entropy_bits(text: str) -> float:
    """Estimate Shannon-style entropy bits for a string."""
    if not text:
        return 0.0
    pool = 0
    if any(c in string.ascii_lowercase for c in text): pool += 26
    if any(c in string.ascii_uppercase for c in text): pool += 26
    if any(c in string.digits           for c in text): pool += 10
    if any(c not in string.ascii_letters + string.digits for c in text): pool += 32
    if pool == 0: pool = 26
    return math.log2(pool) * len(text)


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def detect_tags(content: str) -> list[str]:
    """
    Analyse `content` and return a list of auto-tags to apply.

    Returns a de-duplicated list like ['#link', '#code'].
    Empty list when no patterns match.
    Always safe — never raises.
    """
    if not content or not isinstance(content, str):
        return []

    tags: list[str] = []
    text = content.strip()

    # ── #link ────────────────────────────────────────────────
    if _RE_URL.search(text):
        tags.append("#link")

    # ── #email ───────────────────────────────────────────────
    if _RE_EMAIL.search(text):
        tags.append("#email")

    # ── #ip ──────────────────────────────────────────────────
    if _RE_IPV4.search(text) or _RE_IPV6.search(text):
        tags.append("#ip")

    # ── #path ────────────────────────────────────────────────
    if _RE_PATH.search(text) and "#link" not in tags:
        tags.append("#path")

    # ── #hash ────────────────────────────────────────────────
    if _RE_HEX_HASH.search(text):
        tags.append("#hash")

    # ── #secret ──────────────────────────────────────────────
    is_secret = False
    for pat in _RE_SECRET_PATTERNS:
        if pat.search(text):
            is_secret = True
            break
    # High-entropy single-line string (≥ 90 bits, no spaces, 16+ chars)
    if not is_secret and len(text) >= 16 and " " not in text and "\n" not in text:
        if _entropy_bits(text) >= 90:
            is_secret = True
    if is_secret:
        tags.append("#secret")

    # ── #json ────────────────────────────────────────────────
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            json.loads(text)
            tags.append("#json")
        except (json.JSONDecodeError, ValueError):
            pass

    # ── #code ────────────────────────────────────────────────
    if "\n" in text and len(text) > 40:
        if _CODE_KEYWORDS.search(text) or _CODE_BRACKETS.search(text):
            tags.append("#code")

    return list(dict.fromkeys(tags))  # preserve order, deduplicate


def apply_auto_tags(item_id: int, content: str) -> list[str]:
    """
    Detect and persist auto-tags for a clipboard item.
    Skips tags that are already present on the item.

    Returns the list of newly-added tags.
    """
    try:
        from core import storage
        new_tags = detect_tags(content)
        if not new_tags:
            return []

        current = storage.get_tags(item_id)
        added: list[str] = []
        for tag in new_tags:
            if tag not in current:
                storage.add_tag(item_id, tag)
                added.append(tag)
        return added
    except Exception:
        return []
