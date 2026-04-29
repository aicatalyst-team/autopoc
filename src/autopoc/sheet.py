"""Google Sheet reader for PoC candidate projects.

Reads a POC Explorer spreadsheet via the Google Sheets API, filters rows
to find actionable GitHub projects, and selects one for the pipeline.

The expected sheet structure (matching POC Explorer output):
  - Row 1: metadata (run info)
  - Row 2: review URL
  - Row 3: header row (column names)
  - Row 4+: data rows

Only the first tab (index 0) is read.
"""

import logging
from dataclasses import dataclass
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
