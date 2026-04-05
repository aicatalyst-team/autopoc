"""Tests for the intake agent.

Tests the parsing/validation logic directly and the full agent flow
using a fake LLM that simulates tool-calling behavior.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from autopoc.agents.intake import (
    _parse_intake_output,
    _validate_component,
    intake_agent,
)
from autopoc.state import PoCPhase, PoCState

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# --- Tests for _parse_intake_output ---


class TestParseIntakeOutput:
    def test_parses_valid_json(self) -> None:
        raw = json.dumps(
            {
                "repo_summary": "A test project.",
                "components": [{"name": "app", "language": "python"}],
                "has_helm_chart": False,
                "has_kustomize": False,
                "has_compose": False,
                "existing_ci_cd": None,
            }
        )
        result = _parse_intake_output(raw)
        assert result["repo_summary"] == "A test project."
        assert len(result["components"]) == 1

    def test_strips_markdown_code_fences(self) -> None:
        raw = '```json\n{"repo_summary": "test", "components": []}\n```'
        result = _parse_intake_output(raw)
        assert result["repo_summary"] == "test"

    def test_strips_plain_code_fences(self) -> None:
        raw = '```\n{"repo_summary": "test", "components": []}\n```'
        result = _parse_intake_output(raw)
        assert result["repo_summary"] == "test"

    def test_handles_conversational_text_around_json(self) -> None:
        raw = 'Here is the analysis:\n```json\n{"repo_summary": "test", "components": []}\n```\nHope this helps!'
        result = _parse_intake_output(raw)
        assert result["repo_summary"] == "test"

        raw2 = 'I found this: {"repo_summary": "test2", "components": []} - what do you think?'
        result2 = _parse_intake_output(raw2)
        assert result2["repo_summary"] == "test2"

    def test_handles_invalid_json(self) -> None:
        raw = "This is not JSON at all"
        result = _parse_intake_output(raw)
        assert "Failed to parse" in result["repo_summary"]
        assert result["components"] == []
        assert result["has_helm_chart"] is False

    def test_handles_empty_string(self) -> None:
        result = _parse_intake_output("")
        assert result["components"] == []


# --- Tests for _validate_component ---


class TestValidateComponent:
    def test_full_component(self) -> None:
        comp = {
            "name": "api",
            "language": "python",
            "build_system": "pip",
            "entry_point": "main.py",
            "port": 8080,
            "existing_dockerfile": "Dockerfile",
            "is_ml_workload": False,
            "source_dir": "api/",
        }
        result = _validate_component(comp)
        assert result["name"] == "api"
        assert result["language"] == "python"
        assert result["port"] == 8080
        assert result["dockerfile_ubi_path"] == ""  # Not yet set
        assert result["image_name"] == ""  # Not yet set

    def test_minimal_component_uses_defaults(self) -> None:
        comp = {"name": "app"}
        result = _validate_component(comp)
        assert result["name"] == "app"
        assert result["language"] == "unknown"
        assert result["build_system"] == "unknown"
        assert result["port"] is None
        assert result["is_ml_workload"] is False
        assert result["source_dir"] == "."

    def test_empty_component_uses_all_defaults(self) -> None:
        result = _validate_component({})
        assert result["name"] == "unknown"

    def test_ml_workload_flag(self) -> None:
        comp = {"name": "model", "is_ml_workload": True}
        result = _validate_component(comp)
        assert result["is_ml_workload"] is True


# --- Tests for the full intake_agent flow ---


class TestIntakeAgent:
    """Test the intake agent using mocked LLM responses.

    These tests mock the create_react_agent to avoid real LLM calls
    while still verifying the agent's input/output handling.
    """

    @pytest.fixture
    def flask_state(self) -> PoCState:
        """Initial state pointing to the flask fixture."""
        return PoCState(
            project_name="flask-app",
            source_repo_url="https://github.com/test/flask-app",
            current_phase=PoCPhase.INTAKE,
            local_clone_path=str(FIXTURES_DIR / "python-flask-app"),
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
    def monorepo_state(self) -> PoCState:
        """Initial state pointing to the node monorepo fixture."""
        return PoCState(
            project_name="node-monorepo",
            source_repo_url="https://github.com/test/node-monorepo",
            current_phase=PoCPhase.INTAKE,
            local_clone_path=str(FIXTURES_DIR / "node-monorepo"),
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
    def ml_state(self) -> PoCState:
        """Initial state pointing to the ML serving fixture."""
        return PoCState(
            project_name="ml-serving",
            source_repo_url="https://github.com/test/ml-serving",
            current_phase=PoCPhase.INTAKE,
            local_clone_path=str(FIXTURES_DIR / "ml-serving"),
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

    def _make_mock_agent(self, llm_json_response: dict) -> AsyncMock:
        """Create a mock for create_react_agent that returns a canned response."""
        from langchain_core.messages import AIMessage

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [
                AIMessage(content=json.dumps(llm_json_response)),
            ]
        }
        return mock_agent

    @pytest.mark.asyncio
    async def test_flask_app_intake(self, flask_state: PoCState) -> None:
        """Intake correctly processes a simple Python Flask app."""
        llm_response = {
            "repo_summary": "A simple Flask web application with an existing Dockerfile.",
            "components": [
                {
                    "name": "app",
                    "language": "python",
                    "build_system": "pip",
                    "entry_point": "app.py",
                    "port": 5000,
                    "existing_dockerfile": "Dockerfile",
                    "is_ml_workload": False,
                    "source_dir": ".",
                }
            ],
            "has_helm_chart": False,
            "has_kustomize": False,
            "has_compose": False,
            "existing_ci_cd": None,
        }

        mock_agent = self._make_mock_agent(llm_response)

        with patch("autopoc.agents.intake.create_react_agent", return_value=mock_agent):
            result = await intake_agent(flask_state, llm=AsyncMock())

        assert result["current_phase"] == PoCPhase.INTAKE
        assert len(result["components"]) == 1

        comp = result["components"][0]
        assert comp["name"] == "app"
        assert comp["language"] == "python"
        assert comp["port"] == 5000
        assert comp["existing_dockerfile"] == "Dockerfile"
        assert comp["is_ml_workload"] is False

    @pytest.mark.asyncio
    async def test_monorepo_intake(self, monorepo_state: PoCState) -> None:
        """Intake correctly identifies multiple components in a monorepo."""
        llm_response = {
            "repo_summary": "A two-component app with Node.js frontend and Node.js API.",
            "components": [
                {
                    "name": "frontend",
                    "language": "node",
                    "build_system": "npm",
                    "entry_point": "src/index.js",
                    "port": 3000,
                    "existing_dockerfile": None,
                    "is_ml_workload": False,
                    "source_dir": "frontend/",
                },
                {
                    "name": "api",
                    "language": "node",
                    "build_system": "npm",
                    "entry_point": "src/server.js",
                    "port": 3001,
                    "existing_dockerfile": None,
                    "is_ml_workload": False,
                    "source_dir": "api/",
                },
            ],
            "has_helm_chart": False,
            "has_kustomize": False,
            "has_compose": True,
            "existing_ci_cd": None,
        }

        mock_agent = self._make_mock_agent(llm_response)

        with patch("autopoc.agents.intake.create_react_agent", return_value=mock_agent):
            result = await intake_agent(monorepo_state, llm=AsyncMock())

        assert len(result["components"]) == 2
        names = [c["name"] for c in result["components"]]
        assert "frontend" in names
        assert "api" in names
        assert result["has_compose"] is True

    @pytest.mark.asyncio
    async def test_ml_serving_intake(self, ml_state: PoCState) -> None:
        """Intake correctly identifies ML workload and existing K8s manifests."""
        llm_response = {
            "repo_summary": "ML model serving app with PyTorch, FastAPI, and K8s manifests.",
            "components": [
                {
                    "name": "model-server",
                    "language": "python",
                    "build_system": "pip",
                    "entry_point": "model/serve.py",
                    "port": 8080,
                    "existing_dockerfile": "Dockerfile",
                    "is_ml_workload": True,
                    "source_dir": ".",
                }
            ],
            "has_helm_chart": False,
            "has_kustomize": False,
            "has_compose": False,
            "existing_ci_cd": None,
        }

        mock_agent = self._make_mock_agent(llm_response)

        with patch("autopoc.agents.intake.create_react_agent", return_value=mock_agent):
            result = await intake_agent(ml_state, llm=AsyncMock())

        assert len(result["components"]) == 1
        comp = result["components"][0]
        assert comp["is_ml_workload"] is True
        assert comp["existing_dockerfile"] == "Dockerfile"
        assert comp["port"] == 8080

    @pytest.mark.asyncio
    async def test_clone_path_preserved(self, flask_state: PoCState) -> None:
        """The local_clone_path is preserved in the output state."""
        llm_response = {
            "repo_summary": "test",
            "components": [],
            "has_helm_chart": False,
            "has_kustomize": False,
            "has_compose": False,
            "existing_ci_cd": None,
        }

        mock_agent = self._make_mock_agent(llm_response)

        with patch("autopoc.agents.intake.create_react_agent", return_value=mock_agent):
            result = await intake_agent(flask_state, llm=AsyncMock())

        assert result["local_clone_path"] == str(FIXTURES_DIR / "python-flask-app")

    @pytest.mark.asyncio
    async def test_handles_malformed_llm_output(self, flask_state: PoCState) -> None:
        """Agent handles gracefully when LLM returns non-JSON output."""
        from langchain_core.messages import AIMessage

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [
                AIMessage(content="I couldn't analyze this repo properly."),
            ]
        }

        with patch("autopoc.agents.intake.create_react_agent", return_value=mock_agent):
            result = await intake_agent(flask_state, llm=AsyncMock())

        # Should still return a valid state, just with empty components
        assert result["components"] == []
        assert "Failed to parse" in result["repo_summary"]
