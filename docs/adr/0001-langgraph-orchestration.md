# 1. Use LangGraph for Pipeline Orchestration

Date: 2025-03

## Status

Accepted

## Context

AutoPoC needs to orchestrate 10 agents in a pipeline with:
- Cyclic retry loops (build failure -> fix Dockerfile -> rebuild)
- Parallel execution (poc_plan and fork run concurrently)
- Conditional routing (error handling, deployment model selection)
- Checkpointing for resumable runs
- Shared typed state across all agents

## Decision

Use LangGraph as the orchestration framework. Each agent is a node in a `StateGraph`, reading from and writing to a shared `PoCState` TypedDict.

## Alternatives Considered

- **Plain LangChain**: Lacks cyclic graphs, parallel fan-out/fan-in, and built-in checkpointing.
- **Custom orchestration**: Would require reimplementing state management, retry logic, and checkpoint serialization.

## Consequences

- (+) Cyclic retry loops are native (conditional edges back to earlier nodes)
- (+) Parallel fan-out/fan-in via `Send` API
- (+) Built-in checkpointing with `SqliteSaver` enables `autopoc resume`
- (+) Typed state contract via `PoCState` TypedDict
- (-) Coupling to LangGraph's state merge semantics for parallel nodes
- (-) Requires `poc_plan_error` separate from `error` to avoid parallel state conflicts
