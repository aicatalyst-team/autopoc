"""Candidate pre-filtering and evaluation for PoC project selection."""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from autopoc.sheet import SheetProject, _row_to_project

logger = logging.getLogger(__name__)


class PMCommentSignals(TypedDict, total=False):
    """Structured signals extracted from a PM comment."""

    sentiment: str  # "positive", "neutral", "negative", "none"
    strategic_value: bool  # PM noted strategic alignment
    demo_potential: bool  # PM noted demo/showcase value
    concerns: list[str]  # Extracted concerns
    boost: int  # -10 to +10 adjustment to heuristic score


@dataclass
class CandidateResult:
    """Result of evaluating a single candidate project."""

    project: SheetProject
    """The sheet project metadata."""

    evaluation: dict[str, Any] = field(default_factory=dict)
    """RHOAI evaluation dict (may be empty if evaluation failed)."""

    heuristic_score: float = 0.0
    """Pre-filter heuristic score."""

    clone_path: str | None = None
    """Path to the cloned repo (preserved for winner reuse)."""

    error: str | None = None
    """Error message if evaluation failed."""


# ---- Category-to-strategy mapping ----

# Maps common sheet category values to strategy area identifiers.
# Built once from the baseline, but these are typical fallback defaults.
_DEFAULT_CATEGORY_MAP: dict[str, str] = {
    "rag": "model-customization",
    "retrieval": "model-customization",
    "fine-tuning": "model-customization",
    "fine_tuning": "model-customization",
    "finetuning": "model-customization",
    "training": "model-customization",
    "data-prep": "model-customization",
    "inference": "model-inference",
    "serving": "model-inference",
    "model-serving": "model-inference",
    "model_serving": "model-inference",
    "optimization": "model-inference",
    "quantization": "model-inference",
    "agents": "agentic-ai",
    "agent": "agentic-ai",
    "agentic": "agentic-ai",
    "chatbot": "agentic-ai",
    "tools": "agentic-ai",
    "mcp": "agentic-ai",
    "observability": "management-observability-security",
    "guardrails": "management-observability-security",
    "security": "management-observability-security",
    "monitoring": "management-observability-security",
    "registry": "management-observability-security",
    "catalog": "management-observability-security",
}


def _build_category_mapping(baseline: dict[str, Any]) -> dict[str, str]:
    """Build a mapping from category keywords to strategy area identifiers.

    Starts with defaults and enriches from the baseline's capability labels.
    """
    mapping = dict(_DEFAULT_CATEGORY_MAP)

    for area in baseline.get("strategy_areas", []):
        category = area.get("category", "")
        # Map each capability label to its parent strategy area
        for label in area.get("capability_labels", []):
            mapping.setdefault(label, category)

    return mapping


def _collect_all_capability_labels(baseline: dict[str, Any]) -> set[str]:
    """Collect all capability labels from the strategy baseline."""
    labels: set[str] = set()
    for area in baseline.get("strategy_areas", []):
        for label in area.get("capability_labels", []):
            labels.add(label.lower())
    return labels


def _count_keyword_matches(text: str, labels: set[str]) -> int:
    """Count how many capability labels appear in the text.

    Uses word boundary matching to avoid false positives (e.g. "rag" in
    "storage").  Hyphens are treated as word characters for labels like
    ``fine-tuning``.
    """
    if not text:
        return 0

    text_lower = text.lower()
    count = 0
    for label in labels:
        # Escape the label for regex and match as whole word
        pattern = r"(?:^|[\s/\-_.])(" + re.escape(label) + r")(?:[\s/\-_.]|$)"
        if re.search(pattern, text_lower):
            count += 1
    return count


def _compute_heuristic_score(
    row: dict[str, str],
    category_map: dict[str, str],
    capability_labels: set[str],
) -> float:
    """Compute a cheap heuristic score for a single candidate row.

    Returns a float in the range [0, 60] (before PM comment boost).
    """
    score = 0.0

    # --- Category match (0-30) ---
    category = row.get("category", "").strip().lower()
    if category and category in category_map:
        score += 30.0
    elif category:
        # Partial match: check if category contains a mapped keyword
        for key in category_map:
            if key in category or category in key:
                score += 15.0
                break

    # --- Keyword match in title + link (0-30) ---
    title = row.get("title", "")
    link = row.get("link", "")
    searchable = f"{title} {link}"
    matches = _count_keyword_matches(searchable, capability_labels)
    # Cap at 30, with 10 points per match
    score += min(matches * 10.0, 30.0)

    return score


async def prefilter_candidates(
    rows: list[dict[str, str]],
    *,
    max_candidates: int = 5,
    llm: Any | None = None,
) -> list[tuple[dict[str, str], float]]:
    """Pre-filter candidates using cheap heuristics + optional PM comments.

    Returns a list of ``(row, heuristic_score)`` tuples sorted by score
    descending, capped at *max_candidates*.

    Args:
        rows: Filtered sheet rows (from :func:`filter_projects`).
        max_candidates: Maximum number of candidates to return.
        llm: Optional LLM for PM comments parsing.  If ``None`` and PM
            comments exist, an LLM is created automatically.

    Returns:
        List of (row, score) tuples, sorted by score descending.
    """
    from autopoc.tools.strategy import load_strategy_baseline

    try:
        baseline = load_strategy_baseline()
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Cannot load strategy baseline for pre-filter: %s", exc)
        # Fall back: return rows in original order with score 0
        return [(r, 0.0) for r in rows[:max_candidates]]

    category_map = _build_category_mapping(baseline)
    capability_labels = _collect_all_capability_labels(baseline)

    # Compute heuristic scores
    scored: list[tuple[dict[str, str], float]] = []
    for row in rows:
        score = _compute_heuristic_score(row, category_map, capability_labels)
        scored.append((row, score))

    # --- PM comments boost ---
    has_pm_comments = any(r.get("pm_comments", "").strip() for r in rows)
    if has_pm_comments:
        strategy_areas = [a.get("official_name", "") for a in baseline.get("strategy_areas", [])]
        try:
            pm_signals = await _parse_pm_comments(rows, strategy_areas, llm)
            for i, (row, base_score) in enumerate(scored):
                signals = pm_signals.get(i, {})
                boost = signals.get("boost", 0)
                scored[i] = (row, base_score + boost)
        except Exception as exc:
            logger.warning("PM comments parsing failed: %s — using keyword-only scores", exc)

    # Sort by score descending, stable (preserves sheet order for ties)
    scored.sort(key=lambda x: x[1], reverse=True)

    result = scored[:max_candidates]
    logger.info(
        "Pre-filter: %d candidates → top %d (scores: %s)",
        len(rows),
        len(result),
        [f"{r[0].get('title', '?')[:30]}={r[1]:.0f}" for r in result],
    )
    return result


# ---- PM comments parsing ----

_PM_COMMENTS_PROMPT_PATH = Path(__file__).parent / "prompts" / "prefilter_pm_comments.md"


async def _parse_pm_comments(
    rows: list[dict[str, str]],
    strategy_areas: list[str],
    llm: Any | None = None,
) -> dict[int, PMCommentSignals]:
    """Parse PM comments for all candidates in a single batched LLM call.

    Args:
        rows: All candidate rows.
        strategy_areas: List of strategy area names for context.
        llm: Optional LLM instance.

    Returns:
        Dict mapping row index to extracted signals.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    # Collect non-empty comments
    comments: list[tuple[int, str]] = []
    for i, row in enumerate(rows):
        text = row.get("pm_comments", "").strip()
        if text:
            comments.append((i, text))

    if not comments:
        return {}

    # Build batched prompt
    try:
        system_prompt = _PM_COMMENTS_PROMPT_PATH.read_text()
    except FileNotFoundError:
        logger.warning("PM comments prompt not found — skipping")
        return {}

    entries = []
    for idx, (i, text) in enumerate(comments):
        title = rows[i].get("title", f"candidate-{i}")
        entries.append(f"[{idx}] Project: {title}\n   PM comment: {text}")

    user_message = (
        f"Strategy areas: {', '.join(strategy_areas)}\n\n"
        f"Candidates with PM comments:\n\n"
        + "\n\n".join(entries)
        + "\n\nAnalyze each comment and produce your JSON array output."
    )

    if llm is None:
        from autopoc.llm import create_llm

        llm = create_llm()

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
        )
    except Exception as exc:
        logger.warning("PM comments LLM call failed: %s", exc)
        return {}

    raw = response.content
    if isinstance(raw, list):
        raw = "".join(
            part["text"] if isinstance(part, dict) and "text" in part else str(part) for part in raw
        )

    # Parse JSON array from response
    parsed = _parse_pm_comments_response(raw)
    if not parsed:
        return {}

    # Map back to original row indices
    result: dict[int, PMCommentSignals] = {}
    for idx, signals in enumerate(parsed):
        if idx < len(comments):
            original_idx = comments[idx][0]
            result[original_idx] = signals

    return result


def _parse_pm_comments_response(raw: str) -> list[PMCommentSignals]:
    """Parse the JSON array response from the PM comments LLM call."""
    text = raw.strip()

    # Try markdown code block
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            text = match.group(0)

    try:
        data = json.loads(text)
        if not isinstance(data, list):
            return []
        return data
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse PM comments response as JSON: %s", e)
        return []


# ---- Candidate evaluation ----


async def evaluate_candidates(
    candidates: list[tuple[dict[str, str], float]],
    config: Any,
    *,
    max_candidates: int = 5,
    on_progress: Any | None = None,
) -> list[CandidateResult]:
    """Evaluate multiple candidates using the RHOAI fitness evaluation.

    For each candidate, runs the pipeline with ``stop_after="evaluate"``
    to get intake + RHOAI evaluation results.  Candidates are evaluated
    sequentially to respect LLM rate limits.

    Args:
        candidates: List of ``(row, heuristic_score)`` tuples from
            :func:`prefilter_candidates`.
        config: ``AutoPoCConfig`` instance.
        max_candidates: Maximum number to evaluate (should match pre-filter).
        on_progress: Optional callback ``(index, total, project_name)`` for
            progress reporting.

    Returns:
        List of ``CandidateResult`` sorted by total_score descending.
    """
    from autopoc.graph import build_graph
    from autopoc.sheet import _derive_project_name
    from autopoc.state import PoCPhase

    results: list[CandidateResult] = []
    eval_dir = Path(config.work_dir) / "_eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    to_evaluate = candidates[:max_candidates]

    for idx, (row, heuristic_score) in enumerate(to_evaluate):
        title = row.get("title", f"candidate-{idx}")
        repo_url = row.get("link", "")
        project_name = _derive_project_name(repo_url, title)

        if on_progress:
            on_progress(idx, len(to_evaluate), project_name)

        logger.info(
            "Evaluating candidate %d/%d: %s (heuristic=%.0f)",
            idx + 1,
            len(to_evaluate),
            project_name,
            heuristic_score,
        )

        project = _row_to_project(row, fallback_row_index=idx + 1)

        # Run partial pipeline: intake → evaluate
        try:
            graph = build_graph(stop_after="evaluate")
            initial_state = {
                "project_name": project_name,
                "source_repo_url": repo_url,
                "current_phase": PoCPhase.INTAKE,
                "error": None,
                "messages": [],
                "components": [],
                "repo_digest": "",
                "repo_summary": "",
            }

            result = await graph.ainvoke(initial_state)

            evaluation = result.get("rhoai_evaluation", {})
            clone_path = result.get("local_clone_path")
            error = result.get("error")

            results.append(
                CandidateResult(
                    project=project,
                    evaluation=evaluation,
                    heuristic_score=heuristic_score,
                    clone_path=clone_path,
                    error=error,
                )
            )
        except Exception as exc:
            logger.warning("Evaluation failed for %s: %s", project_name, exc)
            results.append(
                CandidateResult(
                    project=project,
                    evaluation={},
                    heuristic_score=heuristic_score,
                    clone_path=None,
                    error=str(exc),
                )
            )

    # Sort by total_score descending
    results.sort(
        key=lambda r: (
            r.error is None,  # successful evaluations first
            r.evaluation.get("total_score", 0),
            r.heuristic_score,
        ),
        reverse=True,
    )

    logger.info(
        "Evaluation complete: %d candidates scored. Top: %s (%d)",
        len(results),
        results[0].project.name if results else "none",
        results[0].evaluation.get("total_score", 0) if results else 0,
    )

    return results


def select_best_candidate(results: list[CandidateResult]) -> CandidateResult:
    """Select the best candidate from evaluation results.

    Selection priority:
    1. Successful evaluations over failed ones
    2. Highest ``total_score`` from RHOAI evaluation
    3. Highest ``heuristic_score`` from pre-filter
    4. First in list order (stable, preserves sheet order)

    Args:
        results: Sorted results from :func:`evaluate_candidates`.

    Returns:
        The best candidate.

    Raises:
        ValueError: If *results* is empty.
    """
    if not results:
        raise ValueError("No candidate results to select from.")

    # Results are already sorted by evaluate_candidates, so the first is best
    winner = results[0]

    logger.info(
        "Selected best candidate: %s (score=%d, heuristic=%.0f, error=%s)",
        winner.project.name,
        winner.evaluation.get("total_score", 0),
        winner.heuristic_score,
        winner.error,
    )

    return winner


def cleanup_candidate_clones(
    results: list[CandidateResult],
    winner: CandidateResult,
) -> None:
    """Remove clone directories for non-winning candidates.

    Preserves the winner's clone for reuse in the full pipeline.

    Args:
        results: All candidate results.
        winner: The selected winner.
    """
    for result in results:
        if result is winner:
            continue
        if result.clone_path and Path(result.clone_path).exists():
            try:
                shutil.rmtree(result.clone_path)
                logger.debug("Cleaned up clone: %s", result.clone_path)
            except Exception as exc:
                logger.warning("Failed to clean up %s: %s", result.clone_path, exc)
