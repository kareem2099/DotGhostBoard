"""
core/security/detector.py
─────────────────────────
Smart Secret Detection Engine (Cerberus Foundation).

Detects private keys, API tokens, cloud credentials, JWTs, and high-entropy
secrets before they are persisted to plaintext history.
"""

from __future__ import annotations

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


class SecretDetector:
    """
    Regex and heuristic scanner for sensitive credentials in clipboard text.
    Designed for sub-millisecond execution to avoid blocking the pipeline.
    """

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
            re.compile(r"\bAIza[0-9A-Za-z\\-_]{35}\b"),
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
                r"(?i)\b(?:api_key|apikey|secret_key|auth_token|bearer_token|access_token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{20,})['\"]?"
            ),
            0.8,
        ),
    ]

    def analyze(self, text: str) -> Optional[SecretMatch]:
        """
        Analyze plaintext string for known secrets.
        Returns SecretMatch if a match is detected, None otherwise.
        """
        if not text or len(text) > 100_000:
            # Skip empty or excessively huge blobs to maintain predictable perf
            return None

        for secret_type, pattern, confidence in self.PATTERNS:
            match = pattern.search(text)
            if match:
                matched_str = match.group(0)
                # Obfuscate preview: keep first 4 and last 2 chars
                if len(matched_str) > 8:
                    preview = f"{matched_str[:4]}...{matched_str[-2:]}"
                else:
                    preview = "****"
                return SecretMatch(
                    secret_type=secret_type,
                    confidence=confidence,
                    preview=preview,
                )

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
