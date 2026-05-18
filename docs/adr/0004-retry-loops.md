# 4. Self-Healing Retry Loops for Build and Deploy

Date: 2025-04

## Status

Accepted

## Context

LLM-generated Dockerfiles and Kubernetes manifests frequently have issues on the first attempt (missing dependencies, wrong ports, incorrect resource names). Manual intervention for every failure doesn't scale.

## Decision

Two retry loops in the pipeline:

1. **Build retry**: build fails -> increment `build_retries` -> route back to containerize (LLM reads the build error and fixes the Dockerfile) -> rebuild. Max 3 retries.

2. **Deploy retry**: apply fails -> increment `deploy_retries` -> route back to deploy (LLM reads kubectl error and fixes manifests) -> re-apply. Max 3 retries. An outer loop can escalate back to containerize if the error is in the container itself (e.g., CrashLoopBackOff).

Build errors are classified as **permanent** (auth failures, network issues) or **retriable** (Dockerfile bugs). Permanent errors skip the retry loop entirely.

## Alternatives Considered

- **Fail fast**: No retries. Low success rate for complex projects.
- **Human intervention**: Doesn't scale for batch processing.

## Consequences

- (+) Self-healing: LLM often fixes issues given the error context
- (+) Higher end-to-end success rate without human intervention
- (+) Bounded cost via max retry limits
- (+) Build agent also attempts inline Dockerfile patching for "command not found" errors (faster than full containerize round-trip)
- (-) Each retry costs an LLM call (~$0.01-0.05)
- (-) Can exhaust retries on fundamentally broken configurations
