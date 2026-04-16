import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage

from autopoc.agents import build as build_module
from autopoc.agents.build import build_agent
from autopoc.state import PoCPhase, PoCState


@pytest.fixture(autouse=True)
def _clear_login_cache():
    """Reset the module-level login cache between tests."""
    build_module._logged_in_registries.clear()
    yield
    build_module._logged_in_registries.clear()


@pytest.fixture
def initial_state(tmp_path: Path) -> PoCState:
    return PoCState(
        project_name="my-project",
        source_repo_url="https://github.com/my-org/my-repo",
        current_phase=PoCPhase.CONTAINERIZE,
        error=None,
        messages=[],
        gitlab_repo_url="https://gitlab.example.com/my-org/my-repo",
        local_clone_path=str(tmp_path / "repo"),
        repo_summary="Test repo",
        components=[
            {
                "name": "api",
                "language": "python",
                "build_system": "pip",
                "entry_point": "app.py",
                "port": 5000,
                "dockerfile_ubi_path": "api/Dockerfile.ubi",
            },
            {
                "name": "web",
                "language": "node",
                "build_system": "npm",
                "entry_point": "index.js",
                "port": 3000,
                "dockerfile_ubi_path": "web/Dockerfile.ubi",
            },
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


@pytest.fixture
def mock_quay_client():
    client = MagicMock()
    # ensure_repo returns the repo reference
    client.ensure_repo.side_effect = lambda org, name: f"quay.io/{org}/{name}"
    return client


@pytest.fixture
def mock_app_config():
    config = MagicMock()
    config.quay_org = "my-org"
    config.quay_registry = "quay.io"
    config.quay_token = "test-token"
    return config


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(content="You missed a dependency.")
    return llm


@pytest.mark.asyncio
@patch("autopoc.agents.build.podman_login")
@patch("autopoc.agents.build.podman_build")
@patch("autopoc.agents.build.podman_push")
async def test_build_success(
    mock_push,
    mock_build,
    mock_login,
    initial_state: PoCState,
    mock_app_config,
    mock_quay_client,
    mock_llm,
):
    """Test successful build of all components."""
    # Podman succeeds for both components
    mock_build.invoke.return_value = "Build successful"
    mock_push.invoke.return_value = "Push successful"

    result = await build_agent(
        initial_state,
        app_config=mock_app_config,
        quay_client=mock_quay_client,
        llm=mock_llm,
    )

    assert result["current_phase"] == PoCPhase.BUILD
    assert result["error"] is None

    # 2 components built
    assert len(result["built_images"]) == 2
    assert "quay.io/my-org/my-project-api:latest" in result["built_images"]
    assert "quay.io/my-org/my-project-web:latest" in result["built_images"]

    assert result["components"][0]["image_name"] == "quay.io/my-org/my-project-api:latest"
    assert result["components"][1]["image_name"] == "quay.io/my-org/my-project-web:latest"

    # Verify podman calls
    assert mock_build.invoke.call_count == 2
    assert mock_push.invoke.call_count == 2

    # Verify Quay repo created
    assert mock_quay_client.ensure_repo.call_count == 2
    mock_quay_client.ensure_repo.assert_any_call("my-org", "my-project-api")
    mock_quay_client.ensure_repo.assert_any_call("my-org", "my-project-web")


@pytest.mark.asyncio
@patch("autopoc.agents.build.create_llm")
@patch("autopoc.agents.build.podman_login")
@patch("autopoc.agents.build.podman_build")
@patch("autopoc.agents.build.podman_push")
async def test_build_partial_failure(
    mock_push,
    mock_build,
    mock_login,
    mock_create_llm,
    initial_state: PoCState,
    mock_app_config,
    mock_quay_client,
    mock_llm,
):
    """Test when the first component succeeds but the second fails."""

    # The build agent creates a fresh LLM for diagnosis via create_llm()
    diagnosis_llm = AsyncMock()
    diagnosis_llm.ainvoke.return_value = AIMessage(content="You missed a dependency.")
    mock_create_llm.return_value = diagnosis_llm

    # Succeeds on first call, fails on second
    def mock_build_side_effect(args):
        if "web/Dockerfile.ubi" in args["dockerfile"]:
            raise RuntimeError("Compilation failed")
        return "Build successful"

    mock_build.invoke.side_effect = mock_build_side_effect
    mock_push.invoke.return_value = "Push successful"

    result = await build_agent(
        initial_state,
        app_config=mock_app_config,
        quay_client=mock_quay_client,
        llm=mock_llm,
    )

    assert result["current_phase"] == PoCPhase.BUILD
    assert "Build failed for component 'web'" in result["error"]
    assert "Compilation failed" in result["error"]
    assert "You missed a dependency." in result["error"]

    # 1 component built, 1 failed
    assert len(result["built_images"]) == 1
    assert "quay.io/my-org/my-project-api:latest" in result["built_images"]

    # Retries incremented
    assert result["build_retries"] == 1

    # Verify podman calls
    assert mock_build.invoke.call_count == 2
    assert mock_push.invoke.call_count == 1  # Only pushed api

    # Verify LLM was called for diagnosis
    assert diagnosis_llm.ainvoke.call_count == 1
