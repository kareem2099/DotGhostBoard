"""
tests/conftest.py
─────────────────
Global pytest configuration and shared fixtures for DotGhostBoard.
"""

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single persistent QApplication instance exists for Qt GUI tests."""
    app = QApplication.instance()
    if not app:
        app = QApplication(["DotGhostBoard-Tests"])
    return app
