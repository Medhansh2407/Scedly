"""
Shared pytest configuration for the backend test suite.

- Registers the `integration` marker so unit tests can run by default with
  `pytest -m "not integration"` and we don't get unknown-marker warnings.
- Configures pytest-asyncio's default mode so `async def` tests are picked up
  without per-test decorators.
"""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests that hit a real LLM provider (skipped without API keys)",
    )
