# Phase 13: Candidate Comparison for run-sheet

> Detailed implementation plan for the candidate comparison feature — when
> `run-sheet` encounters multiple candidates, evaluate them all using the RHOAI
> fitness evaluation and pick the best one.

---

## Overview

Currently, `run-sheet` reads a Google Sheet, filters to GitHub repos with
optional PM approval, and **picks the first row**. This works when exactly one
project is PM-approved, but falls short in two scenarios:

1. **No PM approvals** — all GitHub projects are candidates; picking the first
   is arbitrary.
2. **Multiple PM approvals** — several projects are approved; we should pick
   the one that best fits the RHOAI strategy.

This phase extends `run-sheet` with a multi-candidate evaluation pipeline:

```
read_sheet → filter_projects → [if multiple candidates]
  → prefilter_candidates (cheap, no LLM)
  → evaluate_candidates (clone + intake + evaluate for each)
  → select_best_candidate (highest score)
→ run_pipeline (on the winner)
```

### Cost Bounding

Full evaluation requires cloning a repo and making 2 LLM calls per candidate
(intake + evaluate). To bound cost:

1. **Pre-filter** uses sheet metadata + keyword matching (no LLM, no clone) to
   narrow candidates.
2. **Cap** limits the number of candidates that get full evaluation (default: 5,
   configurable via `--max-candidates`).
3. **Short-circuit** — if only 1 candidate survives filtering, skip evaluation
   and run directly (current behavior).

---

## Pre-filtering Strategy

The pre-filter operates on sheet row data only — no cloning, no LLM calls. It
produces a rough heuristic score to rank candidates before expensive evaluation.

### Signals Used

| Signal | Source | How |
|--------|--------|-----|
| **Category match** | `category` column | Match against strategy area keywords (e.g., `"rag"` → model-customization, `"agents"` → agentic-ai) |
| **Title/link keywords** | `title` and `link` columns | Match against capability labels from the strategy baseline (e.g., "vllm", "kserve", "langchain", "rag") |
| **PM comments** | `pm_comments` column | LLM call to extract relevance signals from free-form PM commentary. Determine if PM noted strategic value, good demo potential, or flags (too complex, already done, etc.) |

### PM Comments Parsing

The `pm_comments` column contains free-form text from the product manager. This
is inherently unstructured and may contain:
- Strategic value notes ("good fit for inference story", "validates RAG pipeline")
- Concerns ("too complex", "already covered by X")
- Context ("customer requested", "partner use case")
- Empty or irrelevant text

Since this is free-form, we use a **lightweight LLM call** to extract structured
signals. This is the one LLM call in the pre-filter stage, but it's batched —
all candidates' PM comments are sent in a single prompt to minimize cost.

```python
async def _parse_pm_comments(
    candidates: list[dict[str, str]],
    strategy_areas: list[str],
    llm: BaseChatModel,
) -> dict[int, PMCommentSignals]:
    """Parse PM comments for all candidates in a single LLM call.

    Returns a dict mapping candidate index to extracted signals.
    """
```

The LLM returns structured signals per candidate:
```python
class PMCommentSignals(TypedDict, total=False):
    sentiment: str       # "positive", "neutral", "negative", "none"
    strategic_value: bool  # PM noted strategic alignment
    demo_potential: bool   # PM noted demo/showcase value
    concerns: list[str]    # Extracted concerns
    boost: int             # -10 to +10 adjustment to heuristic score
```

### Pre-filter Score Formula

```
heuristic_score = category_match_score + keyword_match_score + pm_comment_boost
```

Where:
- `category_match_score`: 0-30 (based on how well category maps to strategy areas)
- `keyword_match_score`: 0-30 (count of capability label matches in title/link)
- `pm_comment_boost`: -10 to +10 (from PM comments LLM parse)

Candidates are sorted by heuristic score descending, and the top N (from
`--max-candidates`) proceed to full evaluation.

### Pre-filter When PM Comments Are Absent

If the sheet has no `pm_comments` column (or all values are empty), the pre-filter
skips the LLM call entirely and uses only category + keyword matching. The
heuristic score is computed from those two signals alone.

---

## Full Candidate Evaluation

For each candidate that survives pre-filtering, we run a partial pipeline:

1. **Clone** the repo to a temporary directory
2. **Build repo digest** (procedural, no LLM — `build_repo_digest()`)
3. **Run intake LLM call** (one-shot analysis — components, summary)
4. **Run evaluate LLM call** (one-shot RHOAI scoring — from Phase 12)
5. **Record the evaluation** (`RHOAIEvaluation` with `total_score`)
6. **Clean up** clone directory (unless it's the winner)

### Implementation: `evaluate_candidates()`

Rather than building a custom mini-pipeline, we reuse the existing graph
machinery with `stop_after="evaluate"`:

```python
async def evaluate_candidates(
    candidates: list[dict[str, str]],
    config: AutoPoCConfig,
    *,
    max_candidates: int = 5,
    llm: BaseChatModel | None = None,
) -> list[CandidateResult]:
    """Evaluate multiple candidates using the RHOAI fitness evaluation.

    For each candidate:
    1. Derives project name from the sheet row
    2. Runs the pipeline with stop_after="evaluate"
    3. Extracts the RHOAIEvaluation from the final state

    Returns results sorted by total_score descending.
    """
```

Each candidate runs in its own pipeline invocation with a unique `work_dir`
subdirectory to avoid conflicts. Candidates are evaluated sequentially (not
parallel) to respect LLM rate limits.

### CandidateResult Data Model

```python
@dataclass
class CandidateResult:
    """Result of evaluating a single candidate project."""
    project: SheetProject          # The sheet project
    evaluation: RHOAIEvaluation    # RHOAI evaluation (may be empty if failed)
    heuristic_score: float         # Pre-filter heuristic score
    clone_path: str | None         # Path to clone (for winner reuse)
    error: str | None              # Error message if evaluation failed
```

---

## Selection

```python
def select_best_candidate(
    results: list[CandidateResult],
) -> CandidateResult:
    """Select the best candidate from evaluation results.

    Selection priority:
    1. Highest total_score from RHOAI evaluation
    2. If tied, highest heuristic_score from pre-filter
    3. If still tied, first in sheet order (stable sort)

    Candidates with evaluation errors are ranked below successful ones.
    """
```

The winner's clone directory is preserved and reused for the full pipeline run,
avoiding re-cloning. Other candidates' clones are cleaned up.

---

## CLI Changes

### New Options for `run-sheet`

```python
@app.command()
def run_sheet(
    # ... existing options ...
    max_candidates: Annotated[
        int,
        typer.Option(
            "--max-candidates",
            help="Maximum number of candidates to fully evaluate (default: 5)",
        ),
    ] = 5,
    skip_evaluation: Annotated[
        bool,
        typer.Option(
            "--skip-evaluation",
            help="Skip RHOAI evaluation and use first-row selection (legacy behavior)",
        ),
    ] = False,
) -> None:
```

### Flow Logic in CLI

```python
filtered = filter_projects(rows)

if len(filtered) <= 1 or skip_evaluation:
    # Single candidate or evaluation skipped — use existing behavior
    project = select_project(filtered)
    _run_pipeline(project.name, project.repo_url, config, ...)
else:
    # Multiple candidates — evaluate and pick best
    console.print(f"[bold cyan]Multiple candidates ({len(filtered)}). Evaluating...[/bold cyan]")

    # Pre-filter
    prefiltered = await prefilter_candidates(filtered, strategy, llm, max_candidates)

    # Full evaluation
    results = await evaluate_candidates(prefiltered, config, max_candidates=max_candidates)

    # Display comparison table
    _print_candidate_comparison(results)

    # Select best
    winner = select_best_candidate(results)

    # Run full pipeline on winner (reuse clone)
    _run_pipeline(winner.project.name, winner.project.repo_url, config, ...)
```

### Comparison Table Display

When multiple candidates are evaluated, the CLI shows a comparison table before
proceeding with the winner:

```
╭─ Candidate Comparison ────────────────────────────────────────────────╮
│                                                                      │
│  #  Project              Score  Relationship              Areas      │
│  1  vllm-benchmark       82     enriches-existing         Inference  │
│  2  rag-enterprise       71     validates-platform        Custom.    │
│  3  agent-toolkit        65     integrates-with           Agentic    │
│  4  ml-dashboard         43     duplicates-existing       Mgmt       │
│  5  web-scraper          12     misaligned                —          │
│                                                                      │
│  Winner: vllm-benchmark (82/100)                                     │
╰──────────────────────────────────────────────────────────────────────╯
```

---

## Modified / New Files

| File | Change Type | Description |
|------|-------------|-------------|
| `src/autopoc/sheet.py` | Modified | Add `prefilter_candidates()`, `evaluate_candidates()`, `select_best_candidate()`, `CandidateResult` dataclass, `PMCommentSignals` TypedDict |
| `src/autopoc/cli.py` | Modified | Add `--max-candidates`, `--skip-evaluation` options; candidate comparison flow; comparison table display |
| `src/autopoc/prompts/prefilter_pm_comments.md` | New | System prompt for PM comments parsing |
| `tests/test_sheet.py` | Modified | Add tests for pre-filter, candidate evaluation, best selection |
| `tests/test_evaluate_candidates.py` | New | Integration test with mocked LLM for multi-candidate flow |

---

## Task Breakdown

### Task 83 — Pre-filter: keyword matching against strategy labels

**Files:** `src/autopoc/sheet.py`, `src/autopoc/tools/strategy.py`

**Depends on:** Phase 12 (Task 73 — strategy loader)

**Work:**
- Implement `prefilter_candidates()` in `sheet.py`:
  - Load strategy baseline via `load_strategy_baseline()`
  - Extract all capability labels from all strategy areas
  - Build a category-to-strategy-area mapping (e.g., `"rag"` → `"model-customization"`)
  - For each candidate row:
    - Score category match (0-30): how well `category` column maps to strategy areas
    - Score keyword match (0-30): count capability label hits in `title` + `link` columns
    - Compute `heuristic_score = category_match + keyword_match`
  - Sort by heuristic score descending
  - Return top N candidates
- Add helper: `_build_category_mapping(baseline)` → dict mapping category
  keywords to strategy area names
- Add helper: `_count_keyword_matches(text, labels)` → int count of label
  occurrences in text

**Acceptance criteria:**
- Projects with AI/ML-related keywords rank higher than generic projects
- Category column is leveraged when present
- Function is fast (no LLM calls, no I/O beyond strategy file read)
- Returns at most N candidates (configurable)

---

### Task 84 — Pre-filter: PM comments LLM parsing

**Files:** `src/autopoc/sheet.py`, `src/autopoc/prompts/prefilter_pm_comments.md`

**Depends on:** Task 83

**Work:**
- Implement `_parse_pm_comments()` in `sheet.py`:
  - Collects `pm_comments` from all candidate rows
  - If no comments exist, returns empty signals (skip LLM)
  - Otherwise, builds a single LLM prompt with all comments batched
  - Parses structured JSON response into `PMCommentSignals` per candidate
  - Returns dict mapping candidate index to signals
- Write `prompts/prefilter_pm_comments.md` system prompt:
  - Instructs LLM to analyze batched PM comments
  - Extract: sentiment, strategic value notes, demo potential, concerns
  - Output a JSON array with one entry per candidate
  - Keep it concise — this is a lightweight call
- Integrate PM comment boost into `prefilter_candidates()`:
  - Add `pm_comment_boost` (-10 to +10) to heuristic score
  - Negative boost for concerns like "too complex", "already done"
  - Positive boost for "strategic", "customer requested", "good demo"
- Handle edge cases:
  - Missing `pm_comments` column → skip entirely
  - All empty comments → skip LLM call
  - LLM parse failure → ignore PM signals (fall back to keyword-only)

**Acceptance criteria:**
- PM comments with positive signals boost heuristic score
- PM comments with negative signals reduce heuristic score
- Missing/empty comments handled gracefully (no LLM call)
- LLM failure doesn't crash pre-filter
- Single batched LLM call for all candidates (not per-candidate)

---

### Task 85 — evaluate_candidates() orchestrator

**Files:** `src/autopoc/sheet.py`

**Depends on:** Phase 12 (Tasks 76, 77), Task 83

**Work:**
- Implement `evaluate_candidates()`:
  - For each pre-filtered candidate:
    1. Derive project name via `_derive_project_name()`
    2. Create a temporary work directory: `{config.work_dir}/_eval/{project_name}`
    3. Build initial state: `{"project_name": name, "source_repo_url": url}`
    4. Run the pipeline graph with `stop_after="evaluate"`
    5. Extract `rhoai_evaluation` from final state
    6. Build `CandidateResult` with project, evaluation, heuristic score, clone path
  - Handle pipeline failures gracefully (set `error` on the result, continue)
  - Return list of `CandidateResult` sorted by total_score descending
  - Evaluate sequentially (respect LLM rate limits)
- Add `CandidateResult` dataclass to `sheet.py`
- Temp directory management:
  - Winner's clone path is preserved for reuse in the full pipeline
  - Other clones are cleaned up (or left for debugging if verbose)

**Acceptance criteria:**
- Each candidate gets a full intake + evaluate run
- Pipeline failures for one candidate don't affect others
- Results sorted by score
- Winner's clone is preserved
- Temp directories cleaned up for non-winners

---

### Task 86 — select_best_candidate() with scoring

**Files:** `src/autopoc/sheet.py`

**Depends on:** Task 85

**Work:**
- Implement `select_best_candidate()`:
  - Sort results by: (1) has_evaluation (successful > failed),
    (2) total_score descending, (3) heuristic_score descending,
    (4) original sheet order
  - Return the top result
  - Log the selection with score and rationale
- Handle edge case: all evaluations failed → fall back to highest
  heuristic score (or first in sheet order)

**Acceptance criteria:**
- Highest-scoring candidate selected
- Ties broken by heuristic score, then sheet order
- All-failure case handled (doesn't crash)

---

### Task 87 — CLI: --max-candidates, --skip-evaluation, comparison table

**Files:** `src/autopoc/cli.py`

**Depends on:** Tasks 84, 85, 86

**Work:**
- Add `--max-candidates` option to `run_sheet` (default: 5, range: 1-20)
- Add `--skip-evaluation` flag to `run_sheet`
- Update `run_sheet` flow:
  - If `len(filtered) <= 1` or `skip_evaluation`: use existing `select_project()`
  - Otherwise: run `prefilter_candidates()` → `evaluate_candidates()` →
    `select_best_candidate()`
  - Display progress during evaluation ("Evaluating candidate 2/5: vllm-benchmark...")
- Implement `_print_candidate_comparison(results)`:
  - Rich table with columns: rank, project name, score, relationship, strategy areas
  - Highlight winner row
  - Show "Winner: {name} ({score}/{max})" below table
- Handle async: `evaluate_candidates()` and `prefilter_candidates()` are async
  (they call LLM); wrap in `asyncio.run()` or integrate into existing async flow
- Update `_run_pipeline()` to accept optional `clone_path` parameter so the
  winner's existing clone is reused (skip re-cloning in intake)

**Acceptance criteria:**
- `--max-candidates 3` limits evaluation to 3 candidates
- `--skip-evaluation` uses legacy first-row selection
- Comparison table displayed for multi-candidate evaluation
- Winner's clone reused in full pipeline (no re-clone)
- Progress feedback during evaluation

---

### Task 88 — Unit tests: pre-filter

**Files:** `tests/test_sheet.py`

**Depends on:** Tasks 83, 84

**Work:**
- Test `prefilter_candidates()` with various scenarios:
  - All candidates have category column → ranked by category match
  - No category column → ranked by keyword match only
  - Mix of AI/ML and generic projects → AI/ML ranked higher
  - Cap respected (returns at most N)
- Test `_build_category_mapping()`:
  - "rag" maps to "model-customization"
  - "agents" maps to "agentic-ai"
  - Unknown categories get no match
- Test `_count_keyword_matches()`:
  - "vllm-serving-benchmark" matches ["vllm", "serving"]
  - "generic-web-app" matches nothing
- Test `_parse_pm_comments()` with mocked LLM:
  - Positive comments boost score
  - Negative comments reduce score
  - Empty comments → no LLM call
  - LLM failure → graceful fallback

**Acceptance criteria:**
- Pre-filter ranking is deterministic for given inputs
- Edge cases (empty inputs, missing columns) handled
- PM comment parsing tested with mock LLM

---

### Task 89 — Unit tests: candidate comparison

**Files:** `tests/test_sheet.py`

**Depends on:** Tasks 85, 86

**Work:**
- Test `evaluate_candidates()` with mocked pipeline:
  - Mock the graph invocation to return predefined states
  - Verify results sorted by score
  - Verify pipeline failure handling (one fails, others succeed)
  - Verify temp directory management
- Test `select_best_candidate()`:
  - Normal case: highest score wins
  - Tie: heuristic score breaks tie
  - All failures: first candidate wins
  - Single candidate: returns it

**Acceptance criteria:**
- Evaluation orchestration tested with mocks
- Selection logic tested with various scenarios
- Error handling verified

---

### Task 90 — Integration test: multi-candidate flow

**Files:** `tests/test_evaluate_candidates.py`

**Depends on:** Tasks 85, 86, 87

**Work:**
- Create an integration test that:
  - Sets up mock sheet data with 3-5 candidate rows
  - Mocks the LLM to return different evaluation scores per candidate
  - Runs the full pre-filter → evaluate → select flow
  - Verifies the correct candidate is selected
  - Verifies the comparison table data is correct
- Use the existing test fixtures (sample repos) as candidate repos
- Test the async flow end-to-end

**Acceptance criteria:**
- Full flow works with mocked external dependencies
- Correct candidate selected based on scores
- Clean test execution (no leaked temp files)

---

## Sequence Diagram

```
User                CLI                  Sheet              Evaluate
 │                   │                    │                    │
 ├──run-sheet───────▶│                    │                    │
 │                   ├──read_sheet()─────▶│                    │
 │                   │◀─────rows──────────│                    │
 │                   ├──filter_projects()─▶│                   │
 │                   │◀────filtered────────│                   │
 │                   │                    │                    │
 │                   │ [if len(filtered) > 1]                  │
 │                   ├──prefilter_candidates()─────────────────▶│
 │                   │  (keyword match + PM comments LLM)      │
 │                   │◀────top N candidates─────────────────────│
 │                   │                    │                    │
 │                   │  [for each candidate]                   │
 │                   ├──evaluate_candidates()──────────────────▶│
 │                   │  ├─ clone repo                          │
 │                   │  ├─ intake (digest + LLM)               │
 │                   │  ├─ evaluate (RHOAI scoring LLM)        │
 │                   │  └─ record CandidateResult              │
 │                   │◀────sorted results──────────────────────│
 │                   │                    │                    │
 │                   ├──select_best_candidate()                │
 │                   │◀────winner──────────│                    │
 │                   │                    │                    │
 │                   ├──_print_candidate_comparison()           │
 │                   ├──_run_pipeline(winner)                   │
 │                   │                    │                    │
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Too many candidates → expensive LLM calls | Cost/time | Pre-filter + cap (default 5) bounds the cost |
| PM comments LLM parse fails | Bad pre-filter ranking | Fall back to keyword-only (PM comments are a boost, not a gate) |
| Clone fails for a candidate | Candidate can't be evaluated | Record error, continue with remaining candidates |
| All evaluations fail | No winner | Fall back to heuristic score, then sheet order |
| Rate limiting during batch evaluation | Slow/failed evaluations | Sequential evaluation with retry; fail gracefully per candidate |
| Winner's clone stale after evaluation | Intake re-run wastes time | Pass `clone_path` to pipeline; intake detects existing clone and skips |
| Pre-filter excludes the best candidate | Wrong winner | Cap is generous (5); keyword matching covers broad AI/ML vocabulary |
