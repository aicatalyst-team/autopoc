"""E2E tests for the build agent against a real local Quay instance.

These tests require:
  1. Local Quay stack running (via scripts/setup-e2e.sh)
  2. .env.test with valid Quay credentials
  3. --e2e flag passed to pytest
"""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from autopoc.agents.build import build_agent
from autopoc.config import AutoPoCConfig
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.quay_tools import QuayClient


# --- Fixtures ---


@pytest.fixture(scope="session")
def quay_client(e2e_config: AutoPoCConfig) -> QuayClient:
    """Provide a QuayClient connected to local Quay instance."""
    client = QuayClient(e2e_config)
    # Sanity check: verify we can reach Quay
    try:
        # Check a nonexistent repo just to test connectivity/auth
        client.repo_exists(e2e_config.quay_org, "__nonexistent__")
    except Exception as e:
        pytest.skip(f"Cannot connect to local Quay: {e}")
    return client


@pytest.fixture
def local_build_repo(e2e_work_dir: Path) -> Path:
    """Create a local git repo with a functional Dockerfile.ubi."""
    repo = e2e_work_dir / "build-source"
    repo.mkdir(exist_ok=True)

    # Create a tiny functional node app
    (repo / "index.js").write_text("console.log('hello build');\n")
    (repo / "package.json").write_text('{"name":"test","main":"index.js"}\n')

    # Create a valid Dockerfile.ubi
    (repo / "Dockerfile.ubi").write_text(
        "FROM registry.access.redhat.com/ubi9/nodejs-22\n"
        "USER 0\n"
        "WORKDIR /opt/app-root/src\n"
        "COPY package.json index.js ./\n"
        "RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root\n"
        "USER 1001\n"
        'CMD ["node", "index.js"]\n'
    )

    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial build app"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def cleanup_podman_images():
    """Fixture to clean up images generated during the test."""
    images_to_delete = []

    def _register(image_ref: str):
        images_to_delete.append(image_ref)

    yield _register

    for image in images_to_delete:
        try:
            subprocess.run(["podman", "rmi", "-f", image], capture_output=True)
        except Exception:
            pass


# --- Tests ---


class TestBuildAgentE2E:
    """Test the build agent against a local E2E Quay instance."""

    @pytest.mark.asyncio
    async def test_build_and_push_success(
        self,
        local_build_repo: Path,
        e2e_config: AutoPoCConfig,
        quay_client: QuayClient,
        unique_project_name: str,
        cleanup_podman_images,
    ) -> None:
        """Verify the build agent can build an image and push it to Quay."""

        # Build state representing the output of a successful containerize phase
        state = PoCState(
            project_name=unique_project_name,
            source_repo_url=str(local_build_repo),
            current_phase=PoCPhase.CONTAINERIZE,
            local_clone_path=str(local_build_repo),
            error=None,
            messages=[],
            components=[
                {
                    "name": "nodeapp",
                    "language": "node",
                    "build_system": "npm",
                    "entry_point": "index.js",
                    "port": 3000,
                    "existing_dockerfile": None,
                    "is_ml_workload": False,
                    "source_dir": ".",
                    "dockerfile_ubi_path": "Dockerfile.ubi",
                }
            ],
            has_helm_chart=False,
            has_kustomize=False,
            has_compose=False,
            existing_ci_cd=None,
            built_images=[],
            build_retries=0,
            deployed_resources=[],
            routes=[],
        )

        registry = e2e_config.quay_registry
        if "://" in registry:
            registry = registry.split("://", 1)[1]

        expected_image_ref = (
            f"{registry}/{e2e_config.quay_org}/{unique_project_name}-nodeapp:latest"
        )

        # In case the image exists locally from a previous dirty run
        cleanup_podman_images(expected_image_ref)

        result = await build_agent(
            state,
            app_config=e2e_config,
            quay_client=quay_client,
            llm=AsyncMock(),  # LLM only used on failure
        )

        assert result["current_phase"] == PoCPhase.BUILD
        assert result["error"] is None

        # Verify the image was added to the state
        assert expected_image_ref in result["built_images"]

        # Verify the Quay API confirms the repo exists
        assert quay_client.repo_exists(e2e_config.quay_org, f"{unique_project_name}-nodeapp")

        # Verify the image actually exists in local podman
        inspect = subprocess.run(
            ["podman", "inspect", expected_image_ref], capture_output=True, text=True
        )
        assert inspect.returncode == 0

    @pytest.mark.asyncio
    async def test_build_failure_triggers_llm(
        self,
        local_build_repo: Path,
        e2e_config: AutoPoCConfig,
        unique_project_name: str,
    ) -> None:
        """Verify that a broken Dockerfile triggers the LLM diagnosis."""

        # Break the Dockerfile
        bad_dockerfile = local_build_repo / "Dockerfile.ubi"
        bad_dockerfile.write_text("FROM scratch\nRUN this-command-does-not-exist\n")

        state = PoCState(
            project_name=unique_project_name,
            source_repo_url=str(local_build_repo),
            current_phase=PoCPhase.CONTAINERIZE,
            local_clone_path=str(local_build_repo),
            error=None,
            messages=[],
            components=[
                {
                    "name": "brokenapp",
                    "language": "python",
                    "dockerfile_ubi_path": "Dockerfile.ubi",
                }
            ],
            built_images=[],
            build_retries=0,
        )

        # Mock LLM to return a diagnosis
        from langchain_core.messages import AIMessage

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="The command does not exist.")

        result = await build_agent(state, app_config=e2e_config, llm=mock_llm)

        # Verify the state transition and error handling
        assert result["current_phase"] == PoCPhase.BUILD
        assert result["build_retries"] == 1
        assert "The command does not exist" in result["error"]
        assert "this-command-does-not-exist" in result["error"]  # The raw error should be included

        # Verify the LLM was called
        mock_llm.ainvoke.assert_called_once()
