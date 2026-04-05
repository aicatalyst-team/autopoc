"""E2E tests for the intake and fork agents against a real local GitLab CE.

These tests require:
  1. Local GitLab CE running (via scripts/setup-e2e.sh)
  2. .env.test with valid credentials
  3. --e2e flag passed to pytest

The tests use a real GitHub repo (small, public) for the intake + fork flow.
LLM calls are mocked to avoid requiring an Anthropic API key.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from autopoc.agents.fork import fork_agent
from autopoc.agents.intake import intake_agent
from autopoc.config import AutoPoCConfig
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.gitlab_tools import GitLabClient


# --- Test: GitLab connectivity ---


class TestGitLabConnectivity:
    """Verify basic GitLab API connectivity."""

    def test_gitlab_api_reachable(self, gitlab_client: GitLabClient) -> None:
        """GitLab API responds to requests."""
        # get_project returns None for nonexistent project (not an error)
        result = gitlab_client.get_project("__this-does-not-exist__")
        assert result is None

    def test_gitlab_group_exists(self, gitlab_client: GitLabClient) -> None:
        """The poc-demos group exists on the local GitLab."""
        group_id = gitlab_client._get_group_id()
        assert isinstance(group_id, int)
        assert group_id > 0


# --- Test: Fork agent against real GitLab ---


class TestForkAgentE2E:
    """Test the fork agent against a real local GitLab instance."""

    @pytest.fixture
    def local_source_repo(self, e2e_work_dir: Path) -> Path:
        """Create a local git repo to use as 'GitHub' source."""
        repo = e2e_work_dir / "source"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "E2E Test"],
            cwd=str(repo),
            check=True,
            capture_output=True,
        )
        (repo / "README.md").write_text("# E2E Test Project\n")
        (repo / "app.py").write_text("print('hello')\n")
        (repo / "requirements.txt").write_text("flask==3.0\n")
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial commit"],
            cwd=str(repo),
            check=True,
            capture_output=True,
        )
        return repo

    @pytest.mark.asyncio
    async def test_fork_creates_project_on_gitlab(
        self,
        local_source_repo: Path,
        e2e_config: AutoPoCConfig,
        gitlab_client: GitLabClient,
        unique_project_name: str,
        cleanup_gitlab_project,
        e2e_work_dir: Path,
    ) -> None:
        """Fork agent creates a real project on local GitLab and pushes code."""
        cleanup_gitlab_project(unique_project_name)

        # Build initial state
        state = PoCState(
            project_name=unique_project_name,
            source_repo_url=str(local_source_repo),
            current_phase=PoCPhase.INTAKE,
            local_clone_path=str(local_source_repo),
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

        # Run fork agent against real GitLab
        result = await fork_agent(
            state,
            app_config=e2e_config,
            gitlab_client=gitlab_client,
        )

        # Verify project was created on GitLab
        assert result["current_phase"] == PoCPhase.FORK
        assert result["gitlab_repo_url"] is not None

        project = gitlab_client.get_project(unique_project_name)
        assert project is not None
        assert project["name"] == unique_project_name

    @pytest.mark.asyncio
    async def test_fork_pushes_commits_to_gitlab(
        self,
        local_source_repo: Path,
        e2e_config: AutoPoCConfig,
        gitlab_client: GitLabClient,
        unique_project_name: str,
        cleanup_gitlab_project,
        e2e_work_dir: Path,
    ) -> None:
        """Fork agent pushes commits that are visible via GitLab API."""
        cleanup_gitlab_project(unique_project_name)

        state = PoCState(
            project_name=unique_project_name,
            source_repo_url=str(local_source_repo),
            current_phase=PoCPhase.INTAKE,
            local_clone_path=str(local_source_repo),
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

        await fork_agent(
            state,
            app_config=e2e_config,
            gitlab_client=gitlab_client,
        )

        # Query GitLab API for the project's repository tree
        project = gitlab_client.get_project(unique_project_name)
        assert project is not None

        # Get the repo tree via API
        tree_response = gitlab_client._client.get(f"/projects/{project['id']}/repository/tree")
        tree_response.raise_for_status()
        tree = tree_response.json()
        file_names = [f["name"] for f in tree]

        assert "README.md" in file_names
        assert "app.py" in file_names
        assert "requirements.txt" in file_names

    @pytest.mark.asyncio
    async def test_fork_idempotent(
        self,
        local_source_repo: Path,
        e2e_config: AutoPoCConfig,
        gitlab_client: GitLabClient,
        unique_project_name: str,
        cleanup_gitlab_project,
        e2e_work_dir: Path,
    ) -> None:
        """Running fork twice doesn't fail — it skips project creation."""
        cleanup_gitlab_project(unique_project_name)

        state = PoCState(
            project_name=unique_project_name,
            source_repo_url=str(local_source_repo),
            current_phase=PoCPhase.INTAKE,
            local_clone_path=str(local_source_repo),
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

        # First run — creates project
        result1 = await fork_agent(state, app_config=e2e_config, gitlab_client=gitlab_client)
        assert result1["gitlab_repo_url"] is not None

        # Second run — should skip creation, still succeed
        result2 = await fork_agent(state, app_config=e2e_config, gitlab_client=gitlab_client)
        assert result2["gitlab_repo_url"] is not None


# --- Test: Intake + Fork flow (LLM mocked, GitLab real) ---


class TestIntakeForkFlowE2E:
    """Test the combined intake + fork flow.

    The intake agent's LLM calls are mocked (to avoid requiring an API key),
    but the fork agent runs against real GitLab.
    """

    @pytest.fixture
    def local_flask_repo(self, e2e_work_dir: Path) -> Path:
        """Create a local git repo that looks like a Flask app."""
        repo = e2e_work_dir / "flask-source"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "E2E Test"],
            cwd=str(repo),
            check=True,
            capture_output=True,
        )
        (repo / "app.py").write_text(
            "from flask import Flask\n"
            "app = Flask(__name__)\n\n"
            "@app.route('/')\n"
            "def hello(): return 'Hello'\n\n"
            "if __name__ == '__main__':\n"
            "    app.run(port=5000)\n"
        )
        (repo / "requirements.txt").write_text("flask==3.0.0\ngunicorn==21.2.0\n")
        (repo / "README.md").write_text("# Flask E2E Test App\n")
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial flask app"],
            cwd=str(repo),
            check=True,
            capture_output=True,
        )
        return repo

    @pytest.mark.asyncio
    async def test_intake_then_fork(
        self,
        local_flask_repo: Path,
        e2e_config: AutoPoCConfig,
        gitlab_client: GitLabClient,
        unique_project_name: str,
        cleanup_gitlab_project,
    ) -> None:
        """Run intake (mocked LLM) then fork (real GitLab) sequentially."""
        cleanup_gitlab_project(unique_project_name)

        # --- Intake (mocked LLM) ---
        intake_state = PoCState(
            project_name=unique_project_name,
            source_repo_url=str(local_flask_repo),
            current_phase=PoCPhase.INTAKE,
            local_clone_path=str(local_flask_repo),
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

        # Mock the LLM response for intake
        from langchain_core.messages import AIMessage

        intake_response = json.dumps(
            {
                "repo_summary": "A simple Flask web application.",
                "components": [
                    {
                        "name": "app",
                        "language": "python",
                        "build_system": "pip",
                        "entry_point": "app.py",
                        "port": 5000,
                        "existing_dockerfile": None,
                        "is_ml_workload": False,
                        "source_dir": ".",
                    }
                ],
                "has_helm_chart": False,
                "has_kustomize": False,
                "has_compose": False,
                "existing_ci_cd": None,
            }
        )

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"messages": [AIMessage(content=intake_response)]}

        with patch("autopoc.agents.intake.create_react_agent", return_value=mock_agent):
            intake_result = await intake_agent(intake_state, llm=AsyncMock())

        # Verify intake worked
        assert len(intake_result["components"]) == 1
        assert intake_result["components"][0]["name"] == "app"

        # --- Fork (real GitLab) ---
        fork_state = dict(intake_state)
        fork_state.update(intake_result)

        fork_result = await fork_agent(
            fork_state,
            app_config=e2e_config,
            gitlab_client=gitlab_client,
        )

        # Verify fork worked
        assert fork_result["gitlab_repo_url"] is not None

        # Verify project exists on GitLab with the right files
        project = gitlab_client.get_project(unique_project_name)
        assert project is not None

        tree_response = gitlab_client._client.get(f"/projects/{project['id']}/repository/tree")
        tree_response.raise_for_status()
        file_names = [f["name"] for f in tree_response.json()]
        assert "app.py" in file_names
        assert "requirements.txt" in file_names
