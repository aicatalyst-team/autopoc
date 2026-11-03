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

- [ ] Add failing Node tests for revision-2 preparation, missing/tampered assets and copied source assets; implement deterministic asset verification/copying.
- [ ] Implement red opening, white content/conclusion, safe branded footer, local Display/Text/Mono faces, sentence case and an accessible renderer-owned TopoLoop palette.
- [ ] Add behavioral checks for scene font/image failures and overflow, preserving existing content/video failure distinctions; make PDF export and video capture use validated content.
- [ ] Copy assets/helper modules into the UBI image, run Node/Python checks, update both trackers and commit.

## Task 3: Visual acceptance and handoff

**Files:** Renderer/configuration/workflow docs, both project trackers, QA fixtures/scripts as needed.

- [ ] Render archived Omnigent evidence and a failed/incomplete fixture with the new renderer; inspect all PDF pages and representative MP4 frames, source/site asset contents and offline serving.
- [ ] Exercise long content, missing/max-size graphs and all status labels; revise layouts or report actionable failures.
- [ ] Run full supported Python suite, Node tests, pinned Ruff and Pyright. Build/test the UBI image and restricted OCP rendering if available; record actual limitations separately from local results.
- [ ] Obtain a fresh whole-branch review, resolve material findings with regression checks, update docs/trackers, commit and push the feature branch. Do not merge or change deployed image configuration without approval.

## Execution ledger

- User approved design and implementation; inline execution chosen for the tightly coupled renderer/version changes.
- Ruling: use the existing named feature branch/workspace and preserve unrelated `opencode.json`, `.coverage` and `uv.lock`; no second worktree is needed for these sequential changes.
- Pre-flight: Python wrapper forwards the same revision that Node validates; source allowlists must include every helper module referenced by the packaged renderer. Asset copying is shared by PDF/video/browser outputs.
- Task 1 complete: RED showed 13 expected boundary/archive failures; GREEN passed 35 input/render/recovery tests. Complete legacy output reuse remains possible without launching the new engine; fresh legacy rendering requires its original image. Helper modules are explicitly allowlisted and will be exercised with the real Node source in Task 2.
