# Phase 12: RHOAI Fitness Evaluation

> Detailed implementation plan for the RHOAI fitness evaluation agent — a new
> pipeline node that scores how well a project fits as a proof-of-concept on
> OpenShift AI, consulting the strategy baseline in `data/strategy-baseline.yaml`.

---

## Overview

When processing a repository, after intake completes (clone + digest + LLM
summarization) but before forking to GitHub/GitLab, a new **evaluate** node
scores the project's fit for OpenShift AI. The evaluation is:

- **Technically focused** — ML/AI relevance, RHOAI component alignment,
  infrastructure fit, strategic alignment, demo potential.
- **Strategy-driven** — scoring dimensions and criteria are read dynamically
  from the active strategy YAML (`data/strategies/<active>.yaml`) and the
  strategy baseline (`data/strategy-baseline.yaml`).
- **Non-blocking** — if the evaluation LLM call fails (rate limit, parse error,
  etc.), the pipeline continues with an empty evaluation. Evaluation is
  informational; it should never prevent a PoC from running.

### Pipeline Position

```
BEFORE:  intake → [poc_plan ∥ fork] → containerize → ...
AFTER:   intake → evaluate → [poc_plan ∥ fork] → containerize → ...
```

The evaluate node is sequential between intake and the fan-out. It must complete
before fork because:
1. We want the score available before creating a GitHub fork (avoid wasting forks
   on poor-fit projects).
2. The fan-out to `poc_plan` and `fork` can use the evaluation output (e.g.,
   the identified strategy areas and capability labels can inform the PoC plan).

---

## Scoring Model

Scoring dimensions are **read dynamically** from the active strategy YAML
(`data/strategies/redhat-ai-2026.yaml`). The current active strategy defines
5 impact dimensions, each scored 0-20 for a total of 0-100:

| Dimension | What the LLM Evaluates | Range |
|-----------|------------------------|-------|
| `audience_value` | How valuable/interesting is this project to RHOAI users, customers, and the broader AI community? | 0-20 |
| `strategic_alignment` | How well does it align with the 4 official CY2026 strategy areas (inference, customization, agentic, management)? | 0-20 |
| `strategy_fit` | Does it enrich existing capabilities vs. duplicate them? Uses the `enrich_if`/`duplicate_if` criteria from the baseline. | 0-20 |
| `platform_leverage` | Does it leverage RHOAI platform components (KServe, vLLM, pipelines, model registry, etc.)? | 0-20 |
| `demo_potential` | How compelling is this as a live PoC/demo? Visual impact, narrative clarity, audience engagement. | 0-20 |

Because dimensions are read from YAML, switching to the `classic` strategy
(3 dimensions) or adding new strategies automatically changes the scoring
rubric. The evaluate prompt template dynamically renders the dimensions, their
descriptions, and the per-dimension score range based on the formula in the
strategy YAML.

### Output per evaluation

Each dimension includes:
- **Score** (integer, within the dimension's range)
- **Rationale** (1-2 sentences explaining the score)

Plus overall outputs:
- `total_score`: Sum of all dimension scores (0-100 for the default 5-dimension strategy)
- `strategy_areas`: Which of the 4 official areas this project is relevant to
- `relationship`: One of the 5 relationship labels (`enriches-existing-capability`,
  `integrates-with-red-hat-ai`, `validates-platform-story`,
  `duplicates-existing-capability`, `misaligned`)
- `capability_labels`: Which capability labels from the strategy baseline apply
- `rationale`: 2-3 sentence overall assessment
- `strengths`: Key strengths for RHOAI PoC
- `risks`: Key risks or concerns

---

## Data Model

### New TypedDict: `RHOAIEvaluation`

```python
class RHOAIDimensionScore(TypedDict, total=False):
    """Score for a single evaluation dimension."""
    name: str           # e.g. "audience_value"
    score: int          # 0 to max_score (range depends on strategy)
    max_score: int      # max possible score for this dimension
    rationale: str      # 1-2 sentence explanation

class RHOAIEvaluation(TypedDict, total=False):
    """RHOAI fitness evaluation result for a project."""
    total_score: int                          # sum of dimension scores
    max_possible_score: int                   # sum of all max_scores
    dimensions: list[RHOAIDimensionScore]     # per-dimension breakdown
    strategy_areas: list[str]                 # matched official strategy areas
    relationship: str                         # relationship classification label
    capability_labels: list[str]              # matched capability labels
    rationale: str                            # overall 2-3 sentence assessment
    strengths: list[str]                      # key strengths (2-4 items)
    risks: list[str]                          # key risks/concerns (1-3 items)
    strategy_name: str                        # which strategy was used
    strategy_version: str                     # version of the strategy
```

### PoCState additions

```python
# --- RHOAI Evaluation output ---
rhoai_evaluation: RHOAIEvaluation    # The evaluation result
rhoai_evaluation_path: str           # Path to rhoai-evaluation.md in the repo
```

### PoCPhase addition

```python
EVALUATE = "evaluate"   # between INTAKE and POC_PLAN/FORK
```

---

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `src/autopoc/tools/strategy.py` | Strategy loader — reads config, resolves active strategy, loads baseline |
| `src/autopoc/agents/evaluate.py` | Evaluate agent node function |
| `src/autopoc/prompts/evaluate.md` | System prompt template (Jinja2-compatible) |
| `tests/test_strategy.py` | Unit tests for strategy loader |
| `tests/test_evaluate.py` | Unit tests for evaluate agent |

### Modified Files

| File | Change |
|------|--------|
| `src/autopoc/state.py` | Add `RHOAIDimensionScore`, `RHOAIEvaluation`, new `PoCState` fields, new `PoCPhase` value |
| `src/autopoc/graph.py` | Add `evaluate` node, new routing, update `PIPELINE_PHASES` |
| `src/autopoc/cli.py` | Display evaluation results, support `--stop-after=evaluate` |
| `pyproject.toml` | Include `data/` as package data |

### Strategy Loader (`tools/strategy.py`)

The strategy loader is a pure utility module — no LLM, no tools, just YAML
reading and validation.

```python
def load_strategy_config() -> dict:
    """Read data/strategy_config.yaml and return the active strategy name."""

def load_strategy(name: str | None = None) -> dict:
    """Load a strategy profile by name.
    
    If name is None, reads the active strategy from strategy_config.yaml.
    Returns the parsed YAML dict from data/strategies/{name}.yaml.
    """

def load_strategy_baseline(path: str) -> dict:
    """Load the strategy baseline YAML.
    
    Path is resolved relative to the project data/ directory.
    Returns the parsed YAML dict.
    """

def get_scoring_dimensions(strategy: dict) -> list[dict]:
    """Extract impact dimensions from a strategy profile.
    
    Returns list of dicts with name, weight, source, etc.
    Used to dynamically build the evaluation prompt.
    """

def compute_max_score(strategy: dict) -> int:
    """Compute the maximum possible score based on strategy dimensions.
    
    For equal-weight dimensions summing to 100:
    max_per_dim = 100 // num_dimensions (e.g. 20 for 5 dims)
    """
```

**Data path resolution:** The loader resolves `data/` relative to the package
root (using `importlib.resources` or `Path(__file__).parent.parent.parent` to
find the project root). The `data/` directory is included as package data in
`pyproject.toml`.

### Evaluate Agent (`agents/evaluate.py`)

The evaluate agent follows the same pattern as intake: one-shot LLM call, no
ReAct agent, no tools. It receives the repo digest and component info from
intake and produces a structured JSON evaluation.

```python
async def evaluate_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Evaluate a project's fitness for OpenShift AI PoC.

    This is a LangGraph node function. It:
    1. Loads the active strategy and baseline
    2. Builds a prompt with repo context + strategy context
    3. Makes a one-shot LLM call
    4. Parses the JSON response into RHOAIEvaluation
    5. Writes rhoai-evaluation.md to the repo directory
    6. Returns partial state update

    Non-blocking: if any step fails, returns empty evaluation
    and the pipeline continues normally.
    """
```

**Error handling:** Every failure path returns a valid state update with
`rhoai_evaluation` set to a minimal struct (`total_score: 0`,
`rationale: "Evaluation failed: <reason>"`). The pipeline never stops due to
evaluation failure.

### Evaluation Prompt (`prompts/evaluate.md`)

The system prompt is a template that gets filled with:
1. The scoring dimensions (names, descriptions, max scores) — from the strategy YAML
2. The strategy baseline content (strategy areas, capability labels,
   enrichment/duplication criteria, relationship rules) — from the baseline YAML
3. The core products list — from the baseline YAML
4. The expected JSON output schema — dynamically generated from dimensions

The user message includes:
1. Project name and source URL
2. The repo digest (from intake)
3. The repo summary (from intake)
4. The component list with key fields (language, build_system, is_ml_workload, etc.)

### Graph Changes

```python
# New routing function
def route_after_evaluate(state: PoCState) -> list[str]:
    """After evaluate, always fan out to poc_plan + fork.
    
    Evaluation failure does not block the pipeline.
    """
    # Check intake error (shouldn't happen - intake catches its own errors)
    error = state.get("error")
    if error:
        return ["failed"]
    return ["poc_plan", "fork"]

# Updated graph wiring
graph.add_node("evaluate", evaluate_agent)

# intake → evaluate (sequential)
graph.add_edge("intake", "evaluate")

# evaluate → [poc_plan ∥ fork] (fan-out, replaces intake's fan-out)
graph.add_conditional_edges(
    "evaluate",
    route_after_evaluate,
    {"poc_plan": "poc_plan", "fork": "fork", "failed": END},
)
```

The existing `route_after_intake` logic moves to `route_after_evaluate`, and
intake always routes to evaluate (or END on error).

### Markdown Report (`rhoai-evaluation.md`)

Written to `{clone_path}/rhoai-evaluation.md`:

```markdown
# RHOAI Fitness Evaluation

**Project:** {project_name}
**Strategy:** {strategy_name} (v{strategy_version})
**Total Score:** {total_score}/{max_possible_score}

## Score Breakdown

| Dimension | Score | Max | Rationale |
|-----------|-------|-----|-----------|
| audience_value | 15 | 20 | ... |
| strategic_alignment | 18 | 20 | ... |
| ... | ... | ... | ... |

## Strategy Alignment

**Relevant areas:** Model Inference, Agentic AI
**Relationship:** enriches-existing-capability
**Matched capabilities:** vllm, serving, tool-calling, agent-runtime

## Assessment

{rationale}

### Strengths
- ...

### Risks
- ...
```

### CLI Display

When evaluation completes, the CLI shows a compact summary:

```
╭─ RHOAI Evaluation ─────────────────────────────────╮
│ Score:        72/100                                │
│ Relationship: enriches-existing-capability          │
│ Areas:        Model Inference, Agentic AI           │
│ Capabilities: vllm, serving, tool-calling           │
╰─────────────────────────────────────────────────────╯
```

---

## Task Breakdown

### Task 73 — Strategy loader module

**Files:** `src/autopoc/tools/strategy.py`

**Depends on:** nothing

**Work:**
- Create `strategy.py` with functions: `load_strategy_config()`,
  `load_strategy()`, `load_strategy_baseline()`, `get_scoring_dimensions()`,
  `compute_max_score()`
- Resolve `data/` directory path relative to project root (handle both
  installed package and development mode)
- Parse YAML files with `pyyaml` (already a dependency)
- Validate required keys exist in loaded YAML
- Handle missing files gracefully with clear error messages

**Acceptance criteria:**
- `load_strategy()` returns the active strategy dict
- `load_strategy_baseline()` returns the baseline dict
- `get_scoring_dimensions()` returns dimension list from strategy
- `compute_max_score()` returns correct total (100 for 5 equal-weight dims)
- Missing file raises `FileNotFoundError` with helpful message
- Works in both `pip install -e .` and installed package modes

---

### Task 74 — RHOAIEvaluation TypedDict + PoCState fields

**Files:** `src/autopoc/state.py`

**Depends on:** nothing

**Work:**
- Add `RHOAIDimensionScore` TypedDict with fields: `name`, `score`,
  `max_score`, `rationale`
- Add `RHOAIEvaluation` TypedDict with fields: `total_score`,
  `max_possible_score`, `dimensions`, `strategy_areas`, `relationship`,
  `capability_labels`, `rationale`, `strengths`, `risks`, `strategy_name`,
  `strategy_version`
- Add to `PoCState`: `rhoai_evaluation` and `rhoai_evaluation_path`
- Add `EVALUATE = "evaluate"` to `PoCPhase` enum (between INTAKE and POC_PLAN)

**Acceptance criteria:**
- All new types importable from `autopoc.state`
- Existing tests pass (no regressions)
- `PoCPhase.EVALUATE` exists

---

### Task 75 — Evaluation system prompt

**Files:** `src/autopoc/prompts/evaluate.md`

**Depends on:** Task 73 (strategy loader, to understand available data)

**Work:**
- Write a system prompt template for the evaluate LLM call
- The prompt must include placeholders for:
  - Scoring dimensions (names, descriptions, max scores) — injected at runtime
  - Strategy baseline content (strategy areas with capability labels,
    enrichment/duplication criteria) — injected at runtime
  - Core products list — injected at runtime
  - Relationship rules — injected at runtime
  - Expected JSON output schema — dynamically generated from dimensions
- The prompt instructs the LLM to:
  - Analyze the repo digest and component info
  - Score each dimension independently with a rationale
  - Identify relevant strategy areas and capability labels
  - Classify the relationship using the 5-label taxonomy
  - Provide overall assessment, strengths, and risks
- Use `{placeholder}` syntax compatible with Python `.format()` or f-string
  injection (the agent code fills these at runtime)

**Acceptance criteria:**
- Prompt file exists at `src/autopoc/prompts/evaluate.md`
- All placeholders are documented in comments
- Output schema matches `RHOAIEvaluation` TypedDict
- Prompt instructs LLM to respond with only JSON (no markdown fences)

---

### Task 76 — Evaluate agent implementation

**Files:** `src/autopoc/agents/evaluate.py`

**Depends on:** Tasks 73, 74, 75

**Work:**
- Implement `evaluate_agent(state, *, llm=None) -> dict`:
  1. Load active strategy via `load_strategy()`
  2. Load strategy baseline via `load_strategy_baseline()`
  3. Extract scoring dimensions via `get_scoring_dimensions()`
  4. Build the system prompt by reading `evaluate.md` and injecting:
     - Rendered dimensions table
     - Strategy baseline sections (areas, products, labels, rules)
     - JSON output schema
  5. Build user message with: project name, source URL, repo digest,
     repo summary, component list (formatted)
  6. Make one-shot LLM call (same pattern as intake)
  7. Parse JSON response via `_parse_evaluate_output()`
  8. Validate scores are within range, clamp if needed
  9. Write `rhoai-evaluation.md` to the clone path
  10. Return state update with `rhoai_evaluation`, `rhoai_evaluation_path`
- Implement `_parse_evaluate_output(raw: str) -> dict` — same JSON extraction
  logic as intake (handle markdown fences, find JSON object)
- Implement `_build_evaluation_markdown(evaluation, project_name, strategy) -> str`
  — renders the markdown report
- Implement `_format_strategy_for_prompt(baseline, dimensions) -> str` — formats
  the strategy content for the LLM prompt
- All failure paths return a minimal valid state update (non-blocking)

**Acceptance criteria:**
- Agent produces a valid `RHOAIEvaluation` from a mocked LLM response
- Agent writes `rhoai-evaluation.md` to the clone directory
- Agent handles LLM failure gracefully (returns empty evaluation, no exception)
- Agent handles JSON parse failure gracefully
- Strategy content is properly injected into the prompt
- Scoring dimensions are read from strategy YAML, not hardcoded

---

### Task 77 — Graph integration

**Files:** `src/autopoc/graph.py`

**Depends on:** Task 76

**Work:**
- Import `evaluate_agent` from `autopoc.agents.evaluate`
- Add `"evaluate"` to `PIPELINE_PHASES` list between `"intake"` and `"poc_plan"`
- Add `evaluate` node to the graph
- Refactor routing:
  - `route_after_intake` now returns `"evaluate"` on success (instead of
    `["poc_plan", "fork"]`); returns `["failed"]` on error
  - New `route_after_evaluate` function that returns `["poc_plan", "fork"]`
    on success or `["failed"]` on error (though evaluation failure itself
    doesn't set `error` — only intake error propagates)
  - Update all conditional edges in `build_graph()` for the new topology
- Handle `stop_after` correctly for the new node:
  - `stop_after="intake"` → intake → END (unchanged)
  - `stop_after="evaluate"` → intake → evaluate → END
  - `stop_after="poc_plan"` or `stop_after="fork"` → intake → evaluate →
    [poc_plan/fork] → END

**Acceptance criteria:**
- Graph compiles with all `stop_after` values
- `evaluate` node runs between intake and fan-out
- Existing graph topology preserved after evaluate
- `PIPELINE_PHASES` list updated

---

### Task 78 — Markdown report writer

**Files:** `src/autopoc/agents/evaluate.py` (part of Task 76, but separated for clarity)

**Depends on:** Task 76

**Work:**
- The `_build_evaluation_markdown()` function renders a clean markdown report:
  - Header with project name, strategy name/version, total score
  - Score breakdown table (dimension, score, max, rationale)
  - Strategy alignment section (areas, relationship, capabilities)
  - Overall assessment with strengths and risks
- File is written to `{local_clone_path}/rhoai-evaluation.md`
- Path stored in `rhoai_evaluation_path` state field

**Acceptance criteria:**
- Markdown file is well-formatted and readable
- Contains all evaluation data
- Handles edge cases (empty dimensions, missing rationale)

**Implementation note:** This is part of the evaluate agent implementation
(Task 76) and not a separate module. Listed separately for tracking purposes.

---

### Task 79 — Package data configuration

**Files:** `pyproject.toml`

**Depends on:** Task 73

**Work:**
- Ensure `data/` directory (with `strategy_config.yaml`,
  `strategy-baseline.yaml`, `strategies/`) is included as package data
- Add appropriate `[tool.hatch.build]` or `[tool.setuptools.package-data]`
  configuration (depends on build backend — project uses `hatchling`)
- Verify the data files are findable at runtime from the strategy loader

**Acceptance criteria:**
- `pip install -e .` includes `data/` files
- Strategy loader can find and read files at runtime
- `pip install .` (non-editable) also works

---

### Task 80 — Unit tests: strategy loader

**Files:** `tests/test_strategy.py`

**Depends on:** Task 73

**Work:**
- Test `load_strategy_config()` returns active strategy name
- Test `load_strategy()` loads the active strategy profile
- Test `load_strategy("classic")` loads a specific strategy
- Test `load_strategy_baseline()` loads the baseline YAML
- Test `get_scoring_dimensions()` extracts correct dimensions:
  - 5 dimensions for `redhat-ai-2026`
  - 3 dimensions for `classic`
- Test `compute_max_score()` returns 100 for default strategy
- Test missing file handling (clear error messages)
- Test strategy baseline structure (strategy_areas, core_products,
  relationship_rules all present)

**Acceptance criteria:**
- All loader functions tested with real YAML files from `data/`
- Edge cases tested (missing file, malformed YAML)
- Tests pass in CI

---

### Task 81 — Unit tests: evaluate agent

**Files:** `tests/test_evaluate.py`

**Depends on:** Task 76

**Work:**
- Test happy path: mock LLM returns valid JSON → evaluation populated correctly
- Test score clamping: mock LLM returns out-of-range scores → clamped to valid range
- Test LLM failure: mock LLM raises exception → empty evaluation returned,
  no exception propagated
- Test JSON parse failure: mock LLM returns invalid JSON → empty evaluation
- Test markdown report generation: verify file written with correct content
- Test strategy injection: verify the prompt contains strategy content
- Test dimension dynamic loading: verify dimensions come from strategy YAML
- Test with different strategies (redhat-ai-2026 vs classic → different dimensions)
- Fixture: sample repo digest and component list (reuse intake test fixtures)

**Acceptance criteria:**
- All agent behaviors tested (success, failure, edge cases)
- Non-blocking behavior verified (failures don't raise)
- Tests pass in CI

---

### Task 82 — CLI: --stop-after=evaluate and display

**Files:** `src/autopoc/cli.py`

**Depends on:** Task 77

**Work:**
- `--stop-after=evaluate` already works via graph changes (Task 77), but
  verify it displays results correctly
- Add evaluation display to `_print_results()` or a new `_print_evaluation()`
  helper:
  - Show score panel with total, relationship, areas, capabilities
  - Show dimension breakdown table (if verbose)
- Display evaluation results in both `run` and `run-sheet` commands
- Handle the case where evaluation is empty (display "Not evaluated" or similar)

**Acceptance criteria:**
- `--stop-after=evaluate` works and shows evaluation output
- Evaluation results displayed in normal pipeline run
- Empty evaluation handled gracefully in display
- Verbose mode shows dimension breakdown

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM scoring is inconsistent across runs | Different scores for same project | Include clear rubric in prompt; dimension rationales provide transparency |
| Strategy YAML not found at runtime | Agent crashes | Graceful fallback — skip evaluation if strategy not found |
| Evaluation adds latency to pipeline | Slower overall execution | One LLM call (~3-5s); acceptable tradeoff for the insight gained |
| Token budget for strategy baseline | Prompt too large | Strategy baseline is ~200 lines of YAML (~4K tokens); well within budget |
| Dynamic dimension loading breaks schema | JSON parse failure | Validate dimension names match expected schema; fall back to hardcoded if needed |
