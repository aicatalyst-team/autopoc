"""Tests for the PoC Report agent."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopoc.agents.poc_report import (
    _build_user_message,
    poc_report_agent,
)
from autopoc.state import PoCPhase


# --- Tests for _build_user_message ---


class TestBuildUserMessage:
    def test_includes_all_state_fields(self):
        """Test that the user message includes all relevant pipeline data."""
        state = {
            "project_name": "test-app",
            "source_repo_url": "https://github.com/test/app",
            "local_clone_path": "/tmp/test-app",
            "repo_summary": "A Flask web application",
            "poc_type": "web-app",
            "components": [
                {
                    "name": "api",
                    "language": "python",
                    "build_system": "pip",
                    "is_ml_workload": False,
                    "port": 8000,
                },
            ],
            "poc_plan": "# PoC Plan\nTest the web app endpoints",
            "poc_infrastructure": {"resource_profile": "small"},
            "poc_scenarios": [
                {"name": "health", "description": "Health check"},
            ],
            "built_images": ["quay.io/org/test-app-api:latest"],
            "build_retries": 0,
            "deployed_resources": ["deployment/api", "service/api"],
            "routes": ["http://localhost:30080"],
            "deploy_retries": 0,
            "poc_results": [
                {
                    "scenario_name": "health",
                    "status": "pass",
                    "output": "OK",
                    "duration_seconds": 0.5,
                },
            ],
            "poc_script_path": "/tmp/test-app/poc_test.py",
        }
        msg = _build_user_message(state)

        # Check key content is present
        assert "test-app" in msg
        assert "https://github.com/test/app" in msg
        assert "Flask web application" in msg
        assert "web-app" in msg
        assert "api" in msg
        assert "python" in msg
        assert "quay.io/org/test-app-api:latest" in msg
        assert "deployment/api" in msg
        assert "http://localhost:30080" in msg
        assert "PASS" in msg
        assert "health" in msg
        assert "1/1 passed" in msg

    def test_handles_partial_state(self):
        """Test with minimal state (some phases failed)."""
        state = {
            "project_name": "failed-project",
            "source_repo_url": "https://github.com/test/fail",
            "local_clone_path": "/tmp/failed",
            "repo_summary": "A test project",
            "components": [],
            "built_images": [],
            "deployed_resources": [],
            "routes": [],
            "poc_results": [],
            "error": "Build failed: missing dependency",
            "build_retries": 3,
        }
        msg = _build_user_message(state)

        assert "failed-project" in msg
        assert "Build failed: missing dependency" in msg
        assert "Build Retries:** 3" in msg
        assert "No images were built" in msg
        assert "No resources were deployed" in msg
        assert "No test results available" in msg

    def test_includes_poc_infrastructure_json(self):
        """Test that infrastructure requirements are included as JSON."""
        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "poc_infrastructure": {
                "needs_inference_server": True,
                "inference_server_type": "vllm",
                "resource_profile": "gpu",
            },
            "components": [],
            "built_images": [],
            "deployed_resources": [],
            "routes": [],
            "poc_results": [],
        }
        msg = _build_user_message(state)
        assert "vllm" in msg
        assert "gpu" in msg

    def test_includes_gitlab_url(self):
        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "gitlab_repo_url": "https://gitlab.internal/group/test",
            "components": [],
            "built_images": [],
            "deployed_resources": [],
            "routes": [],
            "poc_results": [],
        }
        msg = _build_user_message(state)
        assert "https://gitlab.internal/group/test" in msg


# --- Tests for poc_report_agent ---


class TestPocReportAgent:
    @pytest.mark.asyncio
    async def test_agent_returns_report_path(self):
        """Test that the agent returns the report file path."""
        from langchain_core.messages import AIMessage

        mock_msg = MagicMock(spec=AIMessage)
        mock_msg.content = "Report written to /tmp/test/poc-report.md"

        mock_agent_result = {"messages": [mock_msg]}

        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "repo_summary": "Test project",
            "components": [],
            "built_images": [],
            "deployed_resources": [],
            "routes": [],
            "poc_results": [],
        }

        with patch("autopoc.agents.poc_report.create_react_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = mock_agent_result
            mock_create.return_value = mock_agent

            result = await poc_report_agent(state, llm=MagicMock())

        assert result["current_phase"] == PoCPhase.POC_REPORT
        assert result["poc_report_path"] == "/tmp/test/poc-report.md"

    @pytest.mark.asyncio
    async def test_agent_handles_exception(self):
        """Test error handling when agent invocation fails."""
        state = {
            "project_name": "test",
            "local_clone_path": "/tmp/test",
            "components": [],
            "built_images": [],
            "deployed_resources": [],
            "routes": [],
            "poc_results": [],
        }

        with patch("autopoc.agents.poc_report.create_react_agent") as mock_create:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.side_effect = Exception("LLM timeout")
            mock_create.return_value = mock_agent

            result = await poc_report_agent(state, llm=MagicMock())

        assert result["current_phase"] == PoCPhase.POC_REPORT
        assert "LLM timeout" in result.get("error", "")
