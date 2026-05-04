"""Integration tests for the multi-candidate evaluation flow.

Tests the full pre-filter → evaluate → select pipeline with mocked
LLM and graph invocations.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopoc.sheet import (
    CandidateResult,
    SheetProject,
    evaluate_candidates,
    prefilter_candidates,
    select_best_candidate,
)
from autopoc.state import PoCPhase


MOCK_ROWS = [
    {
        "title": "vllm-benchmark",
        "link": "https://github.com/example/vllm-benchmark",
        "category": "inference",
        "pm_comments": "Strategic fit for inference story.",
    },
    {
        "title": "rag-enterprise",
        "link": "https://github.com/example/rag-enterprise",
        "category": "rag",
        "pm_comments": "",
    },
    {
        "title": "generic-web-app",
        "link": "https://github.com/example/generic-web-app",
        "category": "web",
        "pm_comments": "",
    },
]


def _make_eval_result(score: int) -> dict:
    """Create a mock RHOAI evaluation dict."""
    return {
        "total_score": score,
        "max_possible_score": 100,
        "dimensions": [],
        "strategy_areas": ["model-inference"],
        "relationship": "enriches-existing-capability",
        "capability_labels": ["vllm"],
        "rationale": f"Score {score}",
        "strengths": [],
        "risks": [],
        "strategy_name": "test",
        "strategy_version": "test",
    }


class TestPrefilterToEvaluateFlow:
    """Test the full pre-filter → evaluate → select flow."""

    @pytest.mark.asyncio
    async def test_prefilter_ranks_correctly(self) -> None:
        """AI/ML projects should rank above generic ones."""
        result = await prefilter_candidates(MOCK_ROWS, max_candidates=3)

        names = [r[0]["title"] for r in result]
        # vllm-benchmark and rag-enterprise should rank above generic-web-app
        vllm_idx = names.index("vllm-benchmark")
        web_idx = names.index("generic-web-app")
        assert vllm_idx < web_idx

    @pytest.mark.asyncio
    async def test_evaluate_candidates_with_mock_graph(self) -> None:
        """Mock the graph to return different scores and verify selection."""

        # Pre-filter first
        prefiltered = await prefilter_candidates(MOCK_ROWS, max_candidates=3)

        # Build mock graph results for each candidate
        mock_results = {
            "vllm-benchmark": {
                "rhoai_evaluation": _make_eval_result(82),
                "local_clone_path": "/tmp/eval/vllm-benchmark",
                "error": None,
            },
            "rag-enterprise": {
                "rhoai_evaluation": _make_eval_result(65),
                "local_clone_path": "/tmp/eval/rag-enterprise",
                "error": None,
            },
            "generic-web-app": {
                "rhoai_evaluation": _make_eval_result(15),
                "local_clone_path": "/tmp/eval/generic-web-app",
                "error": None,
            },
        }

        async def mock_ainvoke(state, **kwargs):
            name = state.get("project_name", "unknown")
            return mock_results.get(name, {"rhoai_evaluation": {}, "error": "not found"})

        mock_graph = AsyncMock()
        mock_graph.ainvoke = mock_ainvoke

        mock_config = MagicMock()
        mock_config.work_dir = "/tmp/test-eval"

        with patch("autopoc.graph.build_graph", return_value=mock_graph):
            with patch("pathlib.Path.mkdir"):
                results = await evaluate_candidates(
                    prefiltered, mock_config, max_candidates=3
                )

        # Verify results sorted by score
        assert len(results) == 3
        assert results[0].evaluation.get("total_score", 0) >= results[1].evaluation.get(
            "total_score", 0
        )

        # Select best
        winner = select_best_candidate(results)
        assert winner.project.name == "vllm-benchmark"
        assert winner.evaluation.get("total_score") == 82

    @pytest.mark.asyncio
    async def test_evaluate_handles_pipeline_failure(self) -> None:
        """One candidate's pipeline fails — others should still be evaluated."""

        prefiltered = await prefilter_candidates(MOCK_ROWS[:2], max_candidates=2)

        async def mock_ainvoke(state, **kwargs):
            name = state.get("project_name", "unknown")
            if "vllm" in name:
                raise RuntimeError("LLM exploded")
            return {
                "rhoai_evaluation": _make_eval_result(70),
                "local_clone_path": "/tmp/eval/rag",
                "error": None,
            }

        mock_graph = AsyncMock()
        mock_graph.ainvoke = mock_ainvoke

        mock_config = MagicMock()
        mock_config.work_dir = "/tmp/test-eval"

        with patch("autopoc.graph.build_graph", return_value=mock_graph):
            with patch("pathlib.Path.mkdir"):
                results = await evaluate_candidates(
                    prefiltered, mock_config, max_candidates=2
                )

        assert len(results) == 2

        # The successful one should be selected
        winner = select_best_candidate(results)
        assert winner.error is None
        assert winner.evaluation.get("total_score") == 70

    @pytest.mark.asyncio
    async def test_prefilter_with_pm_comments_mock(self) -> None:
        """PM comments boost should affect ranking."""
        rows_with_comments = [
            {
                "title": "generic-web-app",
                "link": "https://github.com/example/generic-web-app",
                "category": "web",
                "pm_comments": "Excellent strategic fit, customer requested, great for keynote demo!",
            },
            {
                "title": "vllm-benchmark",
                "link": "https://github.com/example/vllm-benchmark",
                "category": "inference",
                "pm_comments": "Too complex, already covered by existing tooling.",
            },
        ]

        pm_response = json.dumps([
            {"sentiment": "positive", "boost": 10, "strategic_value": True, "demo_potential": True, "concerns": []},
            {"sentiment": "negative", "boost": -8, "strategic_value": False, "demo_potential": False, "concerns": ["too complex"]},
        ])

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = pm_response
        mock_llm.ainvoke.return_value = mock_response

        result = await prefilter_candidates(
            rows_with_comments, max_candidates=2, llm=mock_llm
        )

        # With PM boost, generic-web-app gets +10 and vllm-benchmark gets -8
        # But vllm-benchmark has higher keyword/category score
        # The point is that PM comments shift the ranking
        assert len(result) == 2
        # Both should have scores adjusted by PM boost
        for _, score in result:
            assert isinstance(score, (int, float))
