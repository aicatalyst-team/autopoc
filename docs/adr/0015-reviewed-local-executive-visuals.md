# Reviewed local visual assets in executive inputs

## Status

Accepted for the generic storytelling implementation on 10 November 2026.
Local packaging and sealing are implemented. Generic rendering, browser decode
and rollout acceptance remain later implementation tasks.

## Context

An executive story may benefit from authentic project context, but screenshots
are not evidence that a capability was tested. Rendering must remain offline,
recoverable and bound to the exact bytes accepted during content review. The
main worker must not acquire browser or image generation dependencies.

## Decision

Stage zero to four PNGs locally before review. The explicit manifest determines
only IDs and provenance; each source path is assets/<id>.png beside the manifest.
No arbitrary path or network download is accepted. A deterministic visuals.zip
always contains manifest.json, including when there are no images. Optional
contextual capture can fall back to text/diagrams before review with a recorded
gap. Invalid supplied bytes fail rather than being silently cleaned or omitted.

Allow source_capture, project_brand and concept assets. Concepts must be visibly
identified as conceptual; source captures from unversioned pages are contextual
current documentation. Runtime screenshots are outside this contract. Semantic
provenance and caption correctness remain content review responsibilities.

Validate sanitized bounded manifest fields, credential-free HTTPS references,
run and claim references, PNG signatures, geometry, chunk structure and CRCs.
Allow exactly IHDR, PLTE, IDAT, IEND, tRNS, sRGB, gAMA and cHRM. Reject metadata,
animation, duplicate keys/entries, symlinks, unknown members and oversized inputs
before decompression. Bounds are 2 MiB per PNG, 4096 pixels per side, 16 million
total pixels and 8 MiB expanded archive contents; the compressed archive has a
64 KiB ZIP-overhead allowance. Manifest text is limited to 64 KiB.

Add the exact (schema, template, policy) envelope (3,4,2), binding the original
five payloads plus visuals.zip in the input index. Require the schema-3 review
to bind visuals_sha256 as well as narrative, evidence and scenes. Validate slide
visual IDs against the manifest and asset claim IDs against narrative claims.
Legacy (1,1,1), (1,2,1), (2,3,1) keep their exact member and review contracts.
Recovery uses sealed bytes and the original pinned image rather than fetching
current pages. CURRENT_TEMPLATE_VERSION stays 3 until renderer integration;
explicit version tuples and CLI choices already admit template 4 without
retiring template 3 when that constant eventually changes.

PNG compressed pixel streams are not inflated in this preparation validator.
The offline browser must fully decode all assets before speech starts in the
rendering integration. Text-only review must not claim pixel inspection; human
visual inspection remains a release/acceptance gate. This adds no per-run user
approval requirement to unattended dispatch.

## Alternatives considered

- Autonomous crawling or a new browser Job service: expands operational and
  security scope; staged captures meet the initial contextual imagery need.
- Re-fetching images during recovery: breaks immutable review and offline use.
- Stripping metadata after review: changes reviewed bytes and conceals invalid
  inputs. Capture tooling must provide clean PNGs before review.
- Accepting general image formats: adds parsers/dependencies and broader attack
  surface. The initial bounded PNG contract is sufficient.

## Consequences

The archive is deterministic and recoverable with standard-library validation.
Missing imagery remains usable through a reviewed fallback. Sanitization proves
nothing about secrets visibly present in image pixels. Structural acceptance
also does not replace full browser decoding, visual review or listening checks.
Existing evidence limits, input budgets, image pins and publication gates remain.
