# Vale Prose Linting - Detailed Implementation Plan

## Progress

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Core Infrastructure | Done | All 4 tasks complete |
| Phase 2: Agent Integration | Done | All 3 agents integrated |
| Phase 3: Testing & Validation | Done | 21 tests, all pass |

## Architecture

The Vale linting feature is implemented as a **shared utility function**
(`vale_lint_and_revise`) in `src/autopoc/tools/vale_lint.py`, not as a
separate graph node. Each markdown-producing agent calls it inline after
writing its artifact.

### Flow

```
Agent writes markdown file
  -> vale_lint_and_revise(file_path, llm, max_revisions)
    -> Run `vale --output=JSON <file>`
    -> If findings exist:
      -> Feed findings + original content to LLM with revision prompt
      -> Write revised content to file
      -> Re-run Vale
      -> Repeat up to max_vale_revisions times
    -> Return (revised_content, findings_summary)
```

### Key Design Decisions

1. **Utility function, not graph node**: Simpler, no new edges/routing
2. **Optional Vale**: Silently skip with warning if `vale` binary missing
3. **Conservative revision**: LLM treats Vale findings as suggestions
4. **No pipeline failure**: Vale issues never block the pipeline

## Phase 1: Core Infrastructure

### 1.1 Config field (`config.py`) -- Done
- Added `max_vale_revisions: int = Field(default=3, ...)`

### 1.2 State field (`state.py`) -- Done
- Added `vale_findings: list[dict]` to PoCState

### 1.3 Vale utility (`src/autopoc/tools/vale_lint.py`) -- Done
- `run_vale(file_path) -> list[dict]`: Run vale --output=JSON
- `vale_lint_and_revise(file_path, llm, max_revisions) -> tuple[str, list]`:
  Full lint-revise loop
- Handles missing `vale` binary gracefully

### 1.4 Revision prompt (`src/autopoc/prompts/vale_revision.md`) -- Done
- System prompt for conservative, selective revision
- Emphasizes technical accuracy over style compliance

## Phase 2: Agent Integration

### 2.1 poc_report agent -- Done
- Calls `vale_lint_and_revise` after writing poc-report.md, before commit

### 2.2 poc_plan agent -- Done
- Calls `vale_lint_and_revise` after writing poc-plan.md, before commit
- Integrated in both phase 1 (one-shot) and phase 2 (ReAct fallback) paths

### 2.3 blog_post agent -- Done
- Calls `vale_lint_and_revise` after finalization, before commit

## Phase 3: Testing & Validation

### 3.1 Unit tests -- Done (21 tests)
- TestValeAvailable: vale binary detection (2 tests)
- TestRunVale: subprocess handling, JSON parsing, error cases (8 tests)
- TestFormatFindings: findings formatting (2 tests)
- TestValeLintAndRevise: full loop logic (9 tests)
  - No-findings early return
  - Revision fixes issues
  - Max revisions respected
  - Truncation guard
  - LLM failure handling
  - Missing file handling
  - Code fence stripping
  - Explicit max_revisions parameter
  - Multi-part LLM content

### 3.2 Verification -- Done
- `ruff check src/ tests/` -- All checks passed
- `pyright src/` -- 0 errors, 0 warnings
- `pytest tests/ --ignore=tests/e2e` -- 629 passed

---

# OpenCode Harness Rewrite - Implementation Plan

## Progress

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Design | Done | Architecture doc + 3 skills + 14 reference files |
| Phase 2: Foundation | Pending | CLI wrappers, opencode.json, skill testing |
| Phase 3: Container Image | Pending | Dockerfile update, Makefile |
| Phase 4: K8s Manifests & Scripts | Pending | Job, CronJob, run-autopoc.sh |
| Phase 5: Cleanup | Pending | Remove LangGraph, agents, graph, old tests |
| Phase 6: Testing & Validation | Pending | New test suite, E2E validation |

## Architecture

Replace LangGraph multi-agent pipeline with OpenCode skill-driven architecture.
Full design: `.opencode/plans/opencode-harness-rewrite.md`

### Key Changes
- LangGraph -> OpenCode skills (run-poc, run-sheet, blog-create)
- ReAct agents -> OpenCode following skill instructions
- PoCState TypedDict -> Progressive YAML state file
- LangChain @tools -> bash commands + standalone Python scripts
- shiv binary container -> OpenCode binary container

### Skill Files Created

```
.opencode/skills/
  run-poc/
    SKILL.md                     # 11-phase pipeline instructions
    references/
      intake.md                  # Phase 1 analysis rules
      poc-plan.md                # Phase 4 plan generation
      containerize.md            # Phase 5 Dockerfile creation
      deploy.md                  # Phase 7 K8s manifest generation
      poc-execute.md             # Phase 9 test script generation
      poc-report.md              # Phase 10 report generation
      state-schema.md            # YAML state file schema
      retry-strategy.md          # Retry loop logic
      error-triage.md            # Apply failure classification
      ubi-dockerfile-rules.md    # UBI/OpenShift compatibility rules
  run-sheet/
    SKILL.md                     # Sheet-driven batch pipeline
    references/
      prefilter.md               # Heuristic scoring rules
  blog-create/
    SKILL.md                     # Blog generation pipeline (adapted from ai-asset-registry)
    assets/
      blog-template.html         # HTML preview template
    references/
      scoring.md                 # Review scoring and iteration rules
      reviewer-architect.md      # Structure reviewer rubric
      reviewer-content.md        # Content reviewer rubric
      reviewer-formatting.md     # Formatting reviewer rubric
      reviewer-image.md          # Image reviewer rubric
      html-preview-guide.md      # HTML conversion guide
```

## Phase 1: Design -- Done

### 1.1 Architecture Document -- Done
- Created `.opencode/plans/opencode-harness-rewrite.md`
- Covers: execution model, state file design, skill design, container image,
  K8s manifests, standalone scripts, test strategy, migration path, dependencies,
  risk assessment

### 1.2 run-poc Skill -- Done
- SKILL.md: 11-phase pipeline with retry loops
- 10 reference files covering all phases, state schema, retry strategy, error triage

### 1.3 run-sheet Skill -- Done
- SKILL.md: 7-step sheet processing pipeline
- 1 reference file for heuristic pre-filtering

### 1.4 blog-create Skill -- Done
- SKILL.md: Adapted from ai-asset-registry/blog-create
- 6 reference files: scoring, 4 reviewers, HTML guide
- 1 asset: blog-template.html

## Phase 2: Foundation -- Pending

### 2.1 CLI Wrappers for Python Tools
Add `__main__.py` or CLI entry points to:
- `src/autopoc/tools/repo_digest.py`
- `src/autopoc/tools/gitlab_tools.py` (as gitlab_client)
- `src/autopoc/tools/github_tools.py` (as github_client)
- `src/autopoc/tools/quay_tools.py` (as quay_client)
- `src/autopoc/tools/strategy.py`
- `src/autopoc/tools/llm_proxy.py`
- `src/autopoc/sheet.py` (as sheet_reader/sheet_writer)
- `src/autopoc/tools/vale_lint.py` (as vale_runner)

### 2.2 OpenCode Configuration
- Create `opencode.json` with skill definitions and provider config

### 2.3 Headless Mode Verification
- Test OpenCode non-interactive/headless mode for pod execution
- Verify `opencode --skill run-poc --prompt "..."` syntax

## Phase 3: Container Image -- Pending

### 3.1 Dockerfile Update
- Add OpenCode binary download (from GitHub releases)
- Copy skill files into image
- Update ENTRYPOINT to opencode
- Keep existing tools (kubectl, oc, vale, podman)

### 3.2 Makefile
- Update image build/push targets
- Add OpenCode version variable

## Phase 4: K8s Manifests & Scripts -- Pending

### 4.1 Job Manifest
- Update `deploy/base/job.yaml` for OpenCode args

### 4.2 CronJob Manifest
- Update `deploy/base/cronjob.yaml` for run-sheet skill

### 4.3 Run Script
- Update `scripts/run-autopoc.sh` for new Job template

## Phase 5: Cleanup -- Pending

### 5.1 Remove LangGraph Dependencies
- Remove from pyproject.toml: langgraph, langchain-*, typer, rich
- Regenerate requirements.lock

### 5.2 Remove Obsolete Code
- Remove: src/autopoc/agents/, graph.py, state.py, cli.py, cli_batch.py
- Remove: llm.py, context.py, debug.py
- Keep: tools/, prompts/, templates/, data/

### 5.3 Remove Obsolete Tests
- Remove: test_graph_*, test_retry_loop, test_llm_fallback, test_cli_*
- Remove: all agent tests (test_intake, test_containerize, etc.)
- Keep: tool tests, API client tests, strategy tests, sheet tests

## Phase 6: Testing & Validation -- Pending

### 6.1 New Tests
- Standalone script CLI tests
- State file YAML read/write tests
- Skill file validation tests (well-formed, references exist)

### 6.2 E2E Validation
- Full pipeline run with OpenCode in pod
- Retry loop validation
- Sheet processing validation
- Blog generation validation
