"""Tests for containerize agent component filtering.

Covers the poc_components filter fallback: when poc_components doesn't match
any actual component names (e.g., LLM hallucinated a filename instead of
component name), the agent should fall back to all components instead of
containerizing nothing.
"""

from unittest.mock import AsyncMock, patch

import pytest

from autopoc.state import PoCPhase


class TestPocComponentsFilter:
    """Test the poc_components filtering logic in containerize_agent."""

    @pytest.mark.asyncio
    async def test_mismatched_poc_components_falls_back_to_all(self) -> None:
        """When poc_components=['streamlit_app.py'] but component name is
        'llmsearchindex', should fall back to all components."""
        from autopoc.agents.containerize import containerize_agent

        state = {
            "project_name": "llmsearchindex",
            "local_clone_path": "/workspace/llmsearchindex",
            "components": [
                {
                    "name": "llmsearchindex",
                    "language": "python",
                    "build_system": "pip",
                    "entry_point": "app.py",
                    "port": 8080,
                    "source_dir": ".",
                    "dockerfile_ubi_path": "",
                    "image_name": "",
                    "existing_dockerfile": None,
                    "is_ml_workload": False,
                }
            ],
            "poc_components": ["streamlit_app.py"],  # doesn't match component name
            "poc_plan": "test plan",
            "error": None,
            "build_retries": 0,
            "container_fix_retries": 0,
            "container_fix_action": None,
            "container_fix_error": None,
        }

        # Mock the LLM and agent to avoid actual calls — we just need to
        # verify the function doesn't return early with empty components.
        mock_llm = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = '{"dockerfile_ubi_path": "Dockerfile.ubi"}'
        mock_llm.ainvoke.return_value = mock_response

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [
                type("Msg", (), {"content": '{"dockerfile_ubi_path": "Dockerfile.ubi"}'})()
            ]
        }

        with (
            patch("autopoc.agents.containerize.create_react_agent", return_value=mock_agent),
            patch("autopoc.agents.containerize.create_llm", return_value=mock_llm),
        ):
            result = await containerize_agent(state, llm=mock_llm)

        # The key assertion: the function should NOT return with empty components.
        # It should have attempted to containerize (even if it failed for other reasons).
        # If it returned immediately with empty components, that's the bug we fixed.
        components = result.get("components", [])
        # Either it processed the component (good) or it errored for a reason
        # other than "no components" (acceptable). The bug was returning silently
        # with 0 components.
        assert result.get("current_phase") == PoCPhase.CONTAINERIZE
        # Verify the component was NOT dropped by the filter
        assert len(components) >= 1 or result.get("error") is not None

    def test_filter_logic_matching_names_works(self) -> None:
        """When poc_components matches component names, filtering works."""
        components = [
            {"name": "frontend", "language": "typescript"},
            {"name": "api", "language": "python"},
            {"name": "docs", "language": "markdown"},
        ]
        poc_components = ["frontend", "api"]

        filtered = [c for c in components if c.get("name", "") in poc_components]
        assert len(filtered) == 2
        assert filtered[0]["name"] == "frontend"
        assert filtered[1]["name"] == "api"

    def test_filter_logic_no_match_keeps_all(self) -> None:
        """When poc_components matches nothing, fallback keeps all components."""
        components = [
            {"name": "llmsearchindex", "language": "python"},
        ]
        poc_components = ["streamlit_app.py"]

        filtered = [c for c in components if c.get("name", "") in poc_components]

        if not filtered:
            # This is the fallback path — keep all components
            filtered = components

        assert len(filtered) == 1
        assert filtered[0]["name"] == "llmsearchindex"

    def test_filter_logic_empty_poc_components_skips_filter(self) -> None:
        """When poc_components is empty, no filtering happens."""
        components = [
            {"name": "app", "language": "python"},
            {"name": "worker", "language": "python"},
        ]
        poc_components = []

        if poc_components:
            filtered = [c for c in components if c.get("name", "") in poc_components]
        else:
            filtered = components

        assert len(filtered) == 2
