"""Tests for the PoC Plan agent."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopoc.agents.poc_plan import (
    _build_user_message,
    _parse_poc_plan_output,
    _validate_infrastructure,
    _validate_scenario,
    poc_plan_agent,
)
from autopoc.state import PoCPhase, PoCScenario, PoCInfrastructure


# --- Tests for _parse_poc_plan_output ---


class TestParsePocPlanOutput:
    def test_parses_valid_json(self):
        raw = json.dumps(
            {
                "poc_type": "model-serving",
                "poc_plan_summary": "Test plan",
                "infrastructure": {"needs_gpu": True},
                "scenarios": [{"name": "test", "type": "http"}],
            }
        )
        result = _parse_poc_plan_output(raw)
        assert result["poc_type"] == "model-serving"
        assert result["infrastructure"]["needs_gpu"] is True
        assert len(result["scenarios"]) == 1

    def test_parses_json_in_code_fence(self):
        raw = '```json\n{"poc_type": "web-app", "scenarios": []}\n```'
        result = _parse_poc_plan_output(raw)
        assert result["poc_type"] == "web-app"

    def test_parses_json_with_surrounding_text(self):
        raw = 'Here is my analysis:\n{"poc_type": "rag", "scenarios": []}\nDone.'
        result = _parse_poc_plan_output(raw)
        assert result["poc_type"] == "rag"

    def test_returns_defaults_for_malformed_json(self):
        raw = "This is not JSON at all"
        result = _parse_poc_plan_output(raw)
        assert result["poc_type"] == "web-app"
        assert "Failed to parse" in result["poc_plan_summary"]

    def test_parses_empty_string(self):
        result = _parse_poc_plan_output("")
        assert result["poc_type"] == "web-app"


# --- Tests for _validate_scenario ---


class TestValidateScenario:
    def test_validates_complete_scenario(self):
        s = {
            "name": "inference-test",
            "description": "Test inference",
            "type": "http",
            "endpoint": "/predict",
            "input_data": '{"text": "hello"}',
            "expected_behavior": "Returns prediction",
            "timeout_seconds": 60,
        }
        result = _validate_scenario(s)
        assert result["name"] == "inference-test"
        assert result["type"] == "http"
        assert result["endpoint"] == "/predict"
        assert result["timeout_seconds"] == 60

    def test_validates_partial_scenario(self):
        s = {"name": "basic"}
        result = _validate_scenario(s)
        assert result["name"] == "basic"
        assert result["type"] == "http"  # default
        assert result["timeout_seconds"] == 30  # default
        assert result["endpoint"] is None  # default

    def test_validates_empty_scenario(self):
        result = _validate_scenario({})
        assert result["name"] == "unnamed"
        assert result["type"] == "http"


# --- Tests for _validate_infrastructure ---


class TestValidateInfrastructure:
    def test_validates_complete_infrastructure(self):
        i = {
            "needs_inference_server": True,
            "inference_server_type": "vllm",
            "needs_vector_db": True,
            "vector_db_type": "in-memory",
            "needs_gpu": True,
            "gpu_type": "nvidia-a10g",
            "resource_profile": "gpu",
            "odh_components": ["kserve"],
        }
        result = _validate_infrastructure(i)
        assert result["needs_inference_server"] is True
        assert result["inference_server_type"] == "vllm"
        assert result["needs_vector_db"] is True
        assert result["resource_profile"] == "gpu"
        assert result["odh_components"] == ["kserve"]

    def test_validates_empty_infrastructure(self):
        result = _validate_infrastructure({})
        assert result["needs_inference_server"] is False
        assert result["needs_gpu"] is False
        assert result["resource_profile"] == "small"
        assert result["sidecar_containers"] == []
        assert result["extra_env_vars"] == {}
        assert result["odh_components"] == []

    def test_validates_partial_infrastructure(self):
        i = {"needs_pvc": True, "pvc_size": "50Gi"}
        result = _validate_infrastructure(i)
        assert result["needs_pvc"] is True
        assert result["pvc_size"] == "50Gi"
        assert result["needs_inference_server"] is False


# --- Tests for _build_user_message ---


class TestBuildUserMessage:
    def test_includes_project_info(self):
        state = {
            "project_name": "test-project",
            "source_repo_url": "https://github.com/test/repo",
            "local_clone_path": "/tmp/test",
            "repo_summary": "A test project",
            "components": [],
        }
        msg = _build_user_message(state)
        assert "test-project" in msg
        assert "https://github.com/test/repo" in msg
        assert "/tmp/test" in msg

    def test_includes_components(self):
        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "repo_summary": "",
            "components": [
                {
                    "name": "api",
                    "language": "python",
                    "build_system": "pip",
                    "port": 8000,
                    "is_ml_workload": True,
                    "entry_point": "main.py",
                    "source_dir": ".",
                }
            ],
        }
        msg = _build_user_message(state)
        assert "api" in msg
        assert "python" in msg
        assert "ML workload: yes" in msg

    def test_includes_existing_artifacts(self):
        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "repo_summary": "",
            "components": [],
            "has_helm_chart": True,
            "has_compose": True,
            "existing_ci_cd": "github-actions",
        }
        msg = _build_user_message(state)
        assert "Helm chart" in msg
        assert "Docker Compose" in msg
        assert "github-actions" in msg


# --- Tests for poc_plan_agent ---


class TestPocPlanAgent:
    @pytest.mark.asyncio
    async def test_agent_returns_poc_plan_state(self):
        """Test that the agent returns properly structured state."""
        mock_agent_result = {
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {
                            "poc_type": "web-app",
                            "poc_plan_summary": "Deploy and test the Flask app",
                            "infrastructure": {
                                "needs_inference_server": False,
                                "resource_profile": "small",
                            },
                            "scenarios": [
                                {
                                    "name": "health-check",
                                    "description": "Check health endpoint",
                                    "type": "http",
                                    "endpoint": "/health",
                                    "expected_behavior": "Returns 200",
                                    "timeout_seconds": 30,
                                }
                            ],
                        }
                    ),
                    __class__=type("AIMessage", (), {"__instancecheck__": lambda cls, inst: True}),
                )
            ]
        }

        state = {
            "project_name": "test-flask",
            "source_repo_url": "https://github.com/test/flask",
            "local_clone_path": "/tmp/test-flask",
            "repo_summary": "A simple Flask app",
            "components": [
                {
                    "name": "app",
                    "language": "python",
                    "build_system": "pip",
                    "port": 5000,
                    "is_ml_workload": False,
                }
            ],
        }

        with patch("autopoc.agents.poc_plan.create_react_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = mock_agent_result
            mock_create.return_value = mock_agent

            # Need to patch AIMessage isinstance check
            from langchain_core.messages import AIMessage

            with patch("autopoc.agents.poc_plan.AIMessage", AIMessage):
                mock_msg = MagicMock(spec=AIMessage)
                mock_msg.content = json.dumps(
                    {
                        "poc_type": "web-app",
                        "poc_plan_summary": "Deploy and test",
                        "infrastructure": {"resource_profile": "small"},
                        "scenarios": [{"name": "health", "type": "http"}],
                    }
                )
                mock_agent_result["messages"] = [mock_msg]

                result = await poc_plan_agent(state, llm=MagicMock())

        assert result["current_phase"] == PoCPhase.POC_PLAN
        assert result["poc_type"] == "web-app"
        assert len(result["poc_scenarios"]) == 1
        assert result["poc_scenarios"][0]["name"] == "health"
        assert result["poc_infrastructure"]["resource_profile"] == "small"

    @pytest.mark.asyncio
    async def test_agent_handles_malformed_output(self):
        """Test graceful degradation on malformed LLM output."""
        from langchain_core.messages import AIMessage

        mock_msg = MagicMock(spec=AIMessage)
        mock_msg.content = "This is not valid JSON output"

        mock_agent_result = {"messages": [mock_msg]}

        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "repo_summary": "",
            "components": [],
        }

        with patch("autopoc.agents.poc_plan.create_react_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = mock_agent_result
            mock_create.return_value = mock_agent

            result = await poc_plan_agent(state, llm=MagicMock())

        assert result["current_phase"] == PoCPhase.POC_PLAN
        assert result["poc_type"] == "web-app"  # default
        assert result["poc_scenarios"] == []  # no scenarios parsed
