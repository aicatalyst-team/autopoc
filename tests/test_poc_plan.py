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


class TestExtractMarkdownPlan:
    """Test _extract_markdown_plan_from_response with realistic LLM outputs."""

    def test_extracts_full_plan_with_curly_braces_in_prose(self):
        """The bug: plan text containing { was being cut by JSON extraction."""
        from autopoc.agents.poc_plan import _extract_markdown_plan_from_response

        raw = (
            "Here is the plan I created:\n\n"
            "## Project Classification\n"
            "MemPalace is a sophisticated LLM-backed application that:\n"
            "- Stores conversations and project files in a searchable vector database (ChromaDB)\n"
            "- Uses LLM {via LangChain} for retrieval-augmented generation\n"
            "- Provides a CLI and REST API\n\n"
            "## PoC Objectives\n"
            "1. Verify the application containerizes on UBI\n"
            "2. Test the health endpoint\n\n"
            "## Infrastructure Requirements\n"
            "- Resource Profile: medium\n\n"
            "## Test Scenarios\n"
            "### Scenario 1: health-check\n"
            "- Endpoint: /health\n\n"
            '{"poc_type": "llm-app", "scenarios": []}\n'
        )
        result = _extract_markdown_plan_from_response(raw)
        assert "## Project Classification" in result
        assert "ChromaDB" in result
        assert "{via LangChain}" in result  # curly braces should NOT cause truncation
        assert "## PoC Objectives" in result
        assert "## Test Scenarios" in result
        assert "health-check" in result
        assert "poc_type" not in result  # JSON should be cut off

    def test_extracts_plan_when_json_on_own_line(self):
        from autopoc.agents.poc_plan import _extract_markdown_plan_from_response

        raw = (
            "# PoC Plan: test-app\n\n"
            "## Project Classification\n"
            "Type: web-app\n\n"
            "## PoC Objectives\n"
            "Deploy and test.\n\n"
            '{"poc_type": "web-app", "scenarios": []}\n'
        )
        result = _extract_markdown_plan_from_response(raw)
        assert "# PoC Plan" in result
        assert "Deploy and test" in result
        assert "poc_type" not in result

    def test_returns_empty_for_no_plan_markers(self):
        from autopoc.agents.poc_plan import _extract_markdown_plan_from_response

        result = _extract_markdown_plan_from_response("Just some random text with no plan")
        assert result == ""

    def test_extracts_from_multiline_ai_content(self):
        """Simulate concatenated AI messages where plan is in an earlier message."""
        from autopoc.agents.poc_plan import _extract_markdown_plan_from_response

        raw = (
            "I'll analyze the repository.\n\n"
            "Let me read the key files.\n\n"
            "# PoC Plan: my-project\n\n"
            "## Project Classification\n"
            "- **Type:** rag\n"
            "- **Key Technologies:** LangChain, ChromaDB, OpenAI\n\n"
            "## PoC Objectives\n"
            "1. Test document ingestion\n"
            "2. Test RAG query flow\n\n"
            "## Infrastructure Requirements\n"
            "- Vector DB: in-memory (ChromaDB)\n"
            "- Embedding Model: all-MiniLM-L6-v2\n\n"
            "## Test Scenarios\n"
            "### health-check\n"
            "GET /health\n\n"
            "### query-test\n"
            "POST /query\n\n"
            "Now here is the structured output:\n\n"
            '{"poc_type": "rag", "scenarios": [{"name": "health-check"}]}\n'
        )
        result = _extract_markdown_plan_from_response(raw)
        assert "# PoC Plan" in result
        assert "rag" in result
        assert "ChromaDB" in result
        assert "query-test" in result
        assert len(result) > 200  # Should be substantial


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
        """Test that phase 1 (one-shot) returns properly structured state."""
        from langchain_core.messages import AIMessage

        # Phase 1 response: LLM returns poc-plan markdown + JSON directly
        llm_response_text = (
            "# PoC Plan: test-flask\n\n"
            "## Project Classification\n- **Type:** web-app\n\n"
            '{"poc_type": "web-app", "poc_plan_summary": "Deploy and test", '
            '"infrastructure": {"resource_profile": "small"}, '
            '"scenarios": [{"name": "health", "type": "http", "description": "Check health", '
            '"endpoint": "/health", "expected_behavior": "Returns 200", "timeout_seconds": 30}]}'
        )

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content=llm_response_text)

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

        result = await poc_plan_agent(state, llm=mock_llm)

        # poc_plan runs in parallel with fork, so it does NOT set current_phase
        assert "current_phase" not in result
        assert result["poc_type"] == "web-app"
        assert len(result["poc_scenarios"]) == 1
        assert result["poc_scenarios"][0]["name"] == "health"
        assert result["poc_infrastructure"]["resource_profile"] == "small"
        assert result["poc_plan_error"] is None

        # Phase 1 should have been called (one-shot, no ReAct)
        mock_llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_handles_malformed_output(self):
        """Test graceful degradation: phase 1 fails, phase 2 (fallback) also fails."""
        from langchain_core.messages import AIMessage

        # Phase 1: LLM returns non-JSON
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="This is not valid JSON output")

        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "repo_summary": "",
            "components": [],
        }

        # Phase 2 fallback will also be triggered. Mock create_react_agent
        # to return an agent whose output is also malformed.
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"messages": [AIMessage(content="Still not valid JSON")]}

        with (
            patch("autopoc.agents.poc_plan.create_react_agent", return_value=mock_agent),
            patch("autopoc.agents.poc_plan.create_llm", return_value=AsyncMock()),
        ):
            result = await poc_plan_agent(state, llm=mock_llm)

        # poc_plan runs in parallel with fork, so it does NOT set current_phase
        assert "current_phase" not in result
        assert result["poc_type"] == "web-app"  # default
        assert result["poc_scenarios"] == []  # no scenarios parsed
