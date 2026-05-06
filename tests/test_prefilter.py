"""Tests for Phase 13 pre-filter, candidate evaluation, and selection."""

import json

import pytest

from autopoc.sheet import (
    CandidateResult,
    SheetProject,
    _build_category_mapping,
    _collect_all_capability_labels,
    _compute_heuristic_score,
    _count_keyword_matches,
    _parse_pm_comments_response,
    cleanup_candidate_clones,
    prefilter_candidates,
    select_best_candidate,
)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SAMPLE_ROWS = [
    {
        "title": "vllm/vllm-benchmark",
        "link": "https://github.com/vllm-project/vllm-benchmark",
        "category": "inference",
        "pm_comments": "",
    },
    {
        "title": "langchain-rag-demo",
        "link": "https://github.com/example/langchain-rag-demo",
        "category": "rag",
        "pm_comments": "Great fit for customer demo, aligns with RAG strategy.",
    },
    {
        "title": "generic-web-app",
        "link": "https://github.com/example/generic-web-app",
        "category": "web",
        "pm_comments": "",
    },
    {
        "title": "agent-toolkit",
        "link": "https://github.com/example/mcp-agent-toolkit",
        "category": "agents",
        "pm_comments": "Too complex for a PoC, needs GPU cluster.",
    },
    {
        "title": "ml-dashboard",
        "link": "https://github.com/example/ml-dashboard",
        "category": "observability",
        "pm_comments": "",
    },
]


# ---------------------------------------------------------------------------
# Tests: Category mapping
# ---------------------------------------------------------------------------


class TestBuildCategoryMapping:
    def test_default_mappings_present(self) -> None:
        mapping = _build_category_mapping({})
        assert mapping["rag"] == "model-customization"
        assert mapping["inference"] == "model-inference"
        assert mapping["agents"] == "agentic-ai"
        assert mapping["observability"] == "management-observability-security"

    def test_enriched_from_baseline(self) -> None:
        baseline = {
            "strategy_areas": [
                {
                    "category": "model-inference",
                    "capability_labels": ["vllm", "kserve"],
                },
            ],
        }
        mapping = _build_category_mapping(baseline)
        assert mapping["vllm"] == "model-inference"
        assert mapping["kserve"] == "model-inference"

    def test_loads_real_baseline(self) -> None:
        from autopoc.tools.strategy import load_strategy_baseline

        baseline = load_strategy_baseline()
        mapping = _build_category_mapping(baseline)
        assert "vllm" in mapping
        assert "rag" in mapping
        assert "mcp" in mapping


# ---------------------------------------------------------------------------
# Tests: Capability label collection
# ---------------------------------------------------------------------------


class TestCollectCapabilityLabels:
    def test_collects_from_baseline(self) -> None:
        baseline = {
            "strategy_areas": [
                {"capability_labels": ["vllm", "kserve"]},
                {"capability_labels": ["rag", "fine-tuning"]},
            ],
        }
        labels = _collect_all_capability_labels(baseline)
        assert "vllm" in labels
        assert "rag" in labels
        assert "fine-tuning" in labels

    def test_empty_baseline(self) -> None:
        labels = _collect_all_capability_labels({})
        assert len(labels) == 0


# ---------------------------------------------------------------------------
# Tests: Keyword matching
# ---------------------------------------------------------------------------


class TestCountKeywordMatches:
    def test_matches_in_url(self) -> None:
        labels = {"vllm", "serving", "benchmark"}
        assert _count_keyword_matches("vllm-serving-benchmark", labels) == 3

    def test_no_matches(self) -> None:
        labels = {"vllm", "serving"}
        assert _count_keyword_matches("generic-web-app", labels) == 0

    def test_case_insensitive(self) -> None:
        labels = {"vllm", "rag"}
        assert _count_keyword_matches("VLLM RAG Pipeline", labels) == 2

    def test_empty_text(self) -> None:
        labels = {"vllm"}
        assert _count_keyword_matches("", labels) == 0

    def test_empty_labels(self) -> None:
        assert _count_keyword_matches("vllm benchmark", set()) == 0

    def test_partial_match_avoided(self) -> None:
        # "rag" should not match inside "storage"
        labels = {"rag"}
        assert _count_keyword_matches("storage system", labels) == 0

    def test_hyphenated_label(self) -> None:
        labels = {"fine-tuning"}
        assert _count_keyword_matches("fine-tuning pipeline", labels) == 1


# ---------------------------------------------------------------------------
# Tests: Heuristic score computation
# ---------------------------------------------------------------------------


class TestComputeHeuristicScore:
    def setup_method(self) -> None:
        from autopoc.tools.strategy import load_strategy_baseline

        baseline = load_strategy_baseline()
        self.category_map = _build_category_mapping(baseline)
        self.labels = _collect_all_capability_labels(baseline)

    def test_inference_project_scores_high(self) -> None:
        row = {
            "title": "vllm-benchmark",
            "link": "https://github.com/example/vllm-serving-benchmark",
            "category": "inference",
        }
        score = _compute_heuristic_score(row, self.category_map, self.labels)
        assert score >= 30  # category match alone = 30

    def test_generic_project_scores_low(self) -> None:
        row = {
            "title": "generic-web-app",
            "link": "https://github.com/example/generic-web-app",
            "category": "web",
        }
        score = _compute_heuristic_score(row, self.category_map, self.labels)
        assert score < 15

    def test_no_category_uses_keywords(self) -> None:
        row = {
            "title": "vllm-kserve-demo",
            "link": "https://github.com/example/vllm-kserve-demo",
            "category": "",
        }
        score = _compute_heuristic_score(row, self.category_map, self.labels)
        assert score > 0  # keyword matches

    def test_empty_row(self) -> None:
        row = {"title": "", "link": "", "category": ""}
        score = _compute_heuristic_score(row, self.category_map, self.labels)
        assert score == 0


# ---------------------------------------------------------------------------
# Tests: Pre-filter (full pipeline, no PM comments)
# ---------------------------------------------------------------------------


class TestPrefilterCandidates:
    @pytest.mark.asyncio
    async def test_ranks_ai_projects_higher(self) -> None:
        result = await prefilter_candidates(SAMPLE_ROWS, max_candidates=5)
        names = [r[0]["title"] for r in result]
        # AI/ML projects should rank above generic-web-app
        ai_idx = names.index("vllm/vllm-benchmark")
        web_idx = names.index("generic-web-app")
        assert ai_idx < web_idx

    @pytest.mark.asyncio
    async def test_respects_max_candidates(self) -> None:
        result = await prefilter_candidates(SAMPLE_ROWS, max_candidates=2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_all_if_fewer_than_max(self) -> None:
        result = await prefilter_candidates(SAMPLE_ROWS[:2], max_candidates=10)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_handles_empty_rows(self) -> None:
        result = await prefilter_candidates([], max_candidates=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_preserves_scores(self) -> None:
        result = await prefilter_candidates(SAMPLE_ROWS, max_candidates=5)
        # Each entry is (row, score)
        for row, score in result:
            assert isinstance(score, (int, float))


# ---------------------------------------------------------------------------
# Tests: PM comments parsing
# ---------------------------------------------------------------------------


class TestParsePmCommentsResponse:
    def test_parses_valid_array(self) -> None:
        raw = json.dumps(
            [
                {"sentiment": "positive", "boost": 7},
                {"sentiment": "negative", "boost": -5},
            ]
        )
        result = _parse_pm_comments_response(raw)
        assert len(result) == 2
        assert result[0]["boost"] == 7

    def test_handles_code_fences(self) -> None:
        raw = '```json\n[{"boost": 3}]\n```'
        result = _parse_pm_comments_response(raw)
        assert len(result) == 1

    def test_handles_invalid_json(self) -> None:
        result = _parse_pm_comments_response("not json")
        assert result == []

    def test_handles_dict_instead_of_array(self) -> None:
        result = _parse_pm_comments_response('{"boost": 5}')
        assert result == []


# ---------------------------------------------------------------------------
# Tests: select_best_candidate
# ---------------------------------------------------------------------------


class TestSelectBestCandidate:
    def _make_result(
        self, name: str, score: int, heuristic: float = 0.0, error: str | None = None
    ) -> CandidateResult:
        return CandidateResult(
            project=SheetProject(
                name=name, repo_url=f"https://github.com/x/{name}", category="", row_index=1
            ),
            evaluation={"total_score": score, "max_possible_score": 100},
            heuristic_score=heuristic,
            error=error,
        )

    def test_highest_score_wins(self) -> None:
        results = [
            self._make_result("low", 30),
            self._make_result("high", 90),
            self._make_result("mid", 60),
        ]
        # Sort like evaluate_candidates does
        results.sort(
            key=lambda r: (r.error is None, r.evaluation.get("total_score", 0), r.heuristic_score),
            reverse=True,
        )
        winner = select_best_candidate(results)
        assert winner.project.name == "high"

    def test_successful_over_failed(self) -> None:
        results = [
            self._make_result("failed-high", 99, error="boom"),
            self._make_result("success-low", 10),
        ]
        results.sort(
            key=lambda r: (r.error is None, r.evaluation.get("total_score", 0), r.heuristic_score),
            reverse=True,
        )
        winner = select_best_candidate(results)
        assert winner.project.name == "success-low"

    def test_heuristic_breaks_tie(self) -> None:
        results = [
            self._make_result("low-heuristic", 50, heuristic=10),
            self._make_result("high-heuristic", 50, heuristic=40),
        ]
        results.sort(
            key=lambda r: (r.error is None, r.evaluation.get("total_score", 0), r.heuristic_score),
            reverse=True,
        )
        winner = select_best_candidate(results)
        assert winner.project.name == "high-heuristic"

    def test_single_candidate(self) -> None:
        results = [self._make_result("only", 42)]
        winner = select_best_candidate(results)
        assert winner.project.name == "only"

    def test_all_failed(self) -> None:
        results = [
            self._make_result("a", 0, heuristic=30, error="fail"),
            self._make_result("b", 0, heuristic=20, error="fail"),
        ]
        results.sort(
            key=lambda r: (r.error is None, r.evaluation.get("total_score", 0), r.heuristic_score),
            reverse=True,
        )
        # Both failed, pick by heuristic
        winner = select_best_candidate(results)
        assert winner.project.name == "a"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="No candidate"):
            select_best_candidate([])


# ---------------------------------------------------------------------------
# Tests: cleanup_candidate_clones
# ---------------------------------------------------------------------------


class TestCleanupCandidateClones:
    def test_preserves_winner_clone(self, tmp_path) -> None:
        winner_dir = tmp_path / "winner"
        winner_dir.mkdir()
        loser_dir = tmp_path / "loser"
        loser_dir.mkdir()

        winner = CandidateResult(
            project=SheetProject(name="w", repo_url="", category="", row_index=1),
            clone_path=str(winner_dir),
        )
        loser = CandidateResult(
            project=SheetProject(name="l", repo_url="", category="", row_index=2),
            clone_path=str(loser_dir),
        )

        cleanup_candidate_clones([winner, loser], winner)

        assert winner_dir.exists()
        assert not loser_dir.exists()
