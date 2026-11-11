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
| Phase 7: GitHub Repository Safety | Done | Default branch protection and dedicated AutoPoC write branch |

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

## Phase 7: GitHub Repository Safety -- Done ✅

### 7.1 Protect GitHub default branches -- Done ✅
- Added a reusable GitHub repository policy for forked and freshly created repositories.
- Detects the repository's actual default branch (`main`, `master`, or another configured default).
- Enables pull-request review protection and disables force pushes and deletions.

### 7.2 Isolate AutoPoC writes -- Done ✅
- Uses the `autopoc` branch for GitHub source synchronization and pipeline commits.
- Replaced GitHub `--all` and `HEAD` pushes with explicit `autopoc` pushes.
- Retains `autopoc-artifacts` for generated plans, reports, tests, and blog artifacts.

### 7.3 Verification -- Done ✅
- Added skill validation tests for the branch-protection payload and safe push commands.

## PR #57 Review Follow-up ✅

- URL-encode GitHub default branch names before using them in REST API paths.
- Require configured status checks and invalidate stale approvals after new commits.
- Add regression assertions covering the hardened branch-protection policy.

---

# AutoPoC Report Video Feature Ticket

The ticket and sample milestones below retain their historical record. For
implementation, use Phase 6 and the revised executive design as the current
scope: silent presentation video in Phase 1, Google TTS in Phase 2, and a
separate renderer Job with durable input/recovery material. Older architecture
recommendations are not execution instructions.

## Progress

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Ticket definition | ✅ Done | Jira Feature AIPCC-32887 created with scope and Definition of Done |
| Phase 2: Slidev feasibility Epic | ✅ Done | AIPCC-33008 filled with feasibility scope, technical constraints, and Definition of Done |
| Phase 3: Headless presentation and UI evidence requirements | ✅ Done | Documented the requested headless step and proposed capture/evidence flow; implementation choices remain under evaluation |
| Phase 4: Sample presentation and recording feasibility | Sample complete; video work transferred | Omnigent archive and Slidev/PDF complete; executive recording belongs to Phase 6, original UI clip composition is optional later work |
| Phase 5: Presentation automation handoff | Documentation ✅ Done; implementation pending | Session record, repositories/tools, reproduction and staged integration roadmap documented |
| Phase 6: Executive presentation and video scope | Core implementation merged ✅; rollout/acceptance open | Fork master merge verified 3 November; restricted OCP render and personal Drive reference passed; unattended publication, failure acceptance, model review and worker rollout remain |
| Phase 7: Upstream security remediation | ✅ Done | User merged fork PR #2; upstream PR #66 updated to 231fc31 and all six CI jobs, including security, passed |
| Phase 8: Default Red Hat presentation branding | Implementation/local acceptance ✅; OCP rollout pending | 379 Python/eight Node tests and full constrained offline UBI render passed; draft fork PR #3 ready for review; new registry publication and OCP validation remain |

## Phase 1: Ticket Definition ✅

### 1.1 Create Jira feature ticket — ✅
- Created [AIPCC-32887](https://redhat.atlassian.net/browse/AIPCC-32887) in the AIPCC project.
- Captured report-driven video generation scope and acceptance criteria for background, setup, testing, evidence-based suitability conclusion, and report linkage.

## Phase 2: Slidev Feasibility Epic ✅

### 2.1 Fill Jira Epic AIPCC-33008 — ✅
- Added a bounded evaluation of Slidev with AutoPoC, Playwright, and the existing workflow-validation/recording capabilities.
- Recorded the documented recording/export behavior, automation questions, sample-video deliverable, and feasibility recommendation criteria.

## Phase 3: Headless Presentation and UI Evidence Requirements ✅

### 3.1 Document headless generation and UI capture requirements — ✅
- Added [the presentation plan](../../docs/report-presentation-plan.md) covering a headless post-report step without an interactive Slidev login or local operator installation.
- Recorded screenshots at meaningful UI test checkpoints, recordings of selected scenarios, and Playwright traces captured during the original validation run.
- Defined run/scenario evidence linkage, credential handling, and preservation of ephemeral run artifacts for repeatable presentation generation.
- Distinguished AutoPoC's content-generation model from Slidev's model-free rendering.
- Kept presentation/video output scope, narration, storage, and runtime limits open; the separate Job and non-blocking failure behavior are recommendations pending validation.

## Phase 4: Sample Presentation and Recording Feasibility — Historical milestone

### 4.1 Archive one completed PoC — ✅
- Archived the Omnigent run `autopoc-omnigent-8554`: pinned report/plan/evaluation/blog/manifests, original test JSON, sanitized runner and both build logs, and selected job/build metadata.
- Indexed claims and source hashes; labeled later UI/cluster observations separately.
- Recorded missing original browser/distributed traces, UI recordings and workspace state export instead of inventing those artifacts.

### 4.2 Generate and inspect the sample Slidev deck — ✅
- Created `presentations/omnigent-2026-10-20/` with 14 stakeholder slides and 4 technical appendix slides.
- Built a static browser deck and exported/visually inspected an 18-page PDF with headless Chromium.
- Documented reproducible commands, original test coverage, temporary storage, source-branch drift, SCC/report discrepancy and source-linked evidence.
- Added two TopoLoop slides: eight-resource setup topology with three acts and five-check scenario flow driven by the archived original results. Preserved pinned upstream source/licenses, reduced-motion behavior, still-frame controls and deterministic PDF frames.

### 4.3 Recording and composition feasibility — Transferred
- Executive presentation recording is required Phase 1 work in section 6.5. Composition with actual UI test clips is optional later work and is not a prerequisite for the silent executive video. No video capability is claimed by the existing sample.

## Phase 5: Presentation Automation Handoff

### 5.1 Document session and continuation plan — ✅
- Updated [the presentation handoff](../../docs/report-presentation-plan.md) with completed work, repository roles and pinned revisions, tools, sample commands, source files, and evidence boundaries.
- Verified the integration targets against the current OpenCode skill/YAML-state runtime, runner scripts, and container definitions.
- Defined an immutable evidence bundle, a separate headless renderer Job, independent presentation status, publishing, and acceptance checks.
- Added the handoff to the root README documentation index.
- Added a dedicated local HTTP section with Node/npm prerequisites, Slidev and Vite commands, localhost URLs, directory guidance, and Ctrl+C shutdown instructions.

### 5.2 Implement post-report presentation generation — Superseded by Phase 6
- The active Phase 1 deliverables are executive Markdown, editable Slidev/TopoLoop source, browser build, PDF and a silent MP4, with durable inputs, recovery and report links.
- Use the ordered work in sections 6.3–6.7. Original UI capture is optional later work; Google TTS narration is Phase 2. Runtime implementation remains pending.

### 5.3 Plan the evidence collector milestone — ✅
- Resumed from the saved handoff on 26 October 2026 and checked the current OpenCode workflow, CLI, dependency declarations, and repository state.
- Added `docs/superpowers/plans/2026-10-26-presentation-evidence.md` with the bundle contract, collector/verifier and CLI interfaces, original-result capture instructions, test coverage, and publication boundary.
- Collection implementation, storage integration, and automatic rendering remain pending. The plan is ready for review and execution-method selection.

## Phase 6: Executive Presentation and Video Scope

### 6.1 Record expanded feature requirements — ✅
- Added `docs/superpowers/specs/2026-10-26-executive-summary-design.md` for automatic executive Slidev/TopoLoop presentations and videos based on the PoC report.
- Defined repository purpose, testing strategy, actual execution and report-based OpenShift/Kubernetes suitability as required topics in both outputs.
- Included report Executive Summary links, reusable headless recording/encoding, independent failure states, and configurable publication through existing tooling.
- Recorded the user's phase boundary: silent on-screen-text video first, Google TTS voice-over in Phase 2.
- Updated the authoritative handoff and collector plan to reflect the expanded scope; feature implementation remains pending.
- An independent builder review identified one material ambiguity; clarified automated content/publication checks with no per-run human approval gate. Design approval and implementation planning remain pending.

### 6.2 Incorporate Astra assessment — ✅
- Revised the design, collector plan and handoff for all six findings: report lifecycle, durable recovery material, attempt history, extension resume, resource isolation and conflicting active scope.
- Changed the cluster execution choice to a separate renderer Job. Synchronized silent video as a Phase 1 requirement and Google TTS as Phase 2.
- Added acceptance cases for report → extension → blog persistence, original workspace deletion, interrupted uploads, completed-blog resume and forced renderer failure.
- These are documentation corrections only. Implementation remains on hold while the user reviews; a detailed whole-feature implementation plan is still required.

### 6.3 Preserve source evidence and artifact history — ✅
- ✅ Collector Task 0: implemented the common append-only Git writer and CLI; migrated evaluation/plan/tests/report/blog artifact instructions to stable staging and immutable revisions. Independent scoped review passed. Verified 71 affected tests, including real competing Git writers and source-checkout preservation.
- Implemented indexed capture, explicit final execution and incomplete-result handling, sanitized verified evidence ZIPs and historical/synthetic fixtures. Actual child-process/HTTP retry tests cover original attempts; collection never replays PoC tests.
- Evidence review found quoted-credential and index-metadata scan bypasses; both fixed with RED→GREEN regression tests and scoped re-review.

### 6.4 Seal durable render inputs and implement recovery — ✅ implementation; live acceptance open
- Implemented hash-bound review receipts, four-topic JSON and bounded graphs/scenes, pinned image identities and sealed inputs. Existing OpenCode performs production content review; manual reference review receipts are labeled synthetic.
- Added preallocated Drive IDs, upload intents/receipts, verified downloads, append-only Git checkpoints with a bounded immutable input fallback, standalone recovery and phase-independent reconciliation.
- Ten real-Git/fake-provider recovery tests pass, including missing receipts, pending input upload, pre-UID submission and immutable/symlink-safe recovery. Real personal Drive reference publication passed with verified inputs and all six output receipts.

### 6.5 Implement executive rendering and silent video — ✅ local implementation
- Implemented trusted Slidev/TopoLoop components, JSON-only narrative, explicit scene readiness/reset/still frames, source/static ZIPs, PDF, executive Markdown and silent H264 MP4 with ffprobe validation.
- Local host and constrained UBI renders passed. Full six-scene reference: 119.966667-second silent H264 at 1280x720/30 fps; 226.673-second render, peak 2,046,562,304 bytes. PDF text, topology, execution and conclusions visually inspected; two Node boundary tests pass. Broader live fixture/resource acceptance remains open. Google TTS stays Phase 2.

### 6.6 Isolate cluster execution — ✅ restricted OCP render; failure acceptance open
- Published renderer digest `sha256:f65ec5e266f743ce2ace49f978db1c99e68d8430527c9d4710ee56a4bfdab76d` under `quay.io/aicatalyst/autopoc-executive-renderer`. Added Job/RBAC/launcher configuration; renderer has no workload token or RoleBinding.
- Constrained local test: arbitrary UID, read-only root, network disabled, 2 CPUs/3 GiB/4 GiB scratch; 68.539 seconds, peak 2,465,705,984 bytes for short diagnostic. No runtime dependency downloads.
- ✅ 28 October: published image completed six-scene rendering through its normal entrypoint under restricted-v2, UID1000880000, read-only root/no workload token, 2 CPUs/3 GiB/4 GiB scratch. Runtime178.895s; memory peak1,841,668,096 bytes; scratch46,609,764 bytes. Five output hashes verified after export; six-page PDF, silent H264120s1280x720/30fps verified. Forced OOM/disk/admission acceptance and worker-image rollout remain open.

### 6.7 Publish executive links and validate end to end — implementation ✅; live validation in progress
- Implemented independent output validation/publication, durable receipts and report-link revisions after blog completion. Partial failures retain valid presentation/PDF artifacts.
- Google service account is invalid. User authorized temporary personal OAuth; all six reference artifacts uploaded and downloaded for hash verification. Checkpoint complete; report links persisted in the local reference Git remote after completed-blog state. Personal credentials stay local; cluster Secret unchanged.
- Current verification: 366 supported tests passed, 83.48% coverage; pinned Ruff clean; Pyright zero errors; two Node tests passed. Astra's five implementation findings closed with scoped re-review.
- Remaining acceptance: unattended OCP publication and failure scenarios, model-service narrative review and main-worker build/rollout. OCP offline rendering now passes. New cluster outputs remain local because the temporary personal OAuth file was removed from /tmp; original verified Drive reference remains available. No original PoC test replay; no claim of production rollout.

### 6.8 PR-readiness corrections — ✅ 28 October 2026
- Fixed the timeout test's `/proc` check/read race with a bounded wait for child termination; it still fails if the child survives. Production timeout behavior is unchanged.
- Removed trailing whitespace from the two sample font-license copies without changing their text.
- Fresh verification: 366 supported tests passed, 83.48% coverage; focused renderer suite 11 passed; Ruff clean. Unrelated `opencode.json` remains excluded.
- Renewed OCP access. The repository shell sets a different kubeconfig from the default used by `oc login`; acceptance commands explicitly select the renewed `/home/aavraham/.kube/config`.
- ✅ Restricted OCP render/export passed. The first new attempt rejected ConfigMap symlinks; the passing harness copies input to a regular scratch file. Production path validation is unchanged. Updated AGENTS.md and prepared a reviewable PR description.

### 6.9 Publish a draft PR to the user's fork — ✅ 28 October 2026
- Pushed `codex/aipcc-33008-slidev-epic` to the `aavraham` remote, `aviavraham/autopoc`, at the user's request.
- Opened [draft PR #1](https://github.com/aviavraham/autopoc/pull/1) against that fork's `master`; GitHub reports it mergeable. The description records actual validation and remaining rollout/acceptance work.
- Attached the PR to this task. Unrelated `opencode.json` remains uncommitted and excluded. No merge or default-branch push was performed.

### 6.10 Review project state after the user's merge — ✅ 3 November 2026
- Confirmed the user's fork `master` points to merge commit `6b564e5` for PR #1. The current upstream `aicatalyst-team/autopoc` master is `3f266c7` and does not contain this feature.
- Read the merged implementation, workflow/configuration references, handoff and active plans. Phase 6 rollout/acceptance remains open: production service-account repair, unattended publication, forced resource/admission failures, model-service narrative review and main-worker build/rollout.
- Fresh scoped verification: 169 Python tests passed across artifacts, capture, evidence, executive tools, Drive and skill validation; all four Node renderer tests passed. This review did not run a new render, cluster acceptance or full coverage suite.
- Existing `opencode.json`, `.coverage` and `uv.lock` changes remain excluded. Historical draft-PR and implementation-pending wording above describes earlier milestones; this entry records the verified post-merge state.

### 6.11 Check upstream integration and CI — ✅ 3 November 2026
- Refetched upstream `master`, still `3f266c7`. The feature is proposed through open, non-draft [upstream PR #66](https://github.com/aicatalyst-team/autopoc/pull/66), from `aviavraham:master` at `6b564e5` to upstream `master`.
- GitHub reports no merge conflicts (`MERGEABLE`), but merging is blocked and approval is required (`REVIEW_REQUIRED`); there are no submitted reviews.
- [PR CI run 41645246344](https://github.com/aicatalyst-team/autopoc/actions/runs/41645246344): lint, renderer tests, typecheck, Python tests and worker image build passed. Security failed: pip-audit reports 10 findings across certifi, opentelemetry-api, pyasn1 and urllib3 (the certifi advisory appears twice).
- [Upstream master CI run 41590181862](https://github.com/aicatalyst-team/autopoc/actions/runs/41590181862) has the same audit findings; its other CI jobs passed. These dependency findings therefore also exist before the executive feature is merged. No dependency changes, PR comments, pushes or merges were made during this check.

## Phase 7: Upstream Security Remediation — ✅ Done

### 7.1 Fix and verify vulnerable dependency pins — ✅ 3 November 2026
- Reproduced PR #66's security failure locally: the pinned lock produced the same 10 reported findings across four transitive dependencies.
- Regenerated `requirements.lock` with pip-compile and SHA-256 hashes under Python 3.12, selectively updating certifi to 2026.10.23, opentelemetry-api to 1.45.2, pyasn1 to 0.6.5 and urllib3 to 2.8.0. All other package versions are unchanged; no new runtime dependencies were declared.
- Verified a fresh Python 3.12 environment: hash-checked installation succeeded, pip-audit reports no known vulnerabilities, pip check passed, 371 tests passed with 85.55% coverage, pinned Ruff passed, Pyright reported zero errors/warnings, and all four renderer tests passed.
- Prepared on `codex/fix-upstream-security`. Upstream PR #66 tracks the user's fork `master`; merging this fix into that branch requires user approval. The upstream PR's existing CI result remains failed until its source is updated and CI reruns.

### 7.2 Publish the reviewable security fix — ✅ 3 November 2026
- Pushed only `codex/fix-upstream-security` and opened [fork PR #2](https://github.com/aviavraham/autopoc/pull/2), targeting the fork's `master`. GitHub reports it mergeable with no conflicts; no fork CI checks are currently reported.
- Attached fork PR #2 and upstream PR #66 to this chat. Neither default branch was pushed or merged; applying the fix to upstream PR #66 remains pending user merge approval.

### 7.3 Confirm user merge and upstream security recovery — ✅ 3 November 2026
- The user merged fork PR #2 as `231fc31`; upstream PR #66 automatically adopted that source revision. Fresh GitHub inspection confirms all six checks passed: lint, renderer tests, typecheck, security, Python tests and image build. Upstream PR #66 itself remains open.

## Phase 8: Default Red Hat Presentation Branding — Implementation/local acceptance ✅; OCP rollout pending

### 8.1 Inspect references and define the branding phase — ✅ 3 November 2026
- Read the supplied 107-page standard template, inspected representative title/content/color pages visually, recorded its SHA-256 and checked official Red Hat typography, color and logo standards.
- User confirmed Red Hat branding must be the default for newly generated presentations, PDFs and videos. Proposed a red opening scene and light content theme, local fonts/corporate assets, branded TopoLoop status colors and consistent source/browser/PDF/video outputs.
- Added [the branding design](../../docs/superpowers/specs/2026-11-03-red-hat-presentation-branding-design.md), including factual-content preservation, six-scene timing, legacy input/recovery compatibility, packaging, visual QA and rollout acceptance. An independent builder check reported no important unanswered questions.
- Created `codex/red-hat-presentation-branding` from merged fork master `231fc31`. Unrelated local files remain excluded. No renderer implementation or deployment is claimed.

### 8.2 Save all required branding resources in the repository — ✅ 3 November 2026
- User explicitly required local repository copies of every needed branding component. Saved nine official WOFF2 font files (Display/Text/Mono, Regular/Medium/Bold), unmodified official corporate/hat SVGs, upstream font license/authorship notices and a per-file source/hash/size manifest under `renderer/assets/redhat/`.
- Fonts are pinned to RedHatOfficial/RedHatFont commit `6bb1048a6402b0076ea04f42951ec66263cd1437`. Saved the supplied 107-page PDF unchanged under `docs/branding/` and documented its provenance; it is a design reference, not a runtime background.
- Verified all 13 upstream-file hashes/sizes, WOFF2 headers and font families, self-contained SVG structure and both logo previews. The reference PDF matches its original size and SHA-256. No dependency or renderer-behavior changes were made; future source/site packaging must include required local assets and licenses.
- Updated the design to require all later-added artwork, fonts, components and styling to live in the repository, without runtime CDN or operator-local-file dependencies.

### 8.3 Approve the visual design and prepare implementation — ✅ 3 November 2026
- User explicitly approved the design and requested implementation. Added the ordered implementation plan with version/packaging, shared layouts and visual acceptance tasks; execution is in progress on the existing feature branch.

### 8.4 Implement branding and compatible packaging — ✅ 3 November 2026; acceptance in progress
- Bundle official assets/fonts with provenance, implement the shared slide shell and diagram palette, and bind template revision 2 through sealing, rendering and source/recovery packaging while preserving revision-1 recovery.

#### 8.4.1 Bind template revision and local source packaging — ✅ 3 November 2026
- New seals default to revision 2; revision-1 verification/recovery remains supported, with explicit legacy sealing for the original pinned image. The new wrapper rejects fresh v1 rendering and preserves matching complete legacy output reuse.
- Forwarded sealed versions to Node and source/recovery metadata. Added allowlisted local assets/public files and renderer helpers to editable archives.
- Watched the new boundary/archive tests fail, then pass: 35 affected Python tests passed. Layout, Node validation and visual acceptance remain in progress.

#### 8.4.2 Implement the shared brand shell and offline validation — ✅ 3 November 2026
- Implemented six branded scenes using local Display/Text/Mono fonts, a red opening, light content, unmodified corporate/hat SVGs, source references and readable footer bands. Added a renderer-owned light TopoLoop palette with orange failures and green successes; vendored source is unchanged.
- Verified asset inventory/hashes before deck preparation, copied assets/notices to source and browser trees, awaited fonts/logos, and added scene overflow checks before PDF/video capture. Updated the renderer image definition to package all helpers and local assets.
- Seven Node and 25 Python input/render tests pass, including failing-first asset/version cases and a regression preventing publication of a static deck after content validation fails. Initial browser preflight and six-page PDF generation passed; full video/image/cluster acceptance follows in 8.5.

### 8.5 Verify and roll out branded artifacts — Local acceptance ✅; OCP rollout pending
- Verify representative successful/failed fixtures, every PDF page and video frames, offline assets, meaningful compatibility/overflow tests, the supported checks and a restricted OpenShift render before updating deployment configuration.

#### 8.5.1 Resolve review findings and verify local behavior — ✅ 3 November 2026
- Independent code review found one important diagram-text clipping gap, with no critical/minor findings. Added failing browser/Node regressions, then fixed graph-region bounds and deterministic checks of PDF stills, act transitions and original log events. Expanded the scenario terminal layout without dropping evidence text.
- All 379 Python tests pass with 85.62% coverage; eight Node tests pass. Actual browser checks cover six scenes, oversized claims/titles/counters/diagram labels, missing fonts/logos and zero external asset requests. Archived Omnigent, synthetic failure/incomplete and twelve-node fixtures rendered locally; all six Omnigent PDF pages were inspected.
- Full two-minute rendering in the rebuilt constrained image remains in progress. OCP acceptance/publication and deployment configuration changes are not claimed.

#### 8.5.2 Validate constrained UBI rendering and source recovery — ✅ 3 November 2026
- Built reviewed image `d8e792a29858`, local digest `sha256:cf628a4323262e6ee152e7b9825f5705c8b8cac76cf9e34d5143f12eb9bc53ac`. Normal-entrypoint render passed with read-only root, no networking, UID28128/group0, 2 CPUs, 3 GiB memory and 4 GiB scratch.
- Original reviewed Omnigent evidence produced a six-page PDF, silent120.000s H264 MP4 at1280x720/30fps, source/browser ZIPs and Markdown. Runtime213.81s; peak memory2,504,695,808 bytes; scratch45,614,563 bytes. Status is `generated_unpublished`, not deployed/published.
- Verified all output hashes/sizes, all13 original asset hashes in both archives, embedded PDF fonts and source preparation after extraction. Inspected all six final PDF pages and the late login video frame that previously clipped its duration log.
- Local ignored outputs: `presentations/omnigent-2026-10-20/output/redhat-branding-2026-11-03/`. No PoC replay. Registry publication, restricted OCP acceptance and coordinated worker/renderer rollout remain pending.

#### 8.5.3 Publish the reviewable feature branch — ✅ 3 November 2026
- Pushed `codex/red-hat-presentation-branding`, opened [draft fork PR #3](https://github.com/aviavraham/autopoc/pull/3) targeting fork master and attached it to this chat. GitHub reports no conflicts; no fork CI checks are reported.
- Updated renderer/configuration/workflow docs with local assets, v2/v1 compatibility, overflow handling and rollout requirements. No default branch was merged/pushed; deployed configuration is unchanged.


## Phase 9: Kokoro Voice-over — Engineering implementation/acceptance ✅; rollout gates pending

## Progress

| Phase | Status | Notes |
|-------|--------|-------|
| Kokoro local audition | ✅ Done | Two CPU-generated English samples; no pipeline integration |
| Voice selection | ✅ Done | User selected Heart (`af_heart`) |
| Design and implementation planning | ✅ Done | User-approved evidence-backed story, variable timing and eight implementation tasks |
| Engineering implementation and acceptance | ✅ Done | Eight tasks; real local and restricted-v2 OCP media acceptance; independent review fixes verified |
| External refinement review | ✅ Done | 9 November: seven findings checked against implementation |
| Apply accepted refinements | ✅ Done | 9 November: four implemented with tests, one rejected on evidence, two documented; offline listening still pending |
| Omit PoC dates from voice-over | ✅ Done | 9 November: author/reviewer rules updated; existing sealed demo unchanged |
| Fresh OpenShell end-to-end branch run | ✅ Done | 9 November: deployed, original 5/5 pass, corrected report persisted, final 3m28s Kokoro video and five artifacts retrieved/verified; Drive/listening gates remain |
| Regenerate OpenShell with 3D views | ✅ Done | Two TopoLoop scenes; reviewed 3m28s video, animated browser deck/PDF/source retrieved and verified, original tests unchanged |
| Simplify future voice-over English | ✅ Done | Author/reviewer guidance and synthetic example updated; STE principles without a restricted vocabulary; existing media retained |
| Presentation feedback design and planning | ✅ Done | 10 November: storyboard direction approved; generic repository-independent design and seven-task plan saved; builder check complete; product implementation pending |
| Restore cluster access | ✅ Done | 10 November: authenticated; existing OpenShell namespace active; Job-create permission verified; no workloads changed |
| Controlled production rollout | Pending | Drive invalid_grant, human listening and explicit merge/live configuration approval |

### 9.1 Generate and verify a local Kokoro audition — ✅ 8 November 2026
- Google TTS access is blocked on the configured work project: billing is enabled, the API is not enabled and the user lacks `serviceusage.services.use`. No cloud settings were changed.
- Ran a throwaway Python 3.12 environment under `/tmp/autopoc/kokoro-audition-20261108/` with Kokoro 0.9.4, Misaki 0.9.4, CPU-only Torch 2.8.0 and the English spaCy model. No application dependencies or renderer behavior changed.
- Generated the same explicitly labeled executive-narration sample with American English `af_heart` and `am_fenrir`, speed 0.95, two Torch CPU threads. Text includes Red Hat OpenShift, Kubernetes and Quay; it claims no PoC result.
- Heart: 22.150s audio / 14.153s generation. Fenrir: 20.325s audio / 14.186s generation. Model initialization with cached weights took 1.721s; generation timing includes voice loading and file writing, not initial installation/model download. These are local observations, not OCP resource acceptance.
- Verified finite, non-silent waveforms below full scale, 24kHz mono PCM WAV files, MP3 conversion and complete MP3 decoding with ffmpeg/ffprobe. Listening quality and pronunciation remain for user review.
- Saved WAV/MP3 samples, script, package inventory and JSON measurements in the chat's local `kokoro-audition/` artifact directory. WAV SHA-256: Heart `7f5690f255519837485249f40971e51dbe1965ce64218c826f277bde54bb3f22`; Fenrir `c0116cc759402c4c88fec518de63df55aa8b26f0bdbb311b12be1e389ad7e8f9`.
- Corrected spaCy's automatic installer choosing the repository environment: installed its English model explicitly in the trial environment and removed the single newly added model package from the repository environment. Repository dependency declarations/locks are unchanged.
- This is an audition only. No PoC tests were replayed; narration integration, offline image packaging, scene synchronization, resource limits and publication remain unimplemented/unvalidated. Historical Google TTS Phase 2 preference is not treated as a finalized Kokoro adoption decision.


### 9.2 Define the evidence-backed story and prepare implementation — ✅ 8 November 2026
- User selected Heart (`af_heart`) and confirmed video length may exceed two minutes according to PoC scope/complexity. Required topics: objective, testing, setup and results; story also includes limitations/recommendations. Report, plans, recorded setup, original results, logs and traces may supply evidence. Include troubleshooting only when it contributes to explaining the outcome.
- Saved [the design](../../docs/superpowers/specs/2026-11-08-kokoro-narrated-video-design.md) and [eight-task implementation plan](../../docs/superpowers/plans/2026-11-08-kokoro-narrated-video.md). Existing fixed-six-scene/180s, 600s process deadline and supplemental-evidence exclusions are explicitly addressed.
- Plan preserves original PoC evidence, independently reviews visible/spoken claims, packages speech offline only in the renderer, measures audio for timing and retains legacy recovery/valid partial artifacts. Model assets stay outside Git; dependency declarations/locks remain renderer-only.
- Independent builder check reported “Nothing important left.” Self-review checked file paths, interfaces, source/selector checks, version compatibility, failure tests and task coverage. Operational slide/time/resource limits are explicitly builder recommendations, not extra user requirements.
- Planning complete only: implementation, live restricted OCP acceptance and publication remain pending. Existing Drive credential problems are independent of Google TTS. Review the plan and choose execution approach before implementation.

### 9.3 Implementation and engineering acceptance — ✅ 8 November 2026; rollout gates pending

| Task | Status |
|------|--------|
| Retain sanitized supplemental logs/traces/setup evidence | ✅ Done — 67 scoped tests; full suite 401 passed |
| Seal source-linked storyboards and reviewed narration | ✅ Done — 53 scoped tests; legacy inputs retained |
| Update configured-model author/reviewer workflow and ADR | ✅ Done — three configured-model acceptance reviews |
| Package offline Heart assets and generate measured audio | ✅ Done — hash-locked CPU image and constrained offline inference |
| Render variable executive slide chapters | ✅ Done — 6/8/12-slide browser/PDF checks and graph validation |
| Encode narration-driven scenes and retain valid partial outputs | ✅ Done — measured PCM, one AAC encode and partial-output tests |
| Persist narrated Job policy and recover/publish long renders | ✅ Done — saved policy, bounded Jobs, late/partial recovery |
| Complete local/cluster engineering acceptance and prepare rollout | ✅ Done — exact-frame 5m27 stress, reviewed-image OCP success; Drive/listening/activation gates remain pending |


### 9.4 Check OCP access and available GPU scheduling capacity — ✅ 8 November 2026
- Renewed the user's existing OCP login and performed read-only capacity/quota/authorization checks. Authentication data is not stored in the repository.
- Ready, schedulable nodes advertise two NVIDIA L40S GPUs and eight NVIDIA A100-SXM4-80GB GPUs, with sharing disabled. Active pod requests reserve one L40S and six A100 devices: one L40S and two A100 devices were unrequested at this snapshot. This is scheduler-request availability, not GPU utilization, ownership or a reservation for AutoPoC.
- In `autopoc-test`, ResourceQuota, LimitRange and applied ClusterResourceQuota lists were empty. The user can create Jobs and pods there. No workload or GPU benchmark was launched, and actual admission/scheduling/inference remain unvalidated.
- The current narration design remains CPU-first inside the existing renderer Job. GPU acceleration would need a separately measured GPU-enabled image/profile; availability alone does not justify changing the renderer-only CPU lock or claiming GPU acceptance.


#### 9.3.1 Retain sanitized supplemental evidence — ✅ 8 November 2026
- Added schema-2 optional supplemental collection and strict verification, retaining schema-1 behavior and exact original attempt/result totals. Inputs are run-bound, root-confined, hash-checked, size-bounded and sanitized; public descriptors exclude private paths/original hashes.
- Selected deployment exports omit Secret data/environment/annotations/inline TLS keys; trace excerpts retain captured spans/relations/timings without headers/bodies/attributes. Unknown runs/executions/scenarios, undeclared archive members and unsafe sources are rejected. Phase-time staging and CLI usage are documented.
- RED: 19 new tests failed for missing feature support; two further regressions caught private provenance and TLS-key leakage before correction. GREEN: 67 scoped tests and 401 supported Python tests passed; Ruff and scoped Pyright clean. No original PoC replay, new cluster workload or publication occurred.


#### 9.3.2 Seal reviewed storyboards and narration — ✅ 8 November 2026
- Added narrative/input schema 2 and template 3 with source-linked ledger claims, ordered variable slides, title/bullet/graph/narration references, explicit gaps/conflicts and exact original result totals. Validates actual line ranges and RFC 6901 selectors against sanitized evidence bytes.
- Review binds the exact script, evidence and scene policy; measured-audio timing is deferred until generation. Silent narrative-1 still seals as template 2 by default; explicit legacy templates remain verifiable. Kept revision-2 rendering support while introducing latest revision 3.
- RED: four positive narrated cases failed before schema support; an additional regression demonstrated empty-object selectors were accepted, then corrected. GREEN: 53 story/input/cluster tests passed; Ruff and scoped Pyright checked. Full suite and task ledger capture run with the task completion commit.


#### 9.3.3 Define and validate narrative authoring/review — ✅ 8 November 2026
- Added the opt-in narration reference, complete synthetic schema example and ADR 0014. Guidance covers fact ledger → proportional outline → visible/spoken text → independent review, source selectors, exact counts, explicit conflicts/gaps and conditional troubleshooting.
- Behavioral control with the existing configured Qwen model followed the old schema-1/silent/fixed-duration instructions; updated guidance produced schema 2, measured timing, Heart and relevant-fix selection. Three synthetic simple/complex/failed examples pass contract validation and actual same-model semantic review; receipts bind exact draft/evidence/scenes bytes and are explicitly acceptance-only.
- Review caught architecture overclaims and a conflict needing visible explanation; corrected both. Clarified claim-ID-to-visible-text resolution and separated objective factual blockers from style suggestions/tool-count guesses. Retained actual failed-review diagnostics privately instead of fabricating approvals.
- Configured endpoint is cluster-internal: acceptance used a temporary port-forward and existing worker model credentials in memory, not a new provider or stored secret. OpenCode CLI's unbounded generation did not yield a usable completion; bounded same-model API checks did. This does not assert end-to-end unattended worker acceptance.
- GREEN: 93 story/skill tests, full supported suite 434 passed, and CI-pinned Ruff 0.15.11 passed. Production narration/rendering remain subsequent tasks.


#### 9.3.4 Package offline Heart speech and measured timelines — ✅ 8 November 2026
- Added renderer-only dependency declarations/generated hash lock, pinned model/config/Heart SHA-256 inventory, build-only verified asset preparation, package/model license provenance and lazy CPU inference. The main worker imports without Torch/Kokoro; no speech dependencies entered the root lock.
- Exact reviewed sentence PCM samples determine offsets and scene timing, with lead/tail gaps and upward 30fps frame quantization. Source audio/transcript/timeline include script/model identities; wrong/missing/symlink assets, invalid audio, output overwrites and duration overflows fail explicitly.
- Upgraded audition Torch 2.8.0+cpu to 2.15.0+cpu after normalized advisory lookup exposed nine old-version findings. All 94 exact normalized software pins audit clean; the direct English model wheel remains outside PyPI advisory coverage and is upstream/hash-verified. CI audits normalized CPU Torch rather than silently skipping it.
- Replaced the unavailable John Van Sickle archive (wrong checksum/HTML response) with public digest-pinned static FFmpeg 7.0.2 plus exact executable hashes/GPL/version notices. Did not bypass checksum checks or depend on a private historical image in CI.
- RED: 16 missing-feature speech tests and the successful-cache preparer case failed before implementation. GREEN: 18 speech tests, 452 supported Python tests, Ruff/Pyright and hash installation passed. Generated six real scenes with networking disabled and empty caches using the locked environment.
- Built local UBI image `1aad897c6dea`. Actual offline image smoke passed with read-only root, UID28128/group0, 2 CPUs/4Gi limit, empty scratch caches: 5.2s audio, 13.638s elapsed, peak process RSS1,411,387,392 bytes, cgroup peak2,426,052,608 bytes. This is local speech acceptance, not full video/OCP/publication acceptance.

#### 9.3.5 Render variable executive chapters — ✅ 8 November 2026
- Added template-3 ordered slide rendering, source-linked visible claims, exact counters, per-slide graphs, numbered chapters, safe speaker notes and transcript; retained the original template-2 path.
- Actual browser preflight checked every scene and representative graph states. Six-, eight- and twelve-slide decks and failed/incomplete examples rendered successfully; inspected all 42 PDF pages, including the corrected graph page. Missing fonts/logos, oversized titles/claims/results/diagram labels and overlapping node labels are refused.
- Real TopoLoop fixture exposed an incorrect object-only edge requirement in Python/Node; corrected it to actual string pairs with RED→GREEN coverage. Source assets/helpers/transcript remain in recovery allowlists. Image runtime copies follow dependency layers to avoid repeated model downloads during code iteration.
- GREEN: 24 Node tests, 453 supported Python tests, Ruff and scoped Pyright. Local deck/PDF acceptance only; measured narrated encoding follows in Task 6.

#### 9.3.6 Encode measured narration and preserve partial output — ✅ 8 November 2026
- Added sequential prepare → speech → record processes under one format-specific deadline (silent 600s, narrated 3000s). Chromium exits before speech, and speech exits before the recording browser; subprocess failures/timeouts propagate after killing descendants.
- Hash-bound timeline checks validate reviewed input identity, ordered IDs, sentence/scene PCM sample counts, offsets, frame counts and duration policy. Record the prepared variable deck without regenerating content; scale graphs to each measured interval. No silent fallback after speech failure.
- Pad and concatenate PCM before one AAC encode, avoiding per-scene AAC priming; require scene/final duration agreement within 0.25s, H.264 1280×720/30fps/yuv420p plus AAC, and complete decode. Real FFmpeg tone/silence checks passed around the first scene cut.
- Recovery source includes exact transcript, sentence/scene WAVs, timeline, speech identity/notices and renderer-only locks, excluding weights/private diagnostics. Keep five public artifact kinds, source/video caps 512MiB/1GiB for template 3. Summary supports variable chapters and retains valid deck/PDF/source when speech/video fails.
- GREEN: 457 supported Python tests; 35 Node tests (one optional integration skipped in default run), separate 11/11 actual FFmpeg integration tests; Ruff/scoped Pyright. Complete constrained narrated video/OCP acceptance follows in Task 8.

#### 9.3.7 Preserve narrated Job policy and publication recovery — ✅ 8 November 2026
- Derive/persist immutable render policy from verified sealed format before upload/dispatch. Narrated profile keeps 3000s rendering, 3120s Job deadline, tokenless/read-only isolation and provisional 2 CPU/4Gi/8Gi scratch/10Gi ephemeral bounds. Legacy descriptors without policy retain their bytes and defaults.
- Pass saved timeout to remote CLI and reject CLI/sealed/descriptor/launch conflicts. Keep independent 0–600s worker wait, stable Job/upload IDs, three-attempt retry bound and unchanged original input identity. Existing Job deadline/resources must match saved intent.
- Select source/video download caps by saved format/kind, verify exact published hash/size and enforce caps on cached downloads too. Failed narration publishes usable partial artifacts without a successful video link; reconciliation preserves completed blog/phase state after worker deletion.
- Added missing optional narration Secret forwarding in worker Job/CronJob/launcher; documented compatible-image operator precondition, build-time model copies and independent Drive authorization. No live worker/Secret configuration changed.
- RED→GREEN policy/profile/CLI/wiring and forged-size cases; GREEN: 114 affected tests, 478 supported Python tests, full Ruff/Pyright, launcher syntax check. Actual cluster/media/publication acceptance follows in Task 8.

#### 9.3.8.1 Verify browser capture timing and offline failure recovery — ✅ 8 November 2026
- Real constrained video exposed wall-clock trimming that shortened a 6s scene to 5.733s. Crop using recorded media duration; retained a genuine variable-frame browser recording to reproduce fractional frame loss (181 expected versus 180 actual). Normalize/pad video to exactly reviewed frame counts; require exact scene/final frame totals in addition to 0.25s duration bounds.
- 14/14 real FFmpeg tests passed, including AAC cut tones, delayed capture and fractional scene frames. Supported suite now 480 passed at 86.20% coverage; Ruff/Pyright clean. Runtime audio helper SHA matches the published acceptance2 image; three final local cases and restricted-v2 OCP rerun are active.
- Earlier complete local and OCP Omnigent renders passed the original duration bounds, and source/timeline/audio/full decoding were verified. Disk-full,4GiB child OOM and forced termination retained valid partial artifacts. Drive refresh still fails invalid_grant; human listening remains a separate rollout gate.

#### 9.3.8.2 Resolve independent whole-branch review findings — ✅ 8 November 2026
- One fresh read-only GPT-6 Astra reviewer found no Critical findings, two Important defects and no Minors. Fixed both in one regression-driven pass: graph-first/all-graph results always show structured totals, and a PDF-only failure no longer blocks narrated video when the deck remains validated. Content/preparation failures still stop later stages.
- Actual browser regressions failed with zero result counter panels before the fix; both pass with readable counters and diagrams after the fix. PDF-only stage regression failed with only prepare called before correction; now speech/record complete while PDF stays failed. Full suite 482 passed at 86.24% coverage, Ruff/Pyright clean; CI runs the actual browser cases in the trusted offline image.
- Final acceptance documents distinguish image revisions and operational rollout gates. No second reviewer or unrequested minor polish pass was added.

#### 9.3.8 Complete engineering acceptance and prepare controlled rollout — ✅ 8 November 2026
- Published the reviewed renderer digest2910f7cc410050017326bc79f4ac307c960d3003521e335f1468ccfeecd90fb3. Recorded exact image/model/input/output hashes in docs/validation/kokoro-narration-2026-11-08.json; code/asset hashes match the checkout. CPU Heart stays packaged offline only in the renderer.
- Actual constrained core cases: failed8slides50.367s; archived Omnigent8slides159.367s; synthetic12slides327.2s. Verified exact video frame totals, H.264/AAC, full decoding and extracted transcript/PCM/timeline identities; inspected28PDF pages and84cut/midpoint frames. The final image additionally passed actual browser review regressions,14FFmpeg tests and full Omnigent local/OCP reruns.
- Reviewed-image OCP Job completed restricted-v2, nonroot, read-only, tokenless and deny-egress at 2 CPU/4Gi;352.369s elapsed,2,103,570,432 peak bytes. Local reviewed-image Omnigent373.815s/3,417,628,672 peak bytes. Long stress853.337s/4,095,840,256 peak bytes; retain provisional sizing and explicit measurement limits. No original PoC replay or GPU request.
- Missing assets, forced termination, 75s global timeout, 4GiB child OOM and dedicated disk-full injections preserve valid partial outputs without narrated-video success. Admission/upload/restart/late-state cases remain deterministic tests, not falsely reported live Drive publication.
- GREEN:482 supported Python tests at 86.24%, Ruff/Pyright,35 default Node checks plus14actual FFmpeg and2actual browser checks. One fresh reviewer; two Important findings fixed in one RED→GREEN pass; no Critical or deferred Minor findings.
- PR https://github.com/aviavraham/autopoc/pull/4 is stacked on the approved planning branch. Temporary cluster test resources and model port-forward were removed after verified retrieval. All eight engineering tasks are closed; worktree retained for review. Drive refresh still fails invalid_grant; durable publication, human listening/pronunciation and explicit merge/live-worker approval remain pending. No production rollout is claimed.

### 9.5 Review external implementation refinements — ✅ 9 November 2026

Review completed against the current checkout and recorded acceptance, not only
the original plan. This section records dispositions; it does not claim the
proposed follow-up code or new acceptance is complete.

1. **Pronunciation control — proposed improvement.** The real Heart adapter sends
   reviewed sentences directly to Kokoro; there is no project lexicon. Misaki's
   upstream README documents inline phoneme overrides. Add a small versioned
   synthesis-only lexicon, preserving visible text/transcript exactly, and bind
   its hash into the reviewed speech identity. Changing pronunciation must not
   silently reuse an old speech identity. Validate short technical-term samples
   before full renders; human listening is still required. No actual incorrect
   pronunciation of OpenShift, Kubernetes or Quay is established by this review.
2. **Sentence captions — proposed improvement.** Measured sentence offsets already
   exist. Caption times must add scene start and the 0.35s lead-in to those
   offsets. Retain WebVTT in the source ZIP and encode an English mov_text track
   in the existing MP4, preserving the five public artifact kinds. This needs
   escaping, timing/readability and player checks, source recovery support and
   an update to the current exact-two-stream media validator. Word-aligned
   subtitles remain outside scope; this is an extension, not an existing promise.
3. **Job deadline — accept rationale; change proposed.** Current defaults really
   are 3000s process / 3120s Job. Kubernetes measures activeDeadlineSeconds from
   Job startTime, so pending/pull time erodes rendering time. Recommend a 3600s
   default for new narrated policy. Preserve existing sealed/checkpoint policy
   bytes and Job intent; do not silently reinterpret previous 3120s attempts.
   A pull longer than 120s reduces the full process budget; it does not itself
   kill a 3120s Job before rendering starts.
4. **Early duration estimate — accept need with qualification; proposed.** The
   structural maxima permit scripts likely to exceed the measured 900s guard.
   Add a cheap seal-time estimate including scene padding and sentence gaps,
   with actionable diagnostics. A words-per-minute assumption is not proof of
   actual duration: document any conservative rejection policy and its false
   rejection risk. Retain measured PCM limits as authoritative; no clipping or
   speed-up, and no change to the user's complexity-driven duration preference.
5. **Coverage collision — not present in current acceptance.** The recorded full
   suite passed 482 tests at 86.24%, above the unchanged 80% gate. CI also builds
   the renderer and directly initializes _HeartEngine/synthesizes offline audio.
   Those image checks are separate from unit coverage. No no-cover pragma or
   lowered gate is justified just to solve a hypothetical future collision.
6. **Late reconciliation — accept operational emphasis; proposed follow-up.**
   Reviewed-image Omnigent took 352.369s on OCP and 373.815s locally; the long
   stress took 853.337s, all beyond the default 300s worker wait. Durable late
   completion is tested, but reconciliation currently requires dispatch,
   startup/resume or an explicit command; an always-running collector is not
   established. Treat this as a normal narrated flow and specify a reliable
   collection trigger before unattended rollout. Do not describe late report
   link updates as automatic without that trigger.
7. **Asset origin attestation — partial agreement; proposed documentation.**
   prepare-kokoro-assets.py reads the committed manifest, checks revision-scoped
   URLs and verifies exact size/SHA-256 before exposing files. It does not
   generate expected hashes from a first download. The existing README says
   the pins identify the auditioned bytes, but an explicit dated account of
   how initial pins were checked against upstream would improve provenance.
   Record only verification actually performed; do not invent a historical
   human sign-off or imply matching upstream establishes model safety.

Primary technical references checked: [Misaki pronunciation overrides](https://github.com/hexgrad/misaki/blob/main/README.md),
[Kubernetes Job deadline semantics](https://kubernetes.io/docs/reference/kubernetes-api/batch/job-v1/).
Verification for this review: source/CI/recorded-acceptance inspection and
documentation diff checks only; no new render, PoC replay or rollout occurred.

### 9.6 Exclude the PoC date from spoken narration — ✅ 9 November 2026

- User requested that the voice-over not mention the PoC date. Confirmed the
  archived Omnigent source transcript says "This narration describes the archived
  October twentieth run."
- Updated narrated authoring guidance, independent-review rejection criteria and
  the design to omit the run's execution date/timestamp in digits or words. Use
  "the archived run" when relevant, retaining historical evidence distinctions
  and the original provenance dates.
- Scope: content policy only. Existing sealed inputs, review receipts, transcript
  and generated MP4 are unchanged; revising that demo requires a fresh content
  review/seal/render, not an unreviewed speech-time text substitution.
- Verified the actual ZIP transcript and reviewed the documentation diff. No
  runtime code changed and no new rendering or PoC execution is claimed.

### 9.7 Fresh OpenShell end-to-end branch run — ✅ 9 November 2026; optional publication/listening gates remain

#### 9.7.1 Verify access and prepare an isolated branch-based run — ✅

- User requested a new full OpenShell deployment, original validation, report and
  narrated video from the local AutoPoC branch. Current OCP login and Job/project
  creation permissions are verified. Existing deployments are retained.
- Built/pushed worker from engine commit `35f79ec`; image digest
  `sha256:220d1bceb1a37e642830d76efbeb50327eb9b872d9e5f27079852c5de9589326`.
  Six code/config/guidance hashes match this checkout, including date-free speech
  guidance. No pending review refinements are represented as implemented.
- New run `90b344e86812455caf110467384bbbea`; source NVIDIA/OpenShell revision
  `f4a6137513b777c9b362be54baf388f7d45398aa`, new source branch
  `codex/openshell-kokoro-20261109-90b344e8` in the existing protected fork.
  Operator reverified main protection and scoped worker GitHub access.
- Worker Job `autopoc-openshell-kokoro-90b344e8-r1` in `autopoc-test`; new workspace
  PVC and application namespace `poc-openshell-kokoro-20261109`. Runtime and
  validation grants follow the prior restricted setup, scoped to the new run.
  Current configured Qwen model is retained; no shared Secret/CronJob changes.
- Rechecked Drive refresh: `RefreshError` persists. Plan is local sealed inputs
  on the run PVC, trusted pinned Kokoro renderer on OCP and direct verified
  retrieval. This tests actual generation, not Drive publication or automatic
  production dispatch. Reference Dockerfiles/storage lessons are disclosed setup
  assistance, never new-run results. All validation/evidence must be fresh.
- Initial launch referenced the local image manifest digest, which differs from
  the registry-published manifest. It failed with `manifest unknown` before init
  or PoC execution. Retained admission events, obtained the actual push digest,
  and replaced only this pending worker Job using the same fresh workspace/run.
  This is a disclosed launch correction, not a PoC-test retry or result.

#### 9.7.2 Fresh OpenShell intake — ✅ 9 November 2026

- Worker state records intake completed for the pinned source and this new run;
  gateway, supervisor and sandbox sources/chart/SDK were inspected. Reference
  setup provenance is staged separately from new validation results.
- Evaluation is next. No build/deployment/test/report/video success is claimed.

#### 9.7.3 Evaluate OpenShell — ✅ 9 November 2026

- Fresh-run evaluation is completed and staged; worker is publishing its initial
  evaluation artifact. This is an assessment, not deployment/test acceptance.

#### 9.7.4 Adopt the protected fork and isolated source branch — ✅ 9 November 2026

- Worker verified the pinned source branch, remote and operator protection
  attestation, then recorded fork adoption completed without default-branch writes.

#### 9.7.5 Author and publish the fresh PoC plan — ✅ 9 November 2026

- State records plan completed; immutable plan publication succeeded. Five
  scenarios: gateway-health, gateway-metrics, sandbox-exec,
  sandbox-node-placement and network-denial. These are planned checks, not results.
- Containerization follows using three fresh source builds and disclosed
  reference Dockerfiles. Runtime deployment/testing have not yet succeeded.

#### 9.7.6 Prepare fresh UBI container builds — ✅ 9 November 2026

- Three component Dockerfiles were checked against the pinned source, committed
  and pushed to this run's source branch. Reference Dockerfile provenance is
  retained. State records containerization complete; build access is being checked.
- These are build definitions, not successful images or runtime validation.

#### 9.7.7 Build the three new runtime images — ✅ 9 November 2026

##### 9.7.7.1 Build and publish the sandbox image — ✅ 9 November 2026

- OpenShift build `openshell-kokoro-90b344e8-sandbox-1` is Complete and published
  the unique `kokoro-90b344e8` sandbox tag. Its build receipt is retained privately.
  Gateway/supervisor remain Running; no deployment/test success is claimed.

##### 9.7.7.2 Build and publish the supervisor image — ✅ 9 November 2026

- OpenShift build `openshell-kokoro-90b344e8-supervisor-1` is Complete and
  published the unique supervisor tag. Gateway remains Running with active native
  compiler processes; the sandbox/supervisor images are retained without rebuild.

##### 9.7.7.3 Build and publish the full gateway/prover image — ✅ 9 November 2026

- OpenShift build `openshell-kokoro-90b344e8-gateway-1` is Complete/published.
  All three first component builds succeeded, preserving the full prover and
  unique run-specific tags. Actual build receipts retain digests/timestamps.
- Worker subsequently recorded build completed with zero build retries after
  digest verification. Deployment preparation is underway; no runtime pass assumed.

#### 9.7.8 Verify the offline renderer on the target node — ✅ 9 November 2026

- Temporary tokenless/read-only renderer check Job succeeded on the intended OCP
  node with deny-egress policy applied. It verified all packaged Heart asset
  sizes/hashes and exact manifest identity `cc53829e...f00c24` without inference.
- Retained receipt/log and removed the check Job. The renderer image is now
  cached on that node; subsequent rendering is warm-cache acceptance, not a new
  cold-pull deadline or human-listening claim. No PoC tests were executed here.

#### 9.7.9 Install OpenShell and observe initial workload readiness — ✅ 9 November 2026

- Helm install returned success in the isolated application namespace. Gateway
  StatefulSet and supervisor Deployment each report one ready replica; both
  application pods are Running/ready under restricted-v2.
- Actual running gateway/supervisor image IDs match their new build receipts.
  Gateway is on the configured worker-2 node. Retained an operator observation
  privately; it does not replace original validation or worker evidence captures.
- Worker deploy/apply checkpoints were still pending at this observation;
  persistence and original five-case validation remain outstanding. No test pass
  or completed pipeline/report/video is inferred from pod readiness.

#### 9.7.10 Complete deployment/apply checkpoints — ✅ 9 November 2026

- Worker state now records both deploy/apply completed with zero deploy retries.
  It retained readiness observations and is preparing captured original execution.
- Pod readiness/readiness probes are not counted as the planned five-case
  validation. Validation, report, conditional blog and narrated output remain open.

#### 9.7.11 Execute the original five-case validation — ✅ 9 November 2026

- Worker state records poc_execute/capture completed and test exit code 0.
  One captured execution `af1836af24fc49a38c665ed61bfa76da` contains five passing
  scenarios: gateway-health, gateway-metrics, sandbox-exec,
  sandbox-node-placement and network-denial. No failed/error/skip/incomplete
  planned scenarios are reported. Original attempt index is retained.
- Reviewed the actual generated script. Network-denial checks worker TCP access
  to sandbox SSH port 2222 against a reachable gateway port 9090 control; SDK
  execution also succeeded. This is a limited ingress-path observation, not proof
  of all egress policy, application mediation, filesystem isolation or production
  security. Reports/narration must retain that scope.
- Exploratory setup probes preceded the canonical captured suite and were cleaned
  up; they are not extra passing planned scenarios. No tests need replay for media.

#### 9.7.12 Finalize bounded report/narration claims — ✅ 9 November 2026

- Operator review found draft overclaims: the two-target ingress observation
  described as policy proof, confirmed isolation, fully reproducible evidence,
  unqualified zero gaps and an unsupported specific external-database HA action.
  These exceed the five recorded assertions. Narrow the report AND narrative,
  retain exact counts, distinguish UBI core/bootstrap images from Ubuntu workload,
  and require a fresh actual configured-model review before sealing/rendering.
- Paused only the original content worker after validation. Resume Job
  `autopoc-openshell-kokoro-90b344e8-r2` reuses the same workspace/run, existing
  application and original captures. Its init verifies original script/index
  hashes and all five outcomes, archives prior draft/review files, and records
  operator assistance. No core phase/counter reset or new test execution is allowed.
- The content Job budget is bounded within the remaining original four-hour run
  budget. Existing raw model verdict found classification blockers and noted
  reproducibility/coverage wording; it is retained unchanged, not edited into an
  approval. Date-free speech and exact new review/evidence hashes remain required.

##### 9.7.12.1 Generate and inspect the corrected canonical report — ✅ 9 November 2026

- Worker report status is completed. Operator inspected the revised canonical
  text: five original outcomes retained, limited in-cluster TCP ingress contrast
  clearly described, no blanket isolation/reproducibility/zero-gap assurance,
  UBI core/bootstrap versus Ubuntu workload images distinguished, future
  HA/persistence/auth/load/GPU work qualified rather than asserted as supported.
- Original index/payload/script hashes remain the authority. This closes local
  report generation only; immutable final publication, narration review/sealing
  and the conditional blog remain to be verified.

##### 9.7.12.2 Review the complete evidence corpus and seal the scoped content — ✅ 9 November 2026

- In addition to the worker's genuine content review, an independent configured
  Qwen request included every one of the twelve verified bundle members and the
  original audited script. Actual complete response approved with zero blockers;
  exact narrative/scenes/evidence hashes matched unchanged files. Retained raw
  request/response/verdict privately; no prior verdict was edited into approval.
- Sealed this approval as independent input revision `3731b138...d9b833` using
  the tested renderer digest. All 78 copied worker code/config/data files were
  additionally checked against base commit 35f79ec with no mismatches.

##### 9.7.12.3 Validate compact visible copy, re-review and seal layout-v4 — ✅ 9 November 2026

- All six compact slides passed actual browser/PDF preflight and were visually
  inspected as 1280x720 page renders. Spoken sentences are unchanged; visible
  titles/claims fit without weakening layout checks or shrinking fonts.
- Fresh independent Qwen review included all twelve bundle members and the
  original script; actual complete response approved with zero blockers and
  unchanged reviewed input hashes. Sealed new input `3cc8dffa...19d07bd4`,
  narrative `2c46538a...52f4ef`, in a separate immutable layout-v4 revision.

#### 9.7.13 Render and inspect narrated media — ✅ 9 November 2026

- First actual offline OCP attempt rejected scene 1 for visible-content layout
  overflow after 8.566s, before speech. It retained valid source/summary partial
  artifacts and private diagnostics. No narrated-video success is claimed.
- Shortened visible titles/claims and reduced crowded bullet selections in an
  independent layout-v4 draft, preserving every spoken sentence and all original
  evidence/results. Actual same-image browser/PDF draft preflight now succeeds
  across all six slides. A fresh full-evidence review approved the changed bytes
  before sealing. Actual offline Job `autopoc-openshell-kokoro-90b344e8-render-v4`
  is running with a new isolated input/output directory; no tests are replayed.

##### 9.7.13.1 Complete the compact-layout offline technical render — ✅ 9 November 2026

- Actual OCP render-v4 Job succeeded and generated all five artifact kinds.
  Six-scene video is 201.333s / 6040 frames; renderer elapsed 450.197s,
  peak memory 2,981,449,728 bytes and measured scratch 92,998,835 bytes.
- This candidate remains superseded for final delivery: a later primary-source
  review found bundled HA examples, correcting a factual absence claim in its
  report evidence. Retain its immutable inputs/outputs and technical receipt;
  align final report/narration evidence before delivering the final package.

#### 9.7.14 Align final source facts and artifact package — ✅ 9 November 2026

- Exact pinned NVIDIA source includes gateway CI/dev HA values (two replicas,
  Deployment and an external PostgreSQL example) and supervisor E2E HA values
  (two shared supervisors). Operator verified both files at f4a61375, not only
  their names. These configurations were not exercised by this PoC.
- The worker's source-grounded blog review discovered the examples and is
  correcting report/narration/blog references, followed by fresh content review.
  Final package must distinguish source availability from tested HA behavior;
  preserve all five original outcomes without rerunning any tests.

Completed: fresh deployment, original five-case validation, corrected report,
full-source reviewed narration and final offline video generation/direct retrieval.
Drive/Docs publication, optional blog lint configuration and human listening remain
explicitly blocked or pending. This one-off result does not activate production.

### 9.6 Apply the accepted refinements — ✅ 9 November 2026

Implements the dispositions in 9.5. Section 9.5 recorded proposals; this
section records what was actually built, verified and deliberately not built.
Plan task: `docs/superpowers/plans/2026-11-08-kokoro-narrated-video.md` Task 9.

1. **Pronunciation lexicon — implemented.** `src/autopoc/kokoro_lexicon.json`
   is applied only to the string handed to Kokoro, through Misaki's documented
   `[word](/ips/)` override; slides, transcript and captions keep the reviewed
   wording byte-for-byte. Phonemes are validated against Misaki's US vocabulary
   (`misaki.en.US_VOCAB`, read from the installed package) because unsupported
   symbols are dropped silently at inference. `narration.lexicon_sha256` in
   `scenes.json` binds the lexicon to the review, so changing a pronunciation
   cannot reuse an approved plan; plans without the field render with no
   overrides, keeping earlier sealed inputs comparable. Reviewed text containing
   the override syntax is rejected by both the Python and Node validators —
   previously such text would have been silently reinterpreted as phonemes.
   The eight seed entries are expected pronunciations, not measured ones.
2. **Sentence captions — implemented.** `generate_narration` writes
   `captions.vtt` from the measured timeline (scene start + 0.35s lead-in +
   measured sentence offsets) and records `captions_sha256`. The renderer
   verifies that hash before recording, so altered wording fails the render,
   and muxes an English `mov_text` track; the media validator now requires
   three streams. `captions.vtt` and the lexicon are retained in
   `executable-source.zip` for recovery. Word-aligned subtitles remain out of
   scope. Verified against real FFmpeg 8.1.3: the extracted track returns the
   exact reviewed sentence at `00:00.350 --> 00:01.350`.
3. **Job deadline — implemented.** New narrated policy derives 3600s; 3120s
   stays accepted and `submit_renderer` dispatches each descriptor's own
   recorded value, so previous attempts are not reinterpreted.
4. **Early duration estimate — implemented.** `validate_scene_plan` estimates
   total length at 4.0 words/second (Heart delivers roughly 2.4), so it rejects
   only scripts no delivery speed could fit and reports estimate against limit.
   False-rejection risk is therefore nil by construction; the trade is that it
   accepts scripts that measured PCM may still reject, which stays authoritative.
5. **Coverage collision — not implemented, correctly.** 493 Python tests at
   86.44% against the unchanged 80% gate. No pragma and no lowered gate.
6. **Late reconciliation — documented, not automated.** Spec, configuration
   docs and the ADR now state that outlasting the 300s worker wait is the normal
   narrated flow, that collection needs a dispatch, startup/resume or explicit
   `executive-reconcile`, and that report links must not be called automatic
   until a trigger is scheduled. No collector was added.
7. **Asset origin — documented accurately.** `renderer/assets/kokoro/README.md`
   now states that the pins are the bytes downloaded at the pinned revision
   during the 8 November audition, that later builds verify against them, and
   explicitly that this is continuity rather than an upstream signature check
   or a safety assessment. No historical sign-off was invented.

Verification: 493 Python tests (86.44%, 80% gate), 39 Node checks, Ruff 0.15.11
pinned and Pyright clean. Three FFmpeg/browser integration tests remain skipped
on this host because its ffmpeg lacks libx264; two of them predate this work.
The caption mux was therefore verified separately against the real encoder.
No render, PoC replay, cluster change or rollout occurred. Human listening,
pronunciation confirmation, Drive credentials and merge approval remain gates.

##### 9.7.14.1 Freeze final source-aligned media candidate — ✅ 9 November 2026

- Suspended the content-only r2 worker after it exceeded useful wording-review
  rounds; its Pod is gone, with drafts and prior reviews retained on the PVC.
- Froze the corrected report/evidence and a compact six-chapter narrative as
  final-media-v5. Evidence digest is `4e3f9119...5ad433e`; all five original
  captured outcomes remain unchanged. Explicitly distinguish bundled HA
  examples from HA behavior not exercised by this PoC.
- Final independent configured-Qwen review includes all twelve verified bundle
  members, the audited original test script, and both exact pinned HA source
  files. Fresh browser/PDF layout preflight is running before final sealing.
- The one-off run remains pinned to code 35f79ec and the existing trusted renderer;
  later feature-branch refinements are not part of this measured run.

##### 9.7.14.2 Approve and seal final source-aligned narrative — ✅ 9 November 2026

- Same trusted renderer's browser/PDF preflight passed all six slides; operator
  visually inspected all six 1280×720 pages with no clipping or overlap.
- First full-source review exhausted its response budget without a verdict and
  was rejected. Preserved that response; a fresh stateless configured Qwen
  request with adequate output budget returned finish_reason=stop, approval,
  zero blockers, twelve evidence members checked and unchanged input hashes.
  Both exact pinned HA example files and the original audited test script were
  included. Reviewer confirmed date-free narration and scoped network claims.
- Sealed final input `15bd7f8c...3cdc7da`; final offline render-v5 now dispatched
  against the immutable image and isolated transfer directory. Final delivery
  and independent output verification remain pending.

##### 9.7.14.3 Persist corrected canonical report — ✅ 9 November 2026

- Common append-only artifact publisher wrote corrected canonical report
  revision `40175095...7671dc`, commit `5023e376c603fa49916dcaef90ee114767c4eff1`
  in the OpenShell fork's autopoc-artifacts branch. Prior report revisions remain
  retained; source checkout/main were not changed. State records this revision.

##### 9.7.14.4 Finalize and persist the optional blog content — ✅ 9 November 2026

- Corrected HA availability, operator-assisted prerequisites, gateway mTLS
  termination and non-causal network wording; added an explicitly partial SDK
  excerpt from the original script. Four independent configured-Qwen rubric
  requests reviewed the exact v3 draft: overall 9.146/10, minimum dimension 8,
  zero blocking findings. Preserved their actual requests/responses and scores.
- Generated Markdown/SEO/branded HTML with two Mermaid diagrams and no unresolved
  template fields. Sanitized and appended revision `357bac0f...7f8aa2`, commit
  `3d5fb93cd4930ba30366e6ab44393a068f257164` in the fork artifact branch.
- Optional phase 11 remains `generated_validation_blocked`: Vale was invoked but
  returned E100 because its configuration is missing; no lint success is claimed.
  Google Docs/Drive authorization remains blocked by the measured refresh failure.
  These optional publishing gates do not change the five PoC outcomes or block
  independent executive rendering and direct local delivery.

##### 9.7.13.2 Render, retrieve and independently verify final media — ✅ 9 November 2026

- Final offline OCP render-v5 succeeded: 208.267s (3m28s), 6248 frames at 30fps,
  1280×720 H.264 with 24kHz AAC. Runtime 450.941s, measured peak memory
  2,757,124,096 bytes and scratch 95,337,178 bytes, within 2 CPU/4Gi limits.
- Retrieved all five artifacts. Independently verified every size/SHA-256, final
  seal/review/evidence identities, timeline and sentence/scene WAV hashes and
  duration/frame counts. Full host FFmpeg decode passed. All six final PDF pages
  pixel-match the visually inspected preflight; inspected all six video scenes.
- Reverified original script unchanged and all five original payload hashes:
  exactly one captured execution, five passes, no test replay. Gateway and
  supervisor remain ready with zero restarts. Report and narration explicitly
  distinguish available source HA examples from untested HA runtime behavior.
- Local delivery: `/home/aavraham/.codex/visualizations/2026/11/09/openshell-kokoro-90b344e8/`.
  Public receipt: `docs/validation/openshell-kokoro-e2e-2026-11-09.json`.
  Baseline engine remains 35f79ec; later branch refinements are not claimed here.
- Date-free narration is verified from reviewed text; human listening and
  pronunciation acceptance are pending. Drive refresh failed, so no cloud video
  URL, production dispatch/reconcile acceptance or successful upload is claimed.
  Optional blog content is published to the artifact branch; its Vale config and
  Google Docs upload gates remain blocked. Keep the application and workspace PVC.

##### 9.7.15 Stop temporary delivery helpers and retain the deployment — ✅ 9 November 2026

- Saved final media verification/public validation receipts to the PVC and
  retained private review/render proof locally. Deleted only this run's temporary
  artifact-helper and publisher Jobs; both helper Pods are gone.
- Application gateway/supervisor and the bound run workspace PVC remain intact.
  Completed/failed renderer candidates retain their normal seven-day TTL for
  inspection; no shared worker, credential or prior PoC was changed.

### 9.8 Restore TopoLoop 3D views in the OpenShell deliverables — ✅ 9 November 2026

User requested regenerated slides/video with 3D after the omission was traced to
an authoring shortcut. Keep the six chapters, all reviewed spoken sentences,
original five outcomes and corrected HA/source facts. Use the existing pinned
renderer and Heart policy; no deployment/test replay or production rollout.

| Task | Status |
|------|--------|
| Author evidence-linked setup topology and five-check walkthrough | ✅ 9.8.1 |
| Validate actual browser/PDF diagram states and inspect pages | ✅ 9.8.2 |
| Obtain fresh independent full-evidence review and seal changed bytes | ✅ 9.8.3 |
| Render/retrieve/verify revised slides and narrated video | ✅ 9.8.4 |
| Retain prior revisions, record acceptance and stop temporary helper | ✅ 9.8.5 |

#### 9.8.1 Author the two evidence-linked TopoLoop views — ✅ 9 November 2026

- Created an independent 3d-v6 candidate: setup graph shows PoC SDK worker,
  gateway, supervisor, sandbox workload/runtime and gateway block PVC. A second
  graph walks the five original checks; TCP nonresponse remains a limited
  reachability observation rather than a policy-causation claim.
- Shortened graph-slide visible bullet selections to leave room for labels;
  retained all six chapters, exact five-result totals and every spoken sentence.
  Structural/claim-selector validation passed against the same evidence archive.
- Actual trusted-image browser/PDF preflight is running before review/sealing.
  Earlier verified v5 artifacts are preserved and remain available.

#### 9.8.2 Validate and inspect the 3D layouts — ✅ 9 November 2026

- Retained draft revisions v6–v9 while resolving label/title/subtitle overlaps
  and a clipped decorative namespace caption. Final v10 uses concise labels,
  separated storage geometry, and no decorative namespace shell. No renderer
  guards/fonts were changed and no graph was dropped.
- Trusted-image browser/PDF preparation passed all six slides. Inspected both
  changed 3D pages; the other four pages pixel-match the already inspected deck.
- Supplemented native preflight with a reset/remount before each requested frozen
  time: the vendored animation stops its frame loop after freezing, so subsequent
  freeze-prop changes alone do not repaint later states. Independent inspection
  checked complete label boxes, not only titles. All 21 final states passed,
  with all five actual test-step headings and the setup-tour heading observed.
- Remaining product follow-up: make freeze changes repaint without a remount and
  extend the native guard to whole labels/group captions. This regeneration uses
  the existing pinned image; supplemental verification closes that inspection gap
  for these deliverables without claiming a product-code fix.

#### 9.8.3 Review and seal the final 3D candidate — ✅ 9 November 2026

- Fresh independent configured-Qwen review of exact v10 narrative/scenes,
  all twelve evidence members, original script and pinned HA examples returned
  finish_reason=stop, approval and zero blockers. Exact hashes remained unchanged.
- New immutable input `670eef1c...ce270ef`; underlying evidence remains
  `4e3f9119...5ad433e`. Every spoken sentence and original outcome is unchanged;
  the two graphs are evidence-linked and the network scope remains limited.
- Dispatched `autopoc-openshell-kokoro-90b344e8-3d-render-v10` with the same
  offline digest-pinned renderer, CPU/memory limits and isolated PVC transport.
  Final media generation/retrieval/verification remain in progress.

##### 9.8.4.1 Complete the actual offline 3D render — ✅ 9 November 2026

- OCP 3d-render-v10 succeeded with both graph scenes and all five artifact kinds.
  Video: 208.267s (3m28s), 6248 frames; elapsed 469.283s, peak 3,399,409,664
  bytes and scratch 97,810,483 bytes, within the unchanged 2 CPU/4Gi limits.
- Downloaded all five artifacts to a separate 3D delivery directory, retaining
  the earlier video. All six final PDF pages pixel-match the inspected preflight.
  Independent full-media decode, hash/timeline checks and inspection of exported
  animated test steps are finishing before final delivery acceptance.

#### 9.8.4 Verify and deliver the revised slides/video — ✅ 9 November 2026

- Verified all five downloaded size/SHA-256 identities, exact final seal/review/
  evidence bindings, sentence/scene WAV hashes, timeline, 6248 frames and full
  host FFmpeg decode. Both graph scenes are present in source and render manifest;
  every spoken sentence exactly matches the previous reviewed video.
- Inspected all six exported video chapters, all five distinct animated test
  steps and three setup-camera samples. The animations visibly progress through
  health, metrics, SDK exec, placement and the stopped TCP attempt. All six final
  PDF pages pixel-match the inspected preflight; no clipped labels/captions remain.
- Final delivery directory:
  `/home/aavraham/.codex/visualizations/2026/11/09/openshell-kokoro-90b344e8-3d/`.
  Includes MP4, PDF, animated browser ZIP, executable source ZIP and Markdown,
  plus retained recovery/review/animation-state records. Prior v5 media is intact.
- Public receipt: `docs/validation/openshell-kokoro-3d-2026-11-09.json`.
  Original one execution/five passes preserved; no deployment or test replay.
  Drive publication remains blocked by prior authorization failure, human listening
  remains pending, and no production activation or later renderer refinements are
  claimed. This request regenerated artifacts without changing product code.

#### 9.8.5 Retain receipts and stop the temporary regeneration helper — ✅ 9 November 2026

- Retained the genuine final review, sealed input, completed Job receipt, private
  renderer diagnostics, state snapshot and independent media verification. Saved
  output verification back to the run PVC before removing the temporary 3D helper
  Job and observing its Pod deleted.
- Kept the application/workspace PVC and prior artifacts. Completed draft,
  inspection and renderer Jobs retain their normal seven-day TTL for audit.

### 9.8 Tune the refinements against delivered evidence — ✅ 9 November 2026

The 9 November OpenShell delivery produced the first real narration, which made
three of the 9.6 choices measurable instead of assumed. Plan: Task 9 follow-up.

1. **Lexicon rebuilt from spoken content.** The seed set was chosen from the
   design vocabulary, not from narration. Against the delivered transcript it
   fired on 2 of 18 hard terms, and four entries (Kokoro, Qwen, Slidev, RBAC)
   never occurred. Added `NVIDIA`, `mTLS`, `OIDC`, `PVC` and `UBI9`: coverage is
   now 7 of 18. `UBI9` needed its own entry because `UBI` correctly refuses to
   match inside a longer token — every spoken surface form needs an entry, which
   is now asserted by test. Deliberately excluded, with the reasons recorded in
   the lexicon's `selection` field: CamelCase product names Misaki already
   splits (OpenShift, OpenShell, StatefulSet, NetworkPolicies), common
   initialisms it already spells out (GPU, TCP, SDK, API, CPU), and contested
   readings such as kubectl. All entries stay provisional until listening.
2. **Duration estimate recalibrated.** Measured from the delivered audio: 410
   words over 199.60s of speech is 2.05 words/second, per-scene range 1.84-2.20.
   The code assumed 2.4 and guarded at 4.0, so the guard was 1.95x looser than
   reality: a 900s budget really holds about 1848 words while the guard only
   rejected above about 3600, leaving scripts between those sizes to pass
   sealing and fail after synthesis. Now 3.0 — still above the slowest observed
   scene by 63%, so it cannot reject a script that fits, but it catches roughly
   1.5x overruns instead of only 2x.
3. **Vale config discovery fixed.** `.vale.ini` was never missing; it is in the
   worker image at `/opt/autopoc/.vale.ini`. The blog step was the only Vale
   call that `cd`-ed into the run PVC first, and Vale resolves config by walking
   up from the working directory, which never reaches `/opt/autopoc`. The plan
   and report calls pass absolute paths from the image working directory and
   succeeded. The blog call now uses that same pattern, and the image pins
   `VALE_CONFIG_PATH`. Not executed here: vale is not installed on this host, so
   this is a corrected discovery path, not a reproduced lint run.
4. **Result counters render in outcome order.** The deck iterated
   `narrative.results` directly, so display order followed JSON key order.
   Authored narratives serialize alphabetically, which put the only meaningful
   figure, 5 pass, fourth behind four zeros on the delivered results slide.
   The renderer now uses an explicit `pass, fail, error, skip, incomplete`
   order. Colour coding is unchanged; zero-valued error and fail still render
   red, which is a separate design question.

Observed from the 3D re-render, not acted on: peak memory rose from 2.757GB to
3.399GB of the 4Gi limit, 79%, once TopoLoop graph scenes were added, so the
remaining headroom is about 0.9GB and the long-stress case is the one to watch.
The visual preflight also recorded two unfixed renderer issues - `freezeAt`
repaint scheduling and a geometry guard that excludes full node subtitles and
namespace captions - and a clipped decorative caption reached draft output and
was caught by human inspection rather than by the guard.

Verification: 496 Python tests at 86.44% against the unchanged 80% gate, 40 Node
checks, pinned Ruff 0.15.11 and Pyright clean. No render, PoC replay, image
rebuild or cluster change. The renderer capability gate stays open by decision:
a worker rebuilt from HEAD would seal `lexicon_sha256` into plans that the
warm-cached baseline renderer accepts and silently ignores.

##### 9.8.1 Measure the lexicon against the real engine — ✅ 9 November 2026

Built the renderer image from `67d8b2e` and compared Misaki g2p output with and
without each override inside it. This was the first time any override reached
the real engine, and it overturned the premise behind most of them.

- Misaki's defaults are better than assumed. `NVIDIA` (`ɛnvˈɪdiə`), `Quay`
  (`kˈi`), `UBI`, `UBI9` and `mTLS` were already correct; `OIDC`, `PVC` and
  `vLLM` differed only in stress-marker position. The `UBI9` override was worse
  than the default: Misaki says `jˌubˌiˈI nˈIn`, keeping the word break before
  "nine", while the override ran them together. Quay, the term that motivated
  the whole mechanism, was never mispronounced.
- Removed all eight. The five that remain each replace a measured-wrong
  default, now recorded in the lexicon's `measured_defaults` field and enforced
  by test: Kokoro `kəkˈɔɹO`, PoC `pˈOsˌi` (said "poh-see"), Qwen `kjˈuwˈɛn`,
  RBAC `ˌɑɹbˌiˌAsˈi`, Slidev `slˈIdəv`. Of these only PoC appears in delivered
  PoC narration; the rest are AutoPoC's own tooling names.
- Offline Heart smoke passed with no network and empty caches. Identical
  phonemes still produced differing PCM bytes across two synthesis calls, which
  is consistent with the existing rule not to promise byte-identical audio.
- Caption mux verified under real libx264 for the first time: `mov_text` track
  present, reviewed sentence exact, cues at the measured offsets. One real
  defect found and fixed - in the test, not the feature. FFmpeg's webvtt muxer
  re-emits the hour-less `MM:SS.mmm` form, so the assertion expecting
  `HH:MM:SS.mmm` failed. Image suites now pass 16/16 FFmpeg and 2/2 browser,
  the latter also covering the new outcome-ordered result counters.

Standing correction: the original review claimed pronunciation control was
needed because reviewed text cannot be reworded after approval. The mechanism
and its review binding remain justified, but the scale of the problem was
overestimated. Add an entry only after measuring the default in the image.

##### 9.8.2 Publish branch images for a later full run — ✅ 9 November 2026

Built from a clean tree at `59c442d` and pushed under new tags; nothing
previously published was overwritten or retagged.

- `quay.io/aicatalyst/autopoc-executive-renderer:kokoro-tuned-59c442d`
  `sha256:09738e536bcd6622ebaf63da1525fc8434c820c9f3f34ffba3a093f46574c24a`
- `quay.io/aicatalyst/autopoc-opencode:kokoro-tuned-59c442d`
  `sha256:ab2c5d90d2aade47ccd6c52b376330e93196775c1d63fd94b61186b4852e01f4`

The renderer image is byte-identical to the one the 9.8.1 measurements ran
against (same local image ID), and its packaged lexicon hashes to
`2d35409050361931caaf9964c286dee794c3ceb13c3a86c3cdfd97f572a3822c`, matching the
committed file. The worker imports the executive CLI modules with no speech
dependencies present and reports the tuned 3.0 estimate rate.

Both images must be used together. The worker seals `lexicon_sha256` into
`scenes.json`, and an older renderer accepts that field and ignores it, so
pairing this worker with a previously cached renderer would silently drop
pronunciation while the seal still claimed it. No cluster run was started and
no deployment configuration was changed.

### 9.9 Simplify English in future voice-overs — ✅ 9 November 2026

User requested English inspired by ASD-STE100 without its strict vocabulary,
then explicitly selected future videos only. No current OpenShell media revision,
new render, deployment or existing sealed-script change was requested.

| Task | Status |
|------|--------|
| Update author/reviewer writing guidance and design/configuration notes | ✅ 9.9.1 |
| Update and validate the synthetic narration example | ✅ 9.9.2 |
| Confirm existing media preserved and record build/rollout scope | ✅ 9.9.3 |

#### 9.9.1 Define the adapted voice-over style — ✅ 9 November 2026

- Updated executive-narration.md: one main idea per sentence, active voice where
  useful, simple verbs/tenses, consistent terms and helpful first-use explanations.
  Aim for 10–20 words, normally within 25, with clear technical exceptions rather
  than new hard schema limits. No controlled dictionary or compliance claim.
- Preserve uncertainty, coverage limits, original-versus-planned distinctions and
  all important facts. Include a source-linked network example. Simplification
  happens before review/sealing; no synthesis-time paraphrase or duration target.
- Independent review requests revision for dense/ambiguous wording while allowing
  necessary technical vocabulary and justified sentence-length exceptions.
  Updated the design and configuration notes, including worker-build scope.

#### 9.9.2 Validate the revised synthetic spoken example — ✅ 9 November 2026

- Changed only narration entries; retained visible claims, titles, selectors,
  chapter order, graph fields, counts and classifications. Seven spoken entries,
  maximum ten words per entry, with the original limitations preserved.
- Verified its evidence archive and ran actual validate_story/validate_scene_plan
  against the simple fixture. Both contracts passed; git diff whitespace checks
  passed. This is documentation/example validation, not a new model or live run.

#### 9.9.3 Preserve existing media and record activation scope — ✅ 9 November 2026

- Rechecked all ten artifact hashes across the existing plain and 3D OpenShell
  deliveries. Every file is unchanged. No TTS, PoC tests or cluster work ran.
- Rules are committed source guidance. Dockerfile copies them into the worker
  image, so the next worker build must include this revision before future runs
  use it. No deployed image/shared settings or production rollout was changed.

### 9.10 Brainstorm presentation-feedback improvements — ✅ Design/planning complete, 10 November 2026

User requested brainstorming on opening context, authentic project imagery,
less text, explicit test names, AutoPoC pronunciation, fair test-scope wording,
and the late verbal introduction of the recommendation slide. No new render or
product-code change has been authorized by this brainstorming request.

| Task | Status |
|------|--------|
| Inspect actual slides, sentence timing, terminology and renderer capabilities | ✅ 9.10.1 |
| Confirm audience and show a visual storyboard | ✅ 9.10.2 |
| Agree revised story and visual treatment | ✅ 9.10.3 — approved storyboard direction; generic for any source repository |
| Save design and proposed implementation plan | ✅ 9.10.4 — fresh builder check complete; technical choices await review |
| Restore and verify OCP access | ✅ 9.10.5 — authenticated; existing namespace accessible; Job-create permission confirmed |
| Implement and regenerate media | Not started |

#### 9.10.1 Ground the feedback in the existing deliverable — ✅ 10 November 2026

- Opening visible copy states the PoC objective but does not define the project;
  its spoken opening includes the definition. Pinned upstream README includes
  official project branding and a product description suitable as source context.
- Testing speech describes the mechanism and capture instead of naming all five
  checks. Existing TopoLoop board has terse labels; explicit names/actions should
  remain visible and be spoken in the same order. A dedicated checklist treatment
  must respect or deliberately extend the current four-bullet contract.
- Actual final 3D timeline: recommendation scene begins at 177.567s; its first
  sentence starts at 177.917s, then an HA-example sentence at 187.867s. Specific
  next steps start at 198.167s. The approximately 20s mismatch is within the
  authored chapter: recap/context precede the action-oriented narration.
- Current source lexicon overrides standalone PoC but not AutoPoC; verified the
  actual apply() behavior. Delivered video used the earlier renderer without
  the newer pronunciation policy. A future full-name audition/override needs
  measured listening, not only capitalization changes.
- Proposal under discussion: plain project definition; authentic source-page
  screenshot/logo; visuals with a clear explanatory job; explicit five-check
  overview; full-name pronunciation samples; coverage-oriented wording that
  distinguishes untested, partially tested and failed; narration-aligned recap
  and next-steps beats. Generated art would illustrate concepts, while project
  identity and recorded setup remain grounded in authentic assets/evidence.
- Screenshots/illustrations need reviewed asset support in sealed inputs and
  the offline renderer; current fixed input payloads and graph/text template
  do not already provide arbitrary screenshot/image authoring.
- Audience and optional visual-storyboard preference have been asked. These are
  investigation findings and proposals, not an agreed design or implemented fix.

#### 9.10.2 Confirm the audience and deliver a visual storyboard — ✅ 10 November 2026

- User confirmed technical managers/customer engineers as the audience and asked
  to see a storyboard. Assume an engineering background, without prior knowledge
  of OpenShell. Do not assume the viewer understands the project from its name.
- Built a discussion-only interactive eight-scene mockup: project identity,
  PoC goal, five explicit checks, setup topology, results, coverage, takeaway,
  and next tests. Visuals and proposed narration are paired; the last scene's
  first spoken sentence introduces the next actions immediately.
- Opening compares an authentic browser capture of the pinned NVIDIA/OpenShell
  README with a labeled explanatory concept diagram. Source image/hash/provenance
  are retained. No generated artwork or product UI has been fabricated.
- Retained setup specificity (source-built UBI core/bootstrap images, separate
  Ubuntu workload, single SQLite gateway, restricted-v2 and mutual TLS). Coverage
  explicitly names OpenID Connect rather than implying that no authentication
  was exercised. Original five results remain the evidence for observed outcomes.
- Preview includes whole-story navigation, narration/design/evidence views and
  feedback mapping. Checked all eight desktop layouts, opening alternatives,
  loaded source assets and text bounds; narration entries have at most 17 words.
  Fixed preview scaling on scene changes and provided readable narrow-panel
  layouts. Opened the local preview in the in-app browser and kept it available.
- Saved a standalone HTML/asset ZIP and source records under
  `/home/aavraham/.codex/visualizations/2026/11/10/openshell-storyboard/`.
  Live companion content/state stay private and ignored under `.superpowers/`;
  the session access key is absent from tracked files and the standalone export.
- Rechecked all ten existing media artifact hashes: unchanged. This is a visual
  proposal, not an implemented renderer feature or a newly sealed/reviewed script.
  Pronunciation audition/full-name override, actual image support, final storyboard
  agreement and any production regeneration remain future work.

#### 9.10.3 Confirm reusable story direction — ✅ 10 November 2026

- User approved the visual storyboard and explicitly required the template to
  work for any PoC sourced from GitHub or another open-source code platform.
- Project identity, source metadata, components, deployment target, checks,
  outcomes and recommendations must be evidence-driven. OpenShell's five checks
  and eight scenes are examples, not fixed constants. CLI/library projects do
  not need an invented web interface or infrastructure diagram.
- Keep variable chapter repetition and existing resource bounds. Optional source
  imagery has an honest definition/diagram fallback; failures/incomplete checks
  remain visible. Existing media and deployed settings are unchanged.

#### 9.10.4 Save a generic design and implementation plan — ✅ 10 November 2026

- Saved `docs/superpowers/specs/2026-11-10-generic-poc-storytelling-design.md`
  and `docs/superpowers/plans/2026-11-10-generic-poc-storytelling.md`.
- Fresh builder check found no important unanswered questions. Self-reviewed
  plan against existing Python/renderer version dispatch, evidence-derived test
  inventory, sentence timing (including the 0.35s lead-in), asset packaging,
  browser-test opt-in and legacy recovery constraints.
- Proposed seven tasks cover generic schema/layout validation; optional reviewed
  assets; source-independent author/reviewer guidance; identity/check layouts;
  actual TopoLoop pose/collision checks; offline rendering and late recovery;
  pronunciation audition and measured multi-project acceptance.
- Proposed engineering choices are explicit: schema-3/template-4 inputs preserve
  old formats; PNG assets are staged locally before review, with no mandatory new
  crawler/browser service; no new image-generation provider. Authentic captures
  are optional, with source-linked text/diagram fallback. These choices remain
  reviewable and are not claimed as user-approved implementation details.
- Planning phase is complete. Product code, new pronunciation/audio/video,
  automated capture infrastructure, production rollout and cloud publication
  have not been implemented by this documentation change.

#### 9.10.5 Restore and verify OCP access — ✅ 10 November 2026

- Authenticated using the user-supplied credential; no credential bytes retained
  in planning documents or committed files.
- Verified the authenticated identity, active existing OpenShell PoC namespace
  and permission to create batch Jobs there. This verifies access, not a new
  deployment/render or production activation. No cluster workloads changed.


## Phase 10: Generic storytelling implementation and fresh OpenShell cycle — ✅ Complete for local review delivery and code review, 11 November 2026

User explicitly requested implementation of the agreed generic storyboard first,
then a fresh full OpenShell cycle using this AutoPoC branch. This authorizes a
new isolated run and media revision; earlier outputs remain preserved. Technical
design: docs/superpowers/specs/2026-11-10-generic-poc-storytelling-design.md.
Implementation plan: docs/superpowers/plans/2026-11-10-generic-poc-storytelling.md.

| Task | Status |
|---|---|
| Verify isolated branch and baseline | ✅ 10.1 — 496 Python tests, 86.44% coverage; 40 renderer tests passed, 5 browser-gated skips |
| Generic story roles and complete check coverage (plan Task 1) | ✅ 10.2 — 566 Python tests, 86.71% coverage; 108 renderer tests passed, 5 browser-gated skips |
| Reviewed optional visual assets (plan Task 2) | ✅ 10.3 — 621 Python tests, 87.11% coverage; 108 renderer tests passed, 5 browser-gated skips |
| Generic author/reviewer guidance and examples (plan Task 3) | ✅ 10.4 — three source-linked schema-3 worked stories and asset manifests validated; 176 targeted tests passed |
| Reusable identity/check layouts and timing (plan Task 4) | ✅ 10.5 — 109 actual-browser/Node checks, zero skips; 16 real FFmpeg checks; seven-page PDF and measured cue inspected |
| 3D pose lifecycle and full label inspection (plan Task 5) | ✅ 10.6 — 15 actual-browser tests, zero skips; all 10 poses and 60 collision/containment samples; 122 Node tests passed |
| Offline integration, packaging and recovery (plan Task 6) | ✅ 10.7 — 632 Python tests, 87.18% coverage; 134 offline actual-browser/Node/FFmpeg checks, zero skips; source ZIP rebuilt |
| Pronunciation and measured generic acceptance (plan Task 7) | ✅ 10.8 — selected pronunciation; three actual offline Heart renders, 19 PDF pages, 57 scene frames and 24 check-boundary frames; human/full live gates remain |
| En-MaaS provider preflight for the fresh run | ✅ 10.9.1 — external settings/key found; actual worker text/tool calls and in-cluster authenticated connection verified |
| Prepare isolated namespace, access, workspace and source branch | ✅ 10.9.2 — new run c00040c2 only; no application workload launched |
| Fresh branch images and isolated OpenShell full cycle | ✅ 10.9.25/10.9.26 — actual cycle and media complete; lifecycle outcome1pass/1error/3skips remains blocked |
| Repair strict narrated 3D capture coverage | ✅ 10.9.23 — exact short-tail reproduction; bounded schema-3 tail; strict encoded duration/frame/cue checks pass |
| Retrieve and inspect slides/video for user review | ✅ 10.9.26 — all five artifacts/hash checks, nine PDF pages, encoded cue/media/source checks passed |
| Final code-review/provenance correction | ✅ 10.10 — provenance corrected; whole-branch and both scoped live-fix reviews clean |
| Review and commit recovery/layout follow-up | ✅ 10.9.28 — regression gaps closed; 640 Python tests, 87.23% coverage; actual nine-slide browser acceptance passed; local commit only |

### 10.1 Verify isolated branch and clean baseline — ✅ 10 November 2026

Existing linked worktree uses codex/kokoro-narration, starting at 637893d.
Baseline Python suite passed 496 tests with 86.44% coverage; Node suite passed
40 tests with five explicit browser-integration skips. System Python lacked the
coverage plugin; the existing .venv provided the correct project environment.
OCP authentication and prior run resources were inspected read-only; no fresh
run launched before implementing the requested changes. Existing image caches
and retained credentials/resources are available for later isolated execution.

### 10.2 ✅ Generic story roles and complete check coverage — 10 November 2026

Completed plan Task 1. Schema 3 validates source-host-independent project
identity, a visible opening definition, explicit layouts and complete original
scenario coverage with five-row pagination and contiguous, nonoverlapping speech
mappings. Derived checks retain original scenario IDs/names/statuses from
verified final_results.results. Empty inventory requires a testing/checks slide;
the layout task will display the derived no-checks message. Schema-2 behavior
and legacy fixtures remain unchanged. Optional asset manifest binding and actual
layout/rendering remain subsequent tasks; no live run or publication occurred.

TDD: initial RED had six expected Python and five expected Node failures;
additional Node duration/URL boundary RED had two failures. GREEN: 84 focused
Python tests, 61 storyboard tests; full suite 540 passed, 86.69% coverage; full
renderer suite 82 passed with five explicit browser-gated skips. Scoped Ruff,
format checking and Pyright passed. Phase 10 remains in progress.

Task 1 review fix round 1: aligned malformed hostname percent-escape validation
with the offline browser, preserving valid encoded and IPv6 hosts. RED: three
Python malformed-host failures; GREEN: 89 focused Python / 66 storyboard tests.
Full checks: 545 Python passed, 86.71% coverage; 87 renderer passed, five browser
skips; scoped lint, formatting and typecheck passed. Task 1 remains complete.

Task 1 review fix round 2: completed percent-decoded forbidden-domain character
validation, preserving colons only for validated bracketed IPv6. Both suites
cover 21 encoded forbidden/control bytes. RED: encoded colon failed in Python;
GREEN: 110 focused Python / 87 storyboard tests. Full verification: 566 Python
passed, 86.71% coverage; 108 renderer passed, five browser skips; scoped lint,
formatting and typecheck passed. Task 1 remains complete.


### 10.3 ✅ Reviewed optional visual assets — 10 November 2026

Completed plan Task 2. Deterministic local visuals.zip packages zero to four
sanitized, provenance-bound PNGs, with structural/CRC checks, explicit chunk
allowlists, bounded reads and compressed/expanded/pixel guards. Schema-3 inputs
require the archive even when empty, hash all six payloads and bind the visual
hash in review. Slide visual IDs and asset claim IDs are cross-checked. Exact
legacy archive sets and (1,1,1), (1,2,1), (2,3,1) envelopes remain verifiable;
(3,4,2) is admitted explicitly. CLI packaging/sealing and ADR 0015 are included.

TDD RED: 25 missing visual-module failures, nine missing envelope/legacy failures,
one missing CLI command, one identifier-boundary failure and one blocking FIFO
failure. Final GREEN: 89 scoped tests; 616 full Python tests, 87.08% coverage;
108 renderer tests passed with five explicit browser-gated skips. CI-pinned
Ruff 0.15.11 full lint, scoped formatting and full Pyright passed. The local
Ruff 0.17.4 reports 73 unrelated newer-rule findings; no unrelated fixes made.

CURRENT_TEMPLATE_VERSION stays 3 until Task 6 updates renderer admission;
sealing and CLI already accept explicit template 4 and preserve template 3 if
the constant changes. Browser full decode, generic layouts, pixel inspection,
listening and live publication remain later tasks. Phase 10 remains in progress.


Task 2 review fix round 1: seal entry now freezes visual bytes with the same
bounded, nonblocking, regular-file/no-follow reader as standalone preparation.
Five RED regressions proved FIFO blocking, accepted parent symlinks, unbounded
allocation, a final-file symlink replacement race and missing early byte freeze.
GREEN: 94 scoped tests; 621 full Python tests, 87.11% coverage; 108 renderer
passed/five explicit browser skips; CI Ruff 0.15.11 full lint, scoped formatting
and full Pyright passed. Frozen bytes feed overall budgets, review and the
sealed archive without reopening the source. Phase 10 remains in progress.

### 10.4 Generic author/reviewer guidance and examples — ✅ 10 November 2026

Completed plan Task 3. New authoring guidance uses schema/template/policy (3,4,2)
with scene-plan schema 2, a source-linked visible project definition, host-neutral
repository metadata, exact original check inventory and five-row pagination.
It distinguishes intended capabilities, observed negative results and absent
coverage, keeps row speech aligned, and puts next actions at their slide start.
Optional local PNG staging, source/capture attribution, image-free fallbacks,
exact visuals/review hashes and the template-4 sealing recipe are documented.
Text-only model review never substitutes for actual image inspection or genuine
configured-model approval; unavailable review retains an unapproved draft.

Three worker-packaged fictional worked stories retain line-linked sources and
provenance: a GitHub service with six mixed-outcome checks and labeled concept
imagery/unversioned documentation; a GitLab CLI without UI; and a Codeberg library
with empty inventory, missing revision and no invented topology/deployment.
Legacy examples remain intact and structural fixtures are clearly distinguished.

Verification: all three examples passed validate_story, validate_scene_plan,
derive_checks, deterministic prepare_visuals and verify_visuals with real PNG
hashes/dimensions and source provenance hashes. Existing story/visual/input tests
passed 176/176; git diff --check passed. The concept PNG was inspected by the
agent for readable labels and explicit synthetic/context limits, not declared
human media acceptance. No model review, speech/browser render, cluster change,
publication or activation occurred. Phase 10 remains in progress.


### 10.5 ✅ Reusable identity/check layouts and measured timing — 10 November 2026

Completed plan Task 4. Template 4 explicitly consumes schema 3, verified staged
checks/visual manifests and exact local PNG bytes. Identity defines the project,
retains reviewed context and source/revision disclosure; image captions,
attribution and conceptual/contextual labels remain visible. Trusted summary,
checks and topology layouts work without project/host-specific selectors.
Checks retain separate reviewed context, readable labels/purposes, all exact
outcomes and an explicit empty state. Five rows are an upper bound; oversized
context fails bounds with instructions to shorten/paginate, without hiding text
or shrinking fonts. All manifest images fully decode during preparation before
speech; bad referenced images fail preparation. Legacy template 2/3 paths and
empty import defaults are preserved; CURRENT_TEMPLATE_VERSION remains 3 for
Task 6 integration.

Measured row windows include the 0.35s speech lead and half-open sentence
boundaries, reset on seek/slide/print and use an explicit browser clock. A private
pre-roll slate anchors schema-3 capture to actual media-frame PTS; it is removed
from every final video frame. Legacy media-end capture remains unchanged.
The final 181-frame browser/FFmpeg clip showed the cue at frames 11–25
(0.3667–0.8333s), versus measured 0.35–0.85s, within one frame. Repeated capture
measurements stayed within the two-frame browser tolerance.

Verification: required offline actual-browser command passed 109/109 with zero
skips (101.84s), including three worked stories, 6/11-check pagination, generic
topology, visible context/overflow failure, image decode failure, legacy graphs,
print reset, encoded cue/slate exclusion and production seven-page PDF export.
Existing real FFmpeg audio/caption/delayed/fractional-frame regressions passed
16/16 with zero skips. Host full renderer tests passed 122 with 11 explicit
integration skips; those integrations ran separately above. Browser/print poses
and native PDF pages were inspected at 1280×720 / 960×540pt. git diff --check
passed. Full sealed integration, TopoLoop lifecycle correction, listening and
live activation/publication remain later tasks; Phase 10 remains in progress.

### 10.9.1 Verify the externally configured En-MaaS provider — ✅ 10 November 2026

The user identified the current configuration outside the repository. The
previous Qwen namespace no longer exists; current En-MaaS configuration selects
https://api.enmaas.devshift.net/v1 with gpt-6.1-sol via Responses. Authenticated
model listing and actual OpenCode text/function-tool calls succeeded. A small
restricted OCP provider-check Job also completed with ENMAAS_READY. Credentials
were read from the external key file into a new run-specific Secret only;
no key material was written to repository files or logs, and no shared Secret,
CronJob or provider configuration was changed. The probe used a prior trusted
worker image; fresh branch-image and PoC/media acceptance remain pending.


### 10.6 ✅ 3D pose lifecycle and full label inspection — 10 November 2026

Completed plan Task 5. Successive freeze timestamps repaint the same mounted
TopoLoop canvas. One tracked animation callback handles mount, resize, freeze
and release; unmount cancels it. Full visible text ranges include node subtitles,
group captions, headings and footer, with clipping and cross-caption checks.
Intentional graph geometry containment remains permitted. Existing fonts,
tolerances, graphless dispatch, illustrative timing caveat and Task 4 measured
clock/slate path are unchanged.

Meaningful actual-browser RED reproduced stale act 1 at 4.01s and missed subtitle
collision. Final offline Chromium acceptance passed 15 tests with zero skips
(133.12s), including all 10 inspection timestamps on one canvas, 60 synthetic
collision/containment checks, repeated freeze/release, resumed visible movement,
active unmount, legacy/generic slides, real measured capture and PDF export.
Host Node suite passed 122 tests with 12 explicit integration-gated skips; those
browser checks executed separately above. Three act frames and negative caption
collision diagnostics were visually inspected. Expected damaged-PNG diagnostics
are captured/asserted only within that negative test. No live activation,
publication or human listening acceptance claimed. Phase 10 remains in progress.


### 10.9.2 Prepare the isolated fresh OpenShell environment — ✅ 10 November 2026

Created source branch codex/openshell-story-20261110-c00040c2 at pinned upstream
f4a6137513b777c9b362be54baf388f7d45398aa in the existing protected fork. Reverified
main protection before branch creation; the default branch was not written.
Created namespace poc-openshell-story-c00040c2, runtime ServiceAccount, bounded
existing-pattern runtime/validation permissions and a separate 10Gi workspace
PVC. The PVC waits for its first consumer; this is environment preparation,
not successful application deployment or a completed PoC. Fresh branch images
and main worker launch remain pending engineering acceptance. Earlier resources
and artifacts are retained.


### 10.7 ✅ Offline integration, packaging and recovery — 10 November 2026

Template 4 now follows verified preparation/decode/layout, exact reviewed Heart
speech and measured recording sequentially. CURRENT_TEMPLATE_VERSION is 4;
render admission explicitly retains templates 2/3/4. Schema-3 staging derives
checks.json only from verified evidence, writes the verified visual manifest and
unpacks only its selected PNGs into controlled private paths. Source/browser ZIPs
carry the checks, manifest and exact public PNGs; source recovery retains PNGs
even if preparation cannot start. The trusted timing module is included in both
the executable-source allowlist and renderer Dockerfile. The worker Dockerfile
installs the minimal autopoc-tools executable; a real process test verifies CLI
dispatch. Actual fresh-worker image verification remains Task 7.

Templates 3/4 deliberately share the existing kokoro-v3 resource-policy profile:
3000s process, 3600s new Job, existing CPU/memory/storage limits; saved 3120s
Job descriptors retain their launch intent. Schema-3 late recovery preserves
input/asset/check identities and all five artifact hashes after the worker wait
expires, reconciles idempotently, and rejects changed input/output bytes without
rerunning scenarios. A browser-test readiness wait fixes an async reset race;
no collision, font, containment or decode guard was weakened.

RED reproduced missing worker executable, rejected/silent template-4 dispatch,
missing timing/metadata packages and missing recovery PNGs before preparation.
GREEN: 95 focused Python checks; full suite 632 passed at 87.18% coverage;
134 actual-browser/Node/FFmpeg checks passed offline with zero skips; CI Ruff
0.15.11, touched-file formatting and Pyright passed. Actual Python/Node
preparation produced a schema-3 deck/PDF and ZIPs in the cached offline image;
extracting the source ZIP into fresh scratch and rebuilding with its included
files plus provisioned npm dependencies succeeded. This focused packaging smoke
intentionally stopped speech and retained a partial result. Fresh image builds,
actual Heart schema-3 listening/visual acceptance, restricted-v2/OCP validation,
Drive publishing and shared activation remain later gates. Phase 10 remains in
progress.


### 10.8.1 ✅ Selected full-name pronunciation — 10 November 2026

User selected the listened-to Heart “auto P-O-C” audition. Exact measured
phonemes are now a whole-name synthesis override; standalone PoC and reviewed
transcript remain unchanged. Narrowly allow the pinned model's measured T flap,
reject other unknown symbols, and retain sealed lexicon invalidation. Regression
RED: two expected failures; GREEN: 30 speech tests passed. Deferred example
wording now distinguishes absent records from nonexecution and incomplete
outcomes from a proven interruption. Browser lifecycle checks await paint and
observed callback/canvas conditions instead of fixed 60–100ms sleeps.
Task 7 image/media acceptance and Phase 10 fresh OpenShell cycle remain pending.

Independent synthetic review caught the library minimal evidence-index coverage
gap still using the older nonexecution inference. ✅ Corrected that remaining
source field to the same record-not-established wording; fresh worker packaging
and repeat library semantic review are required before media acceptance.


### 10.9.3 Launch the fresh branch-based OpenShell worker — ✅ 10 November 2026

Created one-off worker Job autopoc-openshell-story-c00040c2, run
c00040c2196d4919b3e5b0a7fd947faf, using worker source c997290 and published image
sha256:b169dd89db35f0ac895b4e688ff567d7e6b4c53fa892be3c3df9c00e1b43aa55.
The configured renderer is source9746cbb/image
sha256:1c1dc7b1510b25c113eb28a053d1e9f01fe449860171ba9397a62eab6964f215.
The Pod was admitted under restricted-v2. Initial scheduling/init is pending;
no deployment/test/report success is inferred from Job creation. Core code and
fresh image checks passed; the long source workflow overlaps the final library
synthetic media QA/read-only reviews, with output acceptance still gated.
Shared CronJobs/settings and earlier application deployments remain untouched.

| Fresh original PoC phase | Status |
|---|---|
| Intake | ✅ 10.9.4 — completed |
| Evaluate | ✅ 10.9.5 — completed |
| Fork/adopt prepared source branch | ✅ 10.9.6 — completed |
| Plan | ✅ 10.9.7 — completed |
| Containerize | ✅ 10.9.8 — completed |
| Build | ✅ 10.9.9 — all three original images built and published |
| Deploy manifests | ✅ 10.9.10 — generated, linted and committed |
| Apply | ✅ 10.9.11 — bounded retry and direct workload readiness passed |
| Execute original validation | ✅ 10.9.12 — one pass, one error, three skips; lifecycle objective not achieved |
| Report and reviewed media inputs | ✅ 10.9.13/10.9.16; original approved seal retained, audience revision under review |
| Eligible blog | ✅ 10.9.14 — eligibility assessed; skipped after unsuccessful validation |
| Offline renderer and local retrieval | ✅ 10.9.25/10.9.26 — actual OCP output retrieved and independently verified |


### 10.8 ✅ Pronunciation and measured generic image acceptance — 10 November 2026

Completed plan Task 7 engineering/local-image acceptance. User-selected Heart
full-name pronunciation preserves exact reviewed text; the fresh actual model
retains its measured T flap. New images use unique tags and published push
digests, with worker c997290 and renderer 9746cbb recorded separately. Actual
worker CLI and copied source hashes passed. Corrected missing-record/incomplete
example language, including the minimal library index caught by independent
semantic review; browser lifecycle tests now await conditions/paint.

All three honestly synthetic, independently reviewed source-host/project-type
cases rendered offline with actual af_heart at 0.95, read-only root, UID28128,
2 CPU/4GiB. Service/CLI/library: 352.903/239.793/195.768 seconds;
3,352,420,352/1,658,048,512/1,675,239,424 peak bytes;
110.7/65.733333/52.333333 seconds final media. Each produced all five artifacts.
Every output hash, exact embedded captions/timings, reviewed transcript and
sentence/scene PCM identity, full media decode/frame total and zero slate check
passed. Source ZIPs rebuilt offline. Agent inspected all 19 PDF pages, 57 scene
transition/mid/end frames and 24 check-boundary frames: readable identities,
complete statuses/empty inventory, missing-revision disclosure, optional concept
attribution, correct highlights and no invented deployment/topology.

Required checks: 634 Python tests, 87.22% coverage; CI Ruff0.15.11 and Pyright
clean; 122 default Node passes/12 explicit integration skips, plus 15 actual
browser and 16 actual FFmpeg passes with zero skips. Measured record:
`docs/validation/generic-poc-storytelling-2026-11-10.json`.

Task 7 records honest pending human full-video listening/final visual acceptance.
Fresh OpenShell eleven-phase execution has been launched separately by the
controller; its results and retrieval remain in progress. Drive authorization/
publication and explicit merge/live activation are separate gates. No shared configuration/default branch/Drive
writes or changes to earlier delivered media. Phase 10 remains in progress.


### 10.9.4 Fresh intake — ✅ 10 November 2026

The actual branch worker completed source analysis of the pinned OpenShell
checkout, including component, SDK and chart inspection. Its run-specific state
marks intake completed. No old test outcomes were imported.

### 10.9.5 Fresh evaluation — ✅ 10 November 2026

The configured En-MaaS model completed the evaluation using the current strategy
and retained its new evaluation/source analysis in this run's private staging.
This is a project assessment, not runtime validation.

### 10.9.6 Adopt the prepared fork/source branch — ✅ 10 November 2026

Worker state marks the fork phase completed for the authorized prepared branch.
The protected default branch remains outside the write scope. No build,
deployment or PoC-test success is claimed at this stage. State currently records
zero errors and zero build/deploy/container-fix retries; planning is next.

### 10.10 Final code-review/provenance correction — ✅ 10 November 2026

Updated `renderer/vendor/topoloop/UPSTREAM.md` to preserve upstream commit
`8631cf7955ebf40a579aab4ce3d0cca50d215c21` and MIT/license attribution while
identifying the local lifecycle patch in `src/TopoLoop.vue` from `002873d`.
Phase 10 remains in progress; fresh OpenShell execution and its delivery gates
are ongoing.


### 10.9.7 Fresh PoC plan — ✅ 10 November 2026

The actual worker recorded a new completed PoC plan for this run. Its execution
and conclusions must come from new captured attempts, not earlier outcomes.

### 10.9.8 Fresh containerization — ✅ 10 November 2026

Worker state marks source Dockerfile/containerization work completed and the
build phase in progress. Cluster compiler builds are running; successful images,
deployment and validation are not yet claimed. Source SDK dependencies are
being installed in an isolated workspace environment, preserving the harness.
State still records zero errors and no build/deploy/container-fix retries.

### 10.9.9 Fresh original image builds — ✅ 10 November 2026

All three first-attempt OCP builds completed and pushed unique run images:
gateway `dcda18953431340ab766bc71ad3bed03ec53752cf7ab7167edc949b20575ce15`
(2423 seconds), supervisor
`eb2ae68363c52bf848f866d025826466eee91d019cafd371957fa362615e8199`
(936 seconds), and sandbox
`7a92fe2873dd0cb8a72b7e668c34aa55cc6e77057f731e2e56c98757b8cc6490`
(921 seconds). Gateway's native Z3/full-feature release compilation was the
longest step; no replacement build or build retry was needed. Application
deployment, original validation, report and actual media remain pending.

### 10.9.10 Fresh deployment manifests — ✅ 10 November 2026

The actual worker completed Helm values/manifests, official Helm checksum
verification, lint and a scoped source-branch commit. Application resources were
created in the new namespace. Helm's wait failed because the bounded runner
cannot list ReplicaSets; this original apply error is retained. The worker is
using permitted direct workload observations for the bounded apply retry, with
no privilege expansion. Apply acceptance and original tests remain pending.

### 10.9.11 Fresh application rollout — ✅ 10 November 2026

Worker state records apply completed after one retained Helm wait/RBAC error
and a bounded retry using permitted direct rollout observations. Gateway and
supervisor Pods are Ready; the gateway PVC is Bound on the selected application
node. No extra privileges were granted. Original validation is in progress;
readiness alone is not proof of its five scenario outcomes.

### 10.9.12 Fresh original validation — ✅ 10 November 2026

One captured execution `0329dd4aa56e464092de68f894abe83a` retained five terminal
scenarios: **1 pass, 0 fail, 1 error, 3 skip, 0 incomplete**, process exit 1.
Gateway readiness/positive-negative mTLS controls passed. Sandbox creation
returned failed precondition because no shared supervisor was attached; the
three dependent checks skipped. TLS/token diagnostic requests narrowed the
issue but did not establish the Rust client's root cause or change test totals.
No validation rerun, speculative rebuild or security/RBAC relaxation occurred.
Execution is recorded as completed, not a successful sandbox lifecycle.

### 10.9.13 Canonical blocked-run report and evidence — ✅ 10 November 2026

Verified original evidence ZIP hash is
`4bbfe024bdc4abc896cf417543e4bd561c666f2ca9596b8a51254b0273be2386`.
Canonical report was published as an immutable artifact revision, commit
`caef62b6f26ef8f4dd72c99da6e2317f55983c60`. The worker records report completed.
Fresh media authoring/review/sealing and actual rendering remain pending.

### 10.9.14 Blog eligibility — ✅ 10 November 2026

The original cycle reached blog eligibility assessment and recorded blog and
blog_post skipped: a majority of planned scenarios did not pass. No success
blog was generated. Cloud publication remains blocked and unapproved; local
report-based media preparation continues from the retained unsuccessful run.

### 10.9.15 Audience-focused narration guidance — ✅ 10 November 2026

Actual fresh-run draft inspection found report-publication/branch/provenance
procedure in the narration, including a draft-time statement that no video had
been produced. Refined the generic author/reviewer instructions to keep media
production/export/cloud/Git procedure in supporting records, retain only
material assistance in the spoken outcome, and use explicit "not tested here"
wording for scope exclusions. This changes editorial guidance only, with no
schema/runtime or evidence relaxation. The current draft still requires a new
editorial revision and genuine independent review before final rendering.

### 10.9.16 Original worker authoring, review and seal — ✅ 10 November 2026

The actual worker Job completed. It retained a regular nine-slide schema-3 /
template-4 / policy-2 seal, SHA-256
`647ad00eed09ce632f279470b53dfb6ce5da6c724b7eaaa394ea35719ec5c882`,
with genuine independent same-model content approval. The original reviewed
bytes remain preserved. Parent independently rehashed all 47 evidence members.
Operator is preparing a separate audience-focused content revision with a new
genuine review and the final documentation-corrected renderer pin; no PoC test
replay, original-seal mutation or inherited/fabricated approval is permitted.
The fresh cycle recorded unsuccessful lifecycle results; media output remains
pending and no cloud publication or full human acceptance is claimed.

### 10.9.17 Audience revision, genuine review and final seal — ✅ 10 November 2026

Revised nine-slide narration has 596 spoken words and at most 17 words per
sentence. The genuine first review rejected one planned-versus-observed SDK
link and omission of the material Helm readiness permission constraint. Both
were corrected; original rejection/events/bytes are retained. A second genuine
same-provider/model review approved all 101 selectors and five check mappings.
Media/cloud/Git process noise is absent, while the meaningful deployment
constraint, assistance limits, missing trace, exact outcomes and next actions
remain. No test replay occurred.

Final seal SHA-256 is
`f76785e10f01d7fbb50c4a01bccf12ddf3dac7ae0ce6b8dc50a5744bc53d3d70`,
bound to final renderer `259d5a19…`. Original evidence/scenes/visuals bytes match
the preserved worker seal exactly; narrative/review/image identities are new.
This operator content revision is disclosed assistance, not mutation of an old
approval. Actual OCP rendering/media acceptance remains pending.

### 10.9.18 Compact source revision labels — ✅ 10 November 2026

| Task | Status |
|------|--------|
| Abbreviate only 40/64-character hexadecimal figure revisions to 12 characters plus ellipsis | ✅ Complete |
| Preserve full revision in title, source card, pinned URL and staged visual metadata | ✅ Complete |
| Verify real-browser regression and default renderer suite | ✅ Complete |

The synthetic pinned-README browser regression failed against the original
full-hash label, then passed for a 40-character hash, an uppercase 64-character
hash and an unchanged named version. It verifies a single-line label, no
first-slide layout problems, exact full title/URL/source-card revision and
unchanged input/deck visual metadata. Checks ran offline/read-only as UID
28128/group 0 with 2 CPU/4Gi in trusted local image `9ae79ec5170f…`:
`AUTOPOC_BROWSER_INTEGRATION=1 node --test --test-name-pattern="pinned source captures" browser.test.mjs`
passed; default `npm test` passed 122 tests, with 13 opt-in integration tests
skipped. No font, image, clipping, validation or provenance policy changed.
Fresh renderer image build and actual OpenShell render acceptance remain
pending; these are local synthetic layout results only.

### 10.9.19 Fresh layout-fix renderer image acceptance — ✅ 10 November 2026

Scoped independent review of e478620 is clean. Built/pushed new renderer
`sha256:c493de2e7ddc7fe5c42b6105c5e9a296b56099233a15ffba66e918e91ce401aa`
from that commit. The full actual Chromium suite passed **16 tests, zero
failures and zero skips**, 198.789 seconds, using this fresh image's runtime
under offline/read-only UID28128, 2 CPU/4Gi. The meaningful new regression
previously failed with full hashes and passed after the display-only fix.

The earlier actual OCP render on259d failed closed during first-scene content
preflight (8.452 seconds, before speech); its partial output/logs and original
seal remain retained. Current input caption/attribution and 3D layout revisions
are separately re-reviewed; the final OCP media render remains pending.

### 10.9.20 Final layout content review and sealed handoff — ✅ 10 November 2026

The final current input passes actual fresh-image layout inspection for all
nine slides and nine sampled 3D poses. Source-image caption/attribution are
shorter; PNG bytes, full source URL and full capture revision are preserved.
Setup has one concise visible point and three evidence-backed acts, including
a neutral mounted gateway-data volume view. The diagram never adds a sixth
test or implies a usable sandbox.

A genuine review rejected a missing restricted-v2 selector after source-list
shortening; the rejection and original bytes are retained. Corrected the exact
claim/reference and obtained a new genuine approval of all101selectors. New
seal is `44ac15a1fc42f0cd2b763b2cbd4cf04e02f4439c2c52ccdbbe6c01cb0b0ee634`,
on the fresh tested c493de2e renderer. Original evidence and scene policy are
byte-identical, and no PoC test was rerun. A distinct immutable ConfigMap and
regular-copy transfer prepare v2; actual rendering/retrieval remain pending.

### 10.9.21 Actual OCP deck/PDF preparation — ✅ 10 November 2026

Distinct renderer Job `autopoc-openshell-story-c00040c2-render-v2`, Pod UID
`9b500324-a9b0-4445-b3c1-e10061ebb197`, runs the exact c493de2e image and
44ac15a1 seal. Admitted restricted-v2, no API token, deny-all networking,
2CPU/4Gi,3000-second process budget/3600-second Job deadline. The renderer's
actual preparation stage reports deck and PDF validated; PDF is196777bytes,
SHA-2567193329243eaad194de6b6725e34ddaf33b3358713bb8daaf9702000c287c487.
Kokoro sentence generation is in progress after browser preparation exited.
Final packaging, video recording, retrieval and media inspection remain pending.

### 10.9.22 Actual speech generation and nine-page PDF inspection — ✅ 10 November 2026

OCP Kokoro synthesis finished before video recording. The measured timeline is
296.333333 seconds,8890frames at30fps, nine scenes; no speech clipping or
acceleration is used. Renderer entered recording after speech exited.
Retrieved the actual prepared PDF and verified its recorded size/hash; pdfinfo
reports nine pages. Assistant inspected every rendered page, including source
identity/provenance, all five named check rows, 3D setup still, exact totals,
untested-scope wording and immediate next actions. No clipping observed.
Video encoding, final artifact verification/retrieval and human full listening
remain pending. PDF/media inspection is not PoC functional success.

### 10.9.23 Strict narrated 3D capture coverage repair — ✅ 10 November 2026

| Task | Status |
|------|--------|
| Reproduce the exact setup scene and retain private raw/PTS/color measurements | ✅ Complete |
| Add bounded schema-3 recorder tail and safe numeric coverage diagnostics | ✅ Complete |
| Prove busy 3D RED/GREEN, exact actual-scene capture and encoded cue alignment | ✅ Complete |
| Run the full renderer suite with trusted FFmpeg | ✅ Complete |

The original actual scene reproduced locally in the pinned c493de2e runtime,
offline/read-only as UID28128/group0 with2CPU/4Gi. Raw duration39.840s minus
slate-exit PTS5.080s left34.760s for the required35.400s: a640ms capture-tail
shortage, correctly refused by the strict coverage guard. Software3D compositor
swap timestamps can trail the completed browser-clock wait. Private raw,
frame PTS, corner colors and measurements are retained outside temporary scratch
under `/tmp/autopoc-openshell-layout-c00040c2`; none are published artifacts.

Schema3 now allows a bounded1500ms recorder tail instead of150ms before close.
The private-slate start anchor, strict coverage/frame guards, check clocks,
reviewed scene/audio lengths and process/resource limits are unchanged. Schema2
retains its original duration+150ms behavior. Incomplete anchored capture now
reports numeric raw/anchor/required/available seconds without media paths.

The new actual four-node/three-act TopoLoop regression failed before the repair
(35.160s available), then passed after it (36.520s available), encoding exactly
1062frames/35.4s with no private-slate frames. The separately repeated exact
actual setup input passed with raw41.120s, anchor4.840s and36.280s available;
its encoded output has1062frames/35.4s and no slate. Existing encoded check-cue
regression passed: frames11–24 at30fps versus measured0.35–0.85s, within its
unchanged two-frame tolerance. Both actual-browser tests passed together with
zero skips (79.746s). Diagnostic regression also followed RED/GREEN.

Full renderer `npm test` with FFmpeg integration enabled in the trusted pinned
runtime passed126tests, zero failures,11explicit browser-integration skips
(18.443s). An initial host attempt had three FFmpeg tests fail because its
FFmpeg lacks libx264; the trusted-runtime rerun passed all three. No PoC checks
were replayed. Fresh image rebuild, full image/browser acceptance, actual OCP
rerender, publication and full human listening remain pending; Phase10 remains
in progress. This is a local capture repair, not PoC functional success.

### 10.9.24 Fresh capture-fix image acceptance and new seal — ✅ 10 November 2026

Scoped independent code review of4b5a221 is clean. Fresh renderer
`sha256:51de7478b7b67667cf1ecc165f4b585ee96ee7947b9c126a7ca694544f987711`
passed all17actualbrowser tests (zero failures/skips,257.937s), including the
busy3D regression, and all17audio/FFmpeg tests (zero failures/skips,15.230s)
in its own trusted offline/read-only2CPU/4Gi runtime. No duration, frame,
slate, caption or audio guard was relaxed.

Resealed exact approved evidence/narrative/scenes/visuals bytes to that image;
new input hash13fd83db040ba122723f808b36ab8b2fcd277dc6a22362215d3905180d60ac85.
All four content-review identities are unchanged; no new content approval is
inferred for changed bytes. Distinct immutable v3 input/transfer prepare the
third actual render, retaining both failed attempts and their good artifacts.
OCP render/video acceptance remains pending.

### 10.9.25 Actual OCP media render and five-artifact retrieval — ✅ 10 November 2026

Renderer Job`autopoc-openshell-story-c00040c2-render-v3` completed successfully,
21:17:01–21:28:06UTC, JobUIDdf1dade2-ff3e-4328-ab7b-458c39ce4547. All five
artifact kinds report generated_unpublished and were retrieved to the local
review directory with exact manifest size/SHA-256 checks. Actual MP4 is6558992
bytes, hashc37c180b1c7a55a3d720137672f2f08d6103d7024a02981a9b5b687056c1c993.
No PoC tests were rerun, and the original one-pass/one-error/three-skip outcome
is unchanged. Both prior failed media attempts remain retained.
Independent encoded-media, cue, final PDF and source-rebuild QA are in progress;
human full listening and cloud publication remain separate pending gates.

### 10.9.26 Independent actual-media and source acceptance — ✅ 10 November 2026

All five delivered artifact hashes/sizes passed independent checks. Actual
video is296.333333s/8890frames,1280x720H264/30fps, AAC24kHzmono, with embedded
sentence-level mov_text captions. Full decode passed; no private full-frame
slate detected. Exact reviewed transcript, all sentence/scene WAV identities,
model/lexicon identities and embedded caption text/timestamps passed.

All five encoded check-row highlight windows were measured from actual video
pixels and match audio offsets within two frames. Inspected27scene transition/
mid/end samples,15check-boundary samples and3actual3Dposes. All nine final PDF
pages are pixel-identical to the fully inspected actual OCP PDF. The actual
source ZIP rebuilt offline under non-rootUID28128 with pinned image deps; its
included source-context PNG hash survived the browser build.

Real render elapsed657.492s, peakmemory3503050752bytes, scratch134407077bytes
within2CPU/4Gi/8Gibudgets. No original PoC validation replay. Human full-video
listening, Drive authorization/publication and shared rollout remain pending;
the PoC lifecycle itself remains blocked with1pass/1error/3skips.

### 10.9.27 Durable final handoff and scoped cleanup — ✅ 10 November 2026

Persisted final sealed inputs, genuine content approval/verdict, actual artifact
manifest and operator handoff on the authorized fork's append-only artifact
branch, distinct review-media-handoff head. Commit
`a78bcbc23b8777906015cadab3278f893e7f640c`; all five payloads were independently
fetched and byte-verified, with previous artifact history retained. No source
checkout/default branch or official Drive checkpoint was changed.

Removed the completed run's temporary En-MaaS Secret, read-only retrieval Job/
NetworkPolicy and local registry-auth copy. External key, shared credentials/
settings, application deployment and retained evidence workspaces remain.
Private development review ledger stays available while this feature branch
is under review; no merge or global rollout was performed.

Phase10 is complete for the requested generic implementation and fresh local
slides/video review delivery: nine slides and296.333333-second narrated3Dvideo
are verified. The upstream PoC lifecycle remains unsuccessful and honestly
reported (1pass,1error,3skips); no root cause or product defect was invented.
Human full listening, explicit Drive publication and shared activation remain
separate gates, rather than claims of this completed local review cycle.

### 10.9.28 Review and commit recovery/layout follow-up — ✅ 11 November 2026

Reviewed the five-file recovery/layout delta against da116f9 with an independent
read-only reviewer. Preserved the deck transcript at transcript.txt and the
spoken-format transcript at narration/transcript.txt. Malformed speech package
metadata now fails before inference, and a rejected pronunciation lexicon cannot
discard the independently prepared source, deck or PDF. Added missing/null/list/
string package cases and lexicon-failure recovery cases for both narrated
templates. All six new cases fail against the original modules and pass with
the fixes; six completed-speech cases also reproduce the original transcript
overwrite against the original modules.

Actual offline browser acceptance on the delivered OpenShell deck exposed a
stale opening-slide selector in check-layout.mjs: generic identity slides use a
project definition instead of a legacy claim list. Extended the overflow probe
to both layouts, retained the deterministic topology-label overlap probe, and
reran the exact command successfully: nine scenes and all eight acceptance
checks passed under the pinned image with networking disabled, non-root user,
read-only filesystem, 2 CPU and 4 Gi memory. No PoC validation was replayed and
no delivered artifact was changed.

Final verification: 640 Python tests passed, 87.23% coverage; 122 Node tests
passed with 15 explicit browser/FFmpeg integration skips on the host; Ruff
0.15.11 lint/format and Pyright passed. The changed browser acceptance script
was separately exercised in the trusted renderer image, so its actual browser
path was verified. Independent review has no outstanding findings. Commit
locally as requested; the user will push manually. Existing human listening,
Drive publication and shared activation gates remain unchanged.
