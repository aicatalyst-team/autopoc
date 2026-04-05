import os
from pathlib import Path
from unittest.mock import patch

import pytest

from autopoc.state import PoCPhase, PoCState


@pytest.fixture
def base_state(tmp_path: Path) -> PoCState:
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


@pytest.mark.asyncio
@patch("autopoc.agents.build.podman_push")
async def test_retry_loop_success(
    mock_push,
    base_state: PoCState,
    tmp_path: Path,
):
    """Test build failure triggering containerize retry, then success."""

    # Mock containerize to just set the dockerfile path
    async def mock_containerize(state, **kwargs):
        comps = state["components"]
        comps[0]["dockerfile_ubi_path"] = "Dockerfile.ubi"
        return {"components": comps, "current_phase": PoCPhase.CONTAINERIZE}

    # Mock build to fail first time, succeed second
    build_calls = 0

    async def mock_build(state, **kwargs):
        nonlocal build_calls
        build_calls += 1
        if build_calls == 1:
            return {
                "current_phase": PoCPhase.BUILD,
                "error": "Build failed due to missing dependency",
                "build_retries": state.get("build_retries", 0) + 1,
            }
        return {
            "current_phase": PoCPhase.BUILD,
            "error": None,
            "built_images": ["quay.io/org/my-project-api:latest"],
        }

    env_patch = {
        "ANTHROPIC_API_KEY": "sk-test",
        "GITLAB_URL": "https://gitlab.test",
        "GITLAB_TOKEN": "tok",
        "GITLAB_GROUP": "poc",
        "QUAY_ORG": "org",
        "QUAY_TOKEN": "tok",
        "OPENSHIFT_API_URL": "https://api.test:6443",
        "OPENSHIFT_TOKEN": "tok",
    }

    with patch.dict(os.environ, env_patch, clear=True):
        from langgraph.graph import StateGraph, END
        from autopoc.graph import route_after_build

        sg = StateGraph(PoCState)
        sg.add_node("containerize", mock_containerize)
        sg.add_node("build", mock_build)
        sg.set_entry_point("containerize")
        sg.add_edge("containerize", "build")
        sg.add_conditional_edges(
            "build",
            route_after_build,
            {
                "deploy": END,
                "containerize": "containerize",
                "failed": END,
            },
        )
        compiled = sg.compile()

        result = await compiled.ainvoke(base_state)

    assert result["error"] is None
    assert result["build_retries"] == 1
    assert "quay.io/org/my-project-api:latest" in result["built_images"]


@pytest.mark.asyncio
async def test_retry_loop_exhaustion(
    base_state: PoCState,
    tmp_path: Path,
):
    """Test build failure exceeding max retries."""

    async def mock_containerize(state, **kwargs):
        comps = state["components"]
        comps[0]["dockerfile_ubi_path"] = "Dockerfile.ubi"
        return {"components": comps, "current_phase": PoCPhase.CONTAINERIZE}

    # Build always fails
    async def mock_build(state, **kwargs):
        return {
            "current_phase": PoCPhase.BUILD,
            "error": "Build failed repeatedly",
            "build_retries": state.get("build_retries", 0) + 1,
        }

    env_patch = {
        "ANTHROPIC_API_KEY": "sk-test",
        "GITLAB_URL": "https://gitlab.test",
        "GITLAB_TOKEN": "tok",
        "GITLAB_GROUP": "poc",
        "QUAY_ORG": "org",
        "QUAY_TOKEN": "tok",
        "OPENSHIFT_API_URL": "https://api.test:6443",
        "OPENSHIFT_TOKEN": "tok",
        "MAX_BUILD_RETRIES": "2",  # Limit to 2 for faster test
    }

    with (
        patch.dict(os.environ, env_patch, clear=True),
    ):
        from langgraph.graph import StateGraph, END
        from autopoc.graph import route_after_build

        sg = StateGraph(PoCState)
        sg.add_node("containerize", mock_containerize)
        sg.add_node("build", mock_build)
        sg.set_entry_point("containerize")
        sg.add_edge("containerize", "build")
        sg.add_conditional_edges(
            "build",
            route_after_build,
            {
                "deploy": END,
                "containerize": "containerize",
                "failed": END,
            },
        )
        compiled = sg.compile()

        result = await compiled.ainvoke(base_state)

    assert result["error"] == "Build failed repeatedly"
    assert result["build_retries"] == 2
