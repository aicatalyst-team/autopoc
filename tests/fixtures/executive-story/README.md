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
