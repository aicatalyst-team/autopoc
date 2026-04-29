"""Integration test: intake → fork → containerize graph flow.

Tests the full graph with mocked LLM and mocked GitLab API,
but real git operations on temp repos.
"""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopoc.graph import build_graph
from autopoc.state import PoCPhase, PoCState


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo that looks like a Python Flask app."""
    repo = tmp_path / "sample-repo"
    repo.mkdir()

    # Init git repo
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

    # Create sample files
    (repo / "app.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
    (repo / "requirements.txt").write_text("flask==3.0.0\n")
    (repo / "README.md").write_text("# Sample App\n")

    # Commit
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def gitlab_bare(tmp_path: Path) -> Path:
    """Create a bare git repo to act as GitLab remote."""
    bare = tmp_path / "gitlab.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


@pytest.fixture
def initial_state(sample_repo: Path) -> PoCState:
    """Initial state for the graph."""
    return PoCState(
        project_name="sample-app",
        source_repo_url=str(sample_repo),
        current_phase=PoCPhase.INTAKE,
        error=None,
        messages=[],
        gitlab_repo_url=None,
        local_clone_path=None,
        repo_summary="",
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


INTAKE_JSON_RESPONSE = json.dumps(
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


def _make_containerize_mock_agent() -> AsyncMock:
    """Mock agent for containerize that returns a canned Dockerfile path."""
    from langchain_core.messages import AIMessage

    response = json.dumps(
        {
            "dockerfile_ubi_path": "Dockerfile.ubi",
            "base_image": "registry.access.redhat.com/ubi9/python-312",
            "strategy": "single-stage",
            "notes": "Created from scratch for Flask app",
        }
    )

    mock = AsyncMock()
    mock.ainvoke.return_value = {"messages": [AIMessage(content=response)]}
    return mock


class TestGraphPartial:
    @pytest.mark.asyncio
    async def test_full_flow_intake_fork_containerize(
        self,
        initial_state: PoCState,
        gitlab_bare: Path,
        tmp_path: Path,
    ) -> None:
        """Full graph: intake → fork → containerize with mocks."""

        # Mock GitLab client
        mock_gitlab = MagicMock()
        mock_gitlab.get_project.return_value = None
        mock_gitlab.create_project.return_value = {
            "id": 1,
            "name": "sample-app",
            "path_with_namespace": "poc/sample-app",
            "http_url_to_repo": str(gitlab_bare),
        }
        mock_gitlab.get_project_clone_url.return_value = str(gitlab_bare)

        # Mock config for fork agent
        mock_config = MagicMock()
        mock_config.work_dir = str(tmp_path / "work")

        # Set up env vars so load_config doesn't fail
        env_patch = {
            "ANTHROPIC_API_KEY": "sk-test",
            "FORK_TARGET": "gitlab",
            "GITLAB_URL": "https://gitlab.test",
            "GITLAB_TOKEN": "tok",
            "GITLAB_GROUP": "poc",
            "QUAY_ORG": "org",
            "QUAY_TOKEN": "tok",
            "OPENSHIFT_API_URL": "https://api.test:6443",
            "OPENSHIFT_TOKEN": "tok",
            "WORK_DIR": str(tmp_path / "work"),
        }

        containerize_mock = _make_containerize_mock_agent()

        # Mock LLM for intake (one-shot, returns AIMessage directly)
        from langchain_core.messages import AIMessage as AI

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AI(content=INTAKE_JSON_RESPONSE)

        def mock_create_react_agent(**kwargs):
            return containerize_mock

        # Generic mock agent for downstream nodes (poc_plan, deploy, etc.)
        # Returns minimal valid state so the graph can proceed through each node.
        generic_mock_agent = AsyncMock()
        generic_mock_agent.ainvoke.return_value = {"messages": [AI(content="{}")]}

        def mock_create_react_agent_generic(**kwargs):
            return generic_mock_agent

        # Generic mock LLM for any agent that calls create_llm() directly
        generic_mock_llm = AsyncMock()
        generic_mock_llm.ainvoke.return_value = AI(content="{}")

        with (
            patch.dict(os.environ, env_patch, clear=True),
            # Intake: mock LLM and git_clone (intake no longer uses create_react_agent)
            patch("autopoc.agents.intake.create_llm", return_value=mock_llm),
            patch("autopoc.agents.intake.git_clone") as mock_clone,
            patch(
                "autopoc.agents.intake.build_repo_digest", return_value="# Digest\nSample flask app"
            ),
            # Containerize: uses create_react_agent
            patch(
                "autopoc.agents.containerize.create_react_agent",
                side_effect=mock_create_react_agent,
            ),
            patch("autopoc.agents.fork.GitLabClient", return_value=mock_gitlab),
            patch("autopoc.agents.containerize.git_commit"),
            patch("autopoc.agents.containerize.git_push"),
            patch("autopoc.agents.build.QuayClient"),
            patch("autopoc.agents.build.get_build_strategy"),
            # Mock create_llm for all remaining agents so no real API calls are made
            patch("autopoc.agents.poc_plan.create_llm", return_value=generic_mock_llm),
            patch("autopoc.agents.build.create_llm", return_value=generic_mock_llm),
            patch("autopoc.agents.deploy.create_llm", return_value=generic_mock_llm),
            patch("autopoc.agents.poc_execute.create_llm", return_value=generic_mock_llm),
            patch("autopoc.agents.poc_report.create_llm", return_value=generic_mock_llm),
            # Mock create_react_agent for all remaining agents that use it
            patch(
                "autopoc.agents.poc_plan.create_react_agent",
                side_effect=mock_create_react_agent_generic,
            ),
            patch(
                "autopoc.agents.deploy.create_react_agent",
                side_effect=mock_create_react_agent_generic,
            ),
            patch(
                "autopoc.agents.poc_execute.create_react_agent",
                side_effect=mock_create_react_agent_generic,
            ),
            patch(
                "autopoc.agents.apply.create_react_agent",
                side_effect=mock_create_react_agent_generic,
            ),
        ):
            # Make git_clone return success (the clone_path directory already exists from sample_repo)
            mock_clone.invoke.return_value = f"Cloned to {tmp_path / 'work' / 'sample-app'}"
            graph = build_graph()
            result = await graph.ainvoke(initial_state)

        # Verify intake ran
        assert result.get("repo_summary") == "A simple Flask web application."
        assert len(result.get("components", [])) == 1
        assert result["components"][0]["name"] == "app"
        assert result["components"][0]["language"] == "python"

        # Verify fork ran
        assert result.get("gitlab_repo_url") is not None
        assert result.get("local_clone_path") is not None
        assert Path(result["local_clone_path"]).is_dir()

        # Verify containerize ran
        assert result["components"][0].get("dockerfile_ubi_path") == "Dockerfile.ubi"

        # Verify the repo was actually pushed to the "GitLab" bare repo
        log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(gitlab_bare),
            capture_output=True,
            text=True,
        )
        assert "initial" in log.stdout

    @pytest.mark.asyncio
    async def test_graph_compiles(self) -> None:
        """Graph compiles without errors."""
        graph = build_graph()
        nodes = list(graph.get_graph().nodes.keys())
        assert "__start__" in nodes
        assert "intake" in nodes
        assert "fork" in nodes
        assert "containerize" in nodes
        assert "build" in nodes
        assert "__end__" in nodes
