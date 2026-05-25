# Scoring & Iteration Rules

## Score Aggregation

| Reviewer | Weight | Rationale |
|---|---|---|
| **Architect** | 30% | Structure is the skeleton |
| **Content** | 30% | Substance is why the reader stays |
| **Formatting** | 20% | Important but more fixable |
| **Image** | 20% | Enhances but doesn't make or break |

**Formula**: `overall = (architect * 0.30) + (content * 0.30) + (formatting * 0.20) + (image * 0.20)`

## Pass Criteria

Both must be true:
1. Overall weighted average >= 8.0
2. No individual dimension (across ANY reviewer) below 6.0

### Near-Miss Rule
If overall >= 7.5 AND only ONE dimension is between 5.0 and 5.9: flag as "conditional pass".

## Iteration Controls

- **Max 3 autonomous iterations** before checkpoint
- **For PoC mode** (non-interactive): auto-accept best draft after 3 iterations if score >= 7.0
- **Hard ceiling**: 9 iterations (3 checkpoints)
- **Early exit**: If draft passes before checkpoint, use it immediately

## Revision Priority

1. Fix blockers (dimensions below 6.0)
2. Address lowest-scoring dimension
3. Resolve conflicting feedback (developer blog favors technical depth)
4. Apply editorial quick wins (heading case, commas, product names)
5. Include changelog in new draft

### Changelog Format
```markdown
<!-- CHANGELOG — removed during finalization
vN changes:
- [Dimension]: [What changed and why]
-->
```

## Score Summary File

Update `drafts/reviews/score-summary.md` after each cycle:
```markdown
# Score Summary

## Status: [IN PROGRESS / PASSED / ACCEPTED]

| Version | Architect | Content | Formatting | Image | Overall | Status |
|---|---|---|---|---|---|---|
| v1 | [score] | [score] | [score] | [score] | [overall] | [status] |
```
