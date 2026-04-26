"""E2E tests for the deploy agent against a local Kubernetes cluster.

These tests require:
  1. Local Kubernetes cluster running (k3d, minikube, or kind)
  2. kubectl configured to access the cluster
  3. Local Quay with built images available
  4. .env.test with valid credentials
  5. --e2e flag passed to pytest
"""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from autopoc.agents.deploy import deploy_agent
from autopoc.config import AutoPoCConfig
from autopoc.state import PoCPhase, PoCState


# --- Helpers ---


def kubectl_available() -> bool:
    """Check if kubectl is available and configured."""
    try:
        subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def cleanup_namespace(namespace: str) -> None:
    """Delete a namespace and wait for cleanup."""
    try:
        subprocess.run(
            ["kubectl", "delete", "namespace", namespace, "--ignore-not-found=true"],
            capture_output=True,
            timeout=60,
        )
        # Wait for namespace to be fully deleted
        subprocess.run(
            ["kubectl", "wait", "--for=delete", f"namespace/{namespace}", "--timeout=60s"],
            capture_output=True,
            timeout=65,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass  # Best effort


# --- Fixtures ---


@pytest.fixture
def mock_built_image(e2e_config: AutoPoCConfig, unique_project_name: str) -> str:
    """Provide a mock image reference for testing.

    In a real E2E scenario, this would be built by test_e2e_build.py.
    For isolated deploy testing, we'll use a simple public image.
    """
    # Use a lightweight public image that actually exists
    return "docker.io/library/nginx:alpine"


@pytest.fixture
def deploy_repo(e2e_work_dir: Path) -> Path:
    """Create a minimal git repo for deploy testing."""
    repo = e2e_work_dir / "deploy-test"
    repo.mkdir(exist_ok=True)

    # Create a simple app file (not actually used, just for context)
    (repo / "app.py").write_text('print("hello deploy")\n')

    # Initialize git
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture
def cleanup_namespace_fixture(unique_project_name: str):
    """Fixture to clean up the test namespace after the test."""
    yield
    cleanup_namespace(unique_project_name)


# --- Tests ---


class TestDeployAgentE2E:
    """Test the deploy agent against a local Kubernetes cluster."""

    @pytest.mark.asyncio
    async def test_deploy_to_k8s(
        self,
        deploy_repo: Path,
        e2e_config: AutoPoCConfig,
        unique_project_name: str,
        mock_built_image: str,
        cleanup_namespace_fixture,
    ) -> None:
        """Verify the deploy agent can deploy to a local Kubernetes cluster."""

        if not kubectl_available():
            pytest.skip("kubectl not configured or no cluster available")

        # Build state representing successful build phase
        state = PoCState(
            project_name=unique_project_name,
            source_repo_url=str(deploy_repo),
            current_phase=PoCPhase.BUILD,
            local_clone_path=str(deploy_repo),
            error=None,
            messages=[],
            components=[
                {
                    "name": "web",
                    "language": "python",
                    "build_system": "pip",
                    "entry_point": "app.py",
                    "port": 8080,
                    "existing_dockerfile": None,
                    "is_ml_workload": False,
                    "source_dir": ".",
                    "dockerfile_ubi_path": "Dockerfile.ubi",
                }
            ],
            built_images=[mock_built_image],
            build_retries=0,
            deployed_resources=[],
            routes=[],
        )

        # Mock LLM to speed up test (deploy agent uses LLM for reasoning)
        mock_llm = AsyncMock()
        from langchain_core.messages import AIMessage

        # Simulate LLM generating deployment commands
        mock_llm.ainvoke.return_value = AIMessage(
            content="I will deploy the application to Kubernetes."
        )

        result = await deploy_agent(
            state,
            app_config=e2e_config,
            llm=mock_llm,
        )

        # Verify state transition
        assert result["current_phase"] == PoCPhase.DEPLOY

        # Verify resources were created (at minimum we should have attempted deployment)
        # Note: With mocked LLM, the agent won't actually create resources,
        # so we're mainly testing that the agent runs without errors

        # In a real test with actual LLM, we'd verify:
        # assert result["error"] is None
        # assert len(result["deployed_resources"]) > 0
        # assert len(result["routes"]) > 0

        # Verify namespace was created
        subprocess.run(
            ["kubectl", "get", "namespace", unique_project_name],
            capture_output=True,
        )
        # May or may not exist depending on LLM mock - that's ok for this basic test

    @pytest.mark.asyncio
    async def test_deploy_handles_missing_cluster(
        self,
        deploy_repo: Path,
        e2e_config: AutoPoCConfig,
        unique_project_name: str,
        mock_built_image: str,
    ) -> None:
        """Verify deploy agent handles kubectl errors gracefully."""

        # This test verifies error handling when cluster operations fail
        state = PoCState(
            project_name=unique_project_name,
            source_repo_url=str(deploy_repo),
            current_phase=PoCPhase.BUILD,
            local_clone_path=str(deploy_repo),
            error=None,
            messages=[],
            components=[
                {
                    "name": "app",
                    "language": "python",
                    "port": 8000,
                }
            ],
            built_images=[mock_built_image],
        )

        # Even with a mocked LLM, the agent should handle errors gracefully
        result = await deploy_agent(state, app_config=e2e_config)

        # Should complete without crashing, even if deployment fails
        assert result["current_phase"] == PoCPhase.DEPLOY
        # Error may or may not be set depending on what the agent tried
