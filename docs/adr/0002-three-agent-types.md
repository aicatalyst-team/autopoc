# 2. Three Agent Types: Procedural, Two-Phase, and ReAct

Date: 2025-03

## Status

Accepted

## Context

Not every pipeline step needs a full LLM-powered ReAct agent. Some steps are deterministic (fork a repo, run podman build), some need judgment (generate a Dockerfile), and some benefit from a fast one-shot attempt with a fallback.

## Decision

Use three distinct agent architectures:

- **Procedural** (no LLM): fork, build, apply, poc_report. Pure code, zero LLM calls.
- **Two-phase** (deterministic then LLM): intake (repo_digest + one-shot analysis), poc_plan (one-shot JSON + ReAct fallback).
- **ReAct** (agentic with tools): containerize, deploy, poc_execute. Full tool-calling loop.

## Alternatives Considered

- **Everything ReAct**: Expensive, slow, unreliable for deterministic tasks. Earlier intake versions used ReAct with file-reading tools and often exhausted the step budget before producing output.

## Consequences

- (+) Cost: procedural agents make zero LLM calls
- (+) Speed: fork + build complete in seconds, not minutes
- (+) Reliability: deterministic steps have no LLM variance
- (+) ReAct reserved for tasks that genuinely need iterative reasoning
- (-) Three code patterns to maintain instead of one
