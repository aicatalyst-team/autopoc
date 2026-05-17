"""Evaluate agent — scores a project's fitness for OpenShift AI PoC.

Uses the strategy baseline (``data/strategy-baseline.yaml``) and the active
strategy profile to evaluate how well a repository fits the Red Hat OpenShift
AI platform.  Produces a numeric score (0-100) with per-dimension breakdown.

This agent is **non-blocking**: if the evaluation fails for any reason (LLM
error, JSON parse failure, missing strategy files), the pipeline continues
with an empty evaluation.  Evaluation is informational — it should never
prevent a PoC from running.

Architecture:
    - One-shot LLM call (same pattern as intake — no ReAct, no tools)
    - Strategy content is loaded at runtime and injected into the prompt
    - Scoring dimensions are read dynamically from the active strategy YAML
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from autopoc.llm import create_llm
from autopoc.state import (
    ComponentInfo,
    PoCPhase,
    PoCState,
    PoCStateUpdate,
    RHOAIDimensionScore,
    RHOAIEvaluation,
)
from autopoc.tools.strategy import (
    compute_max_score,
    get_max_per_dimension,
    get_scoring_dimensions,
    load_strategy,
    load_strategy_baseline,
)

logger = logging.getLogger(__name__)

EVALUATE_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "evaluate.md"


def _empty_evaluation(reason: str) -> RHOAIEvaluation:
    """Return a minimal evaluation struct for when evaluation fails."""
    return RHOAIEvaluation(
        total_score=0,
        max_possible_score=0,
        dimensions=[],
        strategy_areas=[],
        relationship="misaligned",
        capability_labels=[],
        rationale=f"Evaluation failed: {reason}",
        strengths=[],
        risks=[],
        strategy_name="unknown",
        strategy_version="unknown",
    )


# ---------------------------------------------------------------------------
# Prompt formatting helpers
# ---------------------------------------------------------------------------


def _format_scoring_dimensions(dimensions: list[dict[str, Any]], max_per_dim: int) -> str:
    """Render scoring dimensions as a numbered list for the prompt."""
    lines = []
    for i, dim in enumerate(dimensions, 1):
        name = dim["name"]
        # Provide human-readable descriptions for known dimensions
        desc = _DIMENSION_DESCRIPTIONS.get(name, name.replace("_", " ").title())
        lines.append(f"{i}. **{name}** (0-{max_per_dim}): {desc}")
    return "\n".join(lines)


_DIMENSION_DESCRIPTIONS: dict[str, str] = {
    "audience_value": (
        "How valuable and interesting is this project to RHOAI users, "
        "customers, and the broader AI/ML community?"
    ),
    "strategic_alignment": (
        "How well does this project align with the 4 official CY2026 "
        "strategy areas (Model Inference, Model Customization, Agentic AI, "
        "Management/Observability/Security)?"
    ),
    "strategy_fit": (
        "Does this project enrich existing Red Hat AI capabilities, or does "
        "it merely duplicate them?  Higher score = enriches / validates; "
        "lower score = duplicates / is misaligned."
    ),
    "platform_leverage": (
        "Does this project leverage RHOAI platform components such as "
        "KServe, vLLM, Kubeflow Pipelines, Model Registry, TrustyAI, "
        "Jupyter workbenches, etc.?"
    ),
    "demo_potential": (
        "How compelling is this as a live PoC or demo?  Consider visual "
        "impact, narrative clarity, audience engagement, and ease of "
        "showcasing on the platform."
    ),
    # Legacy classic dimensions
    "novelty": "How novel or fresh is this project?  Higher for recent, trending projects.",
    "openshift_fit": "How well does this fit on OpenShift specifically?",
}


def _format_core_products(baseline: dict[str, Any]) -> str:
    """Render core products as a bullet list."""
    products = baseline.get("core_products", [])
    lines = []
    for prod in products:
        name = prod.get("name", "Unknown")
        role = prod.get("role", "")
        lines.append(f"- **{name}**: {role}")
    return "\n".join(lines) if lines else "No core products defined."


def _format_strategy_areas(baseline: dict[str, Any]) -> str:
    """Render strategy areas with capability labels and enrich/duplicate criteria."""
    areas = baseline.get("strategy_areas", [])
    sections = []
    for area in areas:
        category = area.get("category", "unknown")
        official_name = area.get("official_name", category)
        summary = area.get("summary", "").strip()
        labels = area.get("capability_labels", [])
        stack = area.get("red_hat_stack", [])
        enrich = area.get("enrich_if", [])
        duplicate = area.get("duplicate_if", [])

        section = f"##### {official_name} (`{category}`)\n\n"
        if summary:
            section += f"{summary}\n\n"
        if labels:
            section += f"**Capability labels:** {', '.join(labels)}\n\n"
        if stack:
            section += f"**Red Hat stack:** {', '.join(stack)}\n\n"
        if enrich:
            section += "**Enrich if:**\n"
            for item in enrich:
                section += f"- {item}\n"
            section += "\n"
        if duplicate:
            section += "**Duplicate if:**\n"
            for item in duplicate:
                section += f"- {item}\n"
            section += "\n"

        sections.append(section)

    return "\n".join(sections) if sections else "No strategy areas defined."


def _format_duplication_guidance(baseline: dict[str, Any]) -> str:
    """Render global duplication guidance."""
    guidance = baseline.get("duplication_guidance", {})
    enrich = guidance.get("enrich_if", [])
    avoid = guidance.get("avoid_if", [])
    lines = []
    if enrich:
        lines.append("**Enrich (positive signal) if:**")
        for item in enrich:
            lines.append(f"- {item}")
    if avoid:
        lines.append("\n**Avoid (negative signal) if:**")
        for item in avoid:
            lines.append(f"- {item}")
    return "\n".join(lines) if lines else "No duplication guidance defined."


def _format_relationship_rules(baseline: dict[str, Any]) -> str:
    """Render relationship classification rules."""
    rules = baseline.get("relationship_rules", {})
    lines = []
    for label, desc in rules.items():
        lines.append(f"- **{label}**: {desc}")
    return "\n".join(lines) if lines else "No relationship rules defined."


def _build_output_schema(dimensions: list[dict[str, Any]], max_per_dim: int) -> str:
    """Build the expected JSON output schema dynamically from dimensions."""
    dim_entries = []
    for dim in dimensions:
        name = dim["name"]
        dim_entries.append(f'        "{name}": <integer 0-{max_per_dim}>')

    dim_rationale_entries = []
    for dim in dimensions:
        name = dim["name"]
        dim_rationale_entries.append(f'        "{name}": "<1-2 sentence rationale>"')

    schema = (
        """{
    "total_score": <integer, sum of all dimension scores>,
    "dimensions": {
"""
        + ",\n".join(dim_entries)
        + """
    },
    "dimension_rationales": {
"""
        + ",\n".join(dim_rationale_entries)
        + """
    },
    "strategy_areas": ["<category-id>", ...],
    "relationship": "<one of the relationship labels>",
    "capability_labels": ["<label>", ...],
    "rationale": "<2-3 sentence overall assessment>",
    "strengths": ["<strength 1>", "<strength 2>", ...],
    "risks": ["<risk 1>", ...]
}"""
    )
    return schema


def _format_components_for_prompt(components: list[dict] | list[ComponentInfo]) -> str:
    """Format component info for the user message."""
    if not components:
        return "No components detected."

    lines = []
    for comp in components:
        name = comp.get("name", "unknown")
        lang = comp.get("language", "unknown")
        build = comp.get("build_system", "unknown")
        ml = comp.get("is_ml_workload", False)
        port = comp.get("port")
        entry = comp.get("entry_point", "")
        source_dir = comp.get("source_dir", ".")

        parts = [
            f"**{name}**: language={lang}, build_system={build}",
            f"ml_workload={ml}",
        ]
        if port:
            parts.append(f"port={port}")
        if entry:
            parts.append(f"entry_point={entry}")
        if source_dir and source_dir != ".":
            parts.append(f"source_dir={source_dir}")

        lines.append("- " + ", ".join(parts))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def _parse_evaluate_output(raw_output: str) -> dict:
    """Parse the JSON output from the evaluate LLM response.

    Handles common issues like markdown code fences around JSON.
    """
    text = raw_output.strip()

    # Try markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Fallback: extract from first { to last }
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse evaluate output as JSON: %s", e)
        return {}


def _build_evaluation_from_parsed(
    parsed: dict,
    dimensions: list[dict[str, Any]],
    max_per_dim: int,
    strategy: dict[str, Any],
) -> RHOAIEvaluation:
    """Convert parsed JSON into a validated RHOAIEvaluation."""
    dim_scores_raw = parsed.get("dimensions", {})
    dim_rationales_raw = parsed.get("dimension_rationales", {})

    dim_scores: list[RHOAIDimensionScore] = []
    total = 0

    for dim in dimensions:
        name = dim["name"]
        raw_score = dim_scores_raw.get(name, 0)
        # Clamp to valid range
        if not isinstance(raw_score, (int, float)):
            raw_score = 0
        score = max(0, min(int(raw_score), max_per_dim))
        total += score

        rationale = dim_rationales_raw.get(name, "")
        dim_scores.append(
            RHOAIDimensionScore(
                name=name,
                score=score,
                max_score=max_per_dim,
                rationale=rationale,
            )
        )

    max_possible = compute_max_score(strategy)

    return RHOAIEvaluation(
        total_score=total,
        max_possible_score=max_possible,
        dimensions=dim_scores,
        strategy_areas=parsed.get("strategy_areas", []),
        relationship=parsed.get("relationship", "misaligned"),
        capability_labels=parsed.get("capability_labels", []),
        rationale=parsed.get("rationale", ""),
        strengths=parsed.get("strengths", []),
        risks=parsed.get("risks", []),
        strategy_name=strategy.get("name", "unknown"),
        strategy_version=strategy.get("version", "unknown"),
    )


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _build_evaluation_markdown(
    evaluation: RHOAIEvaluation,
    project_name: str,
) -> str:
    """Render the evaluation as a Markdown report."""
    lines = [
        "# RHOAI Fitness Evaluation",
        "",
        f"**Project:** {project_name}",
        f"**Strategy:** {evaluation.get('strategy_name', 'unknown')}"
        f" (v{evaluation.get('strategy_version', '?')})",
        f"**Total Score:** {evaluation.get('total_score', 0)}"
        f"/{evaluation.get('max_possible_score', 0)}",
        "",
        "## Score Breakdown",
        "",
        "| Dimension | Score | Max | Rationale |",
        "|-----------|-------|-----|-----------|",
    ]

    for dim in evaluation.get("dimensions", []):
        name = dim.get("name", "")
        score = dim.get("score", 0)
        max_s = dim.get("max_score", 0)
        rationale = dim.get("rationale", "").replace("|", "\\|")
        lines.append(f"| {name} | {score} | {max_s} | {rationale} |")

    lines.extend(
        [
            "",
            "## Strategy Alignment",
            "",
        ]
    )

    areas = evaluation.get("strategy_areas", [])
    lines.append(f"**Relevant areas:** {', '.join(areas) if areas else 'None'}")

    relationship = evaluation.get("relationship", "misaligned")
    lines.append(f"**Relationship:** {relationship}")

    labels = evaluation.get("capability_labels", [])
    lines.append(f"**Matched capabilities:** {', '.join(labels) if labels else 'None'}")

    lines.extend(
        [
            "",
            "## Assessment",
            "",
            evaluation.get("rationale", "No assessment available."),
            "",
        ]
    )

    strengths = evaluation.get("strengths", [])
    if strengths:
        lines.append("### Strengths")
        lines.append("")
        for s in strengths:
            lines.append(f"- {s}")
        lines.append("")

    risks = evaluation.get("risks", [])
    if risks:
        lines.append("### Risks")
        lines.append("")
        for r in risks:
            lines.append(f"- {r}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------


async def evaluate_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> PoCStateUpdate:
    """Evaluate a project's fitness for OpenShift AI PoC.

    This is a LangGraph node function.  It:
    1. Loads the active strategy and baseline
    2. Builds a prompt with repo context + strategy context
    3. Makes a one-shot LLM call
    4. Parses the JSON response into ``RHOAIEvaluation``
    5. Writes ``rhoai-evaluation.md`` to the repo directory
    6. Returns partial state update

    Non-blocking: if any step fails, returns an empty evaluation and
    the pipeline continues normally.

    Args:
        state: Current pipeline state (needs ``repo_digest``,
            ``repo_summary``, ``components`` from intake).
        llm: Optional LLM override (for testing).

    Returns:
        Partial state update dict.
    """
    project_name = state.get("project_name", "unknown")
    clone_path = state.get("local_clone_path")

    logger.info("Starting RHOAI fitness evaluation for %s", project_name)

    # ---- Load strategy ----
    try:
        strategy = load_strategy()
        baseline = load_strategy_baseline()
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Cannot load strategy files: %s — skipping evaluation", exc)
        return {
            "current_phase": PoCPhase.EVALUATE,
            "rhoai_evaluation": _empty_evaluation(str(exc)),
        }

    dimensions = get_scoring_dimensions(strategy)
    max_per_dim = get_max_per_dimension(strategy)

    # ---- Build system prompt ----
    try:
        prompt_template = EVALUATE_PROMPT_PATH.read_text()
    except FileNotFoundError:
        logger.warning("Evaluate prompt not found at %s — skipping", EVALUATE_PROMPT_PATH)
        return {
            "current_phase": PoCPhase.EVALUATE,
            "rhoai_evaluation": _empty_evaluation("Prompt template not found"),
        }

    system_prompt = prompt_template.format(
        scoring_dimensions=_format_scoring_dimensions(dimensions, max_per_dim),
        core_products=_format_core_products(baseline),
        strategy_areas=_format_strategy_areas(baseline),
        duplication_guidance=_format_duplication_guidance(baseline),
        relationship_rules=_format_relationship_rules(baseline),
        output_schema=_build_output_schema(dimensions, max_per_dim),
    )

    # ---- Build user message ----
    repo_digest = state.get("repo_digest", "")
    repo_summary = state.get("repo_summary", "")
    components = state.get("components", [])
    source_url = state.get("source_repo_url", "")

    user_message = (
        f"Project name: {project_name}\n"
        f"Source URL: {source_url}\n\n"
        f"## Repository Summary\n\n{repo_summary}\n\n"
        f"## Detected Components\n\n{_format_components_for_prompt(components)}\n\n"
        f"## Repository Digest\n\n{repo_digest}\n\n"
        f"Evaluate this project and produce your JSON output."
    )

    # ---- LLM call ----
    if llm is None:
        llm = create_llm()

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
        )
    except Exception as exc:
        logger.warning("Evaluate LLM call failed: %s — skipping evaluation", exc)
        return {
            "current_phase": PoCPhase.EVALUATE,
            "rhoai_evaluation": _empty_evaluation(f"LLM call failed: {exc}"),
        }

    # ---- Parse response ----
    raw_output = response.content
    if isinstance(raw_output, list):
        raw_output = "".join(
            part["text"] if isinstance(part, dict) and "text" in part else str(part)
            for part in raw_output
        )

    parsed = _parse_evaluate_output(raw_output)
    if not parsed:
        logger.warning("Failed to parse evaluate output — returning empty evaluation")
        return {
            "current_phase": PoCPhase.EVALUATE,
            "rhoai_evaluation": _empty_evaluation("JSON parse failure"),
        }

    evaluation = _build_evaluation_from_parsed(parsed, dimensions, max_per_dim, strategy)

    logger.info(
        "RHOAI evaluation complete: score=%d/%d, relationship=%s, areas=%s",
        evaluation.get("total_score", 0),
        evaluation.get("max_possible_score", 0),
        evaluation.get("relationship", "?"),
        evaluation.get("strategy_areas", []),
    )

    # ---- Write markdown report ----
    result: dict[str, Any] = {
        "current_phase": PoCPhase.EVALUATE,
        "rhoai_evaluation": evaluation,
    }

    if clone_path:
        try:
            md_content = _build_evaluation_markdown(evaluation, project_name)
            md_path = Path(clone_path) / "rhoai-evaluation.md"
            md_path.write_text(md_content)
            result["rhoai_evaluation_path"] = str(md_path)
            logger.info("Wrote evaluation report to %s", md_path)
        except Exception as exc:
            logger.warning("Failed to write evaluation markdown: %s", exc)

    return result
