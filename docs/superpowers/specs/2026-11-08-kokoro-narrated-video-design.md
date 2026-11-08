# Evidence-based slide text and Kokoro narration

Status: agreed product direction; implementation plan prepared for review.
Date: 8 November 2026.

## Intent and confirmed requirements

Extend the executive presentation/video workflow with spoken explanations using
Kokoro's American English `af_heart` voice, selected after a local audition.
Video length follows the scope and complexity of the PoC; two minutes is not a
target or editorial ceiling. Generate concise slide text and fuller spoken
explanations together from the same evidence.

The user requested project objective, how we test, setup and results. The
brainstormed story also includes limitations and recommendations. Use the final
report, plans, recorded deployment information, original test results, logs and
traces where available. Include troubleshooting/fixes only when they explain
the outcome, reveal an adoption/platform constraint or affect the recommendation.
Routine operational noise does not belong in the story.

Do not rerun PoC tests to create content. Preserve all original attempts and
distinguish intended tests, observed behavior, inference and recommendations.
Missing traces cannot become invented execution walkthroughs. Contradictory
report/evidence claims must be disclosed and qualified. All-pass smoke checks do
not prove production readiness; OpenShift results do not prove a separate
Kubernetes deployment.

This design supersedes the earlier Google-TTS-only Phase 2 preference and the
six-slide/three-minute bound **for the new opt-in narrated format**. Existing
silent videos and their recovery contracts remain supported.

## Current implementation and local evidence

`executive_inputs.py` seals five payloads plus an index, binds automated review
to narrative/evidence hashes and requires six durations totaling at most 180s.
`renderer/render.mjs` and `ExecutiveSlide.vue` assume six fixed slide kinds.
The Python wrapper permits at most 600s of rendering. The cluster Job defaults
to 600s with 2 CPU/3Gi memory and 4Gi scratch. These are real implementation
limits to change, not merely prompt instructions.

`evidence.py` currently accepts only selected state/attempts, report, plan and
evaluation. Most logs, traces and deployment files cannot yet be cited from a
sealed input. Extend this allowlist explicitly before using those sources.

The audition used Kokoro/Misaki 0.9.4, Torch 2.8.0+cpu, Python 3.12 and two Torch
threads. Heart produced 22.150s of audio in 14.153s; model initialization with
cached weights took 1.721s. Peak process RSS was about 1702MiB. This demonstrates
local feasibility, not restricted OpenShift acceptance or production sizing.

## Story generation

Use the configured OpenCode model; do not add a content-generation provider.
The workflow has three authoring passes followed by independent content review:

1. Extract a source-linked fact ledger from a verified evidence bundle. Record
   claim IDs, source locations, whether claims are observed/planned/inferred/
   recommendations, evidence gaps and conflicts.
2. Choose an outline proportional to meaningful findings. Default chapters are
   objective, testing, setup, results, limitations and recommendation. Add an
   execution chapter between setup/results only if it helps explain the outcome.
   Split a chapter when its architecture/scenarios/findings need another slide;
   do not pad a simple PoC to use a time allowance.
3. Draft takeaway titles, up to four short visible points, and natural spoken
   explanations. Every factual title, visible point, narration sentence and
   diagram must resolve to ledger claims. Spoken detail may exceed visible text
   but must preserve the same conclusions, caveats and uncertainty.

The separate reviewer sees all evidence and the exact final JSON, including the
spoken script. It checks factual support, totals, claim classification,
conflicts, omissions, platform distinctions and the relevance of troubleshooting.
Structural checks cannot replace this semantic review. Revise before sealing;
do not reword scripts after review or regenerate narration from an unreviewed
text paraphrase. Model review remains unattended, as in the existing workflow.

## Evidence extension

Keep schema-1 evidence byte-compatible. An optional `evidence-create
--supplemental-index PATH` produces schema-2 evidence with the existing core
members plus `supplemental-index.json` and allowlisted `supplemental/ID.txt` or
`supplemental/ID.json` members. No recursive discovery or remote trace fetching.

The local supplemental descriptor has `schema_version: 1`, matching `run_id`
and records with `id`, `kind`, `path`, `sha256`, `provenance` and optional
`execution_id`/`scenario_id`. Kinds are `log`, `trace`, `deployment`, `analysis`
and `test_definition`. Paths must be regular, non-symlink files under the run's
staged evidence root; reject outside-root paths and identity/hash mismatches.
Normalize a YAML deployment export to selected JSON before staging; exclude
Secret data. Record declarative configuration separately from observed resource
state. A trace excerpt must retain its captured identifiers/timing relationships
and run provenance; do not synthesize spans.

Allow at most 32 supplemental records, at most 512KiB of original text per
record, and retain the existing 20MiB evidence budget. Apply the existing text
sanitizer before publication. Reject unsafe supplied input; optional sources
that were never captured are recorded as gaps. Oversized inputs must be
explicitly excerpted with provenance, never silently truncated. Public source
references address sanitized member line ranges or JSON Pointers, not private
filesystem paths. Hash the published bytes and preserve original input hashes
in private staging only. Existing phase-time staging should supply the files;
historical runs use only files genuinely retained for that run.

## Versioned narrative and sealed input contracts

Introduce narrative schema 2 / input-envelope schema 2 / template revision 3.
Keep evidence sanitizer policy 1 and input policy 1; the new narrative envelope
does not relax either policy. Schema-1 narrative/template-1 and template-2
inputs stay verifiable and recover through their original pinned images.

Narrative schema 2 contains run/project identity; exact `results` totals; a
`claims` ledger; `conflicts`; `coverage_gaps`; and ordered `slides`.
Each claim has `id`, `text`, `kind`, `sources`; each source is an existing member
plus an optional validated line-range or JSON-Pointer selector. Each slide has
`id`, `section`, `title`, `title_claim_ids`, `bullet_claim_ids`, `narration`
sentences (`text`, `claim_ids`), `graph` (null or bounded TopoLoop JSON) and
`graph_claim_ids`. Section values are `objective`, `testing`, `setup`,
`execution`, `results`, `limitations`, `recommendation`. Required chapters appear
in that order, with optional execution between setup/results; repeats are
contiguous. Retain explicit limitations and exact totals even for failed PoCs.

Builder-selected structural bounds: 6–30 slides; 100-character titles;
1–4 bullets per slide, 280-character ledger claims; at most 12 narration
sentences and 180 spoken words per slide. Existing graph bounds (12 nodes,
20 edges, 5 acts) stay per slide. Layout overflow requires content revision,
not tiny text, dropped caveats or clipped output. These limits are operational
defaults, not user-agreed content requirements.

For template 3, `scenes.json` holds the ordered slide IDs, `narration` engine/
voice/speed/model-manifest hash and the timing policy, not guessed final
durations. Review schema 2 binds SHA-256 of the exact narrative, evidence and
scene-plan bytes; `reviewer` remains `configured-opencode`, `approved: true`,
`findings: []`. The input index hashes all five payloads. Keep the existing
24MiB sealed-input bound; weights and audio are not input ZIP members.

## Offline narration and duration

Package Kokoro only in the separate renderer image. Keep model inference out
of the OpenCode worker. Use a separate renderer Python dependency declaration
and generated hash lock, CPU-only Torch, and build-time downloaded, verified
weights/config/Heart voice/English language assets. Never download or install
anything during rendering. Preserve upstream licenses and provenance in the
repository/image and source package. Do not commit model weights to Git.

Starting model pin from the audition is `hexgrad/Kokoro-82M` revision
`f3ff3571791e39611d31c381e3a41a3af07b4987`; verify exact file hashes and licenses
when building. Pin Python packages in `renderer/pyproject.toml` and generate
`renderer/requirements.lock` using a new `make renderer-lock` target, including
the explicit English language model wheel and CPU Torch index. Begin with the
audition's working versions, but require dependency/security checks before
accepting the production lock. Main application dependencies remain unchanged.

Builder-selected defaults: `af_heart`, American English, speed 0.95, two Torch
threads, 24kHz mono PCM. Synthesize each reviewed sentence, join with 0.20s
inter-sentence silence, then measure the result from actual sample counts.
Record sentence boundaries and an engine/model/script identity per scene.
No claim of word-level alignment or live execution timing is made.

Scene duration is `max(6.0, audio_seconds + 0.35 + 0.65)`: 0.35s lead-in,
0.65s tail, extended tail for a short scene. Each scene starts speech at its
own lead-in. Video length is the sum of actual scene durations. Default
operational bounds are 120s per scene and 900s total; they are resource guards,
not editorial targets. Exceeding one returns an actionable partial result for
revision or a separately reviewed larger render policy. Never clip, rush,
silently drop material or time-stretch speech to satisfy a limit.

Match diagram progression to the scene interval and retain the existing
illustrative-timing caveat. Keep visible slide text, narration transcript and
speaker notes available without audio. Word-synchronized subtitles, additional
voices/languages, music and voice cloning are outside this first implementation.

## Rendering, failure behavior and recovery

Split work inside the existing renderer Job into three sequential stages:
prepare/validate deck and PDF; synthesize narration in a bounded subprocess;
record/mux the narrated video. Close Chromium before starting Torch and terminate
the speech subprocess before video capture. Avoid overlapping their memory peaks.
No extra Job, service or change to the eleven-phase cursor is needed.

For each scene, pad audio to its measured scene duration, encode H.264 video
with AAC audio and concatenate with stable codec parameters. Final ffprobe and
full decoding verify video format, audio presence, finite timings, per-scene
boundaries and duration agreement within 0.25s. No scene may lose speech at a
cut; preserve lead/tail intervals. A failed speech/mux stage retains valid
deck/PDF/source/summary and reports video failure. Do not call an unexpected
silent fallback a successful narrated video.

Save generated sentence/scene audio, transcript, `timeline.json`, hashes and
model/version metadata inside `executable-source.zip`, alongside existing
source/recovery materials. Static browser export includes readable notes and
the transcript, but autoplay audio is outside scope. Keep the five top-level
published artifact kinds unchanged. Enforce a 512MiB source ZIP limit and
1GiB video limit for template 3; retain existing legacy limits/contracts.
Update bounded Drive verification/reconciliation for those exact output limits.

Recovery uses sealed content plus a digest-pinned image containing the exact
model assets. Reuse already completed output only after hash validation. An
explicit retry keeps immutable attempt history; it may regenerate audio, so do
not promise byte-identical output across machines. It must never call the
content model or rerun the PoC. Missing/corrupt model files fail explicitly.

Opt in with `AUTOPOC_EXECUTIVE_NARRATION=kokoro` plus a compatible digest-pinned
`AUTOPOC_EXECUTIVE_IMAGE`; unset/`none` keeps the current silent path. Heart is
the initial supported voice. Store narration mode, policy/profile identity,
render timeout and Job deadline in the durable checkpoint before dispatch;
resume must use that saved configuration rather than new environment values.

Builder-selected initial template-3 budgets: 3000s renderer timeout and 3120s
Job deadline; worker wait remains 300s by default and still permits 0–600s.
Allow a 3600s upper bound for narrated Job deadlines. Initial resource profile
is 2 CPU, 4Gi memory, 8Gi scratch with 10Gi ephemeral-storage limit, measured
before rollout. Legacy profiles/deadlines stay unchanged. Longer videos should
complete through existing late reconciliation after the worker continues.

## Acceptance and rollout

Implement and test in small commits, updating both project trackers each time.
Write an ADR for local speech and narration-driven rendering. A first reference
uses the archived Omnigent evidence without replaying tests; supplement it only
with actually archived run data. Also render a synthetic complex PoC over
180 seconds and a failed/incomplete PoC with gaps and a meaningful fix.

Verify every slide/PDF page and representative diagram states, listen to every
narration scene for this acceptance set, and inspect scene boundaries. Validate
offline/no-download execution, arbitrary OpenShift UID/read-only root, process
cleanup, missing assets, speech timeout/OOM and durable late recovery. Measure
full elapsed time, memory and scratch for the new image; revise provisional
budgets if evidence requires it, without silently changing sealed policies.

Production rollout requires a published image digest, restricted OCP acceptance,
worker/renderer compatibility and working artifact destination credentials.
Kokoro removes Google **TTS** access requirements; it does not fix existing
Google Drive publication credentials. Local acceptance is not deployment or
successful publication. Obtain user approval before merging or changing live
deployment configuration; use feature branches and never push a default branch.
