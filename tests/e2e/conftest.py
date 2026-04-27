"""E2E test configuration.

Loads credentials from .env.test (created by scripts/setup-e2e.sh)
and provides fixtures for E2E tests against real local services.

All tests in this directory are skipped unless --e2e is passed.
"""

from pathlib import Path

import pytest
from dotenv import load_dotenv

from autopoc.config import AutoPoCConfig
from autopoc.tools.gitlab_tools import GitLabClient


# --- Skip all E2E tests unless --e2e flag is passed ---


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip E2E tests unless --e2e is passed."""
    if config.getoption("--e2e"):
        return

    skip_e2e = pytest.mark.skip(reason="E2E tests require --e2e flag and local Docker services")
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(skip_e2e)


# --- Load .env.test ---

ENV_TEST_PATH = Path(__file__).parent.parent.parent / ".env.test"


@pytest.fixture(scope="session", autouse=True)
def load_e2e_env() -> None:
    """Load .env.test if it exists."""
    if ENV_TEST_PATH.exists():
        load_dotenv(str(ENV_TEST_PATH), override=True)
    else:
        pytest.skip(f".env.test not found at {ENV_TEST_PATH}. Run scripts/setup-e2e.sh first.")


# --- Fixtures ---


@pytest.fixture(scope="session")
def e2e_config() -> AutoPoCConfig:
    """Load AutoPoC config from .env.test.

    Session-scoped so we don't reload for every test.
    """
    return AutoPoCConfig(_env_file=str(ENV_TEST_PATH))  # type: ignore[call-arg]


@pytest.fixture(scope="session")
def gitlab_client(e2e_config: AutoPoCConfig) -> GitLabClient:
    """Provide a GitLabClient connected to local GitLab CE."""
    client = GitLabClient(e2e_config)
    # Sanity check: verify we can reach GitLab
    try:
        client.get_project("__nonexistent__")
        # If we get here without exception, the API is reachable
    except Exception as e:
        pytest.skip(f"Cannot connect to local GitLab: {e}")
    return client


@pytest.fixture
def e2e_work_dir(tmp_path: Path) -> Path:
    """Provide a temp working directory for E2E tests."""
    work = tmp_path / "autopoc-e2e"
    work.mkdir()
    return work


@pytest.fixture
def unique_project_name() -> str:
    """Generate a unique project name to avoid collisions between test runs."""
    import time

    return f"e2e-test-{int(time.time())}"


@pytest.fixture
def cleanup_gitlab_project(gitlab_client: GitLabClient):
    """Fixture that cleans up created GitLab projects after the test.

    Usage:
        def test_something(cleanup_gitlab_project):
            cleanup_gitlab_project("my-project")
            # ... test creates "my-project" on GitLab
            # cleanup happens automatically after test
    """
    projects_to_delete: list[str] = []

    def _register(name: str) -> None:
        projects_to_delete.append(name)

    yield _register

    for name in projects_to_delete:
        try:
            project = gitlab_client.get_project(name)
            if project:
                gitlab_client._client.delete(f"/projects/{project['id']}")
        except Exception:
            pass  # Best effort cleanup
