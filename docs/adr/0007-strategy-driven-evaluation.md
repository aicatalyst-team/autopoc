# 7. Strategy-Driven Project Evaluation

Date: 2025-09

## Status

Accepted

## Context

Need to score how well a project fits as a Proof-of-Concept on OpenShift AI. The scoring criteria change as business strategy evolves — hardcoding a rubric would require code changes for each strategy shift.

## Decision

Scoring dimensions are defined in YAML strategy files (`data/strategy_config.yaml`). Each strategy defines:
- Weighted scoring dimensions (e.g., audience_value, strategic_alignment)
- Core product categories
- Strategy areas and capability labels
- Relationship classification rules

The evaluate agent reads the active strategy at runtime and builds the scoring prompt dynamically. Switching strategies is a config change, not a code change.

Evaluation is explicitly **non-blocking** — if the LLM call fails, the pipeline continues with an empty evaluation. A failed score should never prevent a PoC from running.

## Alternatives Considered

- **Hardcoded rubric**: Requires code changes for each strategy shift.
- **Blocking evaluation**: Would gate the pipeline on score thresholds, preventing exploration of borderline projects.

## Consequences

- (+) Strategy changes are YAML-only, no code changes
- (+) Multiple strategies can coexist (select via config)
- (+) Non-blocking: pipeline never stops due to evaluation failure
- (-) LLM scoring is inherently inconsistent across runs
- (-) One extra LLM call per pipeline run
