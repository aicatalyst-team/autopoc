"""Tests for the PoC Execute agent."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopoc.agents.poc_execute import (
    _parse_poc_results,
    _validate_result,
    _build_user_message,
    poc_execute_agent,
)
from autopoc.state import PoCPhase, PoCResult


# --- Tests for _parse_poc_results ---


class TestParsePocResults:
    def test_parses_valid_json_results(self):
        raw = json.dumps(
            {
                "results": [
                    {
                        "scenario_name": "health",
                        "status": "pass",
                        "output": "OK",
                        "duration_seconds": 0.5,
                    },
                    {
                        "scenario_name": "api",
                        "status": "fail",
                        "error_message": "404",
                        "duration_seconds": 1.0,
                    },
                ]
            }
        )
        results = _parse_poc_results(raw)
        assert len(results) == 2
        assert results[0]["scenario_name"] == "health"
        assert results[0]["status"] == "pass"
        assert results[1]["status"] == "fail"
        assert results[1]["error_message"] == "404"

    def test_parses_embedded_json(self):
        raw = 'Some text before\n{"results": [{"scenario_name": "test", "status": "pass"}]}\nSome text after'
        results = _parse_poc_results(raw)
        assert len(results) == 1
        assert results[0]["scenario_name"] == "test"

    def test_parses_individual_result_objects(self):
        raw = 'Result 1: {"scenario_name": "a", "status": "pass"}\nResult 2: {"scenario_name": "b", "status": "fail"}'
        results = _parse_poc_results(raw)
        assert len(results) == 2

    def test_returns_empty_for_unparseable_output(self):
        raw = "No JSON here at all, just plain text"
        results = _parse_poc_results(raw)
        assert results == []

    def test_returns_empty_for_empty_string(self):
        results = _parse_poc_results("")
        assert results == []


# --- Tests for _validate_result ---


class TestValidateResult:
    def test_validates_complete_result(self):
        r = {
            "scenario_name": "inference",
            "status": "pass",
            "output": "prediction: positive",
            "error_message": None,
            "duration_seconds": 1.5,
        }
        result = _validate_result(r)
        assert result["scenario_name"] == "inference"
        assert result["status"] == "pass"
        assert result["duration_seconds"] == 1.5

    def test_validates_partial_result(self):
        r = {"scenario_name": "test"}
        result = _validate_result(r)
        assert result["scenario_name"] == "test"
        assert result["status"] == "error"  # default
        assert result["duration_seconds"] == 0  # default

    def test_truncates_long_output(self):
        r = {
            "scenario_name": "test",
            "status": "pass",
            "output": "x" * 5000,
        }
        result = _validate_result(r)
        assert len(result["output"]) <= 2000


# --- Tests for _build_user_message ---


class TestBuildUserMessage:
    def test_includes_poc_plan(self):
        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "poc_plan": "# PoC Plan\nTest the API",
            "poc_scenarios": [],
            "routes": ["http://localhost:8080"],
            "deployed_resources": ["deployment/api"],
        }
        msg = _build_user_message(state)
        assert "PoC Plan" in msg
        assert "Test the API" in msg

    def test_includes_scenarios(self):
        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "poc_scenarios": [
                {
                    "name": "health",
                    "description": "Check health",
                    "type": "http",
                    "endpoint": "/health",
                    "expected_behavior": "200 OK",
                    "timeout_seconds": 30,
                },
            ],
            "routes": [],
            "deployed_resources": [],
        }
        msg = _build_user_message(state)
        assert "health" in msg
        assert "/health" in msg

    def test_includes_routes(self):
        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "poc_scenarios": [],
            "routes": ["http://10.0.0.1:30080", "http://10.0.0.1:30081"],
            "deployed_resources": [],
        }
        msg = _build_user_message(state)
        assert "http://10.0.0.1:30080" in msg
        assert "http://10.0.0.1:30081" in msg


# --- Tests for poc_execute_agent ---


class TestPocExecuteAgent:
    @pytest.mark.asyncio
    async def test_agent_returns_results(self):
        """Test that the agent returns properly structured results."""
        from langchain_core.messages import AIMessage

        mock_msg = MagicMock(spec=AIMessage)
        mock_msg.content = json.dumps(
            {
                "results": [
                    {
                        "scenario_name": "health",
                        "status": "pass",
                        "output": "OK",
                        "duration_seconds": 0.3,
                    },
                ]
            }
        )

        mock_agent_result = {"messages": [mock_msg]}

        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "poc_plan": "Test plan",
            "poc_scenarios": [{"name": "health", "type": "http"}],
            "routes": ["http://localhost:8080"],
            "deployed_resources": ["deployment/app"],
        }

        with patch("autopoc.agents.poc_execute.create_react_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = mock_agent_result
            mock_create.return_value = mock_agent

            result = await poc_execute_agent(state, llm=MagicMock())

        assert result["current_phase"] == PoCPhase.POC_EXECUTE
        assert len(result["poc_results"]) == 1
        assert result["poc_results"][0]["status"] == "pass"

    @pytest.mark.asyncio
    async def test_agent_handles_exception(self):
        """Test error handling when agent invocation fails."""
        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "poc_scenarios": [],
            "routes": [],
            "deployed_resources": [],
        }

        with patch("autopoc.agents.poc_execute.create_react_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.side_effect = Exception("LLM connection failed")
            mock_create.return_value = mock_agent

            result = await poc_execute_agent(state, llm=MagicMock())

        assert result["current_phase"] == PoCPhase.POC_EXECUTE
        assert len(result["poc_results"]) == 1
        assert result["poc_results"][0]["status"] == "error"
        assert "LLM connection failed" in result["error"]
