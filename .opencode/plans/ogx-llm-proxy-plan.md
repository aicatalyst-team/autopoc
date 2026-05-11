# Phase 14: OGX LLM Proxy for PoC Projects

> Detailed implementation plan for deploying an OGX (formerly LlamaStack) server
> as an OpenAI-compatible LLM proxy for PoC projects. Eliminates the need to
> hand real API keys to arbitrary third-party code by routing LLM requests
> through our own infrastructure.

---

## Problem Statement

Many projects we want to PoC require API keys to LLM providers (OpenAI,
Anthropic). Handing real API keys to arbitrary third-party code is a security
risk — keys could be leaked, exfiltrated, or abused. We need a proxy layer that:

1. Presents an **OpenAI-compatible API** to PoC projects
2. Routes requests to our own **vLLM Qwen3-32B** backend (no external API key
   exposure)
3. Runs in-cluster, no auth required (network isolation is sufficient)
4. Is architecturally ready for adding real OpenAI/Anthropic providers later

**Consumers:** PoC projects only. AutoPoC's own agents continue using
Vertex/Anthropic/vLLM directly — this feature does not change the pipeline's
own LLM provider.

---

## Overview

### What is OGX?

OGX (Open GenAI Stack, formerly Llama Stack by Meta) is an open-source agentic
API server. Key properties relevant to us:

- **OpenAI-first API surface** — implements `/v1/chat/completions`,
  `/v1/completions`, `/v1/embeddings`, `/v1/models`
- **Pluggable providers** — 23 inference backends including `remote::vllm`,
  `remote::openai`, `remote::anthropic`
- **Model aliasing** — register a `model_id` (e.g., `gpt-4`) that maps to a
  `provider_model_id` (e.g., `qwen3-32b`) on a specific provider
- **Optional auth** — runs without auth by default; supports OAuth2, K8s
  ServiceAccount, GitHub token, custom auth when needed
- **YAML config** with env var substitution (`${env.VAR:=default}`)
- **UBI9-compatible** — upstream Containerfile already has a `dnf` code path
  for RHEL/UBI bases (they explicitly mention RHOAI in comments)

GitHub: `ogx-ai/ogx` (formerly `meta-llama/llama-stack`)
PyPI: `ogx` | Docker Hub: `llamastack/distribution-*` (rename pending)
Current version: v0.8.0

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  OpenShift Cluster                                              │
│                                                                 │
│  ┌─────────────────┐         ┌──────────────────┐               │
│  │  poc-myproject   │         │  ogx  namespace  │               │
│  │  namespace       │         │                  │               │
│  │                  │         │  ┌────────────┐  │               │
│  │  ┌────────────┐  │         │  │ OGX Server │  │               │
│  │  │ PoC App    │  │  ─────► │  │ :8321      │  │               │
│  │  │ (RAG, LLM  │──┼────────│  └─────┬──────┘  │               │
│  │  │  chatbot)  │  │         │        │         │               │
│  │  └────────────┘  │         └────────┼─────────┘               │
│  └─────────────────┘                   │                         │
│                                ┌───────▼─────────┐               │
│                                │  vllm namespace  │               │
│                                │                  │               │
│                                │  ┌────────────┐  │               │
│                                │  │ vLLM       │  │               │
│                                │  │ Qwen3-32B  │  │               │
│                                │  │ :8000      │  │               │
│                                │  └────────────┘  │               │
│                                └──────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. PoC app calls `http://ogx-svc.ogx.svc.cluster.local:8321/v1/chat/completions`
   with model `qwen3-32b` and `api_key="none"`
2. OGX routes to vLLM at `http://qwen3-svc.vllm.svc.cluster.local:8000/v1`
3. vLLM performs inference with Qwen3-32B, returns response
4. OGX returns OpenAI-format response to PoC app

Cross-namespace DNS (e.g., `ogx-svc.ogx.svc.cluster.local`) works on our
cluster without NetworkPolicy changes.

### How PoC Projects Get Wired Up

The existing pipeline already has the building blocks:

1. **PoC Plan agent** already detects env vars like `OPENAI_API_KEY: "required"`
   and puts them in `extra_env_vars`
2. **Deploy agent** already generates K8s Secrets for sensitive env vars and
   plain `env:` entries for non-sensitive ones

The new flow adds:

1. **PoC Plan agent** additionally sets `needs_llm_api: true` and identifies the
   `llm_env_pattern` (openai, anthropic, langchain, custom)
2. **A new `resolve_llm_env_vars()` function** transforms the env vars: replaces
   `OPENAI_API_KEY: "required"` with `OPENAI_API_KEY: "none"`, adds
   `OPENAI_BASE_URL: "<ogx-url>"`, sets `OPENAI_MODEL: "qwen3-32b"`
3. **Deploy agent** generates manifests with the resolved env vars — all
   non-sensitive, so they go as plain `env:` values (not Secrets)

---

## Component Breakdown

### Component 1: OGX Container Image (UBI9)

**Approach:** Build from upstream Containerfile with UBI9 base arg. The upstream
Containerfile already supports UBI9 via its `dnf` branch — no custom Dockerfile
needed.

```bash
# Clone upstream at pinned tag
git clone --depth 1 --branch v0.8.0 https://github.com/ogx-ai/ogx.git /tmp/ogx

# Build with UBI9 base
podman build \
  -f /tmp/ogx/containers/Containerfile \
  --build-arg BASE_IMAGE=registry.access.redhat.com/ubi9/python-312:latest \
  --build-arg DISTRO_NAME=starter \
  --tag quay.io/autopoc/ogx:ubi9-v0.8.0 \
  /tmp/ogx

# Tag as latest
podman tag quay.io/autopoc/ogx:ubi9-v0.8.0 quay.io/autopoc/ogx:ubi9-latest

# Push
podman push quay.io/autopoc/ogx:ubi9-v0.8.0
podman push quay.io/autopoc/ogx:ubi9-latest
```

**Build pipeline artifacts:**
- New Makefile targets: `ogx-image`, `ogx-image-push`
- New build script: `deploy/build-ogx.sh` (wraps the above with error handling,
  pinned version variable at the top)

### Component 2: OGX Kubernetes Manifests

**Location:** `deploy/lab/ogx.yaml` (following existing pattern of
`qwen3-32b.yaml`, `qwen-2.5-coder.yaml`)

**Namespace:** `ogx` (dedicated, separate from `vllm` and `autopoc`)

```yaml
# --- Namespace ---
apiVersion: v1
kind: Namespace
metadata:
  name: ogx
---
# --- ConfigMap with OGX config ---
apiVersion: v1
kind: ConfigMap
metadata:
  name: ogx-config
  namespace: ogx
data:
  config.yaml: |
    version: 2
    distro_name: autopoc-ogx

    apis:
    - inference

    providers:
      inference:
      - provider_id: vllm
        provider_type: remote::vllm
        config:
          base_url: http://qwen3-svc.vllm.svc.cluster.local:8000/v1
          max_tokens: 4096
          api_token: none

    models:
    # Primary model — matches the vLLM served-model-name
    - model_id: qwen3-32b
      provider_id: vllm
      provider_model_id: qwen3-32b
      model_type: llm
    # Aliases — PoC projects requesting these get routed to Qwen3
    - model_id: gpt-4
      provider_id: vllm
      provider_model_id: qwen3-32b
      model_type: llm
    - model_id: gpt-4o
      provider_id: vllm
      provider_model_id: qwen3-32b
      model_type: llm
    - model_id: gpt-4o-mini
      provider_id: vllm
      provider_model_id: qwen3-32b
      model_type: llm
    - model_id: gpt-3.5-turbo
      provider_id: vllm
      provider_model_id: qwen3-32b
      model_type: llm

    server:
      port: 8321
---
# --- Deployment ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ogx
  namespace: ogx
  labels:
    app: ogx
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ogx
  template:
    metadata:
      labels:
        app: ogx
    spec:
      containers:
      - name: ogx
        image: quay.io/autopoc/ogx:ubi9-latest
        args: ["--config", "/etc/ogx/config.yaml"]
        ports:
        - containerPort: 8321
        volumeMounts:
        - name: config
          mountPath: /etc/ogx
          readOnly: true
        startupProbe:
          httpGet:
            path: /v1/models
            port: 8321
          failureThreshold: 30
          periodSeconds: 5
        readinessProbe:
          httpGet:
            path: /v1/models
            port: 8321
          periodSeconds: 10
          failureThreshold: 3
        livenessProbe:
          httpGet:
            path: /v1/models
            port: 8321
          periodSeconds: 30
          failureThreshold: 3
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2"
            memory: "2Gi"
      volumes:
      - name: config
        configMap:
          name: ogx-config
---
# --- Service ---
apiVersion: v1
kind: Service
metadata:
  name: ogx-svc
  namespace: ogx
  labels:
    app: ogx
spec:
  selector:
    app: ogx
  ports:
  - port: 8321
    targetPort: 8321
    protocol: TCP
```

**Multi-provider readiness:** The ConfigMap's `providers.inference` list can be
extended later with real OpenAI/Anthropic providers. Adding a provider is a
ConfigMap edit + a K8s Secret for the API key:

```yaml
# Future: add OpenAI provider
providers:
  inference:
  - provider_id: vllm
    provider_type: remote::vllm
    config:
      base_url: http://qwen3-svc.vllm.svc.cluster.local:8000/v1
      api_token: none
  - provider_id: openai
    provider_type: remote::openai
    config:
      api_key: ${env.OPENAI_API_KEY}
```

### Component 3: AutoPoC Configuration Extension

**New config fields** in `src/autopoc/config.py`:

```python
# OGX LLM Proxy (for PoC projects that need LLM access)
ogx_base_url: str | None = Field(
    default=None,
    description="OGX server URL for PoC projects "
    "(e.g. http://ogx-svc.ogx.svc.cluster.local:8321/v1). "
    "When set, PoC projects that need LLM access will be directed here.",
)
ogx_model: str = Field(
    default="qwen3-32b",
    description="Default model name to use on the OGX server.",
)
ogx_api_key: str = Field(
    default="none",
    description="API key for OGX server (use 'none' if no auth).",
)
```

**New environment variables:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OGX_BASE_URL` | No | `None` | OGX server URL. When set, enables LLM proxy injection for PoC projects. |
| `OGX_MODEL` | No | `qwen3-32b` | Default model name on OGX. |
| `OGX_API_KEY` | No | `none` | API key for OGX (use `none` if no auth). |

**Other files to update:**

- `.env.example` — add new fields with comments
- `deploy/base/job.yaml` — add OGX env vars from Secret (optional: true)
- `deploy/lab/secret.yaml` — add OGX connection details
- `config.py` `masked_summary()` — add `ogx_api_key` to secret fields

### Component 4: State & Infrastructure Schema

**New fields in `PoCInfrastructure`** (`src/autopoc/state.py`):

```python
class PoCInfrastructure(TypedDict, total=False):
    # ... existing fields ...

    # LLM proxy configuration — set by PoC Plan when project needs LLM API
    needs_llm_api: bool           # Whether the app calls an external LLM API
    llm_env_pattern: str | None   # "openai" | "anthropic" | "langchain" | "custom" | None
```

These fields tell the deploy agent whether and how to inject OGX connection
details. The PoC Plan agent sets them based on analysis of the project's
imports, env vars, and README.

### Component 5: PoC Plan Agent Enhancement

**New section in `src/autopoc/prompts/poc_plan.md`:**

```markdown
## LLM API Detection

Determine whether the project calls an external LLM API. If it does, set
`needs_llm_api: true` and identify the env var pattern.

### Detection Patterns

**"openai"** — Uses OpenAI SDK or expects OpenAI-style env vars:
- `import openai` or `from openai import ...`
- `OPENAI_API_KEY` in env vars, .env files, README, or config
- `OPENAI_BASE_URL` or `OPENAI_API_BASE` references
- LiteLLM with OpenAI-style config

**"anthropic"** — Uses Anthropic SDK or expects Anthropic env vars:
- `import anthropic` or `from anthropic import ...`
- `ANTHROPIC_API_KEY` in env vars or config
- Direct Claude API calls

**"langchain"** — Uses LangChain with configurable LLM backends:
- `from langchain_openai import ChatOpenAI`
- `from langchain_anthropic import ChatAnthropic`
- `from langchain.llms import ...`
- `from langchain_community.llms import ...`

**"custom"** — Uses a custom HTTP client to call LLM endpoints:
- Direct `httpx` / `requests` calls to `/v1/chat/completions`
- Custom wrapper around LLM APIs

### Output Fields

When `needs_llm_api` is true, also ensure `extra_env_vars` contains all
LLM-related env vars the project needs. Use the value `"required"` for
API keys/secrets. Examples:

- OpenAI pattern: `{"OPENAI_API_KEY": "required", "OPENAI_MODEL": "gpt-4"}`
- Anthropic pattern: `{"ANTHROPIC_API_KEY": "required"}`
- LangChain: `{"OPENAI_API_KEY": "required", "OPENAI_API_BASE": "required"}`
```

**Update the JSON output schema** in the prompt to include the new fields:

```json
{
  "infrastructure": {
    "...existing fields...",
    "needs_llm_api": true,
    "llm_env_pattern": "openai"
  }
}
```

### Component 6: LLM Proxy Resolution Logic

**New file:** `src/autopoc/llm_proxy.py`

This module contains the logic for transforming LLM-related env vars to
point at the OGX proxy instead of requiring real API keys.

```python
"""LLM proxy resolution for PoC projects.

When an OGX server is configured, this module transforms LLM-related
environment variables to point at the OGX proxy instead of requiring
real API keys from external providers.
"""

from autopoc.config import AutoPoCConfig
from autopoc.state import PoCInfrastructure


def resolve_llm_env_vars(
    extra_env_vars: dict[str, str],
    infrastructure: PoCInfrastructure,
    config: AutoPoCConfig,
) -> dict[str, str]:
    """Resolve LLM-related env vars by substituting OGX proxy details.

    If OGX is configured and the project needs LLM API access,
    replaces placeholder API keys with OGX connection details.

    Args:
        extra_env_vars: Original env vars from PoC plan.
        infrastructure: PoC infrastructure requirements.
        config: AutoPoC configuration.

    Returns:
        Modified env vars dict with OGX substitutions applied.
        If OGX is not configured or the project doesn't need LLM
        access, returns the original dict unchanged.
    """
    if not config.ogx_base_url or not infrastructure.get("needs_llm_api"):
        return extra_env_vars

    resolved = dict(extra_env_vars)
    pattern = infrastructure.get("llm_env_pattern", "openai")

    # Direct substitutions for known env var names
    substitutions = {
        # API key overrides — replace real keys with OGX (no auth)
        "OPENAI_API_KEY": config.ogx_api_key,
        "ANTHROPIC_API_KEY": config.ogx_api_key,

        # Base URL overrides — point at OGX
        "OPENAI_BASE_URL": config.ogx_base_url,
        "OPENAI_API_BASE": config.ogx_base_url,

        # Model name overrides — use OGX model
        "OPENAI_MODEL": config.ogx_model,
        "MODEL_NAME": config.ogx_model,
        "LLM_MODEL": config.ogx_model,
        "CHAT_MODEL": config.ogx_model,
    }

    for key in list(resolved.keys()):
        if key in substitutions:
            resolved[key] = substitutions[key]
        elif key.endswith("_API_KEY") and resolved[key] in (
            "required",
            "placeholder-replace-me",
        ):
            # Catch-all for any *_API_KEY with placeholder value
            resolved[key] = config.ogx_api_key

    # Ensure base URL and API key are always set when LLM access is needed
    if pattern in ("openai", "langchain"):
        resolved.setdefault("OPENAI_BASE_URL", config.ogx_base_url)
        resolved.setdefault("OPENAI_API_KEY", config.ogx_api_key)
    elif pattern == "anthropic":
        # OGX also supports Anthropic Messages API at the same endpoint
        resolved.setdefault("ANTHROPIC_API_KEY", config.ogx_api_key)
        # Some projects also accept OPENAI_BASE_URL for Anthropic
        resolved.setdefault("OPENAI_BASE_URL", config.ogx_base_url)

    return resolved
```

**Key design decisions:**

- **Passthrough when OGX is not configured:** If `OGX_BASE_URL` is not set,
  the function returns the original env vars unchanged. This means existing
  behavior is preserved — PoC projects that need real API keys will still
  generate `Secret` manifests with `"required"` placeholders.
- **Passthrough when project doesn't need LLM:** If `needs_llm_api` is false,
  no substitution happens.
- **All substituted values are non-sensitive:** `"none"` for API keys,
  cluster-internal URLs for base URLs. These go as plain `env:` values in the
  K8s manifest, not as Secret refs.

### Component 7: Deploy Agent Integration

The deploy agent's prompt (`src/autopoc/prompts/deploy.md`) and/or the deploy
agent code (`src/autopoc/agents/deploy.py`) needs to integrate the LLM proxy
resolution.

**Option A: Code-level integration** (preferred — deterministic):

In the deploy agent, before passing env vars to the manifest template or to the
LLM for manifest generation, call `resolve_llm_env_vars()`:

```python
from autopoc.llm_proxy import resolve_llm_env_vars

# Resolve LLM env vars through OGX proxy
env_vars = resolve_llm_env_vars(
    extra_env_vars=poc_infrastructure.get("extra_env_vars", {}),
    infrastructure=poc_infrastructure,
    config=config,
)
```

This is done **in code** (not in the LLM prompt) because it's a deterministic
transformation — no LLM reasoning needed. The resolved env vars are then
passed to the deploy LLM as context, and it generates manifests with the
OGX-substituted values.

**Option B: Prompt-level integration** (supplement):

Add a note to the deploy prompt so the LLM understands why API keys are `"none"`:

```markdown
## LLM Proxy Note

When the environment variables include `OPENAI_BASE_URL` pointing to an
internal OGX server (e.g., `http://ogx-svc.ogx.svc.cluster.local:8321/v1`)
and `OPENAI_API_KEY` is `"none"`, this is intentional. The OGX server acts
as a proxy to our own inference backend. These env vars should go as plain
`env:` values (not Secrets) since they contain no real secrets.
```

---

## Task Breakdown

### Task 14.1 — OGX Container Image Build Pipeline

**Files:** `deploy/build-ogx.sh`, `Makefile`

**Depends on:** nothing (can be done first)

**Work:**
- Create `deploy/build-ogx.sh`:
  - Pinned `OGX_VERSION=v0.8.0` at top
  - Clones upstream at pinned tag to temp dir
  - Builds with `BASE_IMAGE=registry.access.redhat.com/ubi9/python-312:latest`
    and `DISTRO_NAME=starter`
  - Tags as `quay.io/autopoc/ogx:ubi9-${OGX_VERSION}` and
    `quay.io/autopoc/ogx:ubi9-latest`
  - Pushes both tags
  - Cleanup temp dir
- Add `Makefile` targets:
  - `ogx-image` — build only
  - `ogx-image-push` — build + push

**Acceptance criteria:**
- `make ogx-image` builds successfully on UBI9
- Container starts and responds to `curl http://localhost:8321/v1/models`
- Image is pushed to `quay.io/autopoc/ogx:ubi9-latest`

---

### Task 14.2 — OGX Kubernetes Deployment Manifests

**Files:** `deploy/lab/ogx.yaml`

**Depends on:** Task 14.1

**Work:**
- Create `deploy/lab/ogx.yaml` with:
  - `Namespace` (ogx)
  - `ConfigMap` (ogx-config) with OGX YAML config
    - vLLM provider pointing to `qwen3-svc.vllm.svc.cluster.local:8000`
    - Model registrations: `qwen3-32b`, `gpt-4`, `gpt-4o`, `gpt-4o-mini`,
      `gpt-3.5-turbo` (all routing to Qwen3)
    - Server on port 8321
  - `Deployment` with startup/readiness/liveness probes
  - `Service` (ogx-svc) on port 8321
- Deploy to lab cluster
- Verify with:
  ```bash
  # From a pod in a different namespace
  curl http://ogx-svc.ogx.svc.cluster.local:8321/v1/models
  curl -X POST http://ogx-svc.ogx.svc.cluster.local:8321/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"qwen3-32b","messages":[{"role":"user","content":"Hello"}]}'
  ```
- Test model alias: request `gpt-4` and verify it resolves to Qwen3

**Acceptance criteria:**
- OGX pod is running and healthy
- `/v1/models` returns the registered models
- `/v1/chat/completions` returns valid responses via vLLM
- Cross-namespace access works from `poc-*` namespaces
- Model aliases (gpt-4, etc.) route correctly (or we know they don't and
  rely on deploy-agent override)

---

### Task 14.3 — AutoPoC Configuration Extension

**Files:** `src/autopoc/config.py`, `.env.example`, `deploy/base/job.yaml`,
`deploy/lab/secret.yaml`

**Depends on:** nothing (can be done in parallel with 14.1/14.2)

**Work:**
- Add to `AutoPoCConfig`:
  - `ogx_base_url: str | None` (env: `OGX_BASE_URL`)
  - `ogx_model: str` (env: `OGX_MODEL`, default: `"qwen3-32b"`)
  - `ogx_api_key: str` (env: `OGX_API_KEY`, default: `"none"`)
- Add `ogx_api_key` to `masked_summary()` secret fields set
- Update `.env.example` with commented-out OGX fields
- Update `deploy/base/job.yaml`:
  ```yaml
  - name: OGX_BASE_URL
    valueFrom:
      secretKeyRef:
        name: autopoc-credentials
        key: OGX_BASE_URL
        optional: true
  - name: OGX_MODEL
    valueFrom:
      secretKeyRef:
        name: autopoc-credentials
        key: OGX_MODEL
        optional: true
  - name: OGX_API_KEY
    valueFrom:
      secretKeyRef:
        name: autopoc-credentials
        key: OGX_API_KEY
        optional: true
  ```
- Update `deploy/lab/secret.yaml`:
  ```yaml
  OGX_BASE_URL: "http://ogx-svc.ogx.svc.cluster.local:8321/v1"
  OGX_MODEL: "qwen3-32b"
  OGX_API_KEY: "none"
  ```

**Acceptance criteria:**
- `AutoPoCConfig` validates with new fields present
- `AutoPoCConfig` validates with new fields absent (all optional/have defaults)
- `masked_summary()` masks `ogx_api_key`
- `.env.example` documents new fields
- Job manifest includes OGX env vars

---

### Task 14.4 — State & Infrastructure Schema Updates

**Files:** `src/autopoc/state.py`

**Depends on:** nothing

**Work:**
- Add to `PoCInfrastructure`:
  - `needs_llm_api: bool` — whether the project calls an external LLM API
  - `llm_env_pattern: str | None` — `"openai"` | `"anthropic"` | `"langchain"`
    | `"custom"` | `None`

**Acceptance criteria:**
- New fields are accessible from `PoCInfrastructure`
- Existing code that creates `PoCInfrastructure` still works (total=False)
- No test regressions

---

### Task 14.5 — PoC Plan Agent Prompt Enhancement

**Files:** `src/autopoc/prompts/poc_plan.md`

**Depends on:** Task 14.4

**Work:**
- Add "LLM API Detection" section to the prompt with:
  - Detection patterns for OpenAI, Anthropic, LangChain, custom
  - Instructions to set `needs_llm_api` and `llm_env_pattern`
  - Instructions to populate `extra_env_vars` with LLM-related env vars
- Update the JSON output schema example to include `needs_llm_api` and
  `llm_env_pattern`
- Update all existing examples to include the new fields (set to `false` /
  `null` for non-LLM projects)
- Add a new example for an LLM-dependent project (e.g., RAG app with
  `needs_llm_api: true`, `llm_env_pattern: "openai"`)

**Acceptance criteria:**
- Prompt clearly instructs the LLM on when and how to set the new fields
- JSON schema example includes new fields
- All existing examples updated to show `needs_llm_api: false`
- New LLM example shows `needs_llm_api: true` with correct env vars

---

### Task 14.6 — LLM Proxy Resolution Logic

**Files:** `src/autopoc/llm_proxy.py`, `tests/test_llm_proxy.py`

**Depends on:** Tasks 14.3, 14.4

**Work:**
- Create `src/autopoc/llm_proxy.py` with `resolve_llm_env_vars()` function
  (see Component 6 above for full implementation)
- Create `tests/test_llm_proxy.py` with tests:
  - **OGX configured + LLM needed:** env vars are substituted
  - **OGX not configured:** env vars pass through unchanged
  - **LLM not needed:** env vars pass through unchanged
  - **OpenAI pattern:** `OPENAI_API_KEY` and `OPENAI_BASE_URL` set correctly
  - **Anthropic pattern:** `ANTHROPIC_API_KEY` set correctly
  - **LangChain pattern:** both OpenAI env vars set
  - **Catch-all:** `*_API_KEY` with value `"required"` gets replaced
  - **Existing non-LLM env vars:** untouched (e.g., `DATABASE_URL`)
  - **Defaults added:** `OPENAI_BASE_URL` added even if not in original vars

**Acceptance criteria:**
- All substitution patterns tested
- Passthrough behavior tested (OGX not configured, LLM not needed)
- Edge cases handled (empty env vars, unknown pattern)
- All tests pass

---

### Task 14.7 — Deploy Agent Integration

**Files:** `src/autopoc/agents/deploy.py`, `src/autopoc/prompts/deploy.md`

**Depends on:** Task 14.6

**Work:**
- In the deploy agent code, add a call to `resolve_llm_env_vars()` before
  the LLM generates manifests:
  - Import `resolve_llm_env_vars` and `load_config`
  - Call it with the PoC plan's `extra_env_vars` and `infrastructure`
  - Pass the resolved env vars to the manifest generation context
- Add "LLM Proxy Note" section to `prompts/deploy.md` explaining that
  `OPENAI_API_KEY: "none"` with an internal OGX base URL is intentional
  and should not be placed in a Secret
- Ensure the deploy agent puts OGX-substituted env vars as plain `env:`
  entries (not `secretKeyRef`) since they're non-sensitive

**Acceptance criteria:**
- When OGX is configured and project needs LLM: generated manifests have
  `OPENAI_BASE_URL` pointing to OGX, `OPENAI_API_KEY: "none"` as plain env
- When OGX is not configured: existing behavior preserved (API keys in Secrets
  with placeholder values)
- Deploy prompt explains the OGX proxy pattern

---

### Task 14.8 — End-to-End Validation

**Depends on:** All previous tasks

**Work:**
- Deploy OGX to the lab cluster (Task 14.2)
- Configure AutoPoC with `OGX_BASE_URL` (Task 14.3)
- Run a PoC with a project that uses `OPENAI_API_KEY` (e.g., a LangChain RAG
  app, a chatbot with OpenAI SDK)
- Verify the full flow:
  1. PoC Plan detects `needs_llm_api: true`, `llm_env_pattern: "openai"`
  2. Deploy agent resolves env vars through OGX proxy
  3. Generated manifests have OGX URL and `api_key: "none"`
  4. PoC app starts and successfully calls the LLM via OGX → vLLM → Qwen3
  5. PoC test scenarios pass

**Acceptance criteria:**
- PoC app successfully makes LLM calls through OGX
- No real API keys are present anywhere in the generated manifests
- PoC report notes the LLM proxy configuration

---

## Design Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **OGX over raw vLLM** | OGX adds model aliasing, multi-provider readiness, and the Anthropic Messages API adapter. Adding real providers later is a ConfigMap edit — no AutoPoC code changes. |
| **No auth on OGX** | Cluster-internal only (ClusterIP service). Network isolation via K8s namespacing is sufficient. Adding auth later is a ConfigMap change. |
| **Deploy agent overrides model names** | More reliable than OGX aliasing alone. The deploy agent knows the exact env var pattern and sets the correct model name. Belt and suspenders with OGX aliases as backup. |
| **Separate namespace for OGX** | Keeps the OGX lifecycle independent from both AutoPoC (`autopoc` ns) and vLLM (`vllm` ns). Can be managed independently. |
| **ConfigMap for OGX config** | OGX config is non-sensitive (URLs, model names). Easy to update via `kubectl edit cm`. Future API keys would go in a K8s Secret with env var substitution in OGX config. |
| **`needs_llm_api` as explicit field** | More reliable than inferring from `extra_env_vars` key names. The PoC Plan agent reasons about whether the project truly needs LLM access vs. having an optional API key field. |
| **Code-level resolution (not prompt)** | `resolve_llm_env_vars()` is a deterministic transformation — no LLM reasoning needed. Doing it in code is faster, cheaper, and 100% reliable. |
| **UBI9 via upstream Containerfile** | The upstream Containerfile already has a `dnf` code path for RHEL/UBI bases and explicitly mentions RHOAI. Less maintenance than a custom Dockerfile. |

---

## OGX Configuration Reference

### Adding a New Provider (Future)

To add OpenAI as a provider alongside vLLM:

1. Create a K8s Secret with the API key:
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: ogx-providers
     namespace: ogx
   stringData:
     OPENAI_API_KEY: "sk-..."
   ```

2. Update the ConfigMap:
   ```yaml
   providers:
     inference:
     - provider_id: vllm
       provider_type: remote::vllm
       config:
         base_url: http://qwen3-svc.vllm.svc.cluster.local:8000/v1
         api_token: none
     - provider_id: openai
       provider_type: remote::openai
       config:
         api_key: ${env.OPENAI_API_KEY}

   models:
   - model_id: qwen3-32b
     provider_id: vllm
     provider_model_id: qwen3-32b
     model_type: llm
   - model_id: gpt-4o
     provider_id: openai
     provider_model_id: gpt-4o
     model_type: llm
   ```

3. Mount the Secret as env vars in the OGX Deployment.

4. Update `OGX_MODEL` in AutoPoC config if you want PoC projects to use the
   real model.

### OGX CLI Reference

```bash
# Start with config file
ogx stack run config.yaml --port 8321

# List models
curl http://localhost:8321/v1/models

# Chat completion
curl -X POST http://localhost:8321/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-32b","messages":[{"role":"user","content":"Hello"}]}'
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OGX model aliasing may not work as expected (bare `model_id` vs `provider_id/model_id`) | PoC projects requesting `gpt-4` get 404 | Deploy agent always overrides the model name; aliases are belt-and-suspenders. Test during Task 14.2. |
| OGX UBI9 build may fail due to missing system packages | Can't build the image | The upstream Containerfile already has a `dnf` branch for RHEL. If issues arise, we add packages in a thin wrapper script. |
| Qwen3-32B quality may be insufficient for some PoC projects | PoC tests fail due to poor LLM responses | Expected — architecture supports adding real providers later. Having *something* work is better than failing on missing API keys. |
| OGX adds latency | Slower LLM responses | Minimal — HTTP proxy in the same cluster. vLLM inference latency dominates. |
| Projects that hardcode model names in source code (not env vars) | Can't override at deploy time | Out of scope for automatic handling. PoC report should note this as a limitation. |
| OGX version drift | Future updates break our build | Pin to specific version tag. Update deliberately. |
| vLLM must be running for OGX to work | OGX health check fails if vLLM is down | OGX startup probe tolerates 30 failures (2.5 min). vLLM usually starts first. Could add init container if needed. |

---

## Files Changed Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `deploy/build-ogx.sh` | **New** | Build script for OGX UBI9 image |
| `deploy/lab/ogx.yaml` | **New** | K8s manifests: Namespace, ConfigMap, Deployment, Service |
| `src/autopoc/llm_proxy.py` | **New** | LLM env var resolution through OGX proxy |
| `tests/test_llm_proxy.py` | **New** | Unit tests for LLM proxy resolution |
| `src/autopoc/config.py` | **Modified** | Add `ogx_base_url`, `ogx_model`, `ogx_api_key` fields |
| `src/autopoc/state.py` | **Modified** | Add `needs_llm_api`, `llm_env_pattern` to `PoCInfrastructure` |
| `src/autopoc/agents/deploy.py` | **Modified** | Call `resolve_llm_env_vars()` before manifest generation |
| `src/autopoc/prompts/deploy.md` | **Modified** | Add LLM Proxy Note section |
| `src/autopoc/prompts/poc_plan.md` | **Modified** | Add LLM API Detection section, update examples |
| `.env.example` | **Modified** | Add OGX env vars |
| `deploy/base/job.yaml` | **Modified** | Add OGX env vars from Secret |
| `deploy/lab/secret.yaml` | **Modified** | Add OGX connection details |
| `Makefile` | **Modified** | Add `ogx-image`, `ogx-image-push` targets |
