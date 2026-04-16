"""Tests for the fork agent."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autopoc.agents.fork import fork_agent
from autopoc.config import AutoPoCConfig
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.gitlab_tools import GitLabClient


@pytest.fixture
def fork_config(tmp_path: Path) -> AutoPoCConfig:
    """Config with work_dir pointing to tmp_path."""
    return AutoPoCConfig(
        anthropic_api_key="sk-test",
        gitlab_url="https://gitlab.example.com",
        gitlab_token="glpat-test-token",
        gitlab_group="poc-demos",
        quay_org="org",
        quay_token="tok",
        openshift_api_url="https://api.example.com:6443",
        openshift_token="tok",
        work_dir=str(tmp_path / "work"),
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
        ["git", "config", "user.name", "Test"], cwd=str(repo), check=True, capture_output=True
    )
    (repo / "README.md").write_text("# Test Project\n")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=str(repo), check=True, capture_output=True
    )
    return repo


@pytest.fixture
def gitlab_remote(tmp_path: Path) -> Path:
    """Create a bare git repo to act as the 'GitLab' remote."""
    bare = tmp_path / "gitlab-remote.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


@pytest.fixture
def mock_gitlab_client(gitlab_remote: Path) -> MagicMock:
    """Create a mock GitLabClient that returns the bare repo as clone URL."""
    client = MagicMock(spec=GitLabClient)
    client.get_project.return_value = None  # Project doesn't exist yet
    client.create_project.return_value = {
        "id": 42,
        "name": "test-project",
        "path_with_namespace": "poc-demos/test-project",
        "http_url_to_repo": str(gitlab_remote),
    }
    client.get_project_clone_url.return_value = str(gitlab_remote)
    return client


@pytest.fixture
def initial_state(source_repo: Path) -> PoCState:
    """Initial state for fork agent."""
    return PoCState(
        project_name="test-project",
        source_repo_url=str(source_repo),
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


class TestForkAgent:
    @pytest.mark.asyncio
    async def test_happy_path_new_project(
        self,
        initial_state: PoCState,
        fork_config: AutoPoCConfig,
        mock_gitlab_client: MagicMock,
    ) -> None:
        """Fork agent clones, creates GitLab project, and pushes."""
        result = await fork_agent(
            initial_state,
            app_config=fork_config,
            gitlab_client=mock_gitlab_client,
        )

        # Project was created
        mock_gitlab_client.get_project.assert_called_once_with("test-project")
        mock_gitlab_client.create_project.assert_called_once_with("test-project")

        # State was updated (fork does NOT set current_phase because it runs
        # in parallel with poc_plan — both writing to current_phase would
        # cause a LangGraph state conflict)
        assert "current_phase" not in result
        assert result["gitlab_repo_url"] is not None
        assert result["local_clone_path"] is not None
        assert Path(result["local_clone_path"]).is_dir()

    @pytest.mark.asyncio
    async def test_project_already_exists(
        self,
        initial_state: PoCState,
        fork_config: AutoPoCConfig,
        mock_gitlab_client: MagicMock,
        gitlab_remote: Path,
    ) -> None:
        """Fork agent skips creation if project already exists on GitLab."""
        mock_gitlab_client.get_project.return_value = {
            "id": 42,
            "name": "test-project",
            "path_with_namespace": "poc-demos/test-project",
            "http_url_to_repo": str(gitlab_remote),
        }

        result = await fork_agent(
            initial_state,
            app_config=fork_config,
            gitlab_client=mock_gitlab_client,
        )

        # create_project should NOT be called
        mock_gitlab_client.create_project.assert_not_called()

        # But should still push
        assert "current_phase" not in result
        assert result["gitlab_repo_url"] is not None

    @pytest.mark.asyncio
    async def test_reuses_existing_clone(
        self,
        initial_state: PoCState,
        fork_config: AutoPoCConfig,
        mock_gitlab_client: MagicMock,
        source_repo: Path,
    ) -> None:
        """Fork agent reuses local_clone_path if already set."""
        # Pre-set the clone path to the source repo itself
        initial_state["local_clone_path"] = str(source_repo)

        result = await fork_agent(
            initial_state,
            app_config=fork_config,
            gitlab_client=mock_gitlab_client,
        )

        # Clone path should be the same as what was provided
        assert result["local_clone_path"] == str(source_repo)

    @pytest.mark.asyncio
    async def test_push_reaches_remote(
        self,
        initial_state: PoCState,
        fork_config: AutoPoCConfig,
        mock_gitlab_client: MagicMock,
        gitlab_remote: Path,
    ) -> None:
        """Verify that git push actually reaches the 'GitLab' bare repo."""
        await fork_agent(
            initial_state,
            app_config=fork_config,
            gitlab_client=mock_gitlab_client,
        )

        # Check the bare repo has commits
        log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(gitlab_remote),
            capture_output=True,
            text=True,
        )
        assert "initial" in log.stdout
