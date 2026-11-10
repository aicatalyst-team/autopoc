# Generic PoC Storytelling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce understandable, visually varied presentations for arbitrary source repositories, with complete check coverage and narration aligned to visible content.

**Architecture:** Extend the existing evidence/review/seal/offline-render pipeline with explicit layout roles and optional hashed visual assets. Keep source-independent authoring and evidence-derived scenario metadata separate from trusted rendering. Preserve all legacy input contracts and artifact kinds.

**Tech Stack:** Python 3.12, existing standard-library ZIP/PNG checks, configured OpenCode model, Slidev/Vue/TopoLoop, Playwright, pinned offline Kokoro/Heart and ffmpeg.

**Spec:** [Generic PoC storytelling design](../specs/2026-11-10-generic-poc-storytelling-design.md).

Status: implementation authorized on 10 November 2026, followed by a fresh OpenShell full cycle. Execution is in progress; checkboxes and Phase 10 in both project trackers record current completion and measured acceptance. Engineering choices and later evidence-based refinements remain documented and reviewable.

## Global Constraints

- Narrative/input schema 3, template 4, input policy 2; retain (schema,template,policy) (1,1,1), (1,2,1), (2,3,1). Scene-plan schema stays 2. Evidence/sanitizer contracts stay unchanged.
- Existing ordered chapters; 6–30 slides, 1–4 bullet claims, at most 12 sentences/180 spoken words per slide, 900s resource guard. No fixed eight-slide/five-check/two-minute target.
- Every original final-inventory scenario appears once on testing/checks slides; at most five rows per slide. Exact outcomes derive from verified evidence. Empty inventory is explicit.
- Four optional PNGs maximum; 2 MiB per image; 4096 pixels per side; 16 million total decoded pixels; 8 MiB expanded visual ZIP; 24 MiB sealed inputs; 20 MiB evidence.
- Offline rendering, no automatic website fetch/crawler or new generation provider. Public contextual imagery is optional; no runtime screenshots in this increment.
- Preserve exact reviewed narration/transcript, simple technical English, no spoken execution dates and existing sentence captions. Existing delivered media stays unchanged.
- Heart `af_heart`, speed 0.95; measured sentence offsets; 3000s process/3600s Job; 2 CPU/4Gi; existing storage guards; expected completion after 300s worker wait.
- Never rerun PoC tests for media, infer a deployment for a library, soften real failures or treat project intent as an observed result.
- Complete tasks with both project trackers updated and a feature-branch commit. No default-branch push, merge, shared activation or cloud-publication claim.

## Review Focus

1. A GitLab CLI/Codeberg library without a homepage or UI still gets a clear opening and no fabricated infrastructure (Tasks 1, 3, 7).
2. Empty, mixed-outcome and larger inventories account for every scenario without invented results, overflow or hidden failures (Tasks 1, 3, 4).
3. A reviewed image changes, contains hidden metadata, is malformed or exceeds decompression limits: reject before synthesis; unavailable optional imagery uses a pre-review fallback (Tasks 2, 3, 4).
4. A seek, repeated freeze timestamp or changed slide displays the correct highlight and actual TopoLoop pose; subtitles/captions never overlap (Tasks 4, 5).
5. Legacy inputs and late recovery remain valid while template 4 uses narrated budgets and all immutable assets survive packaging/recovery (Tasks 2, 6, 7).

## File and responsibility map

- `src/autopoc/executive_story.py`, `renderer/storyboard.mjs`: explicit schema dispatch and cross-language story/layout/check validation.
- New `src/autopoc/executive_visuals.py`: local PNG/manifest validation and deterministic ZIP creation; no network client.
- `src/autopoc/executive_inputs.py`, `src/autopoc/executive_cluster.py`: versioned sealing/verification and existing CLI integration.
- `.opencode/skills/run-poc/references/executive-narration.md`, `executive-summary.md`: generic author/reviewer rules, staged assets, fallback and content alignment.
- `renderer/components/ExecutiveSlide.vue`, new `ExecutiveChecks.vue`, `renderer/style.css`: trusted layouts and timed check highlighting.
- `renderer/render.mjs`, `renderer/scene-validation.mjs`, vendored `TopoLoop.vue`: preparation/decode, pose lifecycle, complete visual inspection.
- `src/autopoc/executive_render.py`, `executive_policy.py`, `executive_job.py`, `executive_speech.py`: format integration, derived data, narration and output packaging without changing legacy behavior.
- Existing Python/Node executive test modules plus new `tests/test_executive_visuals.py`: meaningful contract and browser tests. Extend synthetic fixtures under `tests/fixtures/executive-story/`; never rewrite archived evidence.
- `docs/adr/0015-reviewed-local-executive-visuals.md`, configuration/renderer docs and validation record: architecture, operator recipe and measured acceptance.

## ✅ Task 1: Define and validate generic story roles and check coverage

**Files:** modify `src/autopoc/executive_story.py`, `renderer/storyboard.mjs`, `tests/test_executive_story.py`, `renderer/storyboard.test.mjs`; add schema-3 cases to executive-story fixtures.

**Interfaces:** keep `validate_story(narrative: dict, evidence_index: dict, members: dict) -> None` and `validate_scene_plan(plan: dict, narrative: dict) -> None`. Extend `validateStoryboard(narrative, plan)` to schemas 2 and 3 using exact version dispatch. Add `derive_checks(evidence_index: dict) -> dict`, returning `{schema_version: 1, run_id, results: [...]}` from `final_results.results` with original scenario ID/name/status; no authored replacement results. Schema-3 additions are exactly those in the spec.

- [x] Add failing Python/Node cases for source-host-independent identity, null optional metadata, two/one-component graphs, graphless CLI/library, first-slide visible definition, valid contiguous chapters and unchanged schema-2 stories.
- [x] Add inventory cases with 0, 1, 5, 6 and 11 scenarios, mixed statuses, duplicate/missing/unknown IDs, invalid sentence mappings, more than five rows, wrong sections and unknown layout/visual combinations. Six/eleven checks paginate; an empty set requires explicit no-checks content. Prevent overlapping row mappings.
- [x] Run `pytest tests/test_executive_story.py -q` and `node --test renderer/storyboard.test.mjs`; confirm new tests fail for missing behavior, then implement shared constraints and deterministic derivation. Evidence-backed identity definition and labels use existing selector validation.
- [x] Re-run those tests; include long inventories that violate the existing lower-bound duration estimate to prove impossible scripts fail before synthesis. Measured duration remains authoritative for scripts that pass the estimate. Document schema-3 fields in fixture README; update trackers and commit.

Task 1 review fix round 1: malformed hostname parity verified (89 focused Python,
66 storyboard; full 545 Python / 87 renderer passed, five browser skips).

Task 1 review fix round 2: complete decoded forbidden-domain character set
covered in both languages; valid IPv6 retained (110 focused Python / 87 storyboard;
full 566 Python / 108 renderer passed, five browser skips).

## Task 2: ✅ Package optional visuals and bind them to review

**Files:** create `src/autopoc/executive_visuals.py`, `tests/test_executive_visuals.py`; modify `src/autopoc/executive_inputs.py`, `src/autopoc/executive_cluster.py`, `tests/test_executive_inputs.py`, `tests/test_executive_cluster.py`; create ADR 0015.

**Interfaces:** `prepare_visuals(manifest_path: Path, output_path: Path) -> Path` reads explicitly named regular files adjacent to the local manifest and emits deterministic `visuals.zip`. `verify_visuals(path: Path, *, run_id: str, claim_ids: set[str]) -> dict` returns the validated manifest. Add `autopoc-tools executive-visuals --manifest PATH --output PATH`; extend `seal_inputs(..., visuals_path: Path | None = None)` and `executive-seal --visuals PATH`. `verify_inputs(path)` returns `visuals` (manifest or null) alongside its existing values. Schema-3 always includes an archive, including an empty one. Legacy exact member sets remain unchanged.

- [x] Add failing archive/CLI tests for zero/four assets, deterministic bytes, valid provenance, stale review/hash, wrong run/claim ID, unexpected ZIP members, duplicate keys/entries, symlinks, traversal, extension/content mismatch, PNG CRC/geometry errors, hidden PNG text/EXIF, oversized dimensions and compressed/expanded budgets. Bound input reads before decompression; avoid loading unbounded PNG data.
- [x] Run `pytest tests/test_executive_visuals.py tests/test_executive_inputs.py tests/test_executive_cluster.py -q`; implement PNG structural validation, sanitized manifest fields and safe ZIP handling with existing dependencies. Reject supplied invalid assets; do not silently edit bytes or drop them after review.
- [x] Add exact (3,4,2) envelope support, six-payload hashing and required schema-3 review `visuals_sha256`. Verify narrative visual IDs against the manifest and asset claim references against narrative claims. Preserve exact legacy allowlists and hash rules.
- [x] Re-run scoped tests; prove schema-2/template-3 and schema-1/template-2 fixtures remain verifiable, schema downgrade/unknown versions fail, and a changed visual requires review. Record ADR tradeoffs (optional staged capture, offline recovery, no text-only pixel-review claim); update trackers and commit.

## Task 3: Author and review a generic story with useful visual fallbacks

**Files:** modify `.opencode/skills/run-poc/references/executive-narration.md`, `executive-summary.md`, `docs/configuration.md`, `tests/fixtures/executive-story/README.md`; add three synthetic worked schema-3 stories and provenance manifests.

**Interfaces:** consumes verified evidence, source metadata/excerpts and optional staged public PNGs. Produces schema-3 narrative, scene-plan schema 2, optional-assets archive and exact hash-bound review for Task 2. Uses the existing configured OpenCode model; no new provider or acquisition service.

- [ ] Write author instructions for source-linked visible project definition, intended-versus-tested distinction, inventory pagination, truthful outcomes/coverage, evidence-grounded topology and concise takeaway/next-actions alignment. Explain that any open-source code host is acceptable; URL parsing never infers a GitHub API or project type.
- [ ] Specify optional capture staging: use an available tool for a public source/docs/homepage capture, inspect for visible private data, provide attribution and capture provenance, or record a gap and use the identity text/diagram fallback before review. No fabricated app UI or assumption that browser tools exist in the worker. Include exact `executive-visuals`, review-hash and `executive-seal --visuals` recipe.
- [ ] Extend the independent review checklist to reject missing definitions/scenarios, unmatched row speech, unsupported failure/success claims, “unproven” used as a defect without evidence, long recap on a next-actions slide, unsupported asset assertions and spoken dates. Text-only review checks manifest/captions/sources; document actual visual inspection separately.
- [ ] Author a synthetic GitHub service with imagery, GitLab CLI without a UI and Codeberg/self-hosted library without topology. Include a failed and an incomplete scenario, an empty inventory case and unversioned-doc context. Validate them through Tasks 1–2, and read the instructions against each story; do not add tests that merely search prose for strings. Update trackers and commit.

## ✅ Task 4: Render reusable identity, check and summary layouts

**Files:** modify `renderer/components/ExecutiveSlide.vue`, `renderer/style.css`, `renderer/render.mjs`, `renderer/scene-validation.mjs`, `renderer/browser.test.mjs`; create `renderer/components/ExecutiveChecks.vue` and `renderer/check-timing.mjs` with `renderer/check-timing.test.mjs`.

**Interfaces:** browser consumes validated narrative, manifest, derived `checks.json` and existing measured timeline. Add pure `checkWindows(slide, sceneTimeline)` returning `{scenario_id, start_seconds, end_seconds}[]`: each boundary is `scene.start_seconds + 0.35 + sentence_offset`, because offsets start at speech rather than scene start. Add `activeCheck(windows, elapsedSeconds) -> scenario_id | null` with half-open windows. Reuse existing playback/reset events; add a single documented playback-clock event only if current recording does not expose elapsed seconds, with symmetrical listener cleanup.

- [x] Add failing browser tests proving the opening visibly defines each fixture, missing optional imagery renders a source card, image/caption/attribution remain legible, all five outcome classes are shown, and 6/11 checks paginate without tiny fonts or omitted rows.
- [x] Add pure measured-timeline cases for lead-in, sentence gaps, final boundary, scene change and backwards seek. Reject missing/nonfinite/out-of-scene offsets and overlapping windows. Highlight exactly the current row; show all rows without transient highlight in PDF/print mode.
- [x] Implement schema-3 trusted layouts and check component while preserving template-3/default legacy behavior. Copy only verified assets into local public paths; no arbitrary HTML, remote image URLs or user code. Fully decode images and run browser/layout preparation before speech. A referenced asset failing decode is a hard failure, not a late silent fallback.
- [x] In the browser-capable renderer environment run `AUTOPOC_BROWSER_INTEGRATION=1 node --test renderer/storyboard.test.mjs renderer/check-timing.test.mjs renderer/browser.test.mjs` from the repository root. Browser tests must execute, not skip. Inspect all new layouts at 1280×720 and PDF size, including long names/captions; assert readable bounds and image load failures stop before speech. Update trackers and commit.

## Task 5: ✅ Make 3D inspection repaint and catch complete label collisions

**Files:** modify `renderer/vendor/topoloop/src/TopoLoop.vue`, `renderer/scene-validation.mjs`, `renderer/browser.test.mjs`; add a synthetic collision fixture.

**Interfaces:** retain `freezeAt` prop, `executive-still` event and `sceneCheckTimes(graph)`. Extend `inspectScene()` diagnostics without weakening existing checks. Updating freeze time must paint the requested state while paused; releasing freeze resumes one animation loop; unmount cancels it.

- [x] Add a failing browser test that sets three different freeze times on the same mounted graph and checks distinct visible act/pose state, then releases freeze/re-enters/tears down without duplicate animation loops. Remounting between every sample must not conceal the regression.
- [x] Add fixtures where subtitle-to-subtitle, group-caption-to-node and heading-to-label collisions fail, while intentional node body/graph links remain permitted. Exercise every timestamp returned by `sceneCheckTimes`, not just the first pose.
- [x] Fix the Vue lifecycle/watch scheduling and complete text/caption bounds/intersection checks. Preserve real 3D TopoLoop for evidence-supported setups; graphless projects remain graphless. Leave documented illustrative timing caveats intact.
- [x] In the browser-capable renderer environment run `AUTOPOC_BROWSER_INTEGRATION=1 node --test renderer/browser.test.mjs` from the repository root; inspect passing multi-act frames plus failing diagnostics. Do not blanket-shrink text or expand tolerances to pass. Update trackers and commit.

## Task 6: ✅ Integrate template 4 with offline speech, packaging and recovery

**Files:** modify `src/autopoc/executive_render.py`, `executive_policy.py`, `executive_speech.py`, `executive_job.py`, `renderer/render.mjs`, `renderer/README.md`, `Dockerfile`, `Dockerfile.executive`, `tests/test_executive_render.py`, `test_executive_speech.py`, `test_executive_job.py`, `test_executive_cluster.py` as required; create `scripts/autopoc-tools` and `tests/test_cli_tools_entrypoint.py`; inspect CLI/cluster schema assumptions.

**Interfaces:** retain `render_executive(inputs_path, output_dir, *, timeout=None) -> dict`. Template 4 uses the narrated preparation/speech/record sequence and policy. Derive `checks.json` through Task 1 after input verification. Unpack Task 2 assets into controlled local paths. Add manifest/assets/checks/new trusted modules to executable-source and browser ZIPs; do not change the five published artifact kinds.

- [x] Reproduce the observed worker CLI gap with a process-entrypoint test, then package a minimal `scripts/autopoc-tools` shim (`exec python3 -m autopoc.cli_tools "$@"`) in `Dockerfile`. The existing image exposes the source module but lacks its advertised executable. Keep the shim on the same branch source/PYTHONPATH; no new dependency or provider. Task 7 validates it in the actual worker image.
- [x] Add failing integration cases proving template 4 receives narrated budgets, validates/decode-checks before starting speech, uses exact reviewed sentences, packages assets/checks, preserves captions and never makes a remote request. Retain template-3/schema-2 and silent template-2 regression cases.
- [x] Implement explicit version dispatch everywhere that currently assumes `schema == 2` or `template == 3`; search all Python/renderer call sites, including scene-plan validation, speech transcript and input-image compatibility. Keep preparation, speech and recording sequential.
- [x] Add durable late-completion/recovery tests with asset hashes and derived check data: time out worker wait, finish render, reconcile once, preserve all artifact checksums, and reject altered input/output bytes without rerunning scenarios. Keep old sealed 3120s descriptors valid while new Jobs use 3600s.
- [x] Run `pytest tests/test_executive_render.py tests/test_executive_speech.py tests/test_executive_job.py tests/test_executive_cluster.py -q` and renderer tests. Verify source ZIP rebuild uses only included files. Update trackers and commit.

## Task 7: Audition pronunciation and validate generic outputs before rollout

**Files:** modify `src/autopoc/kokoro_lexicon.json` only after a listening choice, `tests/test_executive_speech.py`, `docs/configuration.md`, `docs/report-presentation-plan.md`, `renderer/README.md`; create `docs/validation/generic-poc-storytelling-<actual-date>.json`; update both trackers.

**Interfaces:** consumes all preceding tasks and a newly built, digest-pinned renderer. Produces measured local/image acceptance records, audition samples, proposed pronunciation entry if selected and clear rollout status. Worker guidance needs a new worker image; updating checkout files does not update an existing deployed worker.

- [ ] Generate short Heart samples for the full name with “auto P-O-C” and “auto pock” in realistic sentences, using the actual pinned engine. Present them for listening/selection; retain scripts, lexicon hashes and audio. Do not choose an unlistened variant or mark this substep accepted while pending. After selection, test whole-name matching, standalone PoC, unchanged transcript and sealed lexicon hash invalidation.
- [ ] Render the three synthetic source-host/project-type cases offline through the actual renderer image, including imagery/fallback, mixed results, empty inventory and no topology. Use fake speech for fast browser regressions, but at least one actual Heart render for media acceptance. Do not rerun actual PoC checks or refetch assets to make these renders pass.
- [ ] Inspect PDF pages and video frames at scene transitions, check highlight boundaries and every inspected TopoLoop pose. Confirm next-action speech begins within the normal 0.35s lead-in when its scene appears, captions match exact narration, and identity remains understandable without audio. Record human visual/listening status honestly.
- [ ] Run `make lint`, `make typecheck`, `make test`, `make test-renderer` and the renderer-image smoke test. In the browser-capable image, also run `AUTOPOC_BROWSER_INTEGRATION=1 node --test renderer/browser.test.mjs` with mounted fixtures and trusted modules. The smoke test must run `autopoc-tools executive-render --inputs /absolute/render-inputs.zip --output-dir /absolute/output` on a newly sealed schema-3 input with network disabled and actual Heart assets. Keep the 80% coverage gate; real optional Torch adapter uses its documented image smoke validation. Fix relevant failures and repeat only affected checks after fixes.
- [ ] Record image digests, source revision, resource measurements, output hashes, version compatibility and outstanding permissions/listening/activation gates. Existing OpenShell media remains unchanged unless separately requested. Update both trackers, commit and push the feature branch; do not merge or activate shared settings. Report any pending human audition/Drive/live acceptance rather than calling rollout complete.
