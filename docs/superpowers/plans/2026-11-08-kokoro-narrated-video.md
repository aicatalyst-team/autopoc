# Evidence-based slides and Kokoro narration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate evidence-backed executive slides and Heart narration whose
length follows the PoC, preserving offline rendering and durable recovery.

**Architecture:** OpenCode extracts a fact ledger and authors/reviews a versioned
storyboard from verified original evidence. A separate renderer Job prepares
deck/PDF, runs offline Kokoro in a subprocess, then records/muxes scenes using
measured audio timings. Preserve legacy silent inputs and the existing five
published artifact kinds.

**Tech Stack:** Python 3.12, existing OpenCode author/reviewer, Kokoro/Misaki,
CPU Torch, spaCy English assets, Slidev/Vue/TopoLoop, Chromium, FFmpeg/ffprobe,
UBI 9, existing immutable Git/Drive checkpoints and OpenShift Jobs.

**Spec:** [Evidence-based slide text and Kokoro narration](../specs/2026-11-08-kokoro-narrated-video-design.md).

## Global Constraints

- Voice: `af_heart`, American English, speed 0.95, two Torch threads, 24kHz mono PCM.
- Do not rerun PoC tests, invent missing traces or conflate planned/observed/inferred behavior.
- Troubleshooting belongs only when it explains outcome, adoption constraints or recommendation.
- The configured OpenCode model authors and independently reviews all visible/spoken factual claims.
- Schema-1 evidence and narrative/template-1/template-2 recovery remain compatible; new narrative/input schema 2 uses template 3.
- No content-model calls, speech API calls, model downloads or dependency installation during offline rendering.
- Six required chapters: objective, testing, setup, results, limitations, recommendation; optional execution between setup/results; repeated sections contiguous.
- Bounds: 6–30 slides; title 100 characters; 1–4 visible claims/slide; ledger claim 280 characters; at most 12 sentences/180 spoken words per slide; graph 12 nodes/20 edges/5 acts per slide.
- Timing: 0.20s between sentences; `max(6.0, audio_seconds + 0.35 + 0.65)` per scene; 120s/scene, 900s total operational bounds; fail explicitly rather than clip or accelerate.
- Evidence limits: 32 supplemental records, 512KiB original bytes each, existing 20MiB total; sealed inputs remain 24MiB.
- Template-3 output limits: 512MiB source ZIP and 1GiB video; retain five top-level artifact kinds.
- Template-3 provisional resources: 2 CPU, 4Gi memory, 8Gi scratch, 10Gi ephemeral storage, 3000s render timeout, 3120s Job deadline; Job deadline upper bound 3600s.
- Worker wait stays 300s by default, allowable 0–600s; durable late reconciliation handles longer videos.
- Opt in with `AUTOPOC_EXECUTIVE_NARRATION=kokoro` and a compatible digest-pinned image; unset/`none` keeps the current silent path.
- Generate renderer dependencies from `renderer/pyproject.toml` with hash-pinned `renderer/requirements.lock`; never hand-edit locks or add speech dependencies to the worker.
- Update both `.opencode/plans/implementation-plan.md` and `.opencode/plans/plan.md` at every task completion, and commit each independently verifiable task. Feature branches only; user approval before merge/live configuration changes.

## Review Focus

1. An authoritative-looking final report conflicts with original outcomes: disclose/qualify the conflict and retain exact structured totals (Tasks 2–3).
2. A supplied trace/log belongs to another run or contains credentials, or a cited selector does not exist: reject the supplied input/reference without weakening sanitization (Tasks 1–2).
3. Offline first render has empty writable caches or missing packaged English/voice assets: produce a clear partial result without attempting a download (Tasks 4, 6, 8).
4. A long final sentence/diagram scene crosses the previous three-minute or six-slide boundary: retain all speech, visible caveats and proper scene alignment (Tasks 5–6, 8).
5. Worker restart or changed environment during a late render causes duplicate Jobs, changed policy or lost partial outputs: resume the persisted image/profile/attempt and retain valid artifacts (Tasks 6–7).

## File map and implementation boundaries

- `src/autopoc/evidence_supplemental.py` (new): supplemental staging descriptor, selected-field normalization and sanitizer/provenance checks.
- `src/autopoc/evidence.py`: versioned inclusion/verification of supplemental evidence; existing core result calculations stay authoritative.
- `src/autopoc/executive_story.py` (new): narrative-2, source-selector and scene-plan validation; no LLM or Torch imports.
- `src/autopoc/executive_inputs.py`: v1/v2 envelope compatibility, exact review binding and immutable sealing.
- `src/autopoc/executive_speech.py` (new): optional lazy Kokoro adapter, offline asset verification, sentence/scene audio and measured timeline.
- `src/autopoc/executive_render.py`: sequential stage orchestration, source packaging, partial results and timeout control.
- `src/autopoc/executive_job.py`, `src/autopoc/executive_cluster.py`, `src/autopoc/tools/google_drive_tools.py`: version-specific durable profiles, publication/recovery and bounded outputs.
- `renderer/storyboard.mjs`, `renderer/audio.mjs` (new): template-3 data validation/scene mapping and fixed-argument FFmpeg recording/mux checks.
- `renderer/render.mjs`, `renderer/components/ExecutiveSlide.vue`, `renderer/scene-validation.mjs`, `renderer/check-layout.mjs`, `renderer/style.css`: dynamic slides and explicit preparation/recording stages; preserve revision-2 behavior.
- `renderer/pyproject.toml`, `renderer/requirements.lock`, `renderer/assets/kokoro/manifest.json`, `renderer/assets/kokoro/README.md`, `renderer/assets/kokoro/LICENSES.md` (new): renderer-only dependencies, pinned asset inventory and provenance; weights stay out of Git.
- `scripts/prepare-kokoro-assets.py` (new), `Dockerfile.executive`, `renderer/entrypoint.sh`, `Makefile`, `.github/workflows/ci.yml`: build-time verified installation and offline smoke checks.
- `tests/test_evidence_supplemental.py`, `tests/test_executive_story.py`, `tests/test_executive_speech.py`, `tests/executive_fixtures.py`, `renderer/storyboard.test.mjs`, `renderer/audio.test.mjs` (new), plus existing evidence/input/render/job/cluster/Drive/skill tests: boundary and integration checks.
- `.opencode/skills/run-poc/references/executive-summary.md`, relevant evidence staging sections of `.opencode/skills/run-poc/SKILL.md`, `docs/configuration.md`, `docs/report-presentation-plan.md`, `renderer/README.md`, `AGENTS.md`: authoring, operation and measured rollout status.
- `docs/adr/0014-offline-kokoro-narration.md` (new during implementation): architecture decision and alternatives.

### Task 1: Make retained logs, traces and setup evidence available for citation

**Files:** new `src/autopoc/evidence_supplemental.py`, `tests/test_evidence_supplemental.py`;
modify `src/autopoc/evidence.py`, `tests/test_evidence.py`, `tests/test_evidence_cli.py`,
phase-time evidence staging in `.opencode/skills/run-poc/SKILL.md` and the executive reference.

**Interfaces:**
- Keep `create_bundle(state_path, attempt_index_path, output_dir)` behavior unchanged without options; add keyword-only `supplemental_index: Path | None = None`.
- Add `collect_supplemental(index_path: Path, *, root: Path, run_id: str) -> tuple[dict[str, bytes], dict]` in the new module. It returns sanitized archive members and a public descriptor; input hashes/private paths never enter the public descriptor.
- `verify_bundle(Path) -> dict` accepts evidence schemas 1 and 2; the same final-results computation remains the only source of totals.
- Public schema-2 descriptor records use `id`, `kind`, `member`, `sha256`, `provenance`, optional `execution_id`/`scenario_id`; original descriptor uses `path` instead of `member`. CLI adds `--supplemental-index PATH`.

- [x] **Step 1: Write failing evidence/CLI tests.** Use existing `tests.test_evidence.setup_run` for core state/attempts. Add `test_supplemental_roundtrip_preserves_totals`, asserting schema 2, a sanitized `supplemental/build-1.txt` member and unchanged `{"pass":1,"fail":0,"error":0,"skip":0,"incomplete":0}`. Add parameterized rejection tests for another run, unknown execution/scenario, traversal/symlink, wrong hash, duplicate ID, unsafe text and 33 records/512KiB+1 bytes. Assert optional absent sources become gaps without invented members; an explicit supplied bad descriptor fails.
- [x] **Step 2: Run the new tests and confirm failure.** `python -m pytest tests/test_evidence_supplemental.py tests/test_evidence_cli.py -q --no-cov`; expected failure is missing option/schema support.
- [x] **Step 3: Implement supplemental collection and verification.** Allow only `log`, `trace`, `deployment`, `analysis`, `test_definition`; normalized UTF-8 text/JSON under the staged root. Deployment export keeps only resource kind/name, component links, declared resource/storage/security settings and observed status; remove Secret objects, Secret values, environment values and pod annotations. Trace export keeps identifiers, parent relations, service/operation, timestamps/durations/outcomes; strip headers, bodies, arbitrary attributes. Reject malformed or mixed-run records. Extend exact-member validation only for descriptor-declared entries, and retain original attempt/history checks. Save deliberate excerpt provenance instead of truncating.
- [x] **Step 4: Verify the boundary and legacy behavior.** Run `python -m pytest tests/test_evidence.py tests/test_evidence_supplemental.py tests/test_evidence_cli.py -q --no-cov`; expect all pass, including schema-1 deterministic roundtrip. Document how phases stage supplemental files without replaying tests or querying new trace services.
- [x] **Step 5: Update trackers and commit.** Commit message: `feat: retain sanitized supplemental PoC evidence`.

### Task 2: Seal evidence-backed storyboards and reviewed narration

**Files:** new `src/autopoc/executive_story.py`, `tests/test_executive_story.py`,
`tests/executive_fixtures.py`; modify `src/autopoc/executive_inputs.py`,
seal registration in `src/autopoc/executive_cluster.py`, `tests/test_executive_inputs.py`.

**Interfaces:**
- `validate_story(narrative: dict, evidence_index: dict, members: dict[str, bytes]) -> None`; enforce narrative schema 2, exact totals and source/claim/section consistency.
- `validate_scene_plan(plan: dict, narrative: dict) -> None`; enforce ordered IDs, `narration` identity and exact timing policy. Scene-plan schema is 2 with `slide_ids`, `narration`, `timing_policy`; no final duration guesses.
- Sources are strings: `member`, `member#LSTART-LEND` for text, `member#/json/pointer` for JSON. Resolve selectors against actual sanitized bytes, with RFC 6901 escaping and nonempty/in-range selections. No URL/private-path references.
- Add `make_v3_input(root: Path, *, slides: int = 6) -> Path` to `tests/executive_fixtures.py`; builds a valid run, ledger, scene plan, computed review and sealed template-3 ZIP. A helper `v3_documents(root: Path) -> tuple[Path, Path, Path, Path]` returns evidence/narrative/scenes/review before sealing for mutation tests.
- `seal_inputs(..., template_version: int | None = None)` derives 2 for narrative-1 and 3 for narrative-2 when omitted; explicit 1/2/3 remains validated. `verify_inputs` preserves legacy acceptance and rejects unknown combinations. `CURRENT_TEMPLATE_VERSION=3` must not accidentally make silent narrative-1 inputs template 3.

- [x] **Step 1: Write failing narrative/seal tests.** Include a source-backed eight-slide narrative and test mutations of counts, an unsupported narration sentence, unknown claim ID, missing chapter, reordered/duplicate slide, invalid selector, absent-trace reference, title/graph references and script changed after review. Each must raise `ValueError`; valid narrative-2 returns a verified template-3 package.

```python
def test_v3_seal_preserves_identity(tmp_path):
    result = verify_inputs(make_v3_input(tmp_path, slides=8))
    assert result["versions"]["schema"] == 2
    assert result["versions"]["template"] == 3
    assert len(result["narrative"]["slides"]) == 8
```

- [x] **Step 2: Run new tests and confirm failure.** `python -m pytest tests/test_executive_story.py tests/test_executive_inputs.py -q --no-cov`; expected failure is absent schema-2 support, not a fixture/import unrelated error.
- [x] **Step 3: Implement contracts and binding.** Check factual sentence `claim_ids`, all reference selectors and graph/title sources; classify claims as `planned`, `observed`, `inferred`, `recommendation`. Keep conflicts/gaps in narrative. Validate duplicate keys/nonfinite numbers/booleans-as-numbers, text sanitization and all global bounds. Narrative-2 review uses schema 2 and hashes exact narrative, evidence and scenes bytes; input index/versions use schema 2/template 3, same six ZIP members and 24MiB bound. Legacy reviews retain schema-1 semantics.
- [x] **Step 4: Verify compatibility.** Run the Task 2 command plus `tests/test_executive_cluster.py` with `--no-cov`; retain explicit template-1/template-2 verification and original hash/review/path rejection tests. New tests reject unknown schema/template combinations and changed scene policy after review.
- [x] **Step 5: Update trackers and commit.** Commit message: `feat: seal reviewed executive storyboards and narration`.

### Task 3: Teach the existing author/reviewer to build the agreed story

**Files:** modify `.opencode/skills/run-poc/references/executive-summary.md`,
`tests/test_skill_files.py`,
`docs/report-presentation-plan.md`; add `docs/adr/0014-offline-kokoro-narration.md`
and `tests/fixtures/executive-story/{simple,complex,failed}/` source/expected fixtures.

**Interfaces:** consumes Task 1 evidence and Task 2 contracts. Produces
`narrative.json`, `scenes.json`, `review.json` using the existing configured
OpenCode model. No new LLM Python service, credentials or provider.

- [x] **Step 1: Add acceptance fixtures and failing workflow assertions.** Simple fixture has only smoke evidence and no traces; complex has several components/scenario groups; failed has a relevant fix and incomplete coverage. Assert retained exact totals/gaps and source references in expected documents. Skill checks require fact extraction, narrative-2 review of spoken text, relevance-based troubleshooting, no test replay and no automatic production-readiness claim.
- [x] **Step 2: Run relevant skill tests and document the missing requirements.** `python -m pytest tests/test_skill_files.py -q --no-cov`; expect new assertions to fail until instructions change.
- [x] **Step 3: Write the authoring/review instructions and ADR.** Document ledger → proportional outline → titles/points/spoken sentences → independent semantic review. Include exact schema-2 examples and tools to compute hashes. Describe report/result conflict handling, evidence-supported technical detail, conditional execution/fix scenes and limitations/recommendations. Document `none` versus `kokoro` format selection and operational bounds, with no prompt telling the model to fit two minutes.
- [x] **Step 4: Validate fixtures and perform a content acceptance pass.** Validate all three expected outputs with Task 2 functions. Run a separate configured-model review on these drafts against their evidence, requiring an example that qualifies a contradictory report and excludes routine retries. Preserve review findings/limitations; deterministic tests verify structure, not the truth of prose. Run skill checks again; expect pass.
- [x] **Step 5: Update trackers and commit.** Commit message: `feat: define evidence-backed slide and narration authoring`.

### Task 4: Package offline Heart speech and generate measured audio

**Files:** new `src/autopoc/executive_speech.py`, `tests/test_executive_speech.py`,
`renderer/pyproject.toml`, generated `renderer/requirements.lock`,
`renderer/assets/kokoro/{manifest.json,README.md,LICENSES.md}`,
`scripts/prepare-kokoro-assets.py`; modify `Dockerfile.executive`, `Makefile`,
`renderer/entrypoint.sh`, `.github/workflows/ci.yml`.

**Interfaces:**
- `verify_speech_assets(asset_root: Path) -> dict` validates the committed manifest against local regular files, exact hashes, model revision and supported voice. Asset root is image-owned, never supplied as an untrusted arbitrary directory from the input ZIP.
- `SpeechChunk(sample_rate: int, pcm16: bytes)` and `SpeechEngine.synthesize(text: str) -> SpeechChunk` provide a fakeable boundary without importing Torch in ordinary worker/unit-test environments.
- `generate_narration(narrative_path: Path, scenes_path: Path, output_dir: Path, *, asset_root: Path, engine: SpeechEngine | None = None) -> dict` writes `narration/SLIDE_ID.wav`, `transcript.txt`, `timeline.json`; default adapter lazily imports Kokoro from the renderer-only environment. All filenames derive from validated IDs.
- Timeline schema 1 contains `run_id`, narrative/scene-plan hashes, engine/model-manifest identity and ordered entries `{id, audio_path, audio_sha256, audio_seconds, duration_seconds, start_seconds, sentence_offsets}`; offsets use `{start_seconds,end_seconds}` relative to scene speech start. Total duration is the sum of scene durations.

- [x] **Step 1: Write failing audio/asset tests using an injected PCM engine.** Assert two 1s sentences with one 0.20s gap produce audio 2.20s and scene 6.0s; a 10s single sentence produces scene 11.0s and lead-in 0.35s at mux time. Reject wrong sample rate, empty/malformed PCM, NaN/nonfinite measurements, missing/corrupt voice/language assets, 120s+ scene and 900s+ total. Confirm exact reviewed sentences are passed, with no paraphrase or silent omission.
- [x] **Step 2: Run `python -m pytest tests/test_executive_speech.py -q --no-cov`; confirm missing implementation fails.** Ordinary unit tests must not require downloading weights or installing Torch.
- [x] **Step 3: Implement local inference/timeline and the build-only asset preparer.** Use Kokoro model revision `f3ff3571791e39611d31c381e3a41a3af07b4987`; record SHA-256/config/weight/Heart voice plus license provenance. Declare and hash-lock the CPU packages and explicit spaCy English wheel, starting from audition versions and fixing any reported security incompatibility before acceptance. Add `make renderer-lock` using pip-compile with the explicit CPU Torch index/version, without changing main `requirements.lock`. Install in `/opt/autopoc/speech-venv`, preload required assets under `/opt/autopoc/speech-assets`, and verify before inference. Avoid runtime auto-install paths; load all models/voices from explicit local paths with offline settings and no implicit HF token.
- [x] **Step 4: Verify unit tests, hash installation and a real offline smoke.** Run the Task 4 suite; install the generated renderer lock with hash checking, run dependency audit, and generate a short Heart scene with network disabled and empty writable caches. Record sample rate/duration/hash, package/model identities and time/memory. Verify the main worker can import CLI modules without speech dependencies.
- [x] **Step 5: Update trackers and commit.** Commit message: `feat: generate offline Heart narration in the renderer`.

### Task 5: ✅ Render dynamic evidence-backed slide chapters

**Files:** new `renderer/storyboard.mjs`, `renderer/storyboard.test.mjs`;
modify `renderer/render.mjs`, `renderer/components/ExecutiveSlide.vue`,
`renderer/scene-validation.mjs`, `renderer/check-layout.mjs`, `renderer/style.css`,
`renderer/render.test.mjs`, source allowlists in `src/autopoc/executive_render.py`.

**Interfaces:**
- `validateStoryboard(narrative, scenePlan)` applies the same template-3 structural bounds as Task 2; use shared JSON fixtures for Python/Node agreement.
- `preparePresentation(inputDir, outputDir) -> Promise<manifest>` prepares, builds, checks every scene and exports PDF, then closes Chromium. Legacy `render(inputDir, outputDir)` remains the existing template-2 all-in-one path.
- `ExecutiveSlide` accepts `slideId` for template 3, resolves ledger claims/graphs and derives numbering/section markers from storyboard order; legacy `kind` behavior remains available only for legacy data.
- Prepared source contains narration text as speaker notes and `transcript.txt` without requiring playback. No model execution in Vue/browser.

- [x] **Step 1: Add failing variable-deck tests.** Use six-, eight- and twelve-slide fixtures, repeated setup/results chapters, optional execution and null diagrams. Assert slide order/title/claim rendering, exact result totals, source notes, graph ownership and correct numbering after slide six. Include long/unsafe text and oversized diagram-label layout failures.
- [x] **Step 2: Run `make test-renderer`; expect new template-3 cases to fail.** Keep existing Node tests active.
- [x] **Step 3: Implement storyboard-driven preparation and scene props.** Replace fixed six-index decisions only in the new path; graph validation/preflight receives each slide's graph. Retain Red Hat assets, fixed trusted components and the existing source sanitization boundary. Do not execute generated Vue/JavaScript. Adapt browser validation to iterate all slide IDs and representative diagram states, with content failures invalidating deck/PDF as before.
- [x] **Step 4: Verify Node/Python contracts and browser layout.** Run `make test-renderer` and affected `tests/test_executive_inputs.py`/`tests/test_executive_render.py`. Use the actual browser check on multi-slide fixtures; inspect every PDF page. Source and browser ZIPs must retain fonts/logos/licenses/helpers and transcript after extraction.
- [x] **Step 5: Update trackers and commit.** Commit message: `feat: render variable executive slide chapters`.

### Task 6: ✅ Orchestrate measured narration and encode synchronized video

**Files:** new `renderer/audio.mjs`, `renderer/audio.test.mjs`;
modify `src/autopoc/executive_render.py`, `tests/test_executive_render.py`,
`renderer/render.mjs`, `renderer/render.test.mjs`, source allowlists and README.

**Interfaces:**
- `recordPresentation(inputDir, outputDir, timeline) -> Promise<manifest>` consumes Task 5's prepared deck and Task 4's verified timeline/audio; never recreates the source tree or guesses durations.
- Node stage CLI: `node render.mjs INPUT OUTPUT --stage prepare`; `node render.mjs INPUT OUTPUT --stage record --timeline PATH`. Original two-positional template-2 invocation remains supported.
- `render_executive(inputs_path: Path, output_dir: Path, *, timeout: int | None = None) -> dict` chooses legacy 600s or narrated 3000s by sealed version/profile; an explicit timeout must be positive and within that format's maximum.
- New `timeline.json` and audio metadata stay inside the source ZIP and presentation manifest; no sixth publication artifact is introduced.

- [x] **Step 1: Write failing process, timing and partial-output tests.** Assert process order prepare → closed browser → speech subprocess exit → record. If speech times out or a WAV hash changes, retain source/deck/PDF/summary and mark video failed. Verify reuse requires matching input/output hashes, and recovered rendering never calls a content model or test runner.
- [x] **Step 2: Run `python -m pytest tests/test_executive_render.py -q --no-cov` and `make test-renderer`; confirm new narration cases fail.** Add a small real FFmpeg integration fixture with distinct tones/silence around a scene cut so truncation/offset errors are detectable beyond a final duration check.
- [x] **Step 3: Implement stage orchestration, timing checks and muxing.** Bound/terminate entire process trees using the existing group-kill pattern; propagate failures accurately. Validate timeline hashes/IDs/sample counts and sum before recording. Use 0.35s speech delay, padded scene audio and stable H.264/AAC parameters; concatenate without clipped speech. Scale each graph to its scene interval with illustrative-timing caveat. Use subprocess argument arrays and trusted filters, never generated shell commands.
- [x] **Step 4: Verify outputs and packaging.** Require H.264 1280×720/30fps/yuv420p, AAC audio, per-scene and final duration agreement within 0.25s, and successful complete decoding. Test a generated timeline over 180s and more than six slides without waiting for real-time capture in unit tests; run real capture during Task 8. Add narration transcript/audio/identity/timeline to source archive, preserve exact reviewed text, and remove unconditional “Silent video” wording only for narrated output. Enforce template-3 source/video limits and explicit partial status on any speech/mux failure.
- [x] **Step 5: Update trackers and commit.** Commit message: `feat: encode narration-driven executive videos`.

### Task 7: ✅ Preserve narrated Job policy, long-running recovery and publication

**Files:** modify `src/autopoc/executive_job.py`, `src/autopoc/executive_cluster.py`,
`src/autopoc/tools/google_drive_tools.py`, corresponding job/cluster/Drive tests,
`docs/configuration.md`, `AGENTS.md`, executive workflow reference.

**Interfaces:**
- Add keyword `profile: str = "silent-v2"` to `build_renderer_job`; accepted profiles are `silent-v2` and `kokoro-v3`, with format-specific deadline/resources. Existing calls remain valid.
- `prepare_publication` derives a `render_policy` from verified versions/scenes, persists it before upload/dispatch, and includes it in the durable recovery descriptor. Fields: `profile`, `narration`, `render_timeout_seconds`, `job_deadline_seconds`, `scene_policy_sha256`. Legacy checkpoints without it retain legacy behavior.
- `submit_renderer` uses persisted policy and passes the saved timeout to `executive-render --timeout-seconds N`; add that CLI option for local and remote modes. `render_remote` verifies CLI/descriptor/sealed policy agreement before invoking the wrapper.
- Worker wait remains independently bounded. Existing five artifact slots/intents/receipts and retry cap stay unchanged; Drive download limits are selected by artifact kind and sealed format (source 512MiB, video 1GiB for template 3), not untrusted receipt sizes.

- [x] **Step 1: Add failing durable-policy tests.** Cover new narrated profile/deadlines/resources, unchanged legacy Job, environment change after checkpoint, stale/incompatible image/template, deleted worker directory, late completion beyond worker wait, unchanged input retry, bounded explicit retry and speech-failed partial publication. Assert duplicate dispatch does not allocate a new Job or upload IDs.
- [x] **Step 2: Run job/cluster/Drive test modules with `--no-cov`; confirm new policy/CLI cases fail.** Use `python -m pytest tests/test_executive_job.py tests/test_executive_cluster.py tests/test_google_drive_tools.py -q --no-cov`; do not create a duplicate Drive suite.
- [x] **Step 3: Implement version-specific saved profiles and output bounds.** Keep legacy 600s default/1800s allowed deadline behavior; narrated defaults are 3000s rendering/3120s Job, upper bound 3600s. Use 2 CPU/4Gi/8Gi scratch/10Gi ephemeral storage provisionally. Preserve tokenless renderer, read-only root, scoped RBAC and immutable checkpoint history. Configured image digest is required; do not infer compatibility from a mutable tag. Resume with saved configuration, rejecting conflicts rather than adopting new environment values.
- [x] **Step 4: Verify state and report-link behavior.** Run affected suites plus Task 2 and Task 6 suites. Confirm failed narration never gets a successful video link, valid partial artifacts stay accessible, long renders reconcile after blog completion, exact output hashes/size ceilings are checked on upload/download, and complete legacy output remains reusable without re-rendering. Document that Drive authorization is still required even though Google TTS is not.
- [x] **Step 5: Update trackers and commit.** Commit message: `feat: recover and publish bounded narrated render jobs`.

### Task 8: Validate the complete feature and prepare controlled rollout

**Files:** modify `.github/workflows/ci.yml`, `renderer/check-layout.mjs`,
`renderer/README.md`, `docs/configuration.md`, `docs/report-presentation-plan.md`,
`AGENTS.md` and both project planning documents; add `scripts/check-narrated-render.sh`
for repeatable local acceptance, with synthetic fixture inputs clearly labeled.

**Interfaces:** consumes the sealed storyboard, packaged offline speech and durable
render pipeline. Produces measured acceptance records and a reviewable feature
branch; production deployment/publication is claimed only with observed evidence.

- [ ] **Step 1: Run supported project checks.** Use Python 3.12 and generated locks. Run `make lint`, `make typecheck`, `make test`, `make test-renderer`, renderer-lock hash install/dependency audit and offline asset verification. Require the existing 80% project coverage threshold; do not lower it for optional modules. Add a CI image smoke that uses preinstalled speech dependencies/assets and makes no runtime network requests.
- [ ] **Step 2: Render the acceptance set locally.** Use archived Omnigent evidence with no PoC replay, a complex synthetic run whose narrated result exceeds 180s and six slides, and a failed/incomplete case. Render from empty writable caches with networking disabled, arbitrary nonroot UID and read-only root. Record all exact input/image/model/output hashes, durations, full decoding, memory, scratch and elapsed time. Listen to every scene, especially “OpenShift”, “Kubernetes”, “Quay”, numbers and caveats; inspect every slide/PDF page plus all scene cuts/diagram states.
- [ ] **Step 3: Exercise failures and recovery.** Missing asset, bad script hash, speech timeout/forced termination, OOM, disk exhaustion, admission failure, upload retry and worker restart must preserve evidence and valid partial artifacts, retain attempt history and avoid replay/new model calls. Re-extract source ZIP and verify transcript/timeline/audio hashes; recover with original image/model identity after original workspace deletion.
- [ ] **Step 4: Publish the tested image and perform restricted OCP acceptance when access is available.** Record measured behavior under the intended namespace/profile before changing deployment configuration. Check late completion/reconciliation, independent blog progress and artifact retrieval hash verification with working destination credentials. If access/credentials block this step, mark it blocked/pending explicitly while retaining the completed local acceptance; do not claim production rollout. Obtain user approval before changing live configuration or merging.
- [ ] **Step 5: Finalize docs/trackers and commit; publish only the feature branch.** Separate measured local/cluster/publication results and remaining rollout work. Commit message: `test: validate narrated executive rendering and recovery`. Push the feature branch and open/update a reviewable PR when implementation is authorized; never push a default branch or merge without approval.

## Planning review and execution handoff

The written design received the brainstorming skill's independent builder check:
“Nothing important left.” The reviewer found the consequential provenance,
versioning, offline packaging, measured timing, partial-output and recovery choices
specified; remaining details are builder decisions.

Self-review maps all design requirements to the eight tasks. In particular,
Tasks 1–3 cover evidence/story truthfulness, Tasks 4–6 cover offline generation
and dynamic timing, Task 7 covers durable resource/publication behavior and
Task 8 covers the full acceptance/rollout distinction. Implementation was authorized by the user on 8 November 2026; native execution is in progress.

Recommended execution: native in this chat, task by task, because these tasks
share narrative/timeline/version contracts and benefit from keeping that context
together. A fresh whole-branch reviewer follows implementation. Subagent-driven
execution is also available if the user prefers independent review per task.
The user approved the plan on 8 November 2026. Native execution is active in
the managed `codex/kokoro-narration` worktree; the per-plan ledger records
completed tasks, exact checks and implementation rulings.
