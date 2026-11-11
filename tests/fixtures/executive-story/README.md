# Executive authoring acceptance examples

All three runs are explicitly synthetic fixtures, not measurements of a real
PoC. Each evidence ZIP is independently hash-verifiable and preserves its
original staged report, attempt index and selected outcomes. Companion narrative
and scene-plan JSON illustrate the version-2 authoring contract; they are not
production approvals and contain no fabricated model-review receipts.

- `simple`: one passing HTTP smoke check, no trace evidence, six chapters.
- `complex`: three passing HTTP checks and an eight-slide component/setup story.
- `failed`: one pass, one failure and one unexecuted scenario; the staged report
  has a contradictory success summary. The narrative qualifies that conflict,
  retains the meaningful storage correction and excludes the incidental login retry.

Use configured-model semantic review in addition to structural contract tests.
The tests can prove valid references/counts, not that prose is supported by a
source. Model/asset identities in these examples are test values; acceptance
rendering binds the actual reviewed asset manifest before final review/sealing.

`long/` is a declared synthetic 12-slide stress case with three original fixture
checks. It intentionally uses more narration than a normal three-check summary
to exercise >180s recording, sentence audio and graph states. It is not a
customer PoC or a production-content example.

`omnigent/` imports the committed 20 October original HTTP outcomes/report and
sanitized build excerpts from `presentations/omnigent-2026-10-20/public/evidence`.
Its provenance identifies historical import, rather than newly captured original
workspace state. Missing original workspace, UI recordings and traces remain
explicit; no test was replayed and later observations do not become original
results. Both received independent actual configured-model acceptance reviews
for the exact final draft; receipts remain acceptance-only.

`schema3-cases.json` contains synthetic validator-only service, CLI and library
stories on GitHub, GitLab, Codeberg and a self-hosted Git service. Their inline
source member is a declared synthetic source, not a real PoC or a sealed bundle.
The unchanged directories above remain schema-2 legacy acceptance fixtures.

Schema 3 adds required `project_context` keys `repository_url`, `revision`,
`definition_claim_id`, `homepage_url` and `documentation_url`. The revision and
optional URLs may be null; non-null URLs are credential-free HTTPS references.
Each slide adds required `layout` (`summary`, `identity`, `checks`, `topology`),
`visual_id` (null except optional identity imagery) and `checks` (empty outside
checks layouts). The opening visibly references the definition claim. Topology
requires a graph; one/two-component and graphless cases are included.

Each testing/checks row references its original `scenario_id`, source-linked
`label_claim_id` and `purpose_claim_id`, and nonempty zero-based contiguous
`narration_sentence_indices`. Row ranges follow speech and never overlap. Cases
cover 0, 1, 5, 6 and 11 scenarios and all five statuses; six/eleven paginate at
five rows. Empty inventory still requires a testing/checks slide: the renderer
must show its fixed no-checks message from the verified empty derived inventory.
Source-linked context remains subject to semantic review, without phrase matching.

`derive_checks` copies only scenario ID, original name and status, in verified
`final_results.results` order, into `{schema_version: 1, run_id, results}`. Python
binds exact row IDs against that verified inventory; the evidence-free browser
validator checks uniqueness and cardinality against reviewed totals. Visual
manifest existence/provenance and revision-unavailable display belong to the
subsequent asset/layout tasks. Scene plans retain schema 2 and measured audio
remains authoritative after the lower-bound duration guard.

For **semantically meaningful schema-3 authoring**, use the worker-packaged
[worked examples](../../../.opencode/skills/run-poc/references/executive-story-examples/README.md).
They demonstrate a GitHub service with explicitly conceptual imagery and six
mixed-outcome checks, a GitLab CLI with no UI, and a graphless Codeberg library
with no recorded checks or revision. Each includes a synthetic source ledger,
scene plan and visual/provenance manifest. They have no approval receipts.
`schema3-cases.json` remains validator-only: its inherited placeholder prose
is not a semantic example and must not guide project-specific claims.
