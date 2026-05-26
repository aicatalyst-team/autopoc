"""Google Sheet write-back and URL derivation for PoC results."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from autopoc.sheet import POC_RESULT_COLUMNS, _METADATA_ROWS

logger = logging.getLogger(__name__)


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
    ARTIFACTS_BRANCH = "autopoc-artifacts"

    base = _strip_credentials_from_url(fork_repo_url)
    if fork_target == "gitlab":
        return f"{base}/-/tree/{ARTIFACTS_BRANCH}"
    # Default to GitHub-style
    return f"{base}/tree/{ARTIFACTS_BRANCH}"


def _build_report_url(fork_repo_url: str, fork_target: str) -> str:
    """Build a browsable URL to ``poc-report.md`` on the artifacts branch."""
    ARTIFACTS_BRANCH = "autopoc-artifacts"

    base = _strip_credentials_from_url(fork_repo_url)
    if fork_target == "gitlab":
        return f"{base}/-/blob/{ARTIFACTS_BRANCH}/poc-report.md"
    return f"{base}/blob/{ARTIFACTS_BRANCH}/poc-report.md"


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
) -> None:
    """Write PoC result values to the specified row.

    Only writes to the ``poc_repo``, ``poc_image``, and ``poc_report``
    cells — no other cells are touched.

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

    # Write each cell individually (they may not be contiguous columns)
    values_to_write = {
        "poc_repo": poc_repo_val,
        "poc_image": poc_image_val,
        "poc_report": poc_report_val,
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
        "Wrote PoC results to tab '%s' row %d: repo=%s, image=%s, report=%s",
        tab_name,
        row_number,
        poc_repo_val[:60],
        poc_image_val[:60],
        poc_report_val[:60],
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
