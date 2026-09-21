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


def test_detect_high_entropy_passwords():
    detector = SecretDetector()
    samples = [
        "TestMasterPass123!",
        "4#9XMOFYPa~F",
        "P@ssw0rd2024!",
        "Admin#98765",
        "Kareem_99@2026",
    ]
    for sample in samples:
        match = detector.analyze(sample)
        assert match is not None, f"Failed to detect password: {sample}"
        assert match.secret_type in ("high_entropy_password", "password_assignment")
        assert detector.is_secret(sample) is True

def test_detect_google_api_key():
    detector = SecretDetector()
    # Test key with hyphen and underscore (AIza + 35 chars = 39 chars total)
    sample = "AIzaSyD-1234567890_abcdefghijklmnopQRST"
    assert len(sample) == 39
    match = detector.analyze(sample)
    assert match is not None
    assert match.secret_type == "google_api_key"
    assert detector.is_secret(sample) is True


def test_detect_password_assignments():
    detector = SecretDetector()
    samples = [
        "password: MySecret99!",
        "passwd = SuperSecret123#",
        "master_pass: 'KareemVault2026!'",
        "secret_pass = UltraSecretToken99#",
        "password: Tr0ub4dor.3!",
        "DB_PASSWORD=s3cr3tpass99",
        "POSTGRES_PASSWORD: Hunter2!x",
    ]
    for sample in samples:
        match = detector.analyze(sample)
        assert match is not None, f"Failed to detect assignment: {sample}"
        assert match.secret_type == "password_assignment"
        assert detector.is_secret(sample) is True

    # Real generic API keys in env variables (e.g. SERVICE_API_KEY)
    service_sample = "SERVICE_API_KEY=sec_token_1234567890abcdef1234567890"
    service_match = detector.analyze(service_sample)
    assert service_match is not None
    assert service_match.secret_type == "generic_api_secret"
    assert detector.is_secret(service_sample) is True

    # Multi-line .env / config file with a password line
    env_content = """
    DB_HOST=127.0.0.1
    DB_PORT=5432
    DB_USER=postgres
    DB_PASSWORD=s3cr3tpass99
    CACHE_DRIVER=redis
    """
    assert detector.is_secret(env_content) is True

    # Large .env file (>1000 characters) should still detect assignments
    large_env = "VAR_X=some_normal_value_123\n" * 60 + "DB_PASSWORD=s3cr3tpass99\n"
    assert len(large_env) > 1000
    assert detector.is_secret(large_env) is True

    # Multiline config where first password line is a placeholder/rejected but later line is real
    mixed_content = """
    password = None
    master_pass = self.pw_input.text()
    DB_PASSWORD = s3cr3tpass99
    """
    assert detector.is_secret(mixed_content) is True


def test_extensive_negative_suite_non_secrets():
    detector = SecretDetector()
    negative_samples = [
        "Meeting at 10:30! See you Monday?",
        "Hello world, this is a test note with normal punctuation.",
        "Viewed dashboard.py:320-336",
        "/usr/local/bin/python3",
        "./build/artifacts/output.json",
        "def hello_world(): return True",
        "import os, sys, hashlib",
        '{"status": 200, "message": "OK", "items": []}',
        "c9a646d3-9c61-4cd9-bc14-2a6f2357a749",
        "e8c3dfb8516e4ee4872c9ef2469fc2ca12345678",
        "kareem@dotghostboard.local",
        'git commit -m "feat: initial setup" && pytest',
        "Aa1!Aa1!Aa1!Aa1!",
        "Screenshot_2024.PNG",
        "1234567890",
        "SELECT * FROM clipboard_items WHERE id = 1;",
        # User review cases
        "PWD=/home/kareem/StudioProjects/DotGhostBoard",
        "password = self.pw_input.text()",
        "Password: required",
        "Phase7VaultPanel",
        "getUserById(42)",
        "feature/Phase7Vault",
        "com.example.MyApp1",
        # New false positive test cases from dev workflows
        "2024-09-21T10:30:00Z",
        "00:1A:2B:3C:4D:5E",
        "Invoice_2024_Final",
        "Project_Plan_v2",
        "MAX_RETRIES_3",
        "feature-Phase7Vault",
        # SSH commands, package versions, query strings & URL-encoding
        "kali@10.0.2.15",
        "ssh root@192.168.1.5",
        "react@18.2.0",
        "page=2&sort=desc",
        "q%3Dhello%26page%3D2",
        # Variable assignments and sentences
        "password = DEFAULT_PASSWORD",
        "password = self.password_hash",
        "password: at least 8 characters",
    ]
    for sample in negative_samples:
        assert detector.analyze(sample) is None, f"False positive on negative sample: {sample}"
        assert detector.is_secret(sample) is False

    # Multiline code file containing one 'password = None' line
    multiline_code = "\n".join(
        [f"x_{i} = {i}" for i in range(20)]
        + ["password = None"]
        + [f"y_{i} = {i}" for i in range(20)]
    )
    assert detector.analyze(multiline_code) is None
    assert detector.is_secret(multiline_code) is False


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

    # 3. Password candidate event -> SECRET_CANDIDATE
    pw_event = ClipboardEvent(content_type="text", content="TestMasterPass123!")
    pw_decision = pipeline.process(pw_event)
    assert pw_decision.action == Action.SECRET_CANDIDATE
