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
| Fresh OpenShell end-to-end branch run | In progress | 9 November: access/preflight complete; isolated worker/deployment/testing/report/narrated-media run |
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

### 9.7 Fresh OpenShell end-to-end branch run — In progress, 9 November 2026

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

Remaining: persist deployment checkpoints and execute original validation/report/blog or record a bounded mandatory failure; inspect
actual results/report and genuine narrative review; render/retrieve/verify the
new narrated video when eligible. No end-to-end success is claimed yet.

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
