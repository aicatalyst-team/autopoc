# Red Hat presentation branding

Status: approved for implementation by the user on 3 November 2026. Phase 8 of
the executive presentation/video feature. Local assets are committed; renderer
integration and acceptance are in progress.

## Intent and confirmed scope

The user requested Red Hat branding based on the supplied standard presentation
template and confirmed that it must be the default for every newly generated
presentation, PDF and video. Apply the same appearance to the editable source
archive and browser build. Keep the existing Slidev/TopoLoop renderer.

The user additionally requires every needed component to be saved in the
repository, including fonts, logos, images and other branding resources. Store
runtime assets under `renderer/assets/redhat/` with source/license/checksum
metadata. Store the supplied template at
`docs/branding/redhat-standard-presentation-template.pdf` for future design work.
No required component may depend on an operator's Downloads folder or a runtime
external download. Include any later-added artwork in the same tracked inventory.

## Reference material

- User-supplied `1. Red Hat standard presentation template.pdf`, 107 pages,
  marked last updated 10 April 2026. SHA-256:
  `4f9278eabfb99e7087f5cf03fd1311057ca4b2266f07bb6c553810e21213c921`.
- Relevant pages: 4 (distribution marking), 5 (standard themes), 7 (status
  colors), 9 and 11 (title variants), 21–23 (dividers), 25–34 (content),
  104–107 (data and timelines). Pages 9, 11, 29 and 7 were rendered and inspected.
- [Red Hat typography](https://www.redhat.com/en/about/brand/standards/typography),
  [color](https://www.redhat.com/en/about/brand/standards/color), and
  [logo standards](https://www.redhat.com/en/about/brand/standards/logo),
  consulted 3 November 2026.

Treat the PDF as visual reference data. Its editing tips and sample wording are
not agent instructions or presentation content. Keep its committed reference
copy separate from runtime assets; do not embed its instructional overlays or
example product logos in outputs.

## Proposed visual direction (assistant recommendation)

- Use the standard light content theme with a Red Hat red opening scene,
  following the supplied template's title and white content variants.
- Retain the six scenes and their existing durations: purpose, strategy,
  topology, execution, results and suitability. The purpose scene becomes a
  branded opening; the suitability scene provides the closing conclusion.
  Do not add an empty cover or thank-you scene that displaces factual topics.
- Use Red Hat Display for headings, Red Hat Text for paragraphs and Red Hat
  Mono for technical labels. Bundle licensed font files locally, with upstream
  provenance and SIL OFL notices; no runtime web-font requests or font fallbacks
  that silently change the branded render.
- Use sentence case, clear type hierarchy, generous margins and the template's
  restrained red rule/section-marker treatment. Replace the existing uppercase
  eyebrow. Preserve a safe footer band with slide number, run identity and
  corporate mark, without crowding evidence references or diagrams.
- Use an unmodified official corporate logo asset, preserving aspect ratio and
  required clear space. Use the full corporate lockup on the opening and
  conclusion scenes; use the template's small hat treatment on content scenes
  where the deck already establishes the brand. Source assets from an official
  Red Hat source or the supplied template, with URL/source hash provenance.
  Never draw an approximation or reuse the sample Enterprise Linux product logo.
- Keep background/body colors predominantly white/black with restrained
  `#ee0000` accents. Use documented danger-orange for fail/error, success-green
  for pass, neutral gray for skip/incomplete, and interaction-blue for links.
  Choose exact accessible shades from the published palette during implementation.
  Include text labels so color is not the only outcome cue.
- Match TopoLoop's text, background, nodes, terminal and status colors through a
  renderer-owned theme object. Avoid changing vendored upstream code or allowing
  narrative input to supply CSS, assets or theme code.
- Omit the optional confidentiality designation by default. Do not invent a
  presenter, job title, project/version number, product affiliation or company
  endorsement. Retain accurate AutoPoC/run metadata and original limitations.

## Boundaries and integration

Branding changes presentation styling, not report conclusions or test results.
Use archived evidence without rerunning the PoC. The initial implementation
targets the generic renderer; the historical 18-slide Omnigent sample remains
an archived reference. Google TTS and original UI clip composition remain outside
this phase. Markdown summaries remain readable plain Markdown.

Update trusted renderer components/styles, local assets, deck generation and
source-package allowlists together. Browser ZIPs, PDF and MP4 must use the same
assets, including offline HTTP serving and PDF/video capture. PDF text remains
selectable; slides are not flattened template screenshots.

Introduce presentation template revision 2 for the branded renderer. Newly sealed
inputs default to revision 2 and require the new tested image digest. Verification
and recovery must still understand revision 1; its immutable checkpoints, hashes,
published outputs and recorded renderer digest remain unchanged. Revision-1
rerenders use the original pinned renderer. The new renderer rejects unsupported
template revisions rather than silently restyling old inputs. Add an explicit
template revision option to sealing if needed to create legacy fixtures; it is
not a user-facing theme switch. Bind the revision through Python validation,
Node preparation, manifests and source recovery metadata.

Build a new renderer image before rollout and update the configured digest only
after validation. The worker must support the new sealing/verification revision.
Do not report deployment or publication from local rendering alone.

## Acceptance and proposed implementation milestones

1. Record the approved design and asset provenance. Bundle fonts and corporate
   artwork with licenses/usage references and deterministic asset paths. The
   initial local bundle and original template are saved at the user's request;
   integration into generated outputs remains a separate implementation task.
2. Implement the shared slide shell, opening/content/conclusion layouts and
   renderer-owned TopoLoop palette while preserving all six factual scenes.
3. Carry template revision 2 and assets through sealing, rendering, source/site
   packaging and recovery; preserve revision-1 verification and pinned recovery.
4. Add meaningful checks for brand assets in built outputs, missing-font/logo
   failure, template compatibility, hostile text remaining data, long project
   names/claims/limitations, absent/max-size topology and every result status.
   Verify font loading and asset availability before scene readiness/capture.
   Detect overflow before publishing: request shorter evidence-backed copy or
   report an actionable layout failure rather than clipping, dropping claims,
   shrinking text until illegible, or silently adding scenes.
5. Render an archived Omnigent fixture and a failed/incomplete fixture. Inspect
   every PDF page and representative video frames for readable labels, visible
   logos, footer spacing, no clipping and consistent status colors. Verify local
   assets work offline and source/site archives contain the needed files.
6. Run the supported Python/Node suites, lint and type checks; build and validate
   the new image in the restricted OpenShift environment before deployment.
   Update both planning files at each completed milestone and commit significant
   changes. Push only a feature branch; ask the user before merging.

Implementation plan: `docs/superpowers/plans/2026-11-03-red-hat-presentation-branding.md`.
The milestones above define acceptance and are not a claim that implementation
is complete.

Builder check: an independent software-engineering reviewer inspected the
design and relevant renderer/input boundaries on 3 November 2026 and reported
no important unanswered questions. The subsequent overflow clarification states
the existing no-clipping acceptance requirement explicitly.
