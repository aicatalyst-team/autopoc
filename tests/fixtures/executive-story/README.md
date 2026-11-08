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
