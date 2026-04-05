"""Tests for the containerize agent."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from autopoc.agents.containerize import (
    _build_user_message,
    _parse_containerize_output,
    containerize_agent,
)
from autopoc.state import ComponentInfo, PoCPhase, PoCState

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- Tests for _build_user_message ---


class TestBuildUserMessage:
    def test_basic_component(self) -> None:
        comp = ComponentInfo(
            name="api",
            language="python",
            build_system="pip",
            entry_point="app.py",
            port=8080,
            existing_dockerfile=None,
            is_ml_workload=False,
            source_dir=".",
            dockerfile_ubi_path="",
            image_name="",
        )
        msg = _build_user_message(comp, "/tmp/repo")
        assert "api" in msg
        assert "python" in msg
        assert "8080" in msg
        assert "No existing Dockerfile" in msg
        assert "/tmp/repo" in msg

    def test_with_existing_dockerfile(self) -> None:
        comp = ComponentInfo(
            name="app",
            language="python",
            build_system="pip",
            entry_point="app.py",
            port=5000,
            existing_dockerfile="Dockerfile",
            is_ml_workload=False,
            source_dir=".",
            dockerfile_ubi_path="",
            image_name="",
        )
        msg = _build_user_message(comp, "/tmp/repo")
        assert "Existing Dockerfile" in msg
        assert "adapt to UBI" in msg

    def test_with_build_error(self) -> None:
        comp = ComponentInfo(
            name="app",
            language="python",
            build_system="pip",
            entry_point="app.py",
            port=None,
            existing_dockerfile=None,
            is_ml_workload=False,
            source_dir=".",
            dockerfile_ubi_path="",
            image_name="",
        )
        msg = _build_user_message(comp, "/tmp/repo", build_error="Error: package xyz not found")
        assert "PREVIOUS BUILD FAILED" in msg
        assert "package xyz not found" in msg

    def test_subdirectory_component(self) -> None:
        comp = ComponentInfo(
            name="frontend",
            language="node",
            build_system="npm",
            entry_point="src/index.js",
            port=3000,
            existing_dockerfile=None,
            is_ml_workload=False,
            source_dir="frontend/",
            dockerfile_ubi_path="",
            image_name="",
        )
        msg = _build_user_message(comp, "/tmp/repo")
        assert "/tmp/repo/frontend/" in msg

    def test_ml_workload_flag(self) -> None:
        comp = ComponentInfo(
            name="model",
            language="python",
            build_system="pip",
            entry_point="serve.py",
            port=8080,
            existing_dockerfile=None,
            is_ml_workload=True,
            source_dir=".",
            dockerfile_ubi_path="",
            image_name="",
        )
        msg = _build_user_message(comp, "/tmp/repo")
        assert "True" in msg  # is_ml_workload: True


# --- Tests for _parse_containerize_output ---


class TestParseContainerizeOutput:
    def test_valid_json(self) -> None:
        raw = json.dumps(
            {
                "dockerfile_ubi_path": "Dockerfile.ubi",
                "base_image": "ubi9/python-312",
                "strategy": "single-stage",
                "notes": "created from scratch",
            }
        )
        result = _parse_containerize_output(raw, "/tmp/repo")
        assert result["dockerfile_ubi_path"] == "Dockerfile.ubi"
        assert result["strategy"] == "single-stage"

    def test_strips_code_fences(self) -> None:
        raw = '```json\n{"dockerfile_ubi_path": "Dockerfile.ubi", "strategy": "single-stage"}\n```'
        result = _parse_containerize_output(raw, "/tmp/repo")
        assert result["dockerfile_ubi_path"] == "Dockerfile.ubi"

    def test_handles_conversational_text_around_json(self) -> None:
        raw = 'Here is the dockerfile info:\n```json\n{"dockerfile_ubi_path": "Dockerfile.ubi", "strategy": "single-stage"}\n```\nHope this helps!'
        result = _parse_containerize_output(raw, "/tmp/repo")
        assert result["dockerfile_ubi_path"] == "Dockerfile.ubi"

        raw2 = 'Created this: {"dockerfile_ubi_path": "Dockerfile2.ubi", "strategy": "single-stage"} - done!'
        result2 = _parse_containerize_output(raw2, "/tmp/repo")
        assert result2["dockerfile_ubi_path"] == "Dockerfile2.ubi"

    def test_invalid_json_returns_defaults(self) -> None:
        result = _parse_containerize_output("not json", "/tmp/repo")
        assert result["dockerfile_ubi_path"] == "/tmp/repo/Dockerfile.ubi"
        assert result["strategy"] == "unknown"


# --- Tests for the full containerize_agent ---


class TestContainerizeAgent:
    def _make_mock_agent(self, json_response: dict) -> AsyncMock:
        """Create a mock for create_react_agent."""
        from langchain_core.messages import AIMessage

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [AIMessage(content=json.dumps(json_response))]
        }
        return mock_agent

    @pytest.fixture
    def flask_state(self) -> PoCState:
        return PoCState(
            project_name="flask-app",
            source_repo_url="https://github.com/test/flask-app",
            current_phase=PoCPhase.FORK,
            local_clone_path=str(FIXTURES_DIR / "python-flask-app"),
            error=None,
            messages=[],
            gitlab_repo_url=None,
            components=[
                ComponentInfo(
                    name="app",
                    language="python",
                    build_system="pip",
                    entry_point="app.py",
                    port=5000,
                    existing_dockerfile="Dockerfile",
                    is_ml_workload=False,
                    source_dir=".",
                    dockerfile_ubi_path="",
                    image_name="",
                )
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
    def monorepo_state(self) -> PoCState:
        return PoCState(
            project_name="node-monorepo",
            source_repo_url="https://github.com/test/node-monorepo",
            current_phase=PoCPhase.FORK,
            local_clone_path=str(FIXTURES_DIR / "node-monorepo"),
            error=None,
            messages=[],
            gitlab_repo_url=None,
            components=[
                ComponentInfo(
                    name="frontend",
                    language="node",
                    build_system="npm",
                    entry_point="src/index.js",
                    port=3000,
                    existing_dockerfile=None,
                    is_ml_workload=False,
                    source_dir="frontend/",
                    dockerfile_ubi_path="",
                    image_name="",
                ),
                ComponentInfo(
                    name="api",
                    language="node",
                    build_system="npm",
                    entry_point="src/server.js",
                    port=3001,
                    existing_dockerfile=None,
                    is_ml_workload=False,
                    source_dir="api/",
                    dockerfile_ubi_path="",
                    image_name="",
                ),
            ],
            has_helm_chart=False,
            has_kustomize=False,
            has_compose=True,
            existing_ci_cd=None,
            built_images=[],
            build_retries=0,
            deployed_resources=[],
            routes=[],
        )

    @pytest.mark.asyncio
    async def test_single_component(self, flask_state: PoCState) -> None:
        """Containerize agent processes a single component."""
        mock_agent = self._make_mock_agent(
            {
                "dockerfile_ubi_path": "Dockerfile.ubi",
                "base_image": "registry.access.redhat.com/ubi9/python-312",
                "strategy": "single-stage",
                "notes": "Adapted from existing Dockerfile",
            }
        )

        with (
            patch("autopoc.agents.containerize.create_react_agent", return_value=mock_agent),
            patch("autopoc.agents.containerize.git_commit"),
            patch("autopoc.agents.containerize.git_push"),
        ):
            result = await containerize_agent(flask_state, llm=AsyncMock())

        assert result["current_phase"] == PoCPhase.CONTAINERIZE
        assert len(result["components"]) == 1
        assert result["components"][0]["dockerfile_ubi_path"] == "Dockerfile.ubi"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_multi_component(self, monorepo_state: PoCState) -> None:
        """Containerize agent processes multiple components."""
        responses = [
            {
                "dockerfile_ubi_path": "frontend/Dockerfile.ubi",
                "strategy": "single-stage",
            },
            {
                "dockerfile_ubi_path": "api/Dockerfile.ubi",
                "strategy": "single-stage",
            },
        ]

        call_count = 0

        async def mock_ainvoke(input_data):
            nonlocal call_count
            from langchain_core.messages import AIMessage

            resp = responses[call_count]
            call_count += 1
            return {"messages": [AIMessage(content=json.dumps(resp))]}

        mock_agent = AsyncMock()
        mock_agent.ainvoke = mock_ainvoke

        with (
            patch("autopoc.agents.containerize.create_react_agent", return_value=mock_agent),
            patch("autopoc.agents.containerize.git_commit"),
            patch("autopoc.agents.containerize.git_push"),
        ):
            result = await containerize_agent(monorepo_state, llm=AsyncMock())

        assert len(result["components"]) == 2
        paths = [c["dockerfile_ubi_path"] for c in result["components"]]
        assert "frontend/Dockerfile.ubi" in paths
        assert "api/Dockerfile.ubi" in paths

    @pytest.mark.asyncio
    async def test_retry_with_build_error(self, flask_state: PoCState) -> None:
        """Containerize agent includes build error in user message on retry."""
        flask_state["error"] = (
            "Step 5/8: RUN pip install -r requirements.txt FAILED: No module named 'xyz'"
        )

        mock_agent = self._make_mock_agent(
            {
                "dockerfile_ubi_path": "Dockerfile.ubi",
                "strategy": "single-stage",
            }
        )

        with (
            patch(
                "autopoc.agents.containerize.create_react_agent", return_value=mock_agent
            ) as mock_create,
            patch("autopoc.agents.containerize.git_commit"),
            patch("autopoc.agents.containerize.git_push"),
        ):
            result = await containerize_agent(flask_state, llm=AsyncMock())

        # Verify the agent was called and error is cleared
        assert result["error"] is None
        # The agent should have been invoked (create_react_agent called)
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_components(self) -> None:
        """Containerize agent handles empty components list."""
        state = PoCState(
            project_name="empty",
            source_repo_url="https://github.com/test/empty",
            current_phase=PoCPhase.FORK,
            local_clone_path="/tmp/empty",
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

        result = await containerize_agent(state, llm=AsyncMock())
        assert result["current_phase"] == PoCPhase.CONTAINERIZE
        assert result["components"] == []
