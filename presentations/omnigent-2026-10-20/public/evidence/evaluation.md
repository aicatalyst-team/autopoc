# Omnigent — RHOAI Fitness Evaluation

**Strategy**: Red Hat AI 2026 (`redhat-ai-2026`)
**Relationship**: adjacent

## Summary

Omnigent is an open-source agent **orchestration / runtime** layer (a
"meta-harness") that sits above many AI coding agents and gives teams a common
control plane: multi-agent supervision, MCP tool connectivity, policy/governance
(spend caps, approval gates), a multi-device web UI, and an LLM gateway. It maps
primarily to the **Agentic AI** strategy area (agent runtime, MCP, agents-API,
developer experience) and secondarily to **Management, Observability & Security**
(guardrails/policies, API management).

It is not a model-serving or model-customization project; it is the layer that
*orchestrates* agents. On Red Hat AI it would complement the Llama Stack / MCP
agentic story by proving that a rich, production-shaped agent control plane can
be hosted, governed, and scaled on OpenShift.

## Impact dimensions (0–20)

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| audience_value | 16 | Broad developer audience — anyone running coding agents; multi-device (terminal/browser/phone), collaborative, policy-governed. High everyday appeal. |
| strategic_alignment | 14 | Squarely in the Agentic AI area (agent runtime, MCP, agents-API, developer experience). Not the core model-serving story, but a first-class citizen of the 2026 agentic direction. |
| strategy_fit | 14 | Enriches the agent deployment/runtime story and adds governance (policies, spend caps) that OpenShift AI wants to demonstrate. Some overlap risk with generic agent frameworks, but it has a durable server/platform angle rather than being local-only. |
| platform_leverage | 13 | Deploys cleanly as a self-contained UBI server + web UI on OpenShift (Route, PVC, probes). Could integrate with Llama Stack/MCP, but does not deeply depend on Red Hat AI-specific capabilities. |
| demo_potential | 17 | Highly visual and compelling: multi-agent sessions, live web UI, phone access, policy approval cards, LLM gateway. Strong narrative for a PoC demo. |

**Impact average: 14.8 / 20**

## Feasibility dimensions (0–20)

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| container_readiness | 18 | Ships a UBI 9 Dockerfile (multi-stage, non-root USER 1001, `/health` check) plus full Kustomize manifests and OpenShift/Postgres overlays with Routes and security contexts. Exceptionally container-ready. |
| dependency_profile | 14 | Heavy but well-structured: many Python deps + a React/Vite web build baked into the image + optional harness CLIs. The pnpm web build is the heaviest, most variable step. |
| reproduction_confidence | 15 | Thorough deployment docs (`deploy/README.md`, `deploy/kubernetes/README.md`, docker-compose). Both Postgres and SQLite backends documented. High confidence in reproduction. |
| complexity_sweet_spot | 12 | The full system is large (server + web + SDKs + harnesses + sandboxes). The PoC isolates just the server, which is the right size, but the surrounding system is complex. |

**Feasibility average: 14.8 / 20**

## Total score

**(impact + feasibility) / 40 × 100 = 73.9 / 100**

## Strengths

- First-class **Agentic AI** story: multi-agent orchestration, MCP, policy governance.
- **Already UBI + OpenShift-ready** — ships `Dockerfile.ubi`, Kustomize, and OpenShift overlays.
- Self-contained server deployment (single pod + PVC) is achievable and robust.
- Rich, demo-friendly web UI and multi-device collaboration.

## Risks

- Orchestrates *external* agent harnesses (Claude Code, Codex, …) that are
  external CLIs — the "agent work" happens on registered hosts, not in the pod,
  so a server-only PoC demonstrates the control plane, not full agent execution.
- Heavier build (web UI + many Python deps) increases build time / failure surface.
- Requires a backing store (Postgres or SQLite) and a cookie secret to boot.
- Overlap risk: could be seen as "another agent framework" unless positioned as
  a governable, hostable agent control plane on OpenShift.

## Recommendation

**Proceed.** Strong candidate for the Agentic AI strategy area with excellent
container readiness. Scope the PoC to the self-contained server (SQLite backend,
single pod + PVC, Route) and validate the control-plane endpoints and web UI.
