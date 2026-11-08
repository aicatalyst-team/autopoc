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

# GitHub Repository Safety

## Phase 1: GitHub Repository Safety ✅

| Task | Status |
|------|--------|
| Protect the detected GitHub default branch after fork or repository creation | ✅ Done |
| Route GitHub pipeline commits to the dedicated `autopoc` branch | ✅ Done |
| Preserve `autopoc-artifacts` for generated PoC artifacts | ✅ Done |
| Add skill validation tests for branch protection and safe pushes | ✅ Done |

## PR #57 Review Follow-up ✅

| Task | Status |
|------|--------|
| URL-encode branch names in GitHub protection API paths | ✅ Done |
| Require status checks and invalidate stale approvals | ✅ Done |
| Add regression coverage for the hardened policy | ✅ Done |

---

# AutoPoC Report Video Feature Ticket

## Phase 1: Ticket Definition ✅

| Task | Status |
|------|--------|
| Define scope and Definition of Done for report-driven explanatory videos | ✅ Done |
| Create Jira Feature AIPCC-32887 in the AIPCC project | ✅ Done |

## Phase 2: Slidev Feasibility Epic ✅

| Task | Status |
|------|--------|
| Fill Jira Epic AIPCC-33008 with Slidev feasibility scope and Definition of Done | ✅ Done |

## Phase 3: Headless Presentation and UI Evidence Requirements ✅

| Task | Status |
|------|--------|
| Document the headless post-report presentation step and proposed execution approach | ✅ Done |
| Document UI screenshots, scenario recordings, and Playwright traces during original tests | ✅ Done |
| Document evidence preservation, source linkage, and remaining output/runtime decisions | ✅ Done |

Details: [Presentation session handoff and automation plan](../../docs/report-presentation-plan.md).

## Phase 4: Sample Presentation and Recording Feasibility — Historical milestone

| Task | Status |
|------|--------|
| Archive evidence from a representative completed end-to-end PoC | ✅ Done — Omnigent run autopoc-omnigent-8554, reports, original test JSON, sanitized runner/build logs and later observations |
| Generate and verify a sample Slidev presentation and PDF headlessly | ✅ Done — 14 main slides plus 4 appendix slides, including animated TopoLoop setup and scenario walkthroughs, static browser build and 18-page PDF |
| Evaluate recording/composition | Executive recording transferred to Phase 6; UI clip composition is optional later work |

Sample: `presentations/omnigent-2026-10-20/`. Original browser traces and UI
recordings were not captured by this run's five HTTP checks. The included UI
screenshot is explicitly a later observation. The Phase 1 executive video
records the presentation and does not depend on original UI clips.

## Phase 5: Presentation Automation Handoff

| Task | Status |
|------|--------|
| Document completed work, repositories/tools, reproduction commands, evidence limits, and integration points | ✅ Done |
| Define the evidence-bundle contract and implementation sequence for post-report generation | ✅ Done — roadmap documented; implementation pending |
| Add local HTTP instructions for development and built previews, prerequisites, URLs, and server shutdown | ✅ Done |
| Prepare the evidence collector implementation plan from the saved handoff | ✅ Done — `docs/superpowers/plans/2026-10-26-presentation-evidence.md`; implementation pending |
| Implement evidence preservation, generic renderer, Job integration, silent video and durable publication | Core implementation ✅ — active rollout/acceptance is defined in Phase 6 |

## Phase 6: Executive Presentation and Video Scope

| Task | Status |
|------|--------|
| Specify an automatic executive deck and presentation video covering purpose, strategy, execution, and report-based platform suitability | ✅ Done — full design documented; implementation pending |
| Record silent video for Phase 1 and Google TTS voice-over for Phase 2 | ✅ Done — user preference captured |
| Check the expanded design with an independent builder review | ✅ Done — clarified unattended content/publication checks |
| Incorporate the Astra assessment across the design and active plans | ✅ Done — implementation review also closed five findings |
| Preserve report/artifact history and indexed test attempts | ✅ Done — capture, collector/verifier, immutable Git writer and fixtures |
| Implement durable render inputs, upload intents and independent recovery | ✅ Code/recovery tests and actual personal Drive reference publication |
| Implement executive Slidev/TopoLoop rendering and silent MP4 | ✅ Full six-scene/two-minute local reference verified and uploaded |
| Isolate and verify the renderer Job under resource failures | Packaging/RBAC and restricted OCP render ✅; forced resource-failure acceptance open |
| Publish report links and run cluster acceptance | Link/reconciliation, personal Drive reference and OCP offline render ✅; unattended publication open |
| Approve the design and implement report integration, rendering, video generation and publishing | Implementation authorized 26 October; in progress |
| Correct PR-readiness test race and sample license whitespace | ✅ 28 October — 366 supported tests passed; committed caac1e3 |
| Verify a restricted OCP reference through the published image entrypoint | ✅ 28 October — six-page PDF, silent120sMP4, all output hashes verified; 178.895s, peak1,841,668,096 bytes |
| Push the feature branch and open a draft PR in the user's fork | ✅ [aviavraham/autopoc#1](https://github.com/aviavraham/autopoc/pull/1), targeting fork master |
| Review the merged project state | ✅ 3 November — fork master contains merge `6b564e5`; upstream master `3f266c7` does not contain the feature; 169 scoped Python tests and four Node tests passed |
| Check upstream integration and CI | ✅ 3 November — [PR #66](https://github.com/aicatalyst-team/autopoc/pull/66) open with no merge conflicts; approval required; five CI jobs passed, security audit failed with the same 10 reported findings across four packages as upstream master |

Phase status as of 3 November: core implementation merged into the user's fork;
rollout/acceptance remains open. Repair production Google service credentials,
validate unattended publication, resource/admission failures and model-service
narrative review, then build and roll out the main worker. Earlier pending and
draft-PR rows describe historical milestones.

Verification: 366 supported tests, 83.48% coverage, pinned Ruff clean, Pyright
zero errors and two Node tests passed. Renderer image published to Quay by digest;
main worker rebuild/rollout remains open. Personal Google OAuth credentials are
local only while the production service-account credential is repaired.

## Phase 7: Upstream Security Remediation — ✅ Done

| Task | Status |
|------|--------|
| Reproduce the upstream PR dependency audit failure | ✅ Same 10 reported findings across four transitive dependencies reproduced locally |
| Regenerate patched dependency pins and cryptographic hashes | ✅ certifi 2026.10.23, opentelemetry-api 1.45.2, pyasn1 0.6.5, urllib3 2.8.0; other package versions unchanged |
| Verify the security fix in a fresh Python 3.12 environment | ✅ Clean audit, hash installation and pip check; 371 tests passed, 85.55% coverage; Ruff, Pyright and four renderer tests passed |
| Push the fix branch and open a reviewable fork PR | ✅ [Fork PR #2](https://github.com/aviavraham/autopoc/pull/2), mergeable with no conflicts; no fork CI checks reported |
| Update upstream PR #66 through the fork's master branch | ✅ User merged fork PR #2 as 231fc31; upstream PR #66 updated automatically; all six CI jobs passed |

## Phase 8: Default Red Hat Presentation Branding — Implementation/local acceptance ✅; OCP rollout pending

| Task | Status |
|------|--------|
| Inspect the supplied template and official brand standards | ✅ Representative pages visually inspected; template provenance recorded |
| Confirm scope and define the branding design | ✅ User selected default branding; six-scene deck/PDF/video, assets, diagram palette and compatibility specified |
| Independently check the design for planning gaps | ✅ Builder check found no important unanswered questions |
| Save required branding components and the template in the repository | ✅ Nine official font files, corporate/hat SVGs, licenses/authors and hash/source manifest under renderer/assets/redhat; byte-identical reference PDF under docs/branding; assets verified |
| Approve visual direction and prepare implementation | ✅ User approved design and implementation; ordered implementation plan saved |
| Implement branded layouts, local assets, diagram theme and versioned packaging | ✅ Shared shell, local asset verification/copying, palette, preflight and image packaging defined; seven Node and 25 Python input/render tests passed |
| Bind revision 2 and preserve legacy recovery/source assets | ✅ 35 affected Python tests passed; default v2 sealing, explicit v1 verification and source packaging implemented |
| Validate PDF/video layouts, offline assets and recovery compatibility | ✅ Constrained UBI reference: six-page PDF, silent120sMP4, asset/output hashes and extracted source preparation verified; 213.81s, peak2,504,695,808 bytes |
| Resolve independent review and verify local rendering behavior | ✅ Diagram clipping regression RED→GREEN; 379 Python tests, 85.62% coverage, eight Node tests; real-browser layout/asset checks passed |
| Push feature branch and prepare a reviewable PR | ✅ [Draft fork PR #3](https://github.com/aviavraham/autopoc/pull/3); no merge or deployment configuration changes |
| Publish new renderer digest, validate restricted OCP behavior and roll out worker/renderer | Pending; local validation does not establish OCP deployment/publication |

Design: [Red Hat presentation branding](../../docs/superpowers/specs/2026-11-03-red-hat-presentation-branding-design.md).


## Phase 9: Kokoro Voice-over — Audition/design/planning ✅; implementation in progress

| Task | Status |
|------|--------|
| Check Google TTS availability on the work project | ✅ Billing enabled; TTS API absent; use request denied by project permissions |
| Generate two local Kokoro voice samples | ✅ 8 November — Heart 22.150s and Fenrir 20.325s; CPU generation about 14.2s each |
| Verify sample integrity and preserve audition measurements | ✅ Finite non-silent WAVs; MP3 probe and full decode passed; script/package inventory/results retained locally |
| Select a voice and agree on content/timing direction | ✅ Heart selected; length follows PoC complexity; source-backed objective/testing/setup/results plus limitations/recommendation |
| Save and independently check design and implementation plan | ✅ Eight tasks defined; builder review found no important gaps; user approved implementation 8 November |
| Check OCP GPU capacity and AutoPoC namespace access | ✅ 8 November — one L40S and two A100 devices unrequested; Job/pod creation allowed, no namespace quota found; workload not tested |
| Implement and validate narrated rendering | In progress — supplemental evidence complete; renderer/narration tasks pending |

This is a local throwaway audition, not production narration acceptance. Technical
pronunciation, offline packaging, per-scene synchronization and restricted OCP
resource acceptance remain future design/validation work if Kokoro is selected.


Planning completed 8 November: [design](../../docs/superpowers/specs/2026-11-08-kokoro-narrated-video-design.md)
and [implementation plan](../../docs/superpowers/plans/2026-11-08-kokoro-narrated-video.md).
Use final report, original results, staged setup, logs and available traces;
include fixes only when they help explain the PoC outcome. Implementation was authorized on 8 November; native execution is in progress. The eight implementation tasks and status are tracked in
implementation-plan.md section 9.3; every completed task must update both files.


### Phase 9 implementation tasks

| Task | Status |
|------|--------|
| Retain sanitized supplemental logs/traces/setup evidence | ✅ Done — 67 scoped / 401 full-suite Python tests passed |
| Seal source-linked storyboards and reviewed narration | ✅ Done — 53 scoped tests; legacy inputs retained |
| Update author/reviewer workflow and ADR | ✅ Done — source-linked examples and real configured-model reviews |
| Package offline Heart speech and measured timeline | ✅ Done — 18 speech tests; actual constrained offline image smoke |
| Render variable slide chapters | Pending |
| Encode narrated video and preserve partial outputs | Pending |
| Persist long-render policy/recovery/publication | Pending |
| Complete local/OCP acceptance and controlled rollout | Pending |
