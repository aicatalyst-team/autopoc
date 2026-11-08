# Red Hat presentation branding implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this approved plan continuously. Track completion in this file and both project planning files.

**Goal:** Make repository-contained Red Hat branding the default for new executive decks, PDFs and silent videos.

**Architecture:** Keep trusted Slidev/TopoLoop rendering and the six existing scenes. Package local fonts/logos with a shared branded shell; use sealed template revision 2 while preserving verification/recovery of revision 1 through its pinned image.

**Tech Stack:** Vue, CSS, Node/Slidev/Playwright, Python, UBI/FFmpeg.

**Spec:** `docs/superpowers/specs/2026-11-03-red-hat-presentation-branding-design.md`, approved by the user on 3 November 2026.

## Global constraints

- All branding resources are committed; no runtime external font/image downloads.
- Preserve six factual scenes, original evidence and durations; no PoC replay.
- Corporate artwork remains unmodified, with local licenses/provenance.
- New template revision 2 must not silently restyle revision-1 sealed inputs.
- Only feature-branch pushes are authorized; merging requires user approval.

## Review focus

- Missing/tampered fonts or logos: reject before rendering rather than silently fall back.
- Long names, claims, references and limitations: wrap within safe regions or fail clearly; never drop factual text.
- Legacy seals and output reuse: retain revision-1 validation and pinned recovery; reject v1 rendering in the v2 engine.
- Offline browser/source packages: include fonts, logos, notices, theme and runtime helper files, without external symlinks.
- Scene errors and capture failures: broken content invalidates the deck/PDF; encoding-only failure preserves them.

## Task 1: Seal and package template revision 2

**Files:** `src/autopoc/executive_inputs.py`, `executive_render.py`, `executive_cluster.py`; `tests/test_executive_inputs.py`, `test_executive_render.py`.

**Interfaces:** `seal_inputs(..., template_version=2)` writes the sealed revision; `verify_inputs` accepts 1/2. The v2 wrapper rejects legacy rendering before launching Node, forwards `versions.json`, and preserves brand assets/helper modules in editable source archives.

- [x] Add tests proving default revision 2, explicit revision-1 verification, unsupported revision refusal and local legacy render refusal.
- [x] Watch the new tests fail; implement the version boundary and `--template-version` CLI option.
- [x] Add archive assertions for local brand assets, notices and sealed version metadata; watch failures and fix allowlists.
- [x] Run affected Python tests; update both trackers and commit.

## Task 2: Branded offline slide shell and scene validation

**Files:** `renderer/components/ExecutiveSlide.vue`, `renderer/style.css`, `renderer/render.mjs`, new trusted `renderer/branding.mjs`/`renderer/scene-validation.mjs`, `renderer/render.test.mjs`, `Dockerfile.executive`.

**Interfaces:** `prepareDeck` validates revision 2 and hash-pinned local assets, copies them to `public/brand`, writes local font configuration and trusted components/theme. Browser checks await required faces/images and report layout overflow before publication.

- [x] Add failing Node tests for revision-2 preparation, missing/tampered assets and copied source assets; implement deterministic asset verification/copying.
- [x] Implement red opening, white content/conclusion, safe branded footer, local Display/Text/Mono faces, sentence case and an accessible renderer-owned TopoLoop palette.
- [x] Add behavioral checks for scene font/image failures and overflow, preserving existing content/video failure distinctions; make PDF export and video capture use validated content.
- [x] Copy assets/helper modules into the UBI image definition, run Node/Python checks, update both trackers and commit.

## Task 3: Visual acceptance and handoff

**Files:** Renderer/configuration/workflow docs, both project trackers, QA fixtures/scripts as needed.

- [x] Render archived Omnigent evidence and a failed/incomplete fixture; inspect PDF pages, MP4 frames, source/site assets and offline serving.
- [x] Exercise long content, missing/max-size graphs and all status labels; revise layouts or fail clearly.
- [x] Run the full supported checks and build/test the constrained UBI image; record OCP acceptance as pending registry publication separately from local results.
- [x] Obtain independent review, resolve material findings with regressions, update trackers, commit and push the feature branch. No merge or deployment configuration change.

## Execution ledger

- User approved design and implementation; inline execution chosen for the tightly coupled renderer/version changes.
- Ruling: use the existing named feature branch/workspace and preserve unrelated `opencode.json`, `.coverage` and `uv.lock`; no second worktree is needed for these sequential changes.
- Pre-flight: Python wrapper forwards the same revision that Node validates; source allowlists must include every helper module referenced by the packaged renderer. Asset copying is shared by PDF/video/browser outputs.
- Task 1 complete: RED showed 13 expected boundary/archive failures; GREEN passed 35 input/render/recovery tests. Complete legacy output reuse remains possible without launching the new engine; fresh legacy rendering requires its original image. Helper modules are explicitly allowlisted and will be exercised with the real Node source in Task 2.
- Task 2 complete: RED showed four Node failures and the Python static-deck publication regression; GREEN passed seven Node and 25 input/render tests. Real browser preflight and PDF generation passed on archived Omnigent data after adding heading ink clearance. The host lacks Playwright's recording FFmpeg binary; installing that prerequisite before video acceptance. No original tests were replayed.
- Ruling: preflight every browser scene before PDF export and only package a static deck marked validated by the engine. This closes an existing wrapper gap that otherwise published invalid static output after a scene-content failure.
- Final review: independent reviewer found one important issue and no critical/minor issues: diagram labels and late log states could be clipped despite passing validation.
- Final: fixed diagram bounds and late-state validation — browser oversized-diagram regression and Node animation-sampling regression RED→GREEN; all eight Node tests pass. Production preflight now samples the PDF still, every act's start/middle/end and every original log event; graph labels, HUD, statuses, boards, logs and facts receive visible-region checks. The archived Omnigent render passes all timed checks after terminal layout correction.
- Final: suite 379/379 passed, 85.62% coverage. Real-browser acceptance passed six scenes plus oversized claims/titles/counts/diagram labels, missing fonts/images and zero external requests.
- Final: Ruling: restricted OCP publication/rollout is separate from local code acceptance; a new registry digest must be published and validated before deployment. Existing deployment configuration remains unchanged; no cluster success is inferred from local containers.
- Final: Ruling: unrelated opencode.json, .coverage and uv.lock remain excluded from the change, as requested by project scope.
- Task 3 complete (local implementation acceptance): UBI image `d8e792a29858`, local digest `sha256:cf628a4323262e6ee152e7b9825f5705c8b8cac76cf9e34d5143f12eb9bc53ac`, rendered original Omnigent evidence in 213.81s, peak memory 2,504,695,808 bytes and scratch 45,614,563 bytes under 2 CPUs/3 GiB/4 GiB scratch, read-only root, no network and UID28128/group0. Six-page PDF and silent120s H264/1280x720/30fps MP4 verified. All artifact hashes and both archives' 13 brand-file hashes checked; extracted source successfully prepares another deck. OCP rollout remains open.
- Handoff: [draft fork PR #3](https://github.com/aviavraham/autopoc/pull/3), branch `codex/red-hat-presentation-branding`; no default-branch merge or deployment configuration change.
