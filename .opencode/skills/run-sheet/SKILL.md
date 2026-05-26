---
name: run-sheet
description: Read PoC candidate projects from a Google Sheet, evaluate and rank them, then run the full PoC pipeline for the top picks. Use this skill when asked to process a "run sheet", "PoC candidates sheet", or "batch PoC run".
---

# run-sheet

Batch PoC pipeline that reads candidate projects from a Google Sheet (PoC Explorer spreadsheet), evaluates their fitness for OpenShift AI, ranks them, and runs full PoC pipelines for the top candidates.

## Before You Start

Verify these environment variables are set:
- `AUTOPOC_SHEET_ID` -- Google Sheet ID
- `AUTOPOC_SHEET_CREDENTIALS` -- Path to Google Service Account credentials JSON (default: `/etc/autopoc/google-sa/credentials.json`)
- All credentials required by the `run-poc` skill (LLM, fork, registry, cluster)

## Workflow

```
Step 1: Read Sheet        -> Get all rows from the PoC Explorer spreadsheet
Step 2: Filter            -> Keep only actionable GitHub repos
Step 3: Pre-filter        -> Heuristic scoring (no LLM, no clone)
Step 4: Evaluate          -> Full intake + evaluate for top candidates
Step 5: Select            -> Pick the best candidate(s) by score
Step 6: Run PoC           -> Invoke run-poc skill for each winner
Step 7: Write Back        -> Update the sheet with results
```

## Step 1: Read Sheet

```bash
python -m autopoc.cli_tools sheet-reader \
  --sheet-id "$AUTOPOC_SHEET_ID" \
  --credentials "$AUTOPOC_SHEET_CREDENTIALS" \
  --max-tabs "${MAX_EVALUATED_SHEETS:-4}"
```

This outputs a JSON array of candidate rows with fields: `title`, `link`, `category`, `pm_decision`, `tab_name`, `row_number`, and any existing result columns (`poc_repo`, `poc_image`, `poc_report`).

## Step 2: Filter

From the candidates, keep only rows that:
1. Have a valid GitHub URL in the `link` field
2. Have `pm_decision` = "approve" (case-insensitive) or equivalent
3. Do NOT already have results (`poc_repo`, `poc_image`, or `poc_report` are empty)
4. Are not marked as "FAILED" in result columns

If zero candidates remain after filtering, report "No actionable candidates found" and exit.

## Step 3: Pre-filter (Heuristic)

For each remaining candidate, compute a heuristic score based on:
- **Category keywords**: AI/ML categories score higher than generic categories
- **Title keywords**: Projects mentioning inference, serving, RAG, fine-tuning, etc. score higher
- **PM comments**: If the sheet has a comments column, check for positive/negative signals

Read `references/prefilter.md` for the keyword lists and scoring formula.

Sort candidates by heuristic score descending. Take the top `MAX_CANDIDATES` (default 5).

## Step 4: Evaluate (Optional)

For each top candidate (skip if `--skip-evaluation` was requested or only 1 candidate):

1. Clone the repo:
   ```bash
   git clone "$CANDIDATE_URL" "$WORK_DIR/repos/$CANDIDATE_NAME"
   ```

2. Explore the repo (read README, build files, source structure) to understand what it does.

3. Score the project using the RHOAI evaluation (you ARE the LLM -- read the strategy dimensions from `$AUTOPOC_DATA_DIR/strategies/` YAML files and score against them).

4. Record the total score for each candidate.

## Step 5: Select

Pick the top `MAX_BATCHED_POC` (default 2) candidates by evaluation score.

If evaluation was skipped, use the heuristic pre-filter scores.

Display a comparison table showing all evaluated candidates with their scores and the selection.

## Step 6: Run PoC

For each selected candidate, invoke the `run-poc` skill:
- Project name: derived from the GitHub URL (owner/repo -> repo name)
- Repo URL: the candidate's GitHub URL

Run pipelines **sequentially** (not in parallel) to avoid resource contention.

## Step 7: Write Back

After each pipeline completes (success or failure), update the Google Sheet:

```bash
python -m autopoc.cli_tools sheet-writer \
  --sheet-id "$AUTOPOC_SHEET_ID" \
  --credentials "$AUTOPOC_SHEET_CREDENTIALS" \
  --tab "$TAB_NAME" \
  --row "$ROW_NUMBER" \
  --results '{
    "poc_repo": "https://gitlab.example.com/autopoc/my-project",
    "poc_image": "quay.io/autopoc/my-project:latest",
    "poc_report": "https://gitlab.example.com/autopoc/my-project/-/blob/autopoc-artifacts/poc-report.md",
    "poc_blog": "https://gitlab.example.com/autopoc/my-project/-/blob/autopoc-artifacts/blog-post.md"
  }'
```

For failed pipelines, write "FAILED" to the `poc_repo` column with the error message.

## State Management

Maintain a sheet processing state at `$WORK_DIR/sheet-state.yaml`:

```yaml
sheet_id: "1ABCxyz..."
started_at: "2026-05-25T00:00:00Z"
candidates_found: 15
candidates_filtered: 5
candidates_evaluated: 3
selected: ["my-project", "another-project"]
results:
  - project: "my-project"
    status: "completed"
    score: 78
  - project: "another-project"
    status: "failed"
    error: "Build failed after 3 retries"
```

## Error Handling

- If sheet reading fails (API error, bad credentials): report error and exit
- If a single PoC pipeline fails: record failure, continue to next candidate
- If all candidates fail: report summary and exit
- Always write back results (including failures) to the sheet
