"""Google Sheet reader and writer for PoC candidate projects.

Reads a POC Explorer spreadsheet via the Google Sheets API, filters rows
to find actionable GitHub projects, selects candidates for the pipeline,
and writes PoC results back to the sheet.

The expected sheet structure (matching POC Explorer output):
  - Row 1: metadata (run info)
  - Row 2: review URL
  - Row 3: header row (column names)
  - Row 4+: data rows

Multiple tabs (up to ``max_tabs``) are scanned left-to-right and
aggregated into a single candidate pool.  Each row carries origin
metadata (tab name + row number) so results can be written back to
the correct location.

Rows that already have PoC results (non-empty ``poc_repo``,
``poc_image``, or ``poc_report`` columns) are automatically excluded
from candidate selection.

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

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Number of metadata rows before the header row (run info + review URL).
_METADATA_ROWS = 2

# Columns written by AutoPoC after a PoC run.
POC_RESULT_COLUMNS = ("poc_repo", "poc_image", "poc_report", "poc_blog")

# Internal key injected into row dicts to track sheet origin.
_ORIGIN_KEY = "_origin"


@dataclass
class SheetRowOrigin:
    """Tracks where a row came from in the spreadsheet.

    Uses tab *name* (not index) as the stable identifier so that
    write-back targets the correct tab even if tabs are reordered
    while the pipeline is running.
    """

    tab_name: str
    """Title of the worksheet tab (stable across reorderings)."""

    tab_gid: int
    """Numeric sheet ID (gid) — immutable within a spreadsheet."""

    row_number: int
    """1-based row number within the tab."""


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

    tab_name: str = ""
    """Name of the tab this project came from."""

    tab_gid: int = 0
    """Numeric sheet ID (gid) of the tab."""


def build_sheets_service(credentials_file: str):
    """Create an authenticated Google Sheets API service.

    Args:
        credentials_file: Path to the Google service account JSON key file.

    Returns:
        A ``googleapiclient.discovery.Resource`` for the Sheets v4 API.
    """
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_sheet(
    credentials_file: str,
    sheet_id: str,
    *,
    max_tabs: int = 1,
) -> list[dict[str, str]]:
    """Read data rows from one or more tabs of a Google Sheet.

    Authenticates with a service account, reads up to *max_tabs* tabs
    (left-to-right), skips the two metadata rows per tab, uses row 3
    as the header, and returns all data rows aggregated into a single
    list.

    Each returned dict has an extra ``_origin`` key containing a
    :class:`SheetRowOrigin` instance that tracks which tab and row the
    data came from.  This metadata is used by write-back functions.

    Args:
        credentials_file: Path to the Google service account JSON key file.
        sheet_id: The spreadsheet ID (from the Google Sheets URL).
        max_tabs: Maximum number of tabs to scan (default 1, leftmost first).

    Returns:
        List of dicts, one per data row, keyed by header column names.
        Empty values are represented as empty strings.

    Raises:
        FileNotFoundError: If the credentials file does not exist.
        google.auth.exceptions.DefaultCredentialsError: On auth failure.
        googleapiclient.errors.HttpError: On API errors (e.g. sheet not
            found, permission denied).
        ValueError: If the sheet has no tabs or no valid data rows.
    """
    service = build_sheets_service(credentials_file)

    # Get tab metadata
    spreadsheet = (
        service.spreadsheets().get(spreadsheetId=sheet_id, fields="sheets.properties").execute()
    )
    sheets = spreadsheet.get("sheets", [])
    if not sheets:
        raise ValueError(f"Spreadsheet {sheet_id} has no tabs")

    tabs_to_read = sheets[: max(1, max_tabs)]

    all_parsed: list[dict[str, str]] = []

    for tab_info in tabs_to_read:
        props = tab_info["properties"]
        tab_name = props["title"]
        tab_gid = props.get("sheetId", 0)
        logger.info("Reading tab '%s' (gid=%d) from spreadsheet %s", tab_name, tab_gid, sheet_id)

        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=f"'{tab_name}'!A1:ZZ")
            .execute()
        )
        raw_rows: list[list[str]] = result.get("values", [])

        try:
            parsed = _parse_rows(raw_rows)
        except ValueError as exc:
            logger.warning("Skipping tab '%s': %s", tab_name, exc)
            continue

        # Inject origin metadata into each row
        data_start_row = _METADATA_ROWS + 1  # 0-based index of first data row
        for i, row in enumerate(parsed):
            row[_ORIGIN_KEY] = SheetRowOrigin(
                tab_name=tab_name,
                tab_gid=tab_gid,
                row_number=data_start_row + i + 1,  # 1-based spreadsheet row
            )

        all_parsed.extend(parsed)

    if not all_parsed:
        raise ValueError(
            f"No valid data rows found across {len(tabs_to_read)} tab(s) in spreadsheet {sheet_id}"
        )

    logger.info(
        "Total rows across %d tab(s): %d",
        len(tabs_to_read),
        len(all_parsed),
    )
    return all_parsed


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


def _has_poc_results(row: dict[str, str]) -> bool:
    """Return True if a row already has PoC result data."""
    return any(row.get(col, "").strip() for col in POC_RESULT_COLUMNS)


def filter_projects(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filter rows to actionable GitHub projects.

    Applies three filters in order:
    1. **Link filter**: keep only rows where the ``link`` column is a
       ``github.com`` URL.
    2. **PM decision filter**: if a ``pm_decision`` column exists *and*
       at least one row has a non-empty value, keep only rows where the
       value contains "approve" (case-insensitive).  If the column is
       absent or entirely empty, this filter is skipped.
    3. **Already-processed filter**: exclude rows that already have a
       non-empty value in any of the PoC result columns (``poc_repo``,
       ``poc_image``, ``poc_report``).

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
    pm_column_has_values = has_pm_column and any(r.get("pm_decision", "").strip() for r in rows)

    if pm_column_has_values:
        approved = [r for r in github_rows if "approve" in r.get("pm_decision", "").lower()]
        logger.info(
            "PM decision filter: %d/%d GitHub rows are approved",
            len(approved),
            len(github_rows),
        )
        candidates = approved
    else:
        logger.info("No pm_decision values found — skipping approval filter")
        candidates = github_rows

    # --- Already-processed filter ---
    before_count = len(candidates)
    candidates = [r for r in candidates if not _has_poc_results(r)]
    skipped = before_count - len(candidates)
    if skipped:
        logger.info(
            "Already-processed filter: skipped %d/%d rows with existing PoC results",
            skipped,
            before_count,
        )

    return candidates


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
            for diagnostics when no ``_origin`` metadata is present).
            Defaults to 3 (after 2 metadata + 1 header).

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
    return _row_to_project(row, fallback_row_index=data_start_row + 1)


def _row_to_project(row: dict[str, str], *, fallback_row_index: int = 4) -> SheetProject:
    """Convert a parsed row dict to a ``SheetProject``.

    Uses ``_origin`` metadata when available, otherwise falls back to
    *fallback_row_index*.
    """
    if "title" not in row:
        raise ValueError(
            "Selected row is missing the 'title' column. "
            f"Available columns: {', '.join(sorted(k for k in row if k != _ORIGIN_KEY))}"
        )
    if "link" not in row:
        raise ValueError(
            "Selected row is missing the 'link' column. "
            f"Available columns: {', '.join(sorted(k for k in row if k != _ORIGIN_KEY))}"
        )

    origin: SheetRowOrigin | None = row.get(_ORIGIN_KEY)  # type: ignore[assignment]

    project = SheetProject(
        name=_derive_project_name(row["link"], row["title"]),
        repo_url=row["link"],
        category=row.get("category", ""),
        row_index=origin.row_number if origin else fallback_row_index,
        tab_name=origin.tab_name if origin else "",
        tab_gid=origin.tab_gid if origin else 0,
    )

    logger.info(
        "Selected project: %s (%s) from tab '%s' row %d",
        project.name,
        project.repo_url,
        project.tab_name,
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


# ---------------------------------------------------------------------------
# Write-back: record PoC results in the Google Sheet
# ---------------------------------------------------------------------------


def _strip_credentials_from_url(url: str) -> str:
    """Remove embedded credentials and ``.git`` suffix from a clone URL.

    Examples::

        https://TOKEN@github.com/org/repo.git  →  https://github.com/org/repo
        https://oauth2:TOKEN@gitlab.example.com/g/p.git  →  https://gitlab.example.com/g/p
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
        # Rebuild without userinfo (username:password)
        clean = parsed._replace(netloc=parsed.hostname or "")
        if parsed.port:
            clean = clean._replace(netloc=f"{parsed.hostname}:{parsed.port}")
        result = clean.geturl()
    except Exception:
        result = url
    # Strip trailing .git
    if result.endswith(".git"):
        result = result[:-4]
    return result


def derive_fork_browse_url(
    source_repo_url: str,
    fork_target: str,
    *,
    github_org: str | None = None,
    gitlab_url: str | None = None,
    gitlab_group: str | None = None,
) -> str | None:
    """Derive a browsable URL to the fork from the source repo URL and config.

    This is a best-effort fallback for when the pipeline result does not
    contain ``fork_repo_url`` (e.g. the pipeline crashed before or during
    the fork step, or the fork already existed).

    Args:
        source_repo_url: Original GitHub source repository URL.
        fork_target: ``"github"`` or ``"gitlab"``.
        github_org: GitHub org for forks (if fork_target is github).
        gitlab_url: GitLab instance URL (if fork_target is gitlab).
        gitlab_group: GitLab group/namespace (if fork_target is gitlab).

    Returns:
        Browsable URL to the fork, or ``None`` if it cannot be derived.
    """
    try:
        parsed = urlparse(source_repo_url)
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 2:
            return None
        repo_name = path_parts[1].removesuffix(".git")
    except Exception:
        return None

    if fork_target == "github" and github_org:
        return f"https://github.com/{github_org}/{repo_name}"
    elif fork_target == "gitlab" and gitlab_url and gitlab_group:
        base = gitlab_url.rstrip("/")
        return f"{base}/{gitlab_group}/{repo_name}"

    return None


def derive_quay_search_url(
    project_name: str,
    quay_registry: str,
    quay_org: str,
) -> str:
    """Build a Quay repository search URL for a project.

    Returns a URL to the Quay organization page filtered by the
    project name.  This always resolves to a valid page (the search
    results may be empty, but the page itself loads).

    Args:
        project_name: Project name used as search filter.
        quay_registry: Quay registry hostname (e.g. ``quay.io``).
        quay_org: Quay organization name.

    Returns:
        Browsable URL to the Quay search page.
    """
    # Strip any scheme prefix
    host = quay_registry
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.rstrip("/")
    return f"https://{host}/organization/{quay_org}?tab=repositories&q={project_name}"


def _check_url_exists(url: str, *, timeout: float = 5.0) -> bool:
    """Best-effort HTTP HEAD check to see if a URL exists.

    Returns ``True`` for 2xx and 3xx responses, ``False`` for 4xx/5xx
    or any network/timeout error.  Uses a short timeout to avoid
    blocking the pipeline.
    """
    import httpx

    try:
        response = httpx.head(url, timeout=timeout, follow_redirects=True)
        return response.status_code < 400
    except Exception:
        return False


def _build_artifacts_branch_url(fork_repo_url: str, fork_target: str) -> str:
    """Build a browsable URL to the ``autopoc-artifacts`` branch.

    Args:
        fork_repo_url: Clone URL (may contain embedded credentials).
        fork_target: ``"github"`` or ``"gitlab"``.

    Returns:
        Human-readable URL to the artifacts branch.
    """
    from autopoc.tools.git_tools import ARTIFACTS_BRANCH

    base = _strip_credentials_from_url(fork_repo_url)
    if fork_target == "gitlab":
        return f"{base}/-/tree/{ARTIFACTS_BRANCH}"
    # Default to GitHub-style
    return f"{base}/tree/{ARTIFACTS_BRANCH}"


def _build_report_url(fork_repo_url: str, fork_target: str) -> str:
    """Build a browsable URL to ``poc-report.md`` on the artifacts branch."""
    from autopoc.tools.git_tools import ARTIFACTS_BRANCH

    base = _strip_credentials_from_url(fork_repo_url)
    if fork_target == "gitlab":
        return f"{base}/-/blob/{ARTIFACTS_BRANCH}/poc-report.md"
    return f"{base}/blob/{ARTIFACTS_BRANCH}/poc-report.md"


def _build_blog_url(fork_repo_url: str, fork_target: str) -> str:
    """Build a browsable URL to ``blog-post.md`` on the artifacts branch."""
    from autopoc.tools.git_tools import ARTIFACTS_BRANCH

    base = _strip_credentials_from_url(fork_repo_url)
    if fork_target == "gitlab":
        return f"{base}/-/blob/{ARTIFACTS_BRANCH}/blog-post.md"
    return f"{base}/blob/{ARTIFACTS_BRANCH}/blog-post.md"


def ensure_result_columns(
    service,
    sheet_id: str,
    tab_name: str,
    existing_headers: list[str],
    *,
    tab_gid: int = 0,
) -> dict[str, int]:
    """Ensure the PoC result columns exist in the given tab's header row.

    If any of ``poc_repo``, ``poc_image``, ``poc_report`` are missing
    from *existing_headers*, the sheet grid is expanded (if needed) and
    the new column headers are written.

    Args:
        service: Authenticated Google Sheets API service.
        sheet_id: Spreadsheet ID.
        tab_name: Tab name to update.
        existing_headers: Current header column names.
        tab_gid: Numeric sheet ID (gid) of the tab, used for grid
            expansion via ``appendDimension``.

    Returns:
        Dict mapping each PoC result column name to its 0-based column
        index in the header row.
    """
    header_row = _METADATA_ROWS + 1  # 1-based row number of the header

    missing = [col for col in POC_RESULT_COLUMNS if col not in existing_headers]
    if missing:
        # Expand the sheet grid to accommodate new columns.
        # The Sheets values API cannot write beyond the current grid
        # boundary, so we must add columns first.
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={
                "requests": [
                    {
                        "appendDimension": {
                            "sheetId": tab_gid,
                            "dimension": "COLUMNS",
                            "length": len(missing),
                        }
                    }
                ]
            },
        ).execute()

        # Now write the header names into the newly added columns
        start_col_idx = len(existing_headers)
        start_col = _col_index_to_letter(start_col_idx)
        end_col = _col_index_to_letter(start_col_idx + len(missing) - 1)

        range_str = f"'{tab_name}'!{start_col}{header_row}:{end_col}{header_row}"
        body = {"values": [missing]}

        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=range_str,
            valueInputOption="RAW",
            body=body,
        ).execute()

        logger.info(
            "Added missing PoC result columns to tab '%s': %s (expanded grid by %d columns)",
            tab_name,
            missing,
            len(missing),
        )
        # Update local copy
        existing_headers.extend(missing)

    # Build column index map
    return {col: existing_headers.index(col) for col in POC_RESULT_COLUMNS}


def write_poc_results(
    service,
    sheet_id: str,
    tab_name: str,
    row_number: int,
    col_indices: dict[str, int],
    *,
    fork_repo_url: str | None,
    fork_target: str | None,
    built_images: list[str] | None,
    poc_report_path: str | None,
    poc_image_override: str | None = None,
    poc_report_override: str | None = None,
    blog_post_path: str | None = None,
    poc_blog_override: str | None = None,
) -> None:
    """Write PoC result values to the specified row.

    Only writes to the ``poc_repo``, ``poc_image``, ``poc_report``, and
    ``poc_blog`` cells — no other cells are touched.

    Args:
        service: Authenticated Google Sheets API service.
        sheet_id: Spreadsheet ID.
        tab_name: Tab name containing the row.
        row_number: 1-based row number to write to.
        col_indices: Column index map from :func:`ensure_result_columns`.
        fork_repo_url: Clone URL of the fork (may contain credentials).
        fork_target: ``"github"`` or ``"gitlab"``.
        built_images: List of pushed image refs.
        poc_report_path: Local path to poc-report.md (used only to
            determine if a report was generated).
        poc_image_override: Pre-resolved image URL/value.  When set,
            bypasses the ``built_images`` logic entirely.
        poc_report_override: Pre-resolved report URL.  When set,
            bypasses the local-file + fork URL derivation.
        blog_post_path: Local path to blog-post.md (used only to
            determine if a blog post was generated).
        poc_blog_override: Pre-resolved blog post URL.  When set,
            bypasses the local-file + fork URL derivation.
    """
    target = fork_target or "github"

    # poc_repo → link to artifacts branch
    if fork_repo_url:
        poc_repo_val = _build_artifacts_branch_url(fork_repo_url, target)
    else:
        poc_repo_val = "FAILED"

    # poc_image → override, or first built image, or FAILED
    if poc_image_override:
        poc_image_val = poc_image_override
    elif built_images:
        poc_image_val = built_images[0]
    else:
        poc_image_val = "FAILED"

    # poc_report → override, or derive from fork URL + local file, or FAILED
    if poc_report_override:
        poc_report_val = poc_report_override
    elif fork_repo_url and poc_report_path and Path(poc_report_path).exists():
        poc_report_val = _build_report_url(fork_repo_url, target)
    else:
        poc_report_val = "FAILED"

    # poc_blog → override, or derive from fork URL + local file, or empty
    if poc_blog_override:
        poc_blog_val = poc_blog_override
    elif fork_repo_url and blog_post_path and Path(blog_post_path).exists():
        poc_blog_val = _build_blog_url(fork_repo_url, target)
    else:
        poc_blog_val = ""  # empty, not FAILED — blog is optional

    # Write each cell individually (they may not be contiguous columns)
    values_to_write = {
        "poc_repo": poc_repo_val,
        "poc_image": poc_image_val,
        "poc_report": poc_report_val,
        "poc_blog": poc_blog_val,
    }

    for col_name, value in values_to_write.items():
        col_letter = _col_index_to_letter(col_indices[col_name])
        cell_ref = f"'{tab_name}'!{col_letter}{row_number}"

        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=cell_ref,
            valueInputOption="RAW",
            body={"values": [[value]]},
        ).execute()

    logger.info(
        "Wrote PoC results to tab '%s' row %d: repo=%s, image=%s, report=%s, blog=%s",
        tab_name,
        row_number,
        poc_repo_val[:60],
        poc_image_val[:60],
        poc_report_val[:60],
        poc_blog_val[:60] if poc_blog_val else "(none)",
    )


def _col_index_to_letter(index: int) -> str:
    """Convert a 0-based column index to a spreadsheet column letter.

    Examples: 0→A, 1→B, 25→Z, 26→AA, 27→AB, ...
    """
    result = ""
    while True:
        result = chr(65 + index % 26) + result
        index = index // 26 - 1
        if index < 0:
            break
    return result
