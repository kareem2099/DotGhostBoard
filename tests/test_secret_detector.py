"""
tests/test_secret_detector.py
─────────────────────────────
Tests for Smart Secret Detection Engine (Cerberus Foundation).
"""

from core.security.detector import SecretDetector
from core.clipboard.events import ClipboardEvent, Action
from core.clipboard.pipeline import ClipboardPipeline


def test_detect_ssh_private_key():
    detector = SecretDetector()
    sample = """
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Y1W9Zq8vQZ2...
-----END RSA PRIVATE KEY-----
"""
    match = detector.analyze(sample)
    assert match is not None
    assert match.secret_type == "ssh_or_pem_private_key"
    assert match.confidence == 1.0
    assert detector.is_secret(sample) is True


def test_detect_github_token():
    detector = SecretDetector()
    sample = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    match = detector.analyze(sample)
    assert match is not None
    assert match.secret_type == "github_token"
    assert detector.is_secret(sample) is True


def test_detect_aws_key():
    detector = SecretDetector()
    sample = "Exporting AWS key: AKIAIOSFODNN7EXAMPLE"
    match = detector.analyze(sample)
    assert match is not None
    assert match.secret_type == "aws_access_key"
    assert detector.is_secret(sample) is True


def test_detect_slack_token():
    detector = SecretDetector()
    sample = "xox" + "b-123456789012-1234567890123-FakeTokenForTestingOnly123"
    match = detector.analyze(sample)
    assert match is not None
    assert match.secret_type == "slack_token"
    assert detector.is_secret(sample) is True


def test_detect_jwt():
    detector = SecretDetector()
    sample = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG66mXwpg"
    match = detector.analyze(sample)
    assert match is not None
    assert match.secret_type == "jwt_token"
    assert detector.is_secret(sample) is True


def test_detect_generic_api_secret():
    detector = SecretDetector()
    sample = 'api_key = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5"'
    match = detector.analyze(sample)
    assert match is not None
    assert match.secret_type == "generic_api_secret"
    assert detector.is_secret(sample) is True


def test_ignore_normal_clipboard_content():
    detector = SecretDetector()
    normal_texts = [
        "Hello world! This is a simple note.",
        "https://github.com/kareem2099/DotGhostBoard",
        "def hello(): return 'world'",
        "git commit -m 'feat: add amazing feature'",
        "1234567890",
    ]
    for text in normal_texts:
        assert detector.analyze(text) is None
        assert detector.is_secret(text) is False


def test_pipeline_integration_routes_secret_candidate():
    detector = SecretDetector()
    pipeline = ClipboardPipeline(secret_detector=detector.is_secret)

    # 1. Normal event -> SAVE_NORMAL
    normal_event = ClipboardEvent(content_type="text", content="Just some notes")
    decision = pipeline.process(normal_event)
    assert decision.action == Action.SAVE_NORMAL

    # 2. Secret candidate event -> SECRET_CANDIDATE
    secret_event = ClipboardEvent(content_type="text", content="ghp_1234567890abcdefghijklmnopqrstuvwxyz")
    secret_decision = pipeline.process(secret_event)
    assert secret_decision.action == Action.SECRET_CANDIDATE
    assert secret_decision.payload == secret_event
