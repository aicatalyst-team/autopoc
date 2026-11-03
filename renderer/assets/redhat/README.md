# Local Red Hat brand assets

This directory stores the fonts and corporate artwork needed by the proposed
default Red Hat presentation theme. Assets are committed source files, not
download-on-demand dependencies. The renderer's layout and source-package
integration is a separate Phase 8 task and is not implemented by this bundle.

## Inventory

- `fonts/`: Red Hat Display, Red Hat Text and Red Hat Mono, each in Regular
  (400), Medium (500) and Bold (700), normal style, as WOFF2 files.
- `logos/redhat-logo-standard.svg`: official full-color horizontal corporate
  lockup for light backgrounds and the proposed white footer band.
- `logos/redhat-hat-standard.svg`: official full-color hat mark for established
  brand contexts, following the supplied presentation template.
- `licenses/OFL.txt` and `licenses/AUTHORS.txt`: unmodified upstream font
  licensing and authorship notices.
- `manifest.json`: source URL, SHA-256 and byte size of every bundled upstream
  file, plus the immutable font repository commit and retrieval date.

The supplied reference deck is tracked separately at
[`docs/branding/redhat-standard-presentation-template.pdf`](../../../docs/branding/redhat-standard-presentation-template.pdf).
Its provenance is recorded in `docs/branding/README.md`. It is a design reference,
not an image background for generated slides.

## Sources and use

Fonts come from [RedHatOfficial/RedHatFont](https://github.com/RedHatOfficial/RedHatFont)
at commit `6bb1048a6402b0076ea04f42951ec66263cd1437` and are licensed under
SIL Open Font License 1.1. Preserve the license and author notices in distributable
source archives. Use Display for headings, Text for body copy, and Mono for code
and technical labels.

Logo SVGs are unmodified files from Red Hat's official website. Red Hat names and
logos are trademarks; the font OFL and this repository's software license do not
relicense them. Follow the
[logo standards](https://www.redhat.com/en/about/brand/standards/logo), preserving
proportions, approved colors and clear space. Use the corporate artwork rather
than recreating a wordmark with a font or borrowing the reference's product logo.

Do not recolor these SVGs for a dark/red surface. Use the existing white footer
band or add an official approved colorway, with provenance and a manifest entry.

## Offline and packaging contract

- Use local asset paths in trusted CSS/components. Do not load fonts or brand
  images from Google Fonts, CDNs, the Brand Portal or operator home directories
  while generating, previewing or recording a presentation.
- Copy required assets and font notices into the generated editable source ZIP
  and browser build. Preserve their bytes and use the same versions for PDF and
  MP4 capture. Do not rely on symlinks outside the source package.
- Verify required font faces and images finish loading before capture readiness;
  missing assets must produce an actionable failure, not an unbranded fallback.
- Any additional artwork, backgrounds, icons or font styles must be committed
  alongside their source/license metadata and checksum before use. Layouts,
  palette definitions and reusable components must also live in the repository.

## Updating and verifying

Download font updates only from a reviewed immutable upstream commit. For logo
updates, retrieve the official source without editing its vector paths. Update
the manifest hashes/sizes and source records together. Never fetch an update
automatically during rendering.

For each `manifest.json` file entry, compute SHA-256 over the committed file and
compare both hash and byte size to the recorded values. WOFF2 files must have the
`wOF2` header and the declared family/weight; SVGs must parse as SVG and contain
no scripts, event handlers or external resources. Visual review confirmed the
two committed logo files on 3 November 2026.
