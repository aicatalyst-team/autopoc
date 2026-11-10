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


## Phase 9: Kokoro Voice-over — Engineering implementation/acceptance ✅; rollout gates pending

| Task | Status |
|------|--------|
| Check Google TTS availability on the work project | ✅ Billing enabled; TTS API absent; use request denied by project permissions |
| Generate two local Kokoro voice samples | ✅ 8 November — Heart 22.150s and Fenrir 20.325s; CPU generation about 14.2s each |
| Verify sample integrity and preserve audition measurements | ✅ Finite non-silent WAVs; MP3 probe and full decode passed; script/package inventory/results retained locally |
| Select a voice and agree on content/timing direction | ✅ Heart selected; length follows PoC complexity; source-backed objective/testing/setup/results plus limitations/recommendation |
| Save and independently check design and implementation plan | ✅ Eight tasks defined; builder review found no important gaps; user approved implementation 8 November |
| Check OCP GPU capacity and AutoPoC namespace access | ✅ 8 November — one L40S and two A100 devices unrequested; Job/pod creation allowed, no namespace quota found; workload not tested |
| Implement and validate narrated rendering | ✅ Done — eight tasks, reviewed offline image, real local/OCP video acceptance |
| Review external implementation refinements | ✅ 9 November — all seven checked; dispositions in implementation-plan.md section 9.5 |
| Apply the accepted refinements | ✅ 9 November — four implemented with tests, one rejected on evidence, two documented; section 9.6 |
| Omit PoC dates from spoken narration | ✅ 9 November — author/reviewer policy and design updated; existing demo has not been re-rendered |
| Prepare a fresh OpenShell end-to-end branch run | ✅ 9 November — access, image identity, protected source branch and isolated run configuration verified |
| Execute fresh OpenShell deployment/tests/report/video | ✅ 9 November — fresh deployment, original 5/5 pass, corrected report, reviewed 3m28s Kokoro video and all five artifacts locally verified; Drive/listening gates remain |
| Fresh OpenShell source intake | ✅ 9 November — pinned source inspected; gateway/supervisor/sandbox identified; evaluation next |
| Fresh OpenShell evaluation | ✅ 9 November — assessment completed/staged; artifact publication underway |
| Fresh OpenShell protected-fork adoption | ✅ 9 November — new source branch/remote/attestation verified, no default-branch writes |
| Fresh OpenShell PoC plan | ✅ 9 November — five scenarios planned/published; containerization next, no test results yet |
| Fresh OpenShell UBI containerization | ✅ 9 November — three component Dockerfiles verified/committed/pushed; actual builds next |
| Fresh OpenShell sandbox image build | ✅ 9 November — sandbox-1 Complete/published; gateway and supervisor still building |
| Fresh OpenShell supervisor image build | ✅ 9 November — supervisor-1 Complete/published; gateway still compiling |
| Fresh OpenShell gateway/prover and complete runtime image build | ✅ 9 November — three images published/verified; worker build phase completed with zero retries; deployment preparation underway |
| Fresh OpenShell offline-renderer readiness | ✅ 9 November — OCP packaged-asset verification succeeded; temporary check Job removed, renderer image cached |
| Fresh OpenShell initial install/readiness | ✅ 9 November — gateway/supervisor ready under restricted-v2 with expected new image IDs |
| Fresh OpenShell deploy/apply checkpoints | ✅ 9 November — worker recorded both phases completed, zero deploy retries; captured original validation next |
| Fresh OpenShell captured original validation | ✅ 9 November — one captured execution, five pass/zero fail/error/skip/incomplete; ingress-path scope remains limited |
| Finalize OpenShell report/narration scope | ✅ 9 November — corrected claims and compact visible copy independently approved against full evidence; original five outcomes preserved |
| Corrected OpenShell canonical report generation | ✅ 9 November — scoped wording inspected, five original results preserved; final publication and narration review/seal still pending |
| Full-corpus content review and independent seal | ✅ 9 November — actual configured-model approval on all twelve bundle members and original script; immutable v3 seal retained |
| OpenShell compact-layout review/seal | ✅ 9 November — all six browser/PDF pages inspected, fresh full-evidence review approved, immutable layout-v4 input sealed |
| OpenShell narrated render acceptance | ✅ 9 November — final render-v5 succeeded, 3m28s/6248 frames, five artifact hashes/media decode verified; human listening pending |
| Compact-layout offline technical render | ✅ 9 November — OCP generated all five artifacts, 3m21s/6040-frame video; candidate retained as superseded pending final HA-source correction |
| Final OpenShell source/artifact alignment | ✅ 9 November — final report/narration/evidence distinguish available HA examples from untested behavior; exact final input independently reviewed and delivered |

This is a local throwaway audition, not production narration acceptance. Technical
pronunciation, offline packaging, per-scene synchronization and restricted OCP
resource acceptance remain future design/validation work if Kokoro is selected.


Planning completed 8 November: [design](../../docs/superpowers/specs/2026-11-08-kokoro-narrated-video-design.md)
and [implementation plan](../../docs/superpowers/plans/2026-11-08-kokoro-narrated-video.md).
Use final report, original results, staged setup, logs and available traces;
include fixes only when they help explain the PoC outcome. Implementation was authorized on 8 November; engineering implementation and acceptance are complete, with the recorded rollout gates pending. The eight implementation tasks and status are tracked in
implementation-plan.md section 9.3; every completed task must update both files.


### Phase 9 implementation tasks

| Task | Status |
|------|--------|
| Retain sanitized supplemental logs/traces/setup evidence | ✅ Done — 67 scoped / 401 full-suite Python tests passed |
| Seal source-linked storyboards and reviewed narration | ✅ Done — 53 scoped tests; legacy inputs retained |
| Update author/reviewer workflow and ADR | ✅ Done — source-linked examples and real configured-model reviews |
| Package offline Heart speech and measured timeline | ✅ Done — 18 speech tests; actual constrained offline image smoke |
| Render variable slide chapters | ✅ Done — variable decks, source notes/transcript and actual browser/PDF checks |
| Encode narrated video and preserve partial outputs | ✅ Done — staged processes, measured timelines, real AAC/cut checks |
| Persist long-render policy/recovery/publication | ✅ Done — durable profiles, stable IDs, late/partial publication checks |
| Complete local/OCP engineering acceptance and prepare rollout | ✅ Done — 5m27 stress, reviewed-image OCP success; Drive/listening/activation gates pending |

Capture timing/frame regression and real offline failure recovery — ✅ 8 November 2026. Final long-render/cluster acceptance and rollout gates remain explicitly tracked in implementation-plan.md.

Independent whole-branch review corrections — ✅ 8 November 2026. Two Important findings fixed with failing-then-passing regressions; 482 Python tests at 86.24%, actual result-diagram browser tests pass. No Critical or Minor findings.

Engineering acceptance and controlled-rollout preparation — ✅ 8 November 2026. 482 Python tests/86.24%, actual image/browser/FFmpeg checks, local8/12-slide videos and restricted-v2 OpenShift completion verified. Exact measurements and image revisions are retained in docs/validation/kokoro-narration-2026-11-08.json. Drive invalid_grant, human listening and explicit merge/live-configuration approval remain rollout gates; no production publication is claimed.

Accepted refinements applied — ✅ 9 November 2026. Identity-bound pronunciation
lexicon, sentence `mov_text` captions from the measured timeline, a 3600s
narrated Job deadline keeping sealed 3120s descriptors valid, and a seal-time
duration estimate are implemented with tests: 493 Python tests at 86.44%, 39
Node checks, pinned Ruff and Pyright clean, caption mux confirmed against real
FFmpeg. The coverage exclusion was correctly rejected. Late-result collection
and asset-origin provenance were documented, not automated or invented. Details
in implementation-plan.md section 9.6. Human listening, pronunciation
confirmation, Drive credentials and merge approval remain gates.

External refinement review — ✅ 9 November 2026. Pronunciation lexicon (identity-bound),
sentence captions, a 3600s deadline for new narrated attempts, early duration
diagnostics and an explicit normal late-result collection flow are proposed
follow-ups. The 80% gate already passes at 86.24%; no coverage exclusion is
needed. Asset preparation already verifies committed pins; initial upstream
verification deserves accurate dated documentation, not an invented sign-off.
Review is complete; these proposed changes are not implemented by this review.

Date-free voice-over policy — ✅ 9 November 2026. Omit the PoC execution
date/timestamp from spoken text, including dates written in words; use "the
archived run" if historical context matters. Original evidence dates remain.
Authoring and independent-review guidance now enforce this content requirement.
The existing sealed demo remains unchanged pending a fresh reviewed render.

Fresh OpenShell run preflight — ✅ 9 November 2026. Worker built from current
engine commit 35f79ec, fresh application namespace/workspace/source branch, same
pinned NVIDIA source and configured Qwen model. Prior deployments/results remain
untouched. Deployment/testing/report/reviewed Kokoro rendering are in progress;
Drive refresh still fails, so generation and direct retrieval are distinguished
from cloud publication. Track execution in implementation-plan.md section 9.7.

- ✅ Fresh OpenShell final-content freeze (9.7.14.1): stopped extra content-worker
  review rounds, retained history, froze corrected evidence and compact six-slide
  candidate; final full-source review and layout preflight underway. Original
  five test outcomes are unchanged. Final media delivery remains pending.

- ✅ Final OpenShell approval/seal and canonical report persistence (9.7.14.2–3):
  six pages inspected, complete genuine full-source Qwen approval with zero
  blockers; date-free narration sealed as 15bd7f8c…3cdc7da. Corrected report
  append-only revision 40175095…7671dc saved. Final render-v5 dispatched;
  artifact retrieval/verification remains pending.

- ✅ Optional OpenShell blog content/reviews/artifact persistence (9.7.14.4): four
  real v3 reviews, 9.146/10 overall, sanitized Markdown/SEO/HTML appended as
  357bac0f…7f8aa2. Phase 11 validation/upload stays blocked: missing Vale config
  and existing Google authorization failure; neither is reported as passing.

- ✅ Final OpenShell generation/direct delivery (9.7.13.2): six-scene Heart video
  3m28s, 6248 frames; all five artifact hashes and complete media decode passed.
  Final PDF pages match inspected preflight; all six video scenes inspected.
  Original one execution/five passing attempts preserved. Measured renderer
  450.941s, 2.57GiB peak, 95,337,178 bytes scratch. Report and optional blog are
  appended to immutable fork artifact revisions. App/workspace retained.
  Receipt: docs/validation/openshell-kokoro-e2e-2026-11-09.json. Drive/Docs auth,
  optional blog Vale configuration and human listening remain explicit gates;
  production rollout and later branch refinements are not accepted by this run.

- ✅ Delivery-helper cleanup (9.7.15): temporary helper/publisher Jobs and Pods
  removed after receipt retention; healthy app and bound recovery PVC retained.

### OpenShell 3D regeneration — ✅ 9 November 2026

| Task | Status |
|------|--------|
| Author setup and original-five-check TopoLoop diagrams | ✅ 9.8.1 — evidence-linked candidate; speech and outcomes unchanged |
| Validate browser/PDF states and inspect the revised slides | ✅ 9.8.2 — final v10, 21 reset-based full-label states passed; two 3D pages inspected |
| Fresh independent review and immutable seal | ✅ 9.8.3 — genuine full-corpus Qwen approval, zero blockers; input 670eef1c…ce270ef |
| Render and verify revised slides/video, retain originals and stop helper | ✅ 9.8.4–5 — both 3D scenes, 3m28s video and five files verified; previous video retained, helper deleted |

3D regeneration: final v10 retains both TopoLoop scenes, every spoken sentence
and all original outcomes. Full browser/PDF checks plus independent remount-based
inspection passed 21 animation states. The latter compensates for the current
freeze-prop repaint limitation and checks complete node-label boxes. Product
follow-ups are recorded in implementation-plan.md 9.8.2; this run does not claim
those renderer-code fixes. Final media output verification remains pending.

- ✅ Actual 3D render (9.8.4.1): both graph scenes and five outputs generated;
  3m28s/6248 frames, 469.283s render, 3,399,409,664-byte peak. New files retrieved,
  six final PDF pages match preflight. Final playback/animation inspection pending.

- ✅ Final 3D delivery/cleanup (9.8.4–5): two animated TopoLoop scenes, 3m28s /
  6248-frame video, all five artifact hashes and full playback decode passed.
  Six PDF pages match preflight; inspected six video chapters, all five animated
  checks and three setup poses. Speech/date policy and original five passes
  unchanged. Receipt: docs/validation/openshell-kokoro-3d-2026-11-09.json.
  Temporary helper removed after retaining proof; app/PVC and prior video kept.
  Drive and listening gates remain; no production activation or product-code fix.

- ✅ Evidence-based tuning of the applied refinements (9.8), 9 November: lexicon
  rebuilt from spoken content (2/18 to 7/18 hard terms), duration guard
  recalibrated from the measured 2.05 words/second, Vale config discovery fixed
  and result counters ordered by outcome. 496 Python tests at 86.44%, 40 Node
  checks. Renderer capability gate and human listening remain open.

### Simple English for future voice-overs — ✅ 9 November 2026

| Task | Status |
|------|--------|
| Adapt ASD-STE100 principles for authoring/review without a controlled dictionary | ✅ 9.9.1 — short focused sentences, active voice, simple verbs, consistent technical terms; facts/caveats retained |
| Update the synthetic spoken example and verify its existing data contracts | ✅ 9.9.2 — seven entries, maximum ten words; evidence/story/scene checks passed |
| Preserve current media and document worker-build activation | ✅ 9.9.3 — all ten old artifact hashes unchanged; future videos only, next worker build required |

The user explicitly chose future videos only. Existing OpenShell scripts/videos
remain unchanged. Targets of 10–20 words per sentence, normally within 25, guide
writing rather than introduce a schema gate. Necessary technical vocabulary is
allowed; no formal STE compliance is claimed. No live rollout occurred.

### Presentation feedback discussion — ✅ Design/planning complete, 10 November 2026

| Task | Status |
|------|--------|
| Inspect actual presentation, narration timing and pronunciation support | ✅ 9.10.1 — definition missing from cover; five checks not named in speech; next-step speech begins about 20s into its slide; AutoPoC has no full-name override |
| Confirm audience and provide a visual storyboard | ✅ 9.10.2 — technical managers/customer engineers; interactive eight-scene mockup delivered |
| Agree revised story and visuals | ✅ 9.10.3 — storyboard direction approved; template must work for any repository/code host |
| Save generic design and proposed implementation plan | ✅ 9.10.4 — builder check complete; seven tasks documented; technical choices await review |
| Restore and verify OCP access | ✅ 9.10.5 — authenticated; existing OpenShell namespace active; permission to create Jobs confirmed; no workloads changed |
| Implement product changes and any new media revision | Not started — existing media/deployed settings unchanged |

Potential directions are recorded in implementation-plan.md 9.10.1. Scope
wording must distinguish coverage gaps from product failures. New source images
need offline, reviewed asset support. Existing delivered media is unchanged.

- ✅ Audience/storyboard exploration (9.10.2): interactive eight-scene visual
  proposal with paired simple-English narration, authentic source-page capture,
  optional concept-diagram opening, explicit five-check inventory, accurate
  coverage language and a separate takeaway before next tests. Eight desktop
  layouts inspected; native narrow-panel preview readable. Standalone backup:
  /home/aavraham/.codex/visualizations/2026/11/10/openshell-storyboard/.
  Existing ten media artifact hashes unchanged. Product implementation and new
  audio/video remain unstarted; final design agreement and pronunciation audition
  are still pending. Preview session credentials are not committed/exported.

- ✅ Generic design/planning (9.10.3–9.10.4): approved story direction explicitly
  generalized beyond OpenShell. Saved
  `docs/superpowers/specs/2026-11-10-generic-poc-storytelling-design.md` and
  `docs/superpowers/plans/2026-11-10-generic-poc-storytelling.md`; fresh builder
  check found no important unanswered questions. The seven-task proposal covers
  optional reviewed imagery/fallback, source-independent identity and check
  inventories, timed layouts, 3D verification, offline packaging/recovery and
  multi-project validation. Eight slides/five checks are reference examples,
  not template requirements. Schema/versioning and local asset staging are
  proposed engineering choices pending review. Implementation, pronunciation
  selection, new media and rollout remain unstarted.


## Phase 10: Generic storytelling implementation and fresh OpenShell cycle — ✅ Complete for local review delivery, 10 November 2026

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

Updated the vendored TopoLoop provenance note to retain the upstream base and
license attribution while documenting the local `TopoLoop.vue` lifecycle patch.
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
