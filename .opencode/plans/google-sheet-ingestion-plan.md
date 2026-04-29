# AutoPoC — Google Sheet Ingestion Plan

> Implement `autopoc run-sheet` to read PoC candidate projects from a Google
> Sheet, filter and select one, and run the standard pipeline.
>
> This plan supersedes the `run-sheet` stub in
> [k8s-deployment-plan.md](./k8s-deployment-plan.md) (Phase 3, Task 3.1).
>
> See [plan.md](./plan.md) for overall architecture and
> [implementation-plan.md](./implementation-plan.md) for prior phases.

---

## Overview

Currently `autopoc run` requires `--name` and `--repo` to be provided
explicitly (or via env vars). This feature adds a second entry path:
`autopoc run-sheet` reads a Google Sheet populated by POC Explorer, filters
rows to find an actionable GitHub project, and feeds it into the **same
pipeline graph** starting at `intake`.

The graph topology is **unchanged** — sheet parsing is a CLI-layer concern
that resolves `(project_name, source_repo_url)` before graph invocation.

### Architecture

```
autopoc run-sheet
      │
      ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│ Google Sheet │────▶│ Sheet Parser │────▶│ Project      │
│ (read-only)  │     │ & Filter     │     │ Selector     │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                │
                                    (project_name, repo_url)
                                                │
                                                ▼
                                    ┌───────────────────┐
                                    │ Existing pipeline  │
                                    │ intake → ... → END │
                                    └───────────────────┘
```

### Data Flow

1. **Read sheet**: Google Sheets API v4 with a service account. Read all
   rows from tab index 0 of the configured spreadsheet.
2. **Parse header**: The sheet has 2 metadata rows (run info line + review
   URL), then a header row (row 3), then data rows. Same structure as the
   reference CSV (`POCExplorer - 20260428#1.csv`).
3. **Filter**:
   - `link` must be a GitHub URL (`https://github.com/...`). Excludes
     Reddit, HackerNews, Medium, news sites, YouTube, HuggingFace, etc.
   - If a `pm_decision` column exists, keep only rows where the value
     contains `Approve` (case-insensitive). The field format is
     `Approve(username), Approve(username2)`.
4. **Select**: Take the first remaining row (sheet ordering is preserved;
   top row = highest priority).
5. **Extract**: `project_name` from `title` column, `source_repo_url` from
   `link` column.
6. **Invoke graph**: Build `PoCState`, compile graph, invoke — identical to
   `autopoc run`.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where sheet parsing lives | CLI layer (`cli.py` + `sheet.py` module) | Sheet is a project source, not a pipeline phase. Graph stays unchanged. |
| Graph modification | None | `run-sheet` feeds `name`+`repo` into the same graph entry point (`intake`) |
| Google Sheets library | `google-api-python-client` + `google-auth` | Official Google SDK, lightweight, well-maintained |
| SA credentials | `AUTOPOC_SHEET_CREDENTIALS` env var (path to JSON file) | Avoids colliding with `GOOGLE_APPLICATION_CREDENTIALS` which would hijack Vertex AI auth |
| Sheet ID | `AUTOPOC_SHEET_ID` env var with CLI `--sheet-id` override | Permanent sheet, config-driven |
| Tab selection | First tab (index 0) | Simple, matches current workflow where latest tab is first |
| Link filtering | GitHub only (`github.com` domain) | Only git-cloneable repos supported; HuggingFace not yet implemented |
| pm_decision filtering | Value contains "Approve" (case-insensitive) | Format is `Approve(user1), Approve(user2)` |
| Single vs batch | Single project per invocation | Matches K8s Job model; batch can be layered later |
| Sheet writes | Read-only | We never modify the sheet |

---

## Task Index

| Phase | Tasks | Summary |
|-------|-------|---------|
| **1. Dependencies & Config** | 1.1–1.2 | Google Sheets deps, config fields |
| **2. Sheet Reader** | 2.1 | `sheet.py` module: read, filter, select |
| **3. CLI Integration** | 3.1 | Replace `run-sheet` stub with working command |
| **4. Testing** | 4.1–4.3 | Unit tests, CLI tests, lint pass |
| **5. Docs & Plan Updates** | 5.1–5.2 | `.env.example`, planning doc updates |

---

## Progress

| Phase | Status | Tasks Done |
|-------|--------|------------|
| **1. Dependencies & Config** | **COMPLETE** | 2/2 |
| **2. Sheet Reader** | **COMPLETE** | 1/1 |
| **3. CLI Integration** | **COMPLETE** | 1/1 |
| **4. Testing** | **COMPLETE** | 3/3 |
| **5. Docs & Plan Updates** | **COMPLETE** | 2/2 |

---

## Prerequisites (Manual Steps)

Before the code can be tested end-to-end, the following must be set up
manually (the agent can guide through each step):

1. **Google Cloud project** with the Google Sheets API enabled.
2. **Service Account** created in that project, with a downloaded JSON key
   file.
3. **Spreadsheet sharing**: The target spreadsheet must be shared with the
   SA's email address (viewer / read-only access is sufficient).
4. **Environment variables**:
   - `AUTOPOC_SHEET_CREDENTIALS=/path/to/sa-key.json`
   - `AUTOPOC_SHEET_ID=<spreadsheet-id-from-url>`

The spreadsheet ID is the long alphanumeric string in the Google Sheets URL:
`https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`

---

## Phase 1: Dependencies & Configuration

### Task 1.1 — Add Google Sheets dependencies

**File:** `pyproject.toml`

**Work:** Add to `dependencies`:
```toml
"google-api-python-client>=2.0",
"google-auth>=2.0",
```

**Acceptance:** `pip install -e .` installs `google-api-python-client` and
`google-auth` successfully.

---

### Task 1.2 — Add sheet configuration to `AutoPoCConfig`

**File:** `src/autopoc/config.py`

**Work:** Add two optional fields to `AutoPoCConfig`:

```python
# Google Sheet integration
google_credentials_file: str | None = Field(
    default=None,
    validation_alias="AUTOPOC_SHEET_CREDENTIALS",
    description="Path to Google service account credentials JSON for sheet access",
)
sheet_id: str | None = Field(
    default=None,
    description="Google Sheet ID containing PoC candidate projects",
)
```

Env vars: `AUTOPOC_SHEET_CREDENTIALS`, `AUTOPOC_SHEET_ID`.

**Notes:**
- These fields are optional — `autopoc run` must continue to work without
  them. Only `run-sheet` requires them.
- No model validator needed; validation happens in the CLI command.
- Add to `masked_summary()` for display (credentials file path is not
  secret, sheet_id is not secret).

**Acceptance:** `load_config()` succeeds without these set. When set via env
vars, values are accessible on the config object.

---

## Phase 2: Sheet Reader Module

### Task 2.1 — Create `src/autopoc/sheet.py`

**File:** `src/autopoc/sheet.py` (new)

**Work:** Implement three functions and a data class:

```python
from dataclasses import dataclass

@dataclass
class SheetProject:
    """A project selected from the Google Sheet."""
    name: str           # from 'title' column
    repo_url: str       # from 'link' column
    category: str       # from 'category' column (informational)
    row_index: int      # original row number in sheet (for logging)
```

#### `read_sheet(credentials_file: str, sheet_id: str) -> list[dict[str, str]]`

- Authenticate using `google.oauth2.service_account.Credentials.from_service_account_file()`
  with scope `https://www.googleapis.com/auth/spreadsheets.readonly`.
- Build the Sheets API client: `googleapiclient.discovery.build('sheets', 'v4', credentials=creds)`.
- Get sheet metadata to find the name of the first tab (index 0):
  `spreadsheet.get(spreadsheetId=sheet_id, fields='sheets.properties')`.
- Read range: `'{tab_name}'!A1:ZZ` (all columns, all rows).
- The response is a list of lists (rows × cells).
- **Skip rows 0 and 1** (metadata: run info and review URL).
- **Row 2** (0-indexed) is the header row → use as dict keys.
- **Rows 3+** are data rows → zip with header to create dicts.
- Handle ragged rows (fewer cells than headers) by padding with empty strings.
- Return `list[dict[str, str]]`.

#### `filter_projects(rows: list[dict[str, str]]) -> list[dict[str, str]]`

- **Link filter**: Keep rows where `row.get("link", "")` parses to a URL
  with `netloc` equal to `github.com` (use `urllib.parse.urlparse`).
- **PM decision filter**: If any row has a non-empty `pm_decision` key
  (i.e., the column exists and at least one row has a value), then keep
  only rows where `"approve"` appears in `row.get("pm_decision", "").lower()`.
  If no `pm_decision` column exists at all, skip this filter.
- Preserve original row order.
- Return filtered list.

#### `select_project(rows: list[dict[str, str]], original_offset: int = 3) -> SheetProject`

- If `rows` is empty, raise `ValueError("No projects remain after filtering — nothing to PoC")`.
- Take `rows[0]`.
- Return `SheetProject(name=row["title"], repo_url=row["link"], category=row.get("category", ""), row_index=original_offset)`.
- Note: `row_index` should reflect the 1-indexed row number in the
  spreadsheet (data starts at row 4 in the sheet = index 3 in the values
  array). The caller should track the original indices through filtering.

**Edge cases to handle:**
- Empty sheet (no data rows) → clear error.
- All rows filtered out → clear error with counts (e.g., "15 rows read,
  8 had GitHub links, 0 were approved").
- Missing `title` or `link` column → `KeyError` with descriptive message.
- Google API errors (auth failure, sheet not found, permission denied) →
  let exceptions propagate with clear context.

**Acceptance:** Unit-testable with mocked data. `filter_projects` works
against data matching the reference CSV structure.

---

## Phase 3: CLI Integration

### Task 3.1 — Replace `run-sheet` stub with working implementation

**File:** `src/autopoc/cli.py`

**Work:**

First, **extract shared pipeline logic** from the existing `run` command
into a helper function:

```python
async def _run_pipeline(
    name: str,
    repo: str,
    config: AutoPoCConfig,
    *,
    verbose: bool = False,
    stop_after: str | None = None,
) -> dict:
    """Build and invoke the pipeline graph. Used by both `run` and `run-sheet`."""
    ...
```

This helper contains the shared code from `run`: thread ID generation,
initial state construction, graph compilation, async invocation, timing,
and result printing. Both `run` and `run_sheet` call this helper.

Then, **replace the `run-sheet` stub** with:

```python
@app.command("run-sheet")
def run_sheet(
    sheet_id: Annotated[str | None, typer.Option(
        "--sheet-id",
        envvar="AUTOPOC_SHEET_ID",
        help="Google Sheet ID (or set AUTOPOC_SHEET_ID env var)",
    )] = None,
    credentials: Annotated[str | None, typer.Option(
        "--credentials",
        envvar="AUTOPOC_SHEET_CREDENTIALS",
        help="Path to Google SA credentials JSON (or set AUTOPOC_SHEET_CREDENTIALS)",
    )] = None,
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
    target: Annotated[str | None, typer.Option("--target", "-t")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    skip_validation: Annotated[bool, typer.Option("--skip-validation")] = False,
    stop_after: Annotated[str | None, typer.Option("--stop-after")] = None,
) -> None:
```

The command body:
1. Validate `sheet_id` and `credentials` are available (from args or env).
2. Load and validate config (same as `run`).
3. Call `read_sheet(credentials, sheet_id)`.
4. Call `filter_projects(rows)`.
5. Call `select_project(filtered)`.
6. Print summary panel:
   ```
   Sheet: <sheet_id>
   Rows read: 15
   GitHub repos: 8
   Approved: 3
   Selected: microsoft/TRELLIS.2 (https://github.com/microsoft/TRELLIS.2)
   ```
7. Call `_run_pipeline(project.name, project.repo_url, config, ...)`.
8. Print results (same as `run`).

**Acceptance:**
- `autopoc run-sheet --sheet-id XXXX --credentials /path/to/sa.json`
  reads the sheet, selects a project, runs the pipeline.
- `autopoc run-sheet` with env vars works identically.
- `autopoc run` behavior is unchanged (no regressions).
- `autopoc run-sheet --help` shows all options.

---

## Phase 4: Testing

### Task 4.1 — Unit tests for sheet parser

**File:** `tests/test_sheet.py` (new)

**Test cases for `filter_projects()`:**
- GitHub links pass filter (`https://github.com/org/repo`)
- Reddit links are filtered out (`https://www.reddit.com/...`)
- HackerNews links are filtered out
- Medium / news article links are filtered out
- `pm_decision` containing `"Approve(egeiger)"` passes
- `pm_decision` containing `"Approve(egeiger), Approve(rbelio)"` passes
- Empty `pm_decision` is filtered out when column exists
- When no `pm_decision` column exists in any row, all GitHub rows pass
- Original row order is preserved after filtering

**Test cases for `select_project()`:**
- Returns first row as `SheetProject`
- Raises `ValueError` on empty input
- Extracts `name`, `repo_url`, `category` correctly

**Test cases for `read_sheet()`:**
- Mock Google API response matching CSV structure
- Correctly skips metadata rows and uses row 3 as header
- Handles ragged rows (fewer cells than headers)
- Auth failure raises clear error

**Acceptance:** `pytest tests/test_sheet.py` passes.

---

### Task 4.2 — CLI integration tests for `run-sheet`

**File:** `tests/test_cli.py` (modified)

**Test cases:**
- `run-sheet` without `--sheet-id` or `AUTOPOC_SHEET_ID` → exit code 1
  with error message.
- `run-sheet` without `--credentials` or `AUTOPOC_SHEET_CREDENTIALS`
  → exit code 1 with error message.
- With mocked `read_sheet` returning test data, command selects the correct
  project and attempts pipeline invocation.
- `run-sheet --help` exits 0 and shows option descriptions.

**Acceptance:** Tests pass.

---

### Task 4.3 — Lint and full test pass

Run `make lint && make test`. All checks must pass with the new code.

**Acceptance:** Zero lint errors, all tests pass.

---

## Phase 5: Documentation & Plan Updates

### Task 5.1 — Update `.env.example`

**File:** `.env.example`

**Work:** Add:
```bash
# Google Sheet integration (for `autopoc run-sheet`)
# AUTOPOC_SHEET_CREDENTIALS=/path/to/service-account-key.json
# AUTOPOC_SHEET_ID=your-spreadsheet-id-here
```

---

### Task 5.2 — Update planning documents

**Files:**
- `.opencode/plans/implementation-plan.md` — Add Phase 10 reference in the
  Task Index and Progress tables, pointing to this plan.
- `.opencode/plans/k8s-deployment-plan.md` — Mark Phase 3 (Task 3.1,
  `run-sheet` stub) as superseded by this plan.

---

## Out of Scope

| Item | Notes |
|------|-------|
| **HuggingFace link support** | No `hf_intake` agent on this branch. HF links are filtered out. Expand the link filter when HF support lands. |
| **Batch mode** | Running multiple projects per invocation. `select_project` → `select_projects` is a trivial change; the graph invocation loop is the real work. |
| **Sheet write-back** | No status updates to the sheet. |
| **Tab name parsing** | We use index 0, no date parsing from tab names. |
| **CronJob manifest** | Separate concern, stays in k8s-deployment-plan. |
| **Google Cloud setup automation** | SA creation, API enablement, sheet sharing are manual prerequisites. |
