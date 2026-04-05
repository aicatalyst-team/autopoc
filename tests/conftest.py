"""Shared test fixtures for AutoPoC."""

import os
from collections.abc import Generator
from unittest.mock import patch

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the --e2e command-line option."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run E2E tests against local Docker services (requires setup-e2e.sh)",
    )


# Full set of valid env vars for config tests
VALID_ENV = {
    "ANTHROPIC_API_KEY": "sk-ant-test-key-12345",
    "GITLAB_URL": "https://gitlab.example.com",
    "GITLAB_TOKEN": "glpat-test-token-67890",
    "GITLAB_GROUP": "poc-demos",
    "QUAY_REGISTRY": "quay.io",
    "QUAY_ORG": "test-org",
    "QUAY_TOKEN": "quay-test-token-abc",
    "OPENSHIFT_API_URL": "https://api.cluster.example.com:6443",
    "OPENSHIFT_TOKEN": "sha256~test-token-xyz",
    "OPENSHIFT_NAMESPACE_PREFIX": "poc",
    "MAX_BUILD_RETRIES": "3",
    "WORK_DIR": "/tmp/autopoc-test",
}


@pytest.fixture
def env_vars() -> Generator[dict[str, str], None, None]:
    """Provide a clean environment with all required config vars set.

    Clears any real .env file influence by patching os.environ directly.
    """
    with patch.dict(os.environ, VALID_ENV, clear=True):
        yield VALID_ENV


@pytest.fixture
def env_vars_minimal() -> Generator[dict[str, str], None, None]:
    """Provide only the required env vars (no optional ones with defaults)."""
    minimal = {
        "ANTHROPIC_API_KEY": "sk-ant-test-key-12345",
        "GITLAB_URL": "https://gitlab.example.com",
        "GITLAB_TOKEN": "glpat-test-token-67890",
        "GITLAB_GROUP": "poc-demos",
        "QUAY_ORG": "test-org",
        "QUAY_TOKEN": "quay-test-token-abc",
        "OPENSHIFT_API_URL": "https://api.cluster.example.com:6443",
        "OPENSHIFT_TOKEN": "sha256~test-token-xyz",
    }
    with patch.dict(os.environ, minimal, clear=True):
        yield minimal
