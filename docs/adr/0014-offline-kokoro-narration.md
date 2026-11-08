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

## Alternatives

- Cloud TTS adds credentials, egress and external per-run dependencies.
- An always-on speech service or separate GPU Job adds scheduling/service/recovery
  overhead without evidence that these short narrations require it.
- In-worker synthesis shares model memory and failure modes with the PoC agent.
- Fitting generated speech to fixed timings risks clipped or rushed explanations.

## Consequences

The renderer image is larger and requires its own dependency/asset lock and
offline acceptance. CPU budgets are provisional until measured on OCP; available
GPUs do not imply that a GPU profile is needed or accepted. Legacy silent inputs
remain supported, while narration opt-in requires a compatible image/worker.
Drive authorization remains separate from local speech generation. Source ZIPs
retain transcript/audio/timeline identity so recovery never reruns PoC tests.
