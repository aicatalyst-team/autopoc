# 6. OGX LLM Proxy for PoC Projects

Date: 2025-10

## Status

Accepted

## Context

Many PoC projects require LLM API keys (OpenAI, Anthropic). Handing real API keys to arbitrary third-party code is a security risk — keys could be leaked, exfiltrated, or abused. Need a way to provide LLM access to deployed PoC applications without exposing credentials.

## Decision

Deploy an OGX (Open GenAI Stack) server as a cluster-internal OpenAI-compatible LLM proxy. PoC projects get environment variables pointing to the proxy (`OPENAI_BASE_URL`, `OPENAI_API_KEY=none`). The proxy routes requests to a self-hosted vLLM instance running Qwen3-32B.

The deploy agent resolves LLM environment variables deterministically in code (`resolve_llm_env_vars()`) — not via LLM prompt — making it fast, cheap, and 100% reliable.

## Alternatives Considered

- **Real API keys**: Security risk with third-party code.
- **vLLM directly**: No OpenAI-compatible API translation or model aliasing.
- **Custom proxy**: More code to maintain than leveraging OGX.

## Consequences

- (+) No real API keys exposed to third-party code
- (+) OpenAI-compatible: most projects work with just env var changes
- (+) Model aliasing: projects requesting `gpt-4` transparently get Qwen3-32B
- (+) No auth required (cluster-internal ClusterIP service)
- (-) Qwen3-32B quality may be insufficient for some projects
- (-) Requires OGX + vLLM running in the cluster
- (-) Projects that hardcode model names in source (not env vars) can't be overridden
