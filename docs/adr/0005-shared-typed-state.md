# 5. Shared TypedDict State with Progressive Population

Date: 2025-03

## Status

Accepted

## Context

Pipeline agents need to share data (repo analysis, PoC plan, built images, test results). Need a typed contract that supports incremental construction — early agents set some fields, later agents add more.

## Decision

All agents read from and write to a single `PoCState` TypedDict with `total=False`. Agents return partial dicts (`PoCStateUpdate = dict[str, Any]`) and LangGraph merges them into the full state.

Key design choices:
- `total=False` makes all fields optional (populated progressively)
- `Annotated[list, add_messages]` for LangGraph message accumulation
- Nested TypedDicts for structured data (`ComponentInfo`, `PoCScenario`, `PoCInfrastructure`, `PoCResult`)

## Alternatives Considered

- **Separate state per node**: Would require explicit data passing between agents.
- **Pydantic models**: Heavier, doesn't integrate with LangGraph's state merge.

## Consequences

- (+) Single source of truth for pipeline state
- (+) Type checking via pyright catches field name typos
- (+) LangGraph handles merge semantics (including parallel node outputs)
- (-) Large state object (30+ fields) that grows with each feature
- (-) `total=False` means no compile-time guarantee that required fields are set at a given pipeline stage
- (-) Agents must use `.get()` defensively for optional fields
