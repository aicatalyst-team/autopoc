"""Tests for the evaluate agent (RHOAI fitness evaluation)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from autopoc.agents.evaluate import (
    _build_evaluation_from_parsed,
    _build_evaluation_markdown,
    _build_output_schema,
    _empty_evaluation,
    _format_components_for_prompt,
    _format_core_products,
    _format_scoring_dimensions,
    _format_strategy_areas,
    _parse_evaluate_output,
    evaluate_agent,
)
from autopoc.state import PoCPhase, PoCState, RHOAIEvaluation
from autopoc.tools.strategy import (
    get_max_per_dimension,
    get_scoring_dimensions,
    load_strategy,
    load_strategy_baseline,
)


# --- Sample data ---

SAMPLE_LLM_RESPONSE = json.dumps(
    {
        "total_score": 72,
        "dimensions": {
            "audience_value": 15,
            "strategic_alignment": 18,
            "strategy_fit": 14,
            "platform_leverage": 12,
            "demo_potential": 13,
        },
        "dimension_rationales": {
            "audience_value": "Popular ML serving framework with strong community interest.",
            "strategic_alignment": "Directly aligns with model inference strategy area.",
            "strategy_fit": "Enriches vLLM serving story with benchmarking capabilities.",
            "platform_leverage": "Can leverage KServe and vLLM on RHOAI.",
            "demo_potential": "Good visual demo potential with benchmark dashboards.",
        },
        "strategy_areas": ["model-inference", "model-customization"],
        "relationship": "enriches-existing-capability",
        "capability_labels": ["vllm", "serving", "quantization"],
        "rationale": "This project is a model serving benchmark that aligns well with the Red Hat AI inference strategy.",
        "strengths": ["Directly tests inference performance", "Leverages vLLM"],
        "risks": ["May require GPU resources for meaningful benchmarks"],
    }
)

SAMPLE_STATE: PoCState = {
    "project_name": "vllm-benchmark",
    "source_repo_url": "https://github.com/example/vllm-benchmark",
    "repo_digest": "File tree:\n  README.md\n  benchmark.py\n  requirements.txt",
    "repo_summary": "A benchmarking tool for vLLM inference serving.",
    "components": [
        {
            "name": "benchmark",
            "language": "python",
            "build_system": "pip",
            "entry_point": "benchmark.py",
            "port": None,
            "is_ml_workload": True,
            "source_dir": ".",
        }
    ],
    "local_clone_path": None,
}


# --- Tests for _parse_evaluate_output ---


class TestParseEvaluateOutput:
    def test_parses_valid_json(self) -> None:
        result = _parse_evaluate_output(SAMPLE_LLM_RESPONSE)
        assert result["total_score"] == 72
        assert len(result["dimensions"]) == 5

    def test_strips_markdown_code_fences(self) -> None:
        raw = f"```json\n{SAMPLE_LLM_RESPONSE}\n```"
        result = _parse_evaluate_output(raw)
        assert result["total_score"] == 72

    def test_strips_plain_code_fences(self) -> None:
        raw = f"```\n{SAMPLE_LLM_RESPONSE}\n```"
        result = _parse_evaluate_output(raw)
        assert result["total_score"] == 72

    def test_handles_conversational_text(self) -> None:
        raw = f"Here is the evaluation:\n{SAMPLE_LLM_RESPONSE}\nDone!"
        result = _parse_evaluate_output(raw)
        assert result["total_score"] == 72

    def test_handles_invalid_json(self) -> None:
        result = _parse_evaluate_output("This is not JSON at all")
        assert result == {}

    def test_handles_empty_string(self) -> None:
        result = _parse_evaluate_output("")
        assert result == {}


# --- Tests for _build_evaluation_from_parsed ---


class TestBuildEvaluationFromParsed:
    def setup_method(self) -> None:
        self.strategy = load_strategy("redhat-ai-2026")
        self.dimensions = get_scoring_dimensions(self.strategy)
        self.max_per_dim = get_max_per_dimension(self.strategy)

    def test_builds_evaluation(self) -> None:
        parsed = json.loads(SAMPLE_LLM_RESPONSE)
        eval_ = _build_evaluation_from_parsed(
            parsed, self.dimensions, self.max_per_dim, self.strategy
        )
        assert eval_["total_score"] == 72
        assert eval_["max_possible_score"] == 100
        assert len(eval_["dimensions"]) == 5
        assert eval_["relationship"] == "enriches-existing-capability"
        assert "model-inference" in eval_["strategy_areas"]

    def test_clamps_scores_to_max(self) -> None:
        parsed = json.loads(SAMPLE_LLM_RESPONSE)
        parsed["dimensions"]["audience_value"] = 99  # over max of 20
        eval_ = _build_evaluation_from_parsed(
            parsed, self.dimensions, self.max_per_dim, self.strategy
        )
        # Find the audience_value dimension
        av = next(d for d in eval_["dimensions"] if d["name"] == "audience_value")
        assert av["score"] == 20  # clamped to max

    def test_clamps_negative_scores(self) -> None:
        parsed = json.loads(SAMPLE_LLM_RESPONSE)
        parsed["dimensions"]["audience_value"] = -5
        eval_ = _build_evaluation_from_parsed(
            parsed, self.dimensions, self.max_per_dim, self.strategy
        )
        av = next(d for d in eval_["dimensions"] if d["name"] == "audience_value")
        assert av["score"] == 0

    def test_handles_non_numeric_scores(self) -> None:
        parsed = json.loads(SAMPLE_LLM_RESPONSE)
        parsed["dimensions"]["audience_value"] = "high"
        eval_ = _build_evaluation_from_parsed(
            parsed, self.dimensions, self.max_per_dim, self.strategy
        )
        av = next(d for d in eval_["dimensions"] if d["name"] == "audience_value")
        assert av["score"] == 0  # defaults to 0

    def test_handles_missing_dimensions(self) -> None:
        parsed = {"dimensions": {}, "dimension_rationales": {}}
        eval_ = _build_evaluation_from_parsed(
            parsed, self.dimensions, self.max_per_dim, self.strategy
        )
        assert eval_["total_score"] == 0
        assert len(eval_["dimensions"]) == 5
        for dim in eval_["dimensions"]:
            assert dim["score"] == 0

    def test_preserves_rationales(self) -> None:
        parsed = json.loads(SAMPLE_LLM_RESPONSE)
        eval_ = _build_evaluation_from_parsed(
            parsed, self.dimensions, self.max_per_dim, self.strategy
        )
        av = next(d for d in eval_["dimensions"] if d["name"] == "audience_value")
        assert "community" in av["rationale"].lower()


# --- Tests for _empty_evaluation ---


class TestEmptyEvaluation:
    def test_returns_zero_score(self) -> None:
        eval_ = _empty_evaluation("test failure")
        assert eval_["total_score"] == 0
        assert "test failure" in eval_["rationale"]
        assert eval_["relationship"] == "misaligned"
        assert eval_["dimensions"] == []


# --- Tests for prompt formatting ---


class TestFormatScoringDimensions:
    def test_formats_dimensions(self) -> None:
        dims = [{"name": "audience_value", "weight": 1}]
        result = _format_scoring_dimensions(dims, 20)
        assert "audience_value" in result
        assert "0-20" in result

    def test_formats_multiple_dimensions(self) -> None:
        strategy = load_strategy("redhat-ai-2026")
        dims = get_scoring_dimensions(strategy)
        result = _format_scoring_dimensions(dims, 20)
        assert "audience_value" in result
        assert "strategic_alignment" in result
        assert "demo_potential" in result


class TestFormatCoreProducts:
    def test_formats_products(self) -> None:
        baseline = load_strategy_baseline()
        result = _format_core_products(baseline)
        assert "OpenShift AI" in result
        assert "InstructLab" in result

    def test_handles_empty(self) -> None:
        result = _format_core_products({})
        assert "No core products" in result


class TestFormatStrategyAreas:
    def test_formats_areas(self) -> None:
        baseline = load_strategy_baseline()
        result = _format_strategy_areas(baseline)
        assert "Model Inference" in result
        assert "model-inference" in result
        assert "vllm" in result

    def test_handles_empty(self) -> None:
        result = _format_strategy_areas({})
        assert "No strategy areas" in result


class TestFormatComponents:
    def test_formats_single_component(self) -> None:
        comps = [
            {
                "name": "api",
                "language": "python",
                "build_system": "pip",
                "is_ml_workload": True,
                "port": 8080,
            }
        ]
        result = _format_components_for_prompt(comps)
        assert "api" in result
        assert "python" in result
        assert "ml_workload=True" in result
        assert "port=8080" in result

    def test_handles_empty(self) -> None:
        result = _format_components_for_prompt([])
        assert "No components" in result


class TestBuildOutputSchema:
    def test_includes_dimension_names(self) -> None:
        strategy = load_strategy("redhat-ai-2026")
        dims = get_scoring_dimensions(strategy)
        schema = _build_output_schema(dims, 20)
        assert "audience_value" in schema
        assert "strategic_alignment" in schema
        assert "0-20" in schema


# --- Tests for markdown report ---


class TestBuildEvaluationMarkdown:
    def test_generates_valid_markdown(self) -> None:
        eval_ = RHOAIEvaluation(
            total_score=72,
            max_possible_score=100,
            dimensions=[
                {
                    "name": "audience_value",
                    "score": 15,
                    "max_score": 20,
                    "rationale": "Good audience value.",
                },
                {
                    "name": "strategic_alignment",
                    "score": 18,
                    "max_score": 20,
                    "rationale": "Strong alignment.",
                },
            ],
            strategy_areas=["model-inference"],
            relationship="enriches-existing-capability",
            capability_labels=["vllm", "serving"],
            rationale="Good fit for RHOAI.",
            strengths=["Leverages vLLM"],
            risks=["Needs GPU"],
            strategy_name="Red Hat AI 2026",
            strategy_version="2026-04-29",
        )
        md = _build_evaluation_markdown(eval_, "test-project")
        assert "# RHOAI Fitness Evaluation" in md
        assert "test-project" in md
        assert "72/100" in md
        assert "audience_value" in md
        assert "enriches-existing-capability" in md
        assert "Leverages vLLM" in md
        assert "Needs GPU" in md

    def test_handles_empty_evaluation(self) -> None:
        eval_ = _empty_evaluation("test")
        md = _build_evaluation_markdown(eval_, "empty-project")
        assert "# RHOAI Fitness Evaluation" in md
        assert "0/0" in md


# --- Tests for evaluate_agent ---


class TestEvaluateAgent:
    def _make_mock_llm(self, response_text: str) -> AsyncMock:
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = response_text
        mock_llm.ainvoke.return_value = mock_response
        return mock_llm

    @pytest.mark.asyncio
    async def test_happy_path(self, tmp_path: Path) -> None:
        state = dict(SAMPLE_STATE)
        state["local_clone_path"] = str(tmp_path)

        mock_llm = self._make_mock_llm(SAMPLE_LLM_RESPONSE)
        result = await evaluate_agent(state, llm=mock_llm)

        assert result["current_phase"] == PoCPhase.EVALUATE
        eval_ = result["rhoai_evaluation"]
        assert eval_["total_score"] == 72
        assert eval_["max_possible_score"] == 100
        assert eval_["relationship"] == "enriches-existing-capability"
        assert len(eval_["dimensions"]) == 5

        # Verify markdown was written
        md_path = Path(result["rhoai_evaluation_path"])
        assert md_path.exists()
        md_content = md_path.read_text()
        assert "72/100" in md_content

    @pytest.mark.asyncio
    async def test_llm_failure_is_non_blocking(self) -> None:
        state = dict(SAMPLE_STATE)

        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = RuntimeError("LLM exploded")

        result = await evaluate_agent(state, llm=mock_llm)

        assert result["current_phase"] == PoCPhase.EVALUATE
        eval_ = result["rhoai_evaluation"]
        assert eval_["total_score"] == 0
        assert "LLM call failed" in eval_["rationale"]

    @pytest.mark.asyncio
    async def test_json_parse_failure_is_non_blocking(self) -> None:
        state = dict(SAMPLE_STATE)

        mock_llm = self._make_mock_llm("This is not JSON at all, sorry!")

        result = await evaluate_agent(state, llm=mock_llm)

        assert result["current_phase"] == PoCPhase.EVALUATE
        eval_ = result["rhoai_evaluation"]
        assert eval_["total_score"] == 0
        assert "parse failure" in eval_["rationale"].lower()

    @pytest.mark.asyncio
    async def test_no_clone_path_skips_markdown(self) -> None:
        state = dict(SAMPLE_STATE)
        state["local_clone_path"] = None

        mock_llm = self._make_mock_llm(SAMPLE_LLM_RESPONSE)
        result = await evaluate_agent(state, llm=mock_llm)

        assert result["current_phase"] == PoCPhase.EVALUATE
        assert "rhoai_evaluation_path" not in result
        assert result["rhoai_evaluation"]["total_score"] == 72

    @pytest.mark.asyncio
    async def test_prompt_contains_strategy_content(self) -> None:
        state = dict(SAMPLE_STATE)

        mock_llm = self._make_mock_llm(SAMPLE_LLM_RESPONSE)
        await evaluate_agent(state, llm=mock_llm)

        # Verify the system prompt contains strategy content
        call_args = mock_llm.ainvoke.call_args[0][0]
        system_msg = call_args[0]  # SystemMessage
        assert "Model Inference" in system_msg.content
        assert "OpenShift AI" in system_msg.content
        assert "audience_value" in system_msg.content

    @pytest.mark.asyncio
    async def test_prompt_contains_repo_context(self) -> None:
        state = dict(SAMPLE_STATE)

        mock_llm = self._make_mock_llm(SAMPLE_LLM_RESPONSE)
        await evaluate_agent(state, llm=mock_llm)

        call_args = mock_llm.ainvoke.call_args[0][0]
        user_msg = call_args[1]  # HumanMessage
        assert "vllm-benchmark" in user_msg.content
        assert "benchmark" in user_msg.content.lower()

    @pytest.mark.asyncio
    async def test_llm_response_with_list_content(self) -> None:
        """Test that list-type content from LLM is handled correctly."""
        state = dict(SAMPLE_STATE)

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [{"text": SAMPLE_LLM_RESPONSE}]
        mock_llm.ainvoke.return_value = mock_response

        result = await evaluate_agent(state, llm=mock_llm)

        assert result["rhoai_evaluation"]["total_score"] == 72

    @pytest.mark.asyncio
    async def test_score_clamping_in_full_flow(self, tmp_path: Path) -> None:
        """Test that out-of-range scores from LLM are clamped."""
        state = dict(SAMPLE_STATE)
        state["local_clone_path"] = str(tmp_path)

        bad_response = json.dumps(
            {
                "total_score": 999,
                "dimensions": {
                    "audience_value": 50,
                    "strategic_alignment": -10,
                    "strategy_fit": 14,
                    "platform_leverage": 12,
                    "demo_potential": 13,
                },
                "dimension_rationales": {
                    "audience_value": "r",
                    "strategic_alignment": "r",
                    "strategy_fit": "r",
                    "platform_leverage": "r",
                    "demo_potential": "r",
                },
                "strategy_areas": [],
                "relationship": "enriches-existing-capability",
                "capability_labels": [],
                "rationale": "Test.",
                "strengths": [],
                "risks": [],
            }
        )

        mock_llm = self._make_mock_llm(bad_response)
        result = await evaluate_agent(state, llm=mock_llm)

        eval_ = result["rhoai_evaluation"]
        dims = {d["name"]: d["score"] for d in eval_["dimensions"]}
        assert dims["audience_value"] == 20  # clamped from 50
        assert dims["strategic_alignment"] == 0  # clamped from -10
        assert eval_["total_score"] == 20 + 0 + 14 + 12 + 13  # = 59
