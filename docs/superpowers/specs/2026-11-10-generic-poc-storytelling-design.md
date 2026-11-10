# Generic, evidence-based PoC storytelling

Date: 10 November 2026.
Status: storyboard direction approved; technical design proposed for review.
This document describes future work, not implemented renderer behavior.

## Intent and confirmed direction

Create understandable executive presentations and narrated videos for any PoC
whose source is a Git repository on GitHub or another open-source code platform.
The template is reusable; project names, definitions, components, platforms,
checks, outcomes and recommendations come from that run's sources. It must work
for services, CLI tools, libraries and multi-component projects. Repository-host
independence does not add deployment-platform support to AutoPoC.

The audience is technical managers and customer engineers. Assume engineering
knowledge but no prior knowledge of the project. The opening must visibly explain
what the project does, even if the viewer misses the narration. Prefer authentic
project context and explanatory visuals to a sequence of dense text slides.

The user approved the eight-scene OpenShell storyboard, then explicitly required
a generic template. Its five checks and eight scenes are examples, not constants.
The sequence illustrates these story jobs:

1. Identify and define the project.
2. Explain the PoC question.
3. Name the checks and what each checks.
4. Show the recorded setup and, when useful, execution.
5. Explain observed outcomes, including failures and incomplete work.
6. State coverage limits without implying unsupported product defects.
7. Interpret the result and introduce next actions when their slide appears.

Use the existing ordered chapters: objective, testing, setup, optional execution,
results, limitations, recommendation. Repeated chapters accommodate useful detail.
Project identity and PoC goal can share one objective slide when readable;
takeaway and next actions can share one recommendation slide when speech and
visuals align. Split them when they carry distinct messages. Never add filler to
reach eight slides. Existing 6–30-slide and 900-second resource guards remain;
duration follows meaningful content, not a two-minute target.

## Source and editorial rules

Generate from the verified report, plan, retained results, state and allowlisted
supplemental logs/traces/deployment/source excerpts. Preserve original attempts.
Never rerun tests to generate media. Distinguish project-intended capabilities,
observations, inferences and future recommendations. A README describes project
intent; a screenshot of it does not prove a capability was tested.

Describe checks from the final scenario inventory already computed by evidence
verification. All scenarios must be accounted for, including fail, error, skip
and incomplete; do not select only passing checks. Display meaningful names and
a short explanation, not internal IDs alone. Paginate at most five rows per
check slide rather than squeezing text. For an empty inventory, explicitly state
that no checks were recorded. Bounds that prevent full presentation fail before
synthesis with instructions to revise scope; never silently omit checks.

Use “not tested here,” “not covered in this PoC,” or qualified partial coverage
when accurate. A failed check stays a failed check. The reviewer must reject both
unsupported defect claims and language that hides real negative evidence.
Troubleshooting belongs only when it explains the outcome or recommendation.

Continue the already agreed simple technical English policy: one idea per
sentence, active voice, consistent technical terms, normally 10–20 words and
normally within 25. These are editorial guidance, not schema limits or a formal
ASD-STE100 claim. No spoken execution dates. Reviewed sentences and transcript
remain unchanged during synthesis. Existing media is unchanged; the user chose
future videos only for the narration-style change.

## Reusable content and layout contract — proposed builder choices

Introduce narrative/input schema 3 with template 4 and input policy 2. Keep
legacy (schema, template, policy) combinations (1,1,1), (1,2,1), (2,3,1)
verifiable; recover them using their original image pins. Scene-plan schema 2,
evidence schemas and sanitizer policy are unchanged. Do not replace version
checks with a permissive “version >= 2.”

Schema 3 retains schema-2 claims, chapter ordering, evidence selectors, results,
graphs, narration and bounds. Add these exact fields:

- `project_context`: `{repository_url, revision, definition_claim_id,
  homepage_url, documentation_url}`; revision and the last two may be null. URLs are
  credential-free HTTPS references, never automatically fetched by rendering.
  Use the captured source revision; visibly disclose unavailable revision metadata
  rather than inventing it.
- Each slide adds `layout`: `summary`, `identity`, `checks` or `topology`;
  `visual_id`: null or a manifest asset ID; and `checks`: an array (empty outside
  checks layout). The first slide is identity and visibly renders the definition
  claim. A topology layout requires a graph; identity may use an optional image;
  summary/checks do not use one. Existing 1–4 bullet claims remain separate.
- Each check row is `{scenario_id, label_claim_id, purpose_claim_id,
  narration_sentence_indices}`. Indices are zero-based, nonempty, unique, in
  ascending, contiguous order within each row. Rows follow spoken order and their
  sentence ranges cannot overlap. Claims remain source-linked; exact status
  and raw scenario name are derived from verified `final_results.results`, not
  authored. Every scenario appears exactly once across testing/checks slides.
  Each row's spoken explanation must be reviewed for semantic agreement.

All new fields are required, using null/empty values where specified. Cross-
language validators must agree. A separate derived `checks.json` maps scenario
IDs to original names/statuses for the offline browser; it is regenerated only
from verified evidence, included in source/browser packages, and not an authored
replacement for evidence. No OpenShell terms, test names or host-specific DOM
selectors appear in generic layouts. Host-specific fetching is outside them.

## Authentic images and offline assets — proposed builder choices

Initial scope supports optional locally staged PNG assets. The workflow may use
an existing capture tool to stage an authentic public documentation/homepage
capture. It does not require browser installation in the main worker. If capture
is unavailable, private, unsafe, oversized or unreadable, record the reason and
use the text/diagram fallback before review. A new autonomous website crawler,
browser Job service and image-generation provider are outside this increment.

Generated concept art may be staged through the same contract when available;
it must be labeled conceptual and never impersonate an actual screenshot,
product logo or runtime observation. Prefer TopoLoop for component relationships.
Runtime screenshots are not supported in this first asset contract; this avoids
turning image-only assertions into unreviewable test evidence.

Before content review, `executive-visuals` builds a deterministic `visuals.zip`
from an explicit manifest and regular local files. It always contains
`manifest.json` and zero to four `assets/<id>.png` files. Manifest schema 1 has
`run_id`, `gaps` (bounded sanitized strings), and `assets`. Each asset has `id`,
`kind` (`source_capture`, `project_brand`, `concept`), `source_url` (null only for
concept), `source_revision` (nullable for unversioned public documentation),
`claim_ids`, `caption`, `alt`, `sha256`, `width`, `height`, and `attribution`.
The ID determines the internal path. Capture time is provenance, not narration;
optional `captured_at` records UTC capture time. Unversioned pages must be
identified as contextual current documentation, never the pinned run's source.

Limit each PNG to 2 MiB, each side to 4096 pixels and total decoded pixels across
assets to 16 million. Limit expanded visual ZIP contents to 8 MiB. Keep existing
24 MiB total sealed-input and 20 MiB evidence limits. Reject duplicate ZIP entries,
unknown members, traversal, symlinks, SVG/HTML, mismatched hashes/dimensions,
invalid PNG structure and oversized compressed/expanded input. Use standard-
library PNG structural checks and CRC checks; the offline browser must fully
decode all images before speech starts. No network references in asset bytes.
Accept only PNG chunks IHDR, PLTE, IDAT, IEND, tRNS, sRGB, gAMA and cHRM;
reject other chunks, including textual/EXIF metadata and animated PNG extensions.
Capture tooling must provide a clean visible image. Do not silently strip or
modify reviewed asset bytes. Visible image content requires visual inspection;
text sanitization does not establish that an image contains no credentials.

Seal the original five payloads plus `visuals.zip`, with the input index binding
all six. Schema-3 review additionally binds `visuals_sha256` alongside narrative,
evidence and scene hashes. Model review checks claims, captions and provenance;
it must not claim pixel inspection if the configured model is text-only. Browser
layout/decode checks run automatically; human visual inspection remains the
release/acceptance check for image content, as listening does for speech. No new
per-run user-approval dependency is introduced into unattended dispatch.

Source and browser ZIPs include asset bytes, manifest, derived checks and the
trusted rendering code. PDF and MP4 use identical reviewed visible content.
The published artifact kinds remain the existing five. The renderer stays
offline, and recovery uses sealed bytes rather than re-fetching source pages.

## Timing, pronunciation and visual verification

Use measured sentence offsets from existing synthesis. Each check row highlights
from the start of its first mapped sentence through the end of its last one.
Sentence offsets are relative to speech: absolute time is the scene's measured
start plus the 0.35s lead-in plus the sentence offset. Validate mappings before synthesis;
one sentence may introduce a group but cannot highlight two rows simultaneously.
Keep sentence captions. Do not guess word alignment or label illustrative graph
motion as a recorded trace. Reset highlight state on slide changes/seek/print.

The next-actions slide begins with its next-action explanation. Put lengthy
recaps on a preceding takeaway slide when needed. This is an author/reviewer
semantic check as well as measured timeline QA; shifting slide boundaries alone
cannot fix an incorrectly authored story.

Audition full-name AutoPoC candidates in Heart before selecting a lexicon entry.
Compare “auto P-O-C” and “auto pock” in realistic sentences. Preserve the written
name, exact script and synthesis-only lexicon contract. Retain `af_heart` at 0.95
speed. Selection is pending a listening decision; spelling changes alone are
not a verified fix. Arbitrary new project names are checked during listening,
not assumed correct because the AutoPoC entry is correct.

Fix the existing TopoLoop freeze lifecycle so successive inspection timestamps
actually repaint. Verify heading, subtitle, node labels, edge/group captions and
footer together at every act/pose selected by the validator. Fail on illegible
or clipped text; never shrink all text to conceal an overflow failure.

Keep preparation/browser checks, CPU speech and final recording sequential so
Chromium and Torch memory peaks do not overlap. Preserve 3000s process budget,
3600s Job deadline, 2 CPU/4Gi memory and existing scratch/storage guards. Late
completion beyond the 300s worker wait remains expected and must recover with
the same input/asset hashes, without rerunning PoC tests.

## Acceptance and rollout

Use synthetic fixtures covering a GitHub-hosted service, a GitLab-hosted CLI and
a Codeberg/self-hosted library. These are test classes, not deployment promises.
Include absent imagery, no web UI, empty/large test inventories, mixed outcomes,
long names, partial evidence and no topology. Do not infer Kubernetes objects
for a library merely to fill a 3D layout. Preserve legacy golden fixtures.

Run meaningful Python and browser tests, full project required checks and an
offline renderer-image smoke test. Visually inspect PDF/video poses and listen
to pronunciation samples before declaring media quality accepted. Any live run
uses explicitly configured digest-pinned images and retained evidence; no shared
image/configuration activation, cloud publication or merge is implied by this
design. Drive authorization and existing rollout gates remain outstanding.

## Design review record

The fresh builder check on 10 November 2026 found “nothing important left.”
The versioned schema/asset contract, local-staging-first capture boundary and
resource bounds above are proposed engineering choices, not previously approved
user requirements. An implementation plan accompanies this document; product
execution remains pending review.

The OpenShell storyboard is the worked visual reference only. Product code,
new audio/video, image capture automation and production rollout have not been
implemented by recording this design.
