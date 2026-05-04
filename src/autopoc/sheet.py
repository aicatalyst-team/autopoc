"""Google Sheet reader for PoC candidate projects.

Reads a POC Explorer spreadsheet via the Google Sheets API, filters rows
to find actionable GitHub projects, and selects one for the pipeline.

The expected sheet structure (matching POC Explorer output):
  - Row 1: metadata (run info)
  - Row 2: review URL
  - Row 3: header row (column names)
  - Row 4+: data rows

Only the first tab (index 0) is read.

Phase 13 additions: pre-filtering, multi-candidate evaluation, and
best-candidate selection for the ``run-sheet`` command.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlparse

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Number of metadata rows before the header row (run info + review URL).
_METADATA_ROWS = 2


@dataclass
class SheetProject:
    """A project selected from the Google Sheet."""

    name: str
    """Project name, from the 'title' column."""

    repo_url: str
    """Repository URL, from the 'link' column."""

    category: str
    """Project category (e.g. 'rag', 'agents'), informational."""

    row_index: int
    """1-based row number in the spreadsheet (for logging/diagnostics)."""


def read_sheet(credentials_file: str, sheet_id: str) -> list[dict[str, str]]:
    """Read all data rows from the first tab of a Google Sheet.

    Authenticates with a service account, reads tab 0, skips the two
    metadata rows, uses row 3 as the header, and returns remaining rows
    as a list of dicts keyed by column name.

    Args:
        credentials_file: Path to the Google service account JSON key file.
        sheet_id: The spreadsheet ID (from the Google Sheets URL).

    Returns:
        List of dicts, one per data row, keyed by header column names.
        Empty values are represented as empty strings.

    Raises:
        FileNotFoundError: If the credentials file does not exist.
        google.auth.exceptions.DefaultCredentialsError: On auth failure.
        googleapiclient.errors.HttpError: On API errors (e.g. sheet not
            found, permission denied).
        ValueError: If the sheet has no data rows or no header row.
    """
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Get the name of the first tab
    spreadsheet = (
        service.spreadsheets()
        .get(spreadsheetId=sheet_id, fields="sheets.properties")
        .execute()
    )
    sheets = spreadsheet.get("sheets", [])
    if not sheets:
        raise ValueError(f"Spreadsheet {sheet_id} has no tabs")
    tab_name = sheets[0]["properties"]["title"]
    logger.info("Reading tab '%s' from spreadsheet %s", tab_name, sheet_id)

    # Read all cells from the first tab
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"'{tab_name}'!A1:ZZ")
        .execute()
    )
    all_rows: list[list[str]] = result.get("values", [])

    return _parse_rows(all_rows)


def _parse_rows(all_rows: list[list[str]]) -> list[dict[str, str]]:
    """Parse raw sheet rows into dicts, skipping metadata and using the header.

    Exported for testability — ``read_sheet`` delegates to this after
    fetching the raw values from the API.

    Args:
        all_rows: Raw list-of-lists from the Sheets API (or CSV reader).

    Returns:
        List of dicts keyed by header column names.

    Raises:
        ValueError: If there are not enough rows for metadata + header.
    """
    min_rows = _METADATA_ROWS + 1  # metadata rows + header
    if len(all_rows) < min_rows:
        raise ValueError(
            f"Sheet has {len(all_rows)} rows, expected at least {min_rows} "
            f"({_METADATA_ROWS} metadata + 1 header)"
        )

    header = all_rows[_METADATA_ROWS]
    data_rows = all_rows[_METADATA_ROWS + 1 :]

    if not header:
        raise ValueError("Header row is empty")

    logger.info(
        "Parsed sheet: %d columns, %d data rows",
        len(header),
        len(data_rows),
    )

    parsed: list[dict[str, str]] = []
    for row in data_rows:
        # Pad ragged rows with empty strings
        padded = row + [""] * (len(header) - len(row))
        parsed.append(dict(zip(header, padded)))

    return parsed


def filter_projects(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filter rows to actionable GitHub projects.

    Applies two filters in order:
    1. **Link filter**: keep only rows where the ``link`` column is a
       ``github.com`` URL.
    2. **PM decision filter**: if a ``pm_decision`` column exists *and*
       at least one row has a non-empty value, keep only rows where the
       value contains "approve" (case-insensitive).  If the column is
       absent or entirely empty, this filter is skipped.

    Original row order is preserved.

    Args:
        rows: Parsed sheet rows (list of dicts from ``read_sheet``).

    Returns:
        Filtered list of dicts (subset of *rows*), preserving order.
    """
    # --- Link filter: GitHub repos only ---
    github_rows = [r for r in rows if _is_github_url(r.get("link", ""))]
    logger.info(
        "Link filter: %d/%d rows have GitHub links",
        len(github_rows),
        len(rows),
    )

    # --- PM decision filter ---
    has_pm_column = any("pm_decision" in r for r in rows)
    pm_column_has_values = has_pm_column and any(
        r.get("pm_decision", "").strip() for r in rows
    )

    if pm_column_has_values:
        approved = [
            r
            for r in github_rows
            if "approve" in r.get("pm_decision", "").lower()
        ]
        logger.info(
            "PM decision filter: %d/%d GitHub rows are approved",
            len(approved),
            len(github_rows),
        )
        return approved

    logger.info("No pm_decision values found — skipping approval filter")
    return github_rows


def select_project(
    rows: list[dict[str, str]],
    *,
    data_start_row: int = _METADATA_ROWS + 1,
) -> SheetProject:
    """Select the first project from filtered rows.

    Args:
        rows: Filtered rows from ``filter_projects``. Must not be empty.
        data_start_row: 0-based index of the first data row in the
            original sheet (used to compute the 1-based ``row_index``
            for diagnostics). Defaults to 3 (after 2 metadata + 1 header).

    Returns:
        A ``SheetProject`` for the first row.

    Raises:
        ValueError: If *rows* is empty (nothing survived filtering).
    """
    if not rows:
        raise ValueError(
            "No projects remain after filtering — nothing to PoC. "
            "Check that the sheet has GitHub repos with pm_decision = Approved."
        )

    row = rows[0]

    if "title" not in row:
        raise ValueError(
            "Selected row is missing the 'title' column. "
            f"Available columns: {', '.join(sorted(row.keys()))}"
        )
    if "link" not in row:
        raise ValueError(
            "Selected row is missing the 'link' column. "
            f"Available columns: {', '.join(sorted(row.keys()))}"
        )

    # row_index: 1-based row number in the spreadsheet
    # data_start_row is 0-based index of the first data row in the values
    # array, so the first data row = data_start_row + 1 in the spreadsheet.
    row_index = data_start_row + 1  # 1-based

    project = SheetProject(
        name=_derive_project_name(row["link"], row["title"]),
        repo_url=row["link"],
        category=row.get("category", ""),
        row_index=row_index,
    )

    logger.info(
        "Selected project: %s (%s) from sheet row %d",
        project.name,
        project.repo_url,
        project.row_index,
    )

    return project


def _derive_project_name(repo_url: str, title: str) -> str:
    """Derive a clean, filesystem/registry-safe project name.

    The sheet ``title`` column is typically in ``owner/repo`` format
    (e.g. ``microsoft/TRELLIS.2``).  Slashes, uppercase, and special
    characters cause problems downstream (Quay repo names, directory
    paths, thread IDs).

    Strategy:
    1. Try to extract the repo name from the GitHub URL path
       (``https://github.com/owner/repo`` → ``repo``).
    2. Fall back to the title with the owner prefix stripped.
    3. Lowercase the result and replace any remaining unsafe characters.

    Args:
        repo_url: The GitHub repository URL.
        title: The raw title from the sheet.

    Returns:
        A lowercase, slash-free project name safe for use in paths,
        Quay repo names, and thread IDs.
    """
    name = ""

    # Try to extract from URL path: /owner/repo -> repo
    try:
        path = urlparse(repo_url).path.strip("/")
        parts = path.split("/")
        if len(parts) >= 2:
            name = parts[1]
    except Exception:
        pass

    # Fall back to title
    if not name:
        # Strip owner/ prefix if present
        if "/" in title:
            name = title.rsplit("/", 1)[1]
        else:
            name = title

    # Clean up: lowercase, strip .git suffix, replace unsafe chars
    name = name.lower().removesuffix(".git").strip()
    # Replace characters that are unsafe in file paths, Quay repo names,
    # or Kubernetes resource names with hyphens.
    name = "".join(c if c.isalnum() or c in ".-_" else "-" for c in name)
    # Collapse multiple hyphens and strip leading/trailing hyphens
    while "--" in name:
        name = name.replace("--", "-")
    name = name.strip("-")

    return name or "unknown-project"


def _is_github_url(url: str) -> bool:
    """Check if a URL points to github.com."""
    try:
        parsed = urlparse(url)
        return parsed.netloc in ("github.com", "www.github.com")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Phase 13: Pre-filtering, candidate evaluation, and selection
# ---------------------------------------------------------------------------


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
            part["text"] if isinstance(part, dict) and "text" in part else str(part)
            for part in raw
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

        project = SheetProject(
            name=project_name,
            repo_url=repo_url,
            category=row.get("category", ""),
            row_index=idx + 1,
        )

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
