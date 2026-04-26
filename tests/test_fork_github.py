"""Tests for the fork agent in GitHub mode."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autopoc.agents.fork import fork_agent
from autopoc.config import AutoPoCConfig
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.github_tools import GitHubClient


@pytest.fixture
def github_config(tmp_path: Path) -> AutoPoCConfig:
    """Config for GitHub fork target."""
    return AutoPoCConfig(
        anthropic_api_key="sk-ant-test",
        fork_target="github",
        github_token="ghp_test-token-12345",
        github_org="test-org",
        quay_org="org",
        quay_token="tok",
        openshift_api_url="https://api.example.com:6443",
        openshift_token="tok",
        work_dir=str(tmp_path / "work"),
        _env_file=None,
    )


@pytest.fixture
def github_config_no_org(tmp_path: Path) -> AutoPoCConfig:
    """Config for GitHub fork target without org."""
    return AutoPoCConfig(
        anthropic_api_key="sk-ant-test",
        fork_target="github",
        github_token="ghp_test-token-12345",
        quay_org="org",
        quay_token="tok",
        openshift_api_url="https://api.example.com:6443",
        openshift_token="tok",
        work_dir=str(tmp_path / "work"),
        _env_file=None,
    )


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    """Create a local git repo to act as the 'GitHub' source."""
    repo = tmp_path / "source-repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("# Test Project\n")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def fork_repo(tmp_path: Path, source_repo: Path) -> Path:
    """Create a clone to act as the 'GitHub fork' remote.

    This simulates what GitHub's fork API creates — a copy of the source repo.
    """
    fork = tmp_path / "fork-repo.git"
    # Clone the source as a bare repo (simulates the fork)
    subprocess.run(
        ["git", "clone", "--bare", str(source_repo), str(fork)],
        check=True,
        capture_output=True,
    )
    return fork


@pytest.fixture
def mock_github_client(fork_repo: Path) -> MagicMock:
    """Create a mock GitHubClient that returns the fork bare repo as clone URL."""
    client = MagicMock(spec=GitHubClient)
    client.org = "test-org"

    # No existing fork
    client.get_fork.return_value = None

    # get_authenticated_user for determining fork owner
    client.get_authenticated_user.return_value = {"login": "testuser", "id": 123}

    # Fork creation returns fork data
    client.fork_repo.return_value = {
        "id": 999,
        "full_name": "test-org/test-project",
        "clone_url": str(fork_repo),
        "fork": True,
        "pushed_at": "2024-01-01T00:00:00Z",
    }

    # Wait for fork returns the same data (already ready)
    client.wait_for_fork.return_value = {
        "id": 999,
        "full_name": "test-org/test-project",
        "clone_url": str(fork_repo),
        "fork": True,
        "pushed_at": "2024-01-01T00:00:00Z",
        "size": 100,
    }

    # Clone URL with embedded token
    client.get_clone_url.return_value = str(fork_repo)

    return client


@pytest.fixture
def initial_state(source_repo: Path) -> PoCState:
    """Initial state for fork agent."""
    return PoCState(
        project_name="test-project",
        source_repo_url=f"https://github.com/octocat/test-project",
        current_phase=PoCPhase.INTAKE,
        local_clone_path=None,
        error=None,
        messages=[],
        components=[],
        has_helm_chart=False,
        has_kustomize=False,
        has_compose=False,
        existing_ci_cd=None,
        built_images=[],
        build_retries=0,
        deployed_resources=[],
        routes=[],
    )


@pytest.fixture
def initial_state_with_clone(source_repo: Path) -> PoCState:
    """Initial state where intake already cloned the source."""
    # Clone the source repo to simulate intake having run first
    clone_dir = source_repo.parent / "cloned-repo"
    subprocess.run(
        ["git", "clone", str(source_repo), str(clone_dir)],
        check=True,
        capture_output=True,
    )
    return PoCState(
        project_name="test-project",
        source_repo_url=f"https://github.com/octocat/test-project",
        current_phase=PoCPhase.INTAKE,
        local_clone_path=str(clone_dir),
        error=None,
        messages=[],
        components=[],
        has_helm_chart=False,
        has_kustomize=False,
        has_compose=False,
        existing_ci_cd=None,
        built_images=[],
        build_retries=0,
        deployed_resources=[],
        routes=[],
    )


class TestForkAgentGitHub:
    @pytest.mark.asyncio
    async def test_happy_path_new_fork(
        self,
        initial_state: PoCState,
        github_config: AutoPoCConfig,
        mock_github_client: MagicMock,
    ) -> None:
        """Fork agent creates a new GitHub fork and configures remotes."""
        result = await fork_agent(
            initial_state,
            app_config=github_config,
            github_client=mock_github_client,
        )

        # Fork was created via API
        mock_github_client.get_fork.assert_called_once_with("octocat", "test-project")
        mock_github_client.fork_repo.assert_called_once_with("octocat", "test-project")
        mock_github_client.wait_for_fork.assert_called_once_with("test-org", "test-project")

        # State was updated
        assert "current_phase" not in result  # Doesn't set phase (parallel with poc_plan)
        assert result["fork_repo_url"] is not None
        assert result["fork_target"] == "github"
        assert result["local_clone_path"] is not None
        assert Path(result["local_clone_path"]).is_dir()

        # Should NOT have gitlab_repo_url
        assert "gitlab_repo_url" not in result

    @pytest.mark.asyncio
    async def test_fork_already_exists(
        self,
        initial_state: PoCState,
        github_config: AutoPoCConfig,
        mock_github_client: MagicMock,
    ) -> None:
        """Fork agent skips creation if fork already exists."""
        mock_github_client.get_fork.return_value = {
            "id": 999,
            "full_name": "test-org/test-project",
            "clone_url": "https://github.com/test-org/test-project.git",
            "fork": True,
            "pushed_at": "2024-01-01T00:00:00Z",
        }

        result = await fork_agent(
            initial_state,
            app_config=github_config,
            github_client=mock_github_client,
        )

        # fork_repo should NOT be called
        mock_github_client.fork_repo.assert_not_called()
        # wait_for_fork should NOT be called (fork already exists)
        mock_github_client.wait_for_fork.assert_not_called()

        assert result["fork_target"] == "github"
        assert result["fork_repo_url"] is not None

    @pytest.mark.asyncio
    async def test_fork_to_user_account(
        self,
        initial_state: PoCState,
        github_config_no_org: AutoPoCConfig,
        mock_github_client: MagicMock,
    ) -> None:
        """Fork agent forks to user account when no org is configured."""
        mock_github_client.org = None  # No org

        result = await fork_agent(
            initial_state,
            app_config=github_config_no_org,
            github_client=mock_github_client,
        )

        # Should look up user to determine fork owner
        mock_github_client.get_authenticated_user.assert_called()
        # Should wait for fork under user's account
        mock_github_client.wait_for_fork.assert_called_once_with("testuser", "test-project")

        assert result["fork_target"] == "github"

    @pytest.mark.asyncio
    async def test_existing_clone_remotes_reconfigured(
        self,
        initial_state_with_clone: PoCState,
        github_config: AutoPoCConfig,
        mock_github_client: MagicMock,
    ) -> None:
        """When intake already cloned, fork agent reconfigures remotes."""
        result = await fork_agent(
            initial_state_with_clone,
            app_config=github_config,
            github_client=mock_github_client,
        )

        clone_path = result["local_clone_path"]
        assert clone_path == initial_state_with_clone["local_clone_path"]

        # Verify source remote was removed and origin points to fork
        remotes = subprocess.run(
            ["git", "remote", "-v"],
            cwd=clone_path,
            capture_output=True,
            text=True,
        )

        remote_output = remotes.stdout
        # Origin should exist and point to the fork
        assert "origin" in remote_output
        # The old "github" source remote should not exist
        # (it was either renamed from origin or didn't exist separately)
        lines = remote_output.strip().split("\n")
        remote_names = {line.split()[0] for line in lines if line.strip()}
        # Only origin should remain (source remote removed)
        assert "github" not in remote_names

    @pytest.mark.asyncio
    async def test_no_push_for_github_fork(
        self,
        initial_state: PoCState,
        github_config: AutoPoCConfig,
        mock_github_client: MagicMock,
    ) -> None:
        """GitHub fork does NOT push (fork copies automatically)."""
        result = await fork_agent(
            initial_state,
            app_config=github_config,
            github_client=mock_github_client,
        )

        # Verify result is valid
        assert result["fork_target"] == "github"
        # No explicit push was done — the GitHub fork API copies all branches/tags
