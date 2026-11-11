# Offline Kokoro narration with evidence-backed variable scenes

## Status

Accepted and implemented following user plan approval on 8 November 2026.
Measured local and restricted-v2 OpenShift acceptance is complete. Production
activation still requires working Drive publication credentials, human listening
review and explicit merge/live-configuration approval. See
`docs/validation/kokoro-narration-2026-11-08.json` for measured scope and image revisions.

## Context

The executive video is currently silent, fixed at six slides and at most three
minutes. The user selected Kokoro Heart after a CPU audition and asked for
duration proportional to PoC complexity. Google Cloud TTS access is unavailable
on the configured work project. Reports alone omit useful execution evidence,
while narration can introduce claims absent from the visible slides.

## Decision

Extend original evidence with bounded, sanitized and run-bound supplemental
logs/traces/setup. The existing configured OpenCode model authors a source-linked
fact ledger and variable storyboard, including visible text and narration, then
independently reviews the final content. Bind review to exact narrative,
evidence and scene-policy hashes using new schema-2/template-3 inputs.

Package CPU-only Kokoro, Heart and English assets by pinned revisions/hashes in
the separate renderer image at build time; no inference/downloads in the worker.
In one renderer Job, prepare deck/PDF, generate speech in a subprocess, and record
video in sequential memory-isolated stages. Actual audio determines timings.
Keep existing five output kinds, immutable checkpoints, original image recovery,
independent worker wait and explicit partial results.

Troubleshooting enters the story only when it explains the outcome, adoption
constraints or recommendation. Retained evidence is not a checklist of content
that must appear. Missing traces and report/result conflicts remain explicit.

Revised on 9 November 2026 after an external review. Pronunciation of coined
names and initialisms is controlled by a versioned, hash-bound, synthesis-only
lexicon rather than by rewording reviewed text, because the reviewed script is
immutable after approval and a mispronunciation otherwise has no remedy short
of re-authoring. Sentence-level captions are derived from the measured timeline
and muxed as a `mov_text` track, because the sentence offsets already exist and
a spoken executive video without captions is not accessible; word-synchronized
subtitles still need alignment data Kokoro does not provide. The narrated Job
deadline is 3600s rather than 3120s, because a deadline runs from `startTime`
and image pull erodes the rendering budget. Sealing estimates total duration so
that a structurally valid but unrenderable script fails before synthesis rather
than after it.

## Alternatives

- Cloud TTS adds credentials, egress and external per-run dependencies.
- An always-on speech service or separate GPU Job adds scheduling/service/recovery
  overhead without evidence that these short narrations require it.
- In-worker synthesis shares model memory and failure modes with the PoC agent.
- Fitting generated speech to fixed timings risks clipped or rushed explanations.
- Respelling words in the reviewed script would change approved content to fix a
  pronunciation; a synthesis-only lexicon leaves the reviewed text untouched.
- Burning captions into the video frames would make them unselectable and would
  force a re-render to correct a typo.

## Consequences

The renderer image is larger and requires its own dependency/asset lock and
offline acceptance. CPU budgets are provisional until measured on OCP; available
GPUs do not imply that a GPU profile is needed or accepted. Legacy silent inputs
remain supported, while narration opt-in requires a compatible image/worker.
Drive authorization remains separate from local speech generation. Source ZIPs
retain transcript/audio/timeline/caption identity and the lexicon, so recovery
never reruns PoC tests and can show exactly which pronunciations and cues an
approved timeline refers to.

Pronunciation and captions are now part of the review surface: correcting a
pronunciation invalidates the sealed speech identity and requires a new review,
which is the intended cost of never silently changing what was approved. Seed
lexicon entries are expected pronunciations and remain unverified until the
acceptance listening pass. Measured narrated renders outlast the default 300s
worker wait, so late collection is the normal flow; it still requires a
dispatch, a startup/resume or an explicit `executive-reconcile`, and rollout
must schedule that trigger rather than describe link updates as automatic.
