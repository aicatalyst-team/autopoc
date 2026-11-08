# Executive rendering as a recoverable extension

## Status

Accepted for implementation on 26 October 2026. Production rollout and full
cluster acceptance remain open; see the presentation handoff.

## Context

The eleven-phase OpenCode PoC pipeline needs executive presentations and silent
videos based on the generated report and original test evidence. Chromium and
FFmpeg require independent resources. Worker emptyDir storage and later artifact
branch writes cannot be relied on for recovery or report preservation.

## Decision

Keep OpenCode as the content author/reviewer. Capture original attempts and seal
an allowlisted, sanitized evidence bundle with reviewed narrative JSON, scene
data and pinned renderer identity. Render trusted Slidev/TopoLoop templates in a
separate UBI Job with explicit resources, deadline, read-only root and no workload
API token. Treat narrative and reports as data; do not execute generated code or
replay PoC tests to produce the presentation.

Use append-only run-specific Git revisions for artifacts and recovery. Retain a
bounded sealed-input fallback in the first immutable checkpoint. Publish inputs
to Drive before dispatch, reserve upload identities before side effects, and
reconcile output intents/receipts and report links independently of PoC phase
progress. Valid partial outputs survive recording/publication failures.

## Alternatives

Rendering in the main worker shares its memory/deadline and increases failure
coupling. Ephemeral-only inputs prevent recovery after worker deletion. Replacing
the artifact branch loses earlier reports and links. A second content-generation
model service duplicates the existing OpenCode author/reviewer capability.

## Consequences

The renderer has a separate build/image and the main worker must also be rebuilt
for rollout. Drive authorization and destination access must be configured.
Silent video is Phase 1; Google TTS narration is Phase 2. Temporary personal OAuth
may be injected for local publication, with personal tokens retained locally.
Resource sizing and failure acceptance require actual cluster verification.
