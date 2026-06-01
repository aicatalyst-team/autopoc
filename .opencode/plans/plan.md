# Vale Prose Linting - Implementation Plan

## Overview

Add a post-generation Vale lint step as a shared utility function that any
markdown-producing agent can call. The function runs Vale, feeds findings to
the LLM for conservative revision, and repeats up to `max_vale_revisions`
times. Vale availability is optional (graceful skip if not installed).

Based on: `docs/adr/0010-vale-prose-linting.md`

## Phase 1: Core Infrastructure

| Task | Status |
|------|--------|
| Add `max_vale_revisions` config field | Done |
| Add `vale_findings` state field | Done |
| Create `src/autopoc/tools/vale_lint.py` utility | Done |
| Create `src/autopoc/prompts/vale_revision.md` | Done |

## Phase 2: Agent Integration

| Task | Status |
|------|--------|
| Integrate into `poc_report` agent | Done |
| Integrate into `poc_plan` agent | Done |
| Integrate into `blog_post` agent | Done |

## Phase 3: Testing & Validation

| Task | Status |
|------|--------|
| Write unit tests for vale_lint utility | Done (21 tests) |
| Run lint, typecheck, tests | Done (629/629 pass) |
| Update ADR status to Accepted | Done |

---

# OpenCode Harness Rewrite

## Overview

Replace the LangGraph multi-agent pipeline with an OpenCode skill-driven architecture.
OpenCode becomes the orchestration harness; pipeline logic stays the same but execution
model changes fundamentally. See `opencode-harness-rewrite.md` for full architecture.

## Phase 1: Design ✅

| Task | Status |
|------|--------|
| Research current codebase thoroughly | Done |
| Design architecture (opencode-harness-rewrite.md) | Done |
| Design run-poc skill (SKILL.md + 8 references) | Done |
| Design run-sheet skill (SKILL.md + 1 reference) | Done |
| Design blog-create skill (adapted from ai-asset-registry) | Done |
| Design state file schema (poc-state.yaml) | Done |
| Design retry strategy | Done |
| Design error triage rules | Done |

## Phase 2: Foundation ✅

| Task | Status |
|------|--------|
| Add CLI wrappers to retained Python tools | Done |
| Create opencode.json configuration | Done |
| Verify OpenCode headless/non-interactive mode | Done |
| Test skill loading and invocation | Done |

## Phase 3: Container Image ✅

| Task | Status |
|------|--------|
| Update Dockerfile with OpenCode binary | Done |
| Update Makefile targets | Done |

## Phase 4: K8s Manifests & Scripts ✅

| Task | Status |
|------|--------|
| Update deploy/base/job.yaml | Done |
| Update deploy/base/cronjob.yaml | Done |
| Update scripts/run-autopoc.sh | Done |

## Phase 5: Cleanup ✅

| Task | Status |
|------|--------|
| Remove LangGraph dependencies | Done |
| Remove agent files, graph.py, state.py, cli.py | Done (18,684 lines) |
| Remove obsolete tests (22 test files) | Done |
| Remove @tool decorators from 6 tool files | Done |

## Phase 6: Testing & Validation ✅

| Task | Status |
|------|--------|
| Write CLI tools tests (20 tests) | Done |
| Write skill validation tests (48 tests) | Done |
| Run full test suite (348 passed) | Done |
| Lint + format clean | Done |

---

# AutoPoC Cleanup Improvements

## Overview

Implement comprehensive cleanup functionality to address resource accumulation and improve retry success rates. Includes build/deployment failure cleanup, GitHub repository tagging, and smart fork detection.

## Phase 1: Core Infrastructure ✅

| Task | Status |
|------|--------|
| Create ADR 0012 for cleanup improvements | ✅ Done |
| Implement cleanup_tools.py module | ✅ Done |
| Implement github_tools.py module | ✅ Done |
| Add cleanup configuration options | ✅ Done |

## Phase 2: Integration ✅

| Task | Status |
|------|--------|
| Update Phase 3 (Fork) with smart GitHub detection | ✅ Done |
| Update Phase 5 (Containerize) with build cleanup | ✅ Done |
| Update Phase 7 (Deploy) with deployment cleanup | ✅ Done |
| Update tools/__init__.py exports | ✅ Done |

## Phase 3: Testing ✅

| Task | Status |
|------|--------|
| Write cleanup tools unit tests | ✅ Done |
| Write GitHub tools unit tests | ✅ Done |
| Validate integration with run-poc skill | ✅ Done |
| Run import and config validation tests | ✅ Done |
| Code quality checks (ruff lint/format) | ✅ Done |
