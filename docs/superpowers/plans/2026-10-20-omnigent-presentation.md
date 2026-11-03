# Omnigent AutoPoC Presentation Plan

**Goal:** Deliver the approved stakeholder presentation of run
`autopoc-omnigent-8554` as editable Slidev source, a browser deck and a PDF.

**Scope approved in chat:** Twelve main slides, approximately ten minutes,
plus a technical evidence appendix. Use a red/charcoal visual style, diagrams,
source references and speaker notes. Cover outcome, purpose, scope, pipeline,
timeline, architecture, recovery, tests, deliverables, limitations, value and
next steps. This is a presentation of one run, not a new pipeline integration.

**Architecture:** A self-contained Slidev project under
`presentations/omnigent-2026-10-20/`. Evidence is pinned to GitHub commit
`f2d3c4d8183de4d67f5a2cb3135c3b653211f6e6` and original runner/build logs.
Use Slidev's native static build and Playwright PDF exporter.

**Tech stack:** Node 22, Slidev 53, default theme, Playwright/Chromium.

## Tasks

- [x] Archive reports, original test JSON, sanitized logs and selected cluster
  metadata. Index slide claims to their sources and distinguish original
  evidence from later observations. Record missing trace/media artifacts.
- [x] Author twelve stakeholder slides and a short evidence appendix with
  editable diagrams, timelines, source links and speaker notes.
- [x] Build the browser deck and export the PDF. Inspect every rendered slide,
  verify source links/local assets, check evidence and scan for credentials.
- [x] Package deliverables, document reproducible commands, update existing
  planning documents and commit only this presentation's changes.

## Verification record

- Slidev production build succeeded; PDF exported as 16 pages.
- Visually reviewed all pages and rechecked the final dark-slide contrast.
- Seven archived source hashes match; all 43 local asset references resolve.
- All 15 unique local evidence/media assets are served by the static preview.
- Scanned all 14 evidence files, decompressing logs, for recognizable credential
  patterns. Raw logs remain outside the presentation directory.
- Repository pre-commit checks passed for authored sources; archived evidence
  remains byte-identical to its indexed source snapshot.
- Independent final content review found no material issues.
- ZIP archive integrity check passed. Video work remains outside this delivery.

## Follow-up: TopoLoop setup and scenario walkthroughs

User requested TopoLoop topology and scenario flow added to the existing deck.
The result has fourteen main slides plus the existing four-slide appendix.

- [x] Vendor the unmodified runtime at commit
  `8631cf7955ebf40a579aab4ce3d0cca50d215c21`, retain MIT/OFL attribution and pin
  the Vue/Three dependencies. Node minimum is now 22.18.
- [x] Add an eight-resource setup spec with three acts and a five-act scenario
  spec derived directly from original result JSON. Label illustrative timing.
- [x] Integrate active-slide rendering, reduced-motion preference, evidence
  loading/error handling, still-frame controls and frozen PDF frames.
- [x] Complete all-act rendering/label checks, inspect the revised 18-page PDF,
  repackage sources and commit this follow-up.

Follow-up verification: both native specs validate; all three setup acts and
five scenario acts render with no active-label intersections at the inspected
frames. Reduced-motion default, explicit playback and missing-evidence fallback
were exercised in Chromium. The updated PDF has 18 pages; both new pages were
visually inspected. Seven archived source hashes remain unchanged and all 14
vendored runtime files match the pinned upstream revision. MIT/OFL assets are
served by the static preview, authored-file pre-commit checks pass, ZIP
integrity passes, and independent content/code review found no material issues.

## Verification focus

- Five HTTP smoke checks prove reachability and expected response text only.
- The 94m31s job duration includes documentation and blog review work.
- Persistent storage, authenticated workflows and inference remain untested.
- Preserve the actual retry and security-context history without overstating
  production readiness or measured labor savings.
- Raw logs and Secret resources must never enter the deliverable or commit.
- Exported pages must remain readable with no clipped content or missing assets.

## Rulings

- Use the already selected Slidev feature branch. This task adds presentation
  content and its local rendering dependencies; it changes no application code.
- Execute directly as authorized by the user's “Approve and build” response.
  Native build/export and visual inspection provide appropriate verification
  for this reversible presentation task; no application tests are needed.
- Video feasibility remains a separate, pending task in the existing plan.
