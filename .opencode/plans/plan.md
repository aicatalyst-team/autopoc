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

## Phase 2: Foundation

| Task | Status |
|------|--------|
| Add CLI wrappers to retained Python tools | Pending |
| Create opencode.json configuration | Pending |
| Verify OpenCode headless/non-interactive mode | Pending |
| Test skill loading and invocation | Pending |

## Phase 3: Container Image

| Task | Status |
|------|--------|
| Update Dockerfile with OpenCode binary | Pending |
| Update Makefile targets | Pending |
| Test image build | Pending |

## Phase 4: K8s Manifests & Scripts

| Task | Status |
|------|--------|
| Update deploy/base/job.yaml | Pending |
| Update deploy/base/cronjob.yaml | Pending |
| Update scripts/run-autopoc.sh | Pending |

## Phase 5: Cleanup

| Task | Status |
|------|--------|
| Remove LangGraph dependencies | Pending |
| Remove agent files, graph.py, state.py, cli.py | Pending |
| Remove obsolete tests | Pending |
| Update requirements.lock | Pending |

## Phase 6: Testing & Validation

| Task | Status |
|------|--------|
| Write standalone script tests | Pending |
| Write state file tests | Pending |
| Write skill validation tests | Pending |
| E2E validation | Pending |
