"""
core/security/detector.py
─────────────────────────
Smart Secret Detection Engine (Cerberus Foundation).

Detects private keys, API tokens, cloud credentials, JWTs, and high-entropy
secrets before they are persisted to plaintext history.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.clipboard.events import ClipboardEvent


@dataclass(frozen=True)
class SecretMatch:
    """Detailed metadata for a detected secret candidate."""
    secret_type: str
    confidence: float
    preview: str


def shannon_entropy(data: str) -> float:
    """Calculate the Shannon entropy of a string in bits per character."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    counts: dict[str, int] = {}
    for char in data:
        counts[char] = counts.get(char, 0) + 1
    for count in counts.values():
        p_x = count / length
        if p_x > 0:
            entropy -= p_x * math.log2(p_x)
    return entropy


class SecretDetector:
    """
    Regex and heuristic scanner for sensitive credentials in clipboard text.
    Designed for sub-millisecond execution to avoid blocking the pipeline.
    """

    PASSWORD_SYMBOLS = set("!@#$%^&*_+=-~/?|`~^:;")
    STANDALONE_SYMBOLS = set("!@#$^~")
    IDENTIFIER_LIKE = re.compile(r"^[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)+$")
    CODE_CALL_PATTERN = re.compile(r"^[\w.]+\(.*\);?$")
    ISO_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
    MAC_ADDR_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

    ASSIGNMENT_PATTERN = re.compile(
        r"(?i)(?<![A-Za-z0-9])(?:password|passwd|master_pass|secret_pass|user_pass|admin_pass)\s*[:=]\s*[\x27\"]?([^\r\n\x27\"]{4,128})[\x27\"]?"
    )
    UUID_PATTERN = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    HEX_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{32,64}$")
    EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
    FILE_LINE_PATTERN = re.compile(r"\b\w+\.\w+:\d+")

    PATTERNS: list[tuple[str, re.Pattern, float]] = [
        # Private Keys
        (
            "ssh_or_pem_private_key",
            re.compile(r"-----BEGIN\s+(?:[A-Z0-9_-]+\s+)?PRIVATE KEY-----", re.MULTILINE),
            1.0,
        ),
        # GitHub Tokens
        (
            "github_token",
            re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"),
            0.95,
        ),
        (
            "github_fine_grained_pat",
            re.compile(r"\bgithub_pat_[A-Za-z0-9_]{80,}\b"),
            0.95,
        ),
        # AWS Access Key ID
        (
            "aws_access_key",
            re.compile(r"\b(?:AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}\b"),
            0.95,
        ),
        # AWS Secret Access Key (assignment heuristic)
        (
            "aws_secret_key",
            re.compile(r"(?i)\baws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"),
            0.9,
        ),
        # Slack Tokens
        (
            "slack_token",
            re.compile(r"\bxox[baprs]-[0-9A-Za-z]{10,48}\b"),
            0.9,
        ),
        # Google API Key
        (
            "google_api_key",
            re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
            0.9,
        ),
        # OpenAI / Anthropic API Key
        (
            "ai_api_key",
            re.compile(r"\bsk-(?:ant-)?[a-zA-Z0-9_-]{20,}\b"),
            0.9,
        ),
        # JWT Token
        (
            "jwt_token",
            re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}\.[A-Za-z0-9._-]{10,}\b"),
            0.85,
        ),
        # Generic credential assignments (e.g. api_key = "...", auth_token = "...")
        (
            "generic_api_secret",
            re.compile(
                r"(?i)(?<![A-Za-z0-9])(?:api_key|apikey|secret_key|auth_token|bearer_token|access_token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{20,})['\"]?"
            ),
            0.8,
        ),
    ]

    def _obfuscate(self, text: str) -> str:
        return "••••••••••••"

    def _validate_assignment_value(self, raw_val: str) -> Optional[str]:
        """Validate and sanitize candidate assignment value; returns cleaned val if valid, else None."""
        if not raw_val:
            return None
        raw_val = raw_val.strip().rstrip(",;")
        if raw_val.startswith(("'", '"')) and raw_val.endswith(("'", '"')):
            raw_val = raw_val[1:-1].strip()

        # Take the first token so sentences ("at least 8 characters") are excluded
        val = raw_val.split(None, 1)[0] if raw_val else ""
        val_lower = val.lower()

        is_path = (
            val.startswith(("/", "~/", "./", "../", "file://", "http://", "https://"))
            or bool(re.match(r"^[a-zA-Z]:[\\/]", val))
        )
        is_code_call = bool(self.CODE_CALL_PATTERN.match(val))
        is_placeholder = (
            val.startswith("${")
            or (val.startswith("<") and val.endswith(">"))
            or val.startswith("***")
            or val_lower in (
                "null", "none", "true", "false", "undefined",
                "required", "optional", "todo", "fixme",
                "password", "changeme", "string", "text",
            )
        )

        if not is_path and not is_code_call and not is_placeholder and len(val) >= 6:
            has_digit_or_sym = (
                any(c.isdigit() for c in val)
                or any(c in self.STANDALONE_SYMBOLS for c in val)
            )
            if has_digit_or_sym and not (val.isupper() and "_" in val):
                return val
        return None

    def _check_password_heuristic(self, text: str) -> Optional[SecretMatch]:
        s = text.strip()
        if not s:
            return None

        # 1. Explicit assignment (searches all matches in multiline text, e.g. .env or configs)
        for m in self.ASSIGNMENT_PATTERN.finditer(s):
            val = self._validate_assignment_value(m.group(1))
            if val:
                return SecretMatch(
                    secret_type="password_assignment",
                    confidence=0.95,
                    preview=self._obfuscate(val),
                )

        # 2. Standalone token heuristic (capped at 1000 chars, max 2 tokens)
        if len(s) > 1000:
            return None

        tokens = s.split()
        if len(tokens) > 2:
            return None

        for token in tokens:
            clean = token.strip(",;:()[]{}\x27\"`")
            if not (10 <= len(clean) <= 64):
                continue

            # Exclude tokens containing dot (domain names, IP addresses, package versions)
            if "." in clean:
                continue

            # Exclude identifiers, ISO timestamps, and MAC addresses
            if self.IDENTIFIER_LIKE.match(clean):
                continue
            if self.ISO_TIMESTAMP_PATTERN.match(clean):
                continue
            if self.MAC_ADDR_PATTERN.match(clean):
                continue

            # Exclude paths, URLs, code expressions
            if (
                clean.startswith(("http://", "https://", "ftp://", "file://", "/", "./", "../"))
                or "/" in clean
                or "\\" in clean
                or "(" in clean
                or ")" in clean
            ):
                continue

            if self.FILE_LINE_PATTERN.search(clean):
                continue
            if (
                self.UUID_PATTERN.match(clean)
                or self.HEX_HASH_PATTERN.match(clean)
                or self.EMAIL_PATTERN.match(clean)
            ):
                continue
            if clean.startswith(("{", "}", "[", "]")):
                continue

            has_upper = bool(re.search(r"[A-Z]", clean))
            has_lower = bool(re.search(r"[a-z]", clean))
            has_digit = bool(re.search(r"[0-9]", clean))
            has_sym = any(c in self.STANDALONE_SYMBOLS for c in clean)

            # Standalone token MUST have at least one explicit standalone password symbol (!@#$^~)
            if not has_sym:
                continue

            classes_count = sum([has_upper, has_lower, has_digit, has_sym])
            if classes_count >= 3 and shannon_entropy(clean) >= 3.0:
                return SecretMatch(
                    secret_type="high_entropy_password",
                    confidence=0.90,
                    preview=self._obfuscate(clean),
                )

        return None

    def analyze(self, text: str) -> Optional[SecretMatch]:
        """
        Analyze plaintext string for known secrets.
        Returns SecretMatch if a match is detected, None otherwise.
        """
        if not text or len(text) > 100_000:
            return None

        for secret_type, pattern, confidence in self.PATTERNS:
            match = pattern.search(text)
            if match:
                matched_str = match.group(0)
                return SecretMatch(
                    secret_type=secret_type,
                    confidence=confidence,
                    preview=self._obfuscate(matched_str),
                )

        # Evaluate password assignments and high-entropy password heuristics
        pw_match = self._check_password_heuristic(text)
        if pw_match is not None:
            return pw_match

        return None

    def is_secret(self, target: ClipboardEvent | str | None) -> bool:
        """
        Check if target (ClipboardEvent or string) contains a secret candidate.
        Matches the Callable[[ClipboardEvent], bool] signature expected by ClipboardPipeline.
        """
        if target is None:
            return False

        if isinstance(target, str):
            text = target
        else:
            # ClipboardEvent
            if target.content_type != "text" or not target.content:
                return False
            text = str(target.content)

        return self.analyze(text) is not None
