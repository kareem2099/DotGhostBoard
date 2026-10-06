"""
core/security/vault/csv_importer.py
─────────────────────────────────────
Offline CSV password importer for The Vault.

Supports auto-detection of exports from:
  • Google Chrome / Google Passwords Manager
  • Microsoft Edge
  • Mozilla Firefox
  • Bitwarden
  • 1Password
  • LastPass
  • Generic (name + password fallback)

Password Strength Analysis (offline, regex-based):
  • Detects weak passwords (short, numeric-only, common patterns)
  • Flags repeated or sequential characters
  • Provides a score and human-readable label per entry

NOTE: Leaked-password (HIBP breach) detection is NOT included because
obtaining the full SHA-1 hash database requires a paid license.
The HIBP k-anonymity API is available online but is out of scope for
this offline-first tool.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Optional


# ── Password Strength Regex Engine ───────────────────────────────────────────

# Common / trivially-guessable patterns (partial match)
_COMMON_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(password|passw0rd|p@ssword|p@ssw0rd)$", re.IGNORECASE),
    re.compile(r"^(123456|1234567|12345678|123456789|1234567890)$"),
    re.compile(r"^(qwerty|qwertyuiop|asdfgh|zxcvbn)$", re.IGNORECASE),
    re.compile(r"^(admin|root|login|user|guest|test|demo)$", re.IGNORECASE),
    re.compile(r"^(abc123|letmein|welcome|monkey|dragon|iloveyou)$", re.IGNORECASE),
    re.compile(r"^(.)\1{4,}$"),
    re.compile(r"^(01234|12345|23456|34567|45678|56789|67890)+$"),
]

_SEQUENTIAL_RUN = re.compile(
    r"(0123|1234|2345|3456|4567|5678|6789|"
    r"abcd|bcde|cdef|defg|efgh|fghi|ghij|hijk|ijkl|jklm|klmn|lmno|mnop|"
    r"nopq|opqr|pqrs|qrst|rstu|stuv|tuvw|uvwx|vwxy|wxyz)",
    re.IGNORECASE,
)


def _character_classes(password: str) -> int:
    classes = 0
    if re.search(r"[a-z]", password):
        classes += 1
    if re.search(r"[A-Z]", password):
        classes += 1
    if re.search(r"\d", password):
        classes += 1
    if re.search(r"[^a-zA-Z0-9]", password):
        classes += 1
    return classes


def analyse_password_strength(password: str) -> dict:
    """
    Offline regex-based password strength analyser.

    Returns a dict with:
      score  : int 0-100
      label  : str ("Very Weak" | "Weak" | "Fair" | "Strong" | "Very Strong")
      issues : list[str]
      is_weak: bool  -- True when score < 40
    """
    issues: list[str] = []
    score = 0

    if not password:
        return {"score": 0, "label": "Empty", "issues": ["Password is empty"], "is_weak": True}

    length = len(password)

    # Length scoring (max 40 pts)
    if length < 6:
        issues.append("Too short (< 6 characters)")
        score += 5
    elif length < 8:
        issues.append("Short password (< 8 characters)")
        score += 15
    elif length < 12:
        score += 25
    elif length < 16:
        score += 33
    else:
        score += 40

    # Character-class diversity (max 28 pts)
    classes = _character_classes(password)
    score += classes * 7
    if classes < 2:
        issues.append("Uses only one character class (add uppercase, digits, or symbols)")

    # Common patterns (-30 pts)
    for pattern in _COMMON_PATTERNS:
        if pattern.search(password):
            issues.append("Matches a very common password pattern")
            score -= 30
            break

    # Sequential runs (-15 pts)
    if _SEQUENTIAL_RUN.search(password):
        issues.append("Contains sequential characters (e.g. '1234', 'abcd')")
        score -= 15

    # Numeric-only penalty (-20 pts)
    if re.match(r"^\d+$", password):
        issues.append("All-numeric password")
        score -= 20

    # Repetition penalty (-10 pts)
    if re.search(r"(.)\1{2,}", password):
        issues.append("Contains repeated characters (e.g. 'aaa', '111')")
        score -= 10

    score = max(0, min(100, score))

    if score < 20:
        label = "Very Weak"
    elif score < 40:
        label = "Weak"
    elif score < 60:
        label = "Fair"
    elif score < 80:
        label = "Strong"
    else:
        label = "Very Strong"

    return {
        "score": score,
        "label": label,
        "issues": list(dict.fromkeys(issues)),
        "is_weak": score < 40,
    }


# ── CSV Source Detection ──────────────────────────────────────────────────────

_SOURCE_PROFILES: dict[str, tuple[str, ...]] = {
    "google":     ("name", "url", "username", "password"),
    "edge":       ("name", "url", "username", "password"),
    "firefox":    ("url", "username", "password"),
    "bitwarden":  ("name", "login_uri", "login_username", "login_password"),
    "1password":  ("title", "username", "password", "urls"),
    "lastpass":   ("url", "username", "password", "name", "grouping"),
    "generic":    ("name", "password"),
}

_DETECTION_ORDER = ["bitwarden", "1password", "lastpass", "google", "firefox", "edge", "generic"]


def detect_csv_source(headers: list[str]) -> str:
    normalised = {h.strip().lower() for h in headers}
    for source in _DETECTION_ORDER:
        required = set(_SOURCE_PROFILES[source])
        if required.issubset(normalised):
            return source
    return "generic"


# ── Parsed Entry ──────────────────────────────────────────────────────────────

@dataclass
class CsvEntry:
    """A single password row parsed from a CSV export."""
    title: str
    username: str
    password: str
    url: str = ""
    notes: str = ""
    strength: dict = field(default_factory=dict)

    @property
    def vault_secret_text(self) -> str:
        parts = [self.password]
        if self.username:
            parts.append(f"username: {self.username}")
        if self.url:
            parts.append(f"url: {self.url}")
        if self.notes:
            parts.append(f"notes: {self.notes}")
        return "\n".join(parts)

    @property
    def is_weak(self) -> bool:
        return self.strength.get("is_weak", False)

    @property
    def strength_label(self) -> str:
        return self.strength.get("label", "Unknown")

    @property
    def strength_score(self) -> int:
        return self.strength.get("score", 0)


# ── Per-source Row Extractor ──────────────────────────────────────────────────

def _extract_row(row: dict, source: str) -> Optional[CsvEntry]:
    def g(key: str) -> str:
        for k, v in row.items():
            if k.strip().lower() == key:
                return (v or "").strip()
        return ""

    if source in ("google", "edge"):
        title    = g("name")
        username = g("username")
        password = g("password")
        url      = g("url")
        notes    = ""

    elif source == "firefox":
        title    = g("url")
        username = g("username")
        password = g("password")
        url      = g("url")
        notes    = ""

    elif source == "bitwarden":
        title    = g("name")
        username = g("login_username")
        password = g("login_password")
        url      = g("login_uri")
        notes    = g("notes")

    elif source == "1password":
        title    = g("title")
        username = g("username")
        password = g("password")
        url      = g("urls")
        notes    = g("notes")

    elif source == "lastpass":
        title    = g("name")
        username = g("username")
        password = g("password")
        url      = g("url")
        notes    = g("extra")

    else:  # generic
        title    = g("name") or g("title") or g("label") or g("site")
        username = g("username") or g("user") or g("email") or g("login")
        password = g("password") or g("pass") or g("secret")
        url      = g("url") or g("uri") or g("website") or g("site")
        notes    = g("notes") or g("comment") or g("extra")

    if not password:
        return None
    if not title:
        title = url or username or "Imported Secret"

    return CsvEntry(
        title=title,
        username=username,
        password=password,
        url=url,
        notes=notes,
    )


# ── Public Parser ─────────────────────────────────────────────────────────────

@dataclass
class CsvParseResult:
    """Result from parse_csv_export."""
    source: str
    entries: list[CsvEntry]
    skipped_rows: int = 0
    weak_count: int = 0
    total_count: int = 0


def parse_csv_export(csv_text: str) -> CsvParseResult:
    """
    Parse a password manager CSV export string.

    Steps:
      1. Detect source from headers
      2. Extract rows using per-source schema
      3. Run offline password strength analysis on each entry
      4. Return CsvParseResult with annotated entries

    Raises ValueError if file appears empty or has no recognisable headers.
    """
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    headers = reader.fieldnames or []
    if not headers:
        raise ValueError("CSV file has no headers — cannot parse.")

    source = detect_csv_source(list(headers))
    entries: list[CsvEntry] = []
    skipped = 0

    for row in reader:
        entry = _extract_row(row, source)
        if entry is None:
            skipped += 1
            continue
        entry.strength = analyse_password_strength(entry.password)
        entries.append(entry)

    weak_count = sum(1 for e in entries if e.is_weak)

    return CsvParseResult(
        source=source,
        entries=entries,
        skipped_rows=skipped,
        weak_count=weak_count,
        total_count=len(entries),
    )
