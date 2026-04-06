# AutoPoC — LangGraph Agent System Plan

## Overview

AutoPoC is a LangGraph-based multi-agent system that automates the end-to-end workflow of
taking an open-source project from GitHub and deploying it as a proof-of-concept on
OpenShift AI. The system uses Claude as its reasoning engine and interacts with external
systems (GitLab, Quay, OpenShift) primarily through CLI tools.

**Input:** Project name + GitHub repo URL
**Output:** Running PoC on OpenShift AI, with all artifacts (forked repo, UBI-based images,
deployment manifests) committed and available.

> **Implementation plan:** See [implementation-plan.md](./implementation-plan.md) for the
> detailed, ordered task breakdown (36 tasks across 5 phases).

---

## Architecture

### High-Level Flow

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Intake     │───▶│  Fork &     │───▶│ Containerize│───▶│  Build &    │───▶│  Deploy to  │
│   Agent      │    │  Clone      │    │  (UBI)      │    │  Push       │    │  OpenShift  │
│              │    │  Agent      │    │  Agent      │    │  Agent      │    │  AI Agent   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │                  │
       └──────────────────┴──────────────────┴──────────────────┴──────────────────┘
                                         │
                                  ┌──────┴──────┐
                                  │ Shared State │
                                  │ (PoC Record) │
                                  └─────────────┘
```

### Technology Stack

| Component       | Choice                                              |
|-----------------|-----------------------------------------------------|
| Framework       | Python 3.12+ with LangGraph                         |
| LLM             | Anthropic Claude (via `langchain-anthropic`)         |
| CLI Tools       | `git`, `podman`, `oc`, `helm`, `skopeo`              |
| Secrets         | Environment variables (`.env` file via `python-dotenv`) |
| State           | LangGraph `StateGraph` with `TypedDict` state        |
| Interface       | CLI (`typer`)                                        |
| Testing         | `pytest` + `pytest-asyncio`                          |

---

## Project Structure

```
autopoc/
├── plan.md
├── pyproject.toml
├── README.md
├── .env.example                  # Template for required env vars
├── src/
│   └── autopoc/
│       ├── __init__.py
│       ├── cli.py                # CLI entry point (typer)
│       ├── config.py             # Configuration & env var loading
│       ├── state.py              # Shared state definitions (TypedDict)
│       ├── graph.py              # Main LangGraph orchestrator graph
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── intake.py         # Repo analysis agent
│       │   ├── fork.py           # GitLab fork agent
│       │   ├── containerize.py   # Dockerfile.ubi generation agent
│       │   ├── build.py          # Image build & push agent
│       │   └── deploy.py         # OpenShift deployment agent
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── git_tools.py      # git clone, push, branch operations
│       │   ├── gitlab_tools.py   # GitLab API (fork, create project)
│       │   ├── podman_tools.py   # podman build, tag, push
│       │   ├── quay_tools.py     # Quay repo creation, image listing
│       │   ├── openshift_tools.py# oc apply, helm install, route mgmt
│       │   └── file_tools.py     # Read/write/search files in cloned repo
│       ├── prompts/
│       │   ├── intake.md         # System prompt for intake analysis
│       │   ├── containerize.md   # System prompt for Dockerfile generation
│       │   └── deploy.md         # System prompt for deployment planning
│       └── templates/
│           ├── Dockerfile.ubi.j2          # Jinja2 base UBI Dockerfile template
│           ├── Dockerfile.ubi-builder.j2  # Multi-stage builder template
│           ├── deployment.yaml.j2         # K8s Deployment template
│           ├── service.yaml.j2            # K8s Service template
│           ├── route.yaml.j2              # OpenShift Route template
│           └── helm/                      # Helm chart skeleton
│               ├── Chart.yaml.j2
│               ├── values.yaml.j2
│               └── templates/
├── tests/
│   ├── conftest.py
│   ├── test_intake.py
│   ├── test_containerize.py
│   ├── test_build.py
│   ├── test_deploy.py
│   └── fixtures/                 # Sample repos / Dockerfiles for testing
└── docs/
    └── (generated during development as needed)
```

---

## Shared State

All agents read from and write to a shared `PoCState` that flows through the LangGraph.

```python
from typing import TypedDict, Optional
from enum import Enum

class PoCPhase(str, Enum):
    INTAKE = "intake"
    FORK = "fork"
    CONTAINERIZE = "containerize"
    BUILD = "build"
    DEPLOY = "deploy"
    DONE = "done"
    FAILED = "failed"

class ComponentInfo(TypedDict):
    name: str                          # e.g. "frontend", "api", "worker"
    language: str                      # e.g. "python", "node", "go", "java"
    build_system: str                  # e.g. "pip", "npm", "maven", "cargo"
    entry_point: str                   # e.g. "main.py", "dist/index.js"
    port: int | None                   # Exposed port, if applicable
    existing_dockerfile: str | None    # Path to existing Dockerfile, if any
    dockerfile_ubi_path: str           # Path where Dockerfile.ubi will be written
    image_name: str                    # Full quay.io/org/name:tag
    is_ml_workload: bool               # Whether this is an ML serving / pipeline component

class PoCState(TypedDict):
    # Input
    project_name: str
    source_repo_url: str               # GitHub URL

    # Phase tracking
    current_phase: PoCPhase
    error: str | None
    messages: list                     # LangGraph message history

    # Fork phase output
    gitlab_repo_url: str | None
    local_clone_path: str | None

    # Intake/analysis output
    repo_summary: str                  # LLM-generated summary of the repo
    components: list[ComponentInfo]    # Detected components/apps
    has_helm_chart: bool
    has_kustomize: bool
    has_compose: bool
    existing_ci_cd: str | None         # e.g. "github-actions", "gitlab-ci", etc.

    # Build phase output
    built_images: list[str]            # List of pushed image refs

    # Deploy phase output
    deployed_resources: list[str]      # List of created K8s resources
    routes: list[str]                  # Accessible URLs
```

---

## Agent Details

### Agent 1: Intake Agent (`agents/intake.py`)

**Purpose:** Analyze the source GitHub repository to understand what it contains, how it
builds, what components it has, and what deployment patterns already exist.

**Inputs:** `source_repo_url`

**Tools available:**
- `git_clone` — Clone the repo locally
- `list_files` — Recursive file listing with filtering
- `read_file` — Read file contents
- `search_files` — Grep/ripgrep across repo

**LLM reasoning tasks:**
1. Identify the programming language(s) and build system(s).
2. Determine if this is a monorepo or single-component repo.
3. For each component, identify:
   - Language, framework, build tool
   - Entry point / main command
   - Exposed ports (from code, existing Dockerfiles, or docs)
   - Whether it's an ML workload (model serving, training pipeline, notebook)
4. Check for existing deployment artifacts:
   - Dockerfiles (and their base images)
   - Helm charts
   - Kustomize overlays
   - docker-compose files
   - Kubernetes manifests
   - CI/CD pipelines
5. Produce a structured `repo_summary` and populate `components[]`.

**Output:** Updated state with `repo_summary`, `components`, `has_helm_chart`,
`has_kustomize`, `has_compose`, `existing_ci_cd`.

---

### Agent 2: Fork Agent (`agents/fork.py`)

**Purpose:** Fork the GitHub repo to the internal self-hosted GitLab instance under the
designated organization/group.

**Inputs:** `source_repo_url`, `project_name`

**Tools available:**
- `gitlab_create_project` — Create a new project in the target GitLab group (via API)
- `git_clone` — Clone from GitHub
- `git_push_remote` — Add GitLab as remote and push

**Logic (mostly deterministic, minimal LLM needed):**
1. Create a new project on GitLab under the configured group.
2. Clone from GitHub (if not already cloned by intake).
3. Add the GitLab repo as the `origin` remote (or `gitlab` remote).
4. Push all branches and tags to GitLab.

**Output:** `gitlab_repo_url`, `local_clone_path`

**Note:** This agent is largely procedural. LLM reasoning is minimal — mainly for error
handling and edge cases (e.g., repo already exists, name conflicts).

---

### Agent 3: Containerize Agent (`agents/containerize.py`)

**Purpose:** Create `Dockerfile.ubi` files for each component, based on Red Hat Universal
Base Image (UBI). This is the most LLM-intensive agent.

**Inputs:** `components[]`, `local_clone_path`

**Tools available:**
- `read_file` — Read existing Dockerfiles, source code, config files
- `write_file` — Write Dockerfile.ubi to the repo
- `search_files` — Find dependency files, configs
- `git_commit` — Commit the new Dockerfiles
- `git_push` — Push to GitLab

**LLM reasoning tasks (per component):**

1. **Existing Dockerfile analysis:**
   - If a Dockerfile exists, read it and understand the build stages.
   - Identify the base image(s) and map them to UBI equivalents:
     - `python:3.x` → `registry.access.redhat.com/ubi9/python-312`
     - `node:2x` → `registry.access.redhat.com/ubi9/nodejs-22`
     - `golang:1.2x` → `registry.access.redhat.com/ubi9/go-toolset`
     - `eclipse-temurin` / `openjdk` → `registry.access.redhat.com/ubi9/openjdk-21`
     - Generic / `alpine` / `ubuntu` → `registry.access.redhat.com/ubi9/ubi-minimal`
   - Preserve existing build logic but adapt package installs:
     - `apt-get` → `microdnf` / `dnf`
     - `apk add` → `microdnf install`
   - Adjust `USER`, `WORKDIR`, permission patterns for OpenShift (arbitrary UIDs).

2. **No Dockerfile — create from scratch:**
   - Read dependency manifests (`requirements.txt`, `package.json`, `pom.xml`, `go.mod`, etc.)
   - Decide on single-stage vs. multi-stage build:
     - Multi-stage if there's a compiled language or build step.
     - Single-stage for interpreted languages with simple deps.
   - Generate a Dockerfile.ubi with:
     - Correct UBI base image
     - Dependency installation
     - Source code copy
     - Build commands (if applicable)
     - Non-root user setup (OpenShift compatible)
     - `EXPOSE` for detected ports
     - Correct `CMD` / `ENTRYPOINT`

3. **ML workload considerations:**
   - If the component serves an ML model, consider:
     - GPU support (CUDA base images from NVIDIA + UBI)
     - Model file handling (download at build or mount at runtime?)
     - Inference server setup (TorchServe, Triton, custom Flask/FastAPI)
   - For pipeline components, ensure proper Python environment with ML libs.

4. **OpenShift compatibility checks:**
   - No `USER root` in final stage
   - Writable directories assigned to group 0
   - Arbitrary UID support
   - No privileged ports (< 1024) unless necessary

**Output:** Dockerfile.ubi files committed and pushed to GitLab. `components[].dockerfile_ubi_path` updated.

---

### Agent 4: Build & Push Agent (`agents/build.py`)

**Purpose:** Build container images using `podman` and push them to the Quay registry.

**Inputs:** `components[]`, `local_clone_path`

**Tools available:**
- `podman_build` — Build image from Dockerfile
- `podman_tag` — Tag image
- `podman_push` — Push to Quay
- `podman_inspect` — Inspect built image
- `quay_create_repo` — Ensure Quay repo exists (may need API call)

**Logic:**
1. For each component:
   a. `podman build -f <dockerfile_ubi_path> -t quay.io/<org>/<project>-<component>:latest <context>`
   b. Verify the build succeeds. If it fails:
      - Parse the build error log.
      - Use LLM to diagnose the issue (missing dependency, wrong base image, etc.).
      - **Loop back to Containerize Agent** with error context for a fix.
      - Retry (max 3 attempts per component).
   c. `podman push quay.io/<org>/<project>-<component>:latest`

2. Verify pushed images are accessible.

**Output:** `built_images[]` populated with full image references.

**Error-handling loop (key LangGraph feature):**

```
┌──────────────┐     success    ┌──────────────┐
│ Build Image  │───────────────▶│  Push Image  │
└──────┬───────┘                └──────────────┘
       │ failure
       ▼
┌──────────────┐
│ Diagnose     │
│ Build Error  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Fix          │──────────────▶ (retry Build)
│ Dockerfile   │
└──────────────┘
```

---

### Agent 5: Deploy Agent (`agents/deploy.py`)

**Purpose:** Deploy the built images to OpenShift AI, creating appropriate Kubernetes
resources.

**Inputs:** `components[]`, `built_images[]`, `has_helm_chart`, `has_kustomize`

**Tools available:**
- `oc_apply` — Apply YAML manifests
- `oc_create_namespace` — Create/ensure namespace exists
- `oc_get` — Get resource status
- `oc_logs` — Get pod logs for debugging
- `helm_install` — Install/upgrade Helm release
- `write_file` — Generate manifests
- `git_commit` / `git_push` — Commit generated manifests

**LLM reasoning tasks:**

1. **Deployment strategy selection:**
   - If Helm chart exists in repo → adapt it (update image refs, values).
   - If Kustomize exists → create an overlay for OpenShift AI.
   - If nothing exists → generate manifests from scratch.

2. **For each component, generate/adapt:**
   - `Deployment` (or `DeploymentConfig`) with:
     - Correct image reference from Quay
     - Resource requests/limits (inferred from workload type)
     - Liveness/readiness probes (inferred from framework)
     - Environment variables
     - Volume mounts if needed (model files, data, etc.)
   - `Service` with correct port mapping
   - `Route` for externally-accessible components

3. **ML/AI-specific deployments (when detected):**
   - For model serving: Consider `InferenceService` (KServe) on OpenShift AI
   - For notebooks: Create a notebook CR in OpenShift AI dashboard namespace
   - For pipelines: Consider Kubeflow/Tekton pipeline resources

4. **Post-deployment verification:**
   - Wait for pods to be `Running`
   - Check readiness probes pass
   - Verify routes are accessible
   - If pods crash:
     - Read logs via `oc logs`
     - Use LLM to diagnose and suggest fixes
     - May loop back to Containerize or update deployment config

**Output:** `deployed_resources[]`, `routes[]`

---

## LangGraph Orchestration (`graph.py`)

The main graph wires the agents together as nodes with conditional edges.

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(PoCState)

# Add nodes
graph.add_node("intake", intake_agent)
graph.add_node("fork", fork_agent)
graph.add_node("containerize", containerize_agent)
graph.add_node("build", build_agent)
graph.add_node("deploy", deploy_agent)

# Linear flow with error handling
graph.set_entry_point("intake")
graph.add_edge("intake", "fork")
graph.add_edge("fork", "containerize")
graph.add_edge("containerize", "build")

# Conditional: build can loop back to containerize on failure
graph.add_conditional_edges(
    "build",
    route_after_build,   # returns "deploy" or "containerize" or "failed"
    {
        "deploy": "deploy",
        "containerize": "containerize",  # retry loop
        "failed": END,
    }
)

# Conditional: deploy can loop back or finish
graph.add_conditional_edges(
    "deploy",
    route_after_deploy,  # returns "done" or "containerize" or "failed"
    {
        "done": END,
        "containerize": "containerize",  # full rebuild loop
        "failed": END,
    }
)
```

---

## Configuration (`config.py`)

```
# .env variables required:

# LLM
ANTHROPIC_API_KEY=sk-ant-...

# GitLab
GITLAB_URL=https://gitlab.internal.example.com
GITLAB_TOKEN=glpat-...
GITLAB_GROUP=poc-demos          # Target group/org for forked repos

# Quay
QUAY_REGISTRY=quay.io           # or internal Quay
QUAY_ORG=my-org
QUAY_TOKEN=...                  # Robot account token for push

# OpenShift
OPENSHIFT_API_URL=https://api.cluster.example.com:6443
OPENSHIFT_TOKEN=sha256~...      # Or use kubeconfig
OPENSHIFT_NAMESPACE_PREFIX=poc  # Will create poc-<project-name>

# Build
PODMAN_BUILD_ARGS=              # Optional extra podman build args
MAX_BUILD_RETRIES=3
```

---

## Implementation Plan — Phased Approach

### Phase 1: Foundation (Week 1)

**Goal:** Project scaffolding, state model, basic CLI, and the Intake Agent.

| # | Task | Details |
|---|------|---------|
| 1.1 | Project setup ✅ | `pyproject.toml` with dependencies (`langgraph`, `langchain-anthropic`, `typer`, `python-dotenv`, `jinja2`, `pyyaml`, `httpx`). Set up `src/autopoc/` package structure. |
| 1.2 | Config module ✅ | `config.py` — Load env vars, validate required ones are set, provide typed config object. |
| 1.3 | State definition ✅ | `state.py` — Define `PoCState`, `ComponentInfo`, `PoCPhase` as shown above. |
| 1.4 | CLI entry point ✅ | `cli.py` — `typer` app with `run` command accepting `--name` and `--repo` args. |
| 1.5 | File tools ✅ | `tools/file_tools.py` — Wrappers for reading, writing, listing, searching files in a cloned repo. |
| 1.6 | Git tools ✅ | `tools/git_tools.py` — Wrappers for `git clone`, `git remote add`, `git push`, `git commit`. |
| 1.7 | Intake agent ✅ | `agents/intake.py` — LLM-powered repo analysis. Bind file tools. Write system prompt in `prompts/intake.md`. |
| 1.8 | Tests for intake ✅ | Unit tests with fixture repos (small sample repos in `tests/fixtures/`). |

### Phase 2: Fork & Containerize (Week 2)

**Goal:** Fork to GitLab and generate UBI Dockerfiles.

| # | Task | Details |
|---|------|---------|
| 2.1 | GitLab tools ✅ | `tools/gitlab_tools.py` — Create project via API, manage remotes. |
| 2.2 | Fork agent ✅ | `agents/fork.py` — Mostly procedural: create project, push repo. |
| 2.3 | Dockerfile templates ✅ | `templates/Dockerfile.ubi*.j2` — Jinja2 templates for common patterns (Python, Node, Go, Java, generic). |
| 2.4 | Containerize agent ✅ | `agents/containerize.py` — The core LLM-heavy agent. System prompt in `prompts/containerize.md`. |
| 2.5 | Containerize prompt engineering ✅ | Craft the system prompt with UBI image mappings, OpenShift compatibility rules, multi-stage build patterns, and ML workload considerations. |
| 2.6 | Wire graph (partial) ✅ | `graph.py` — Wire intake → fork → containerize in a `StateGraph`. |
| 2.7 | Integration test ✅ | End-to-end test: given a sample GitHub repo, run through intake → fork → containerize and verify Dockerfile.ubi is generated correctly. |

### Phase 3: Build & Push (Week 3)

**Goal:** Build images with podman and push to Quay.

| # | Task | Details |
|---|------|---------|
| 3.1 | Podman tools ✅ | `tools/podman_tools.py` — Build, tag, push, inspect wrappers. |
| 3.2 | Quay tools ✅ | `tools/quay_tools.py` — Ensure repo exists (API call or just push). |
| 3.3 | Build agent ✅ | `agents/build.py` — Build loop with error diagnosis and retry. |
| 3.4 | Build→Containerize retry loop ✅ | Implement conditional edge in graph: on build failure, go back to containerize agent with error context. |
| 3.5 | Tests ✅ | Test build agent with intentionally broken Dockerfiles to verify retry logic. |

### Phase 4: Deploy (Week 4)

**Goal:** Deploy to OpenShift AI and verify.

| # | Task | Details |
|---|------|---------|
| 4.1 | OpenShift tools | `tools/openshift_tools.py` — `oc` CLI wrappers for apply, get, logs, namespace management. |
| 4.2 | K8s manifest templates | `templates/deployment.yaml.j2`, `service.yaml.j2`, `route.yaml.j2`, and Helm chart skeleton. |
| 4.3 | Deploy agent | `agents/deploy.py` — Deployment strategy selection, manifest generation, apply, and verification. System prompt in `prompts/deploy.md`. |
| 4.4 | ML workload support | Handle KServe `InferenceService`, OpenShift AI notebook CRs when appropriate. |
| 4.5 | Full graph wiring | Complete `graph.py` with all agents and conditional edges. |
| 4.6 | End-to-end test | Full pipeline run against a real cluster (or mocked). |

### Phase 5: Hardening (Week 5)

**Goal:** Error handling, logging, observability, and polish.

| # | Task | Details |
|---|------|---------|
| 5.1 | Structured logging | Add logging throughout with structured context (project name, phase, component). |
| 5.2 | LangSmith tracing | Integrate LangSmith (or LangFuse) for LLM call tracing and debugging. |
| 5.3 | State persistence | Use LangGraph checkpointing so runs can be resumed if interrupted. |
| 5.4 | Error recovery | Ensure graceful handling of: network failures, CLI tool not found, permission denied, quota exceeded, etc. |
| 5.5 | CLI polish | Progress output, colored status, summary report at end. |
| 5.6 | Documentation | README with setup instructions, usage examples, architecture overview. |

### Phase 6: Local E2E Harness (Week 6)

**Goal:** Provide end-to-end integration tests against real infrastructure running locally.

| # | Task | Details |
|---|------|---------|
| 6.1 | Docker-compose E2E test infrastructure ✅ | `docker-compose.test.yml`, `scripts/setup-e2e.sh`, `tests/e2e/test_e2e_intake_fork.py`. Sets up GitLab CE and Quay for testing. |
| 6.2 | Build & Push E2E tests | `tests/e2e/test_e2e_build.py` — Test the `build_agent` against the local Quay instance. |
| 6.3 | Deploy E2E tests | `tests/e2e/test_e2e_deploy.py` — Test the `deploy_agent` and full graph against a local K8s/OpenShift setup (MicroShift or Kind). |

---

## Key Design Decisions

### 1. Agent vs. Node

Not every step needs a full LLM-powered agent. The distinction:

| Step | Type | Rationale |
|------|------|-----------|
| Intake | **LLM Agent** | Needs to reason about repo structure, identify languages, components |
| Fork | **Procedural Node** | Deterministic sequence of git/API commands |
| Containerize | **LLM Agent** | Heavy reasoning about Dockerfile creation/adaptation |
| Build | **Hybrid** | Procedural build, LLM only for error diagnosis |
| Deploy | **LLM Agent** | Needs to reason about deployment strategy, resource configuration |

### 2. Why LangGraph over plain LangChain?

- **Cyclic flows:** Build failures loop back to containerize — LangGraph supports cycles natively.
- **State management:** Shared typed state across all nodes.
- **Checkpointing:** Can resume interrupted runs.
- **Conditional routing:** Different paths based on what the intake agent discovers.

### 3. Why CLI tools over pure API?

- `podman build` is the only practical way to build container images.
- `oc` CLI handles kubeconfig, auth, and complex resource management better than raw API calls.
- `git` CLI is more robust than any Git library for complex operations.
- `helm` CLI is the standard for Helm operations.

### 4. Retry budget

Each component gets a maximum of 3 build attempts. On each failure, the LLM gets the
full build log and can modify the Dockerfile. After 3 failures, the component is marked
as failed and the run continues with remaining components (partial success is acceptable).

---

## Dependencies

```toml
[project]
dependencies = [
    "langgraph>=0.2",
    "langchain-anthropic>=0.3",
    "langchain-core>=0.3",
    "typer>=0.12",
    "python-dotenv>=1.0",
    "jinja2>=3.1",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "rich>=13.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.6",
]
```

---

## Local E2E Testing Strategy

Unit and integration tests use mocked external services (GitLab API, Anthropic, Quay, OpenShift)
and run fast with no dependencies. For local E2E testing against real services, we use Docker
containers:

| Service | Local E2E solution | Notes |
|---------|--------------------|-------|
| GitLab | GitLab CE in Docker | Full API compatibility; ~4GB RAM, 3-5 min startup |
| Quay / Registry | Local Docker registry or Quay mirror | For Phase 3 (build & push) |
| OpenShift | MicroShift or Kind + OLM | For Phase 4 (deploy) |

**Setup:** `docker-compose -f docker-compose.test.yml up -d` starts the test infrastructure.
A setup script creates test users/tokens and writes them to `.env.test`.

**Running:** `pytest tests/e2e/ --e2e` runs the E2E suite (skipped by default).

**Teardown:** `docker-compose -f docker-compose.test.yml down -v`

This is opt-in — the default `pytest` run uses mocks only and requires no external services.

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM generates broken Dockerfile | Build fails | Retry loop with error feedback; Jinja2 templates as starting points |
| Repo structure too complex | Intake misidentifies components | Include heuristics (not just LLM) for common patterns; allow manual override |
| OpenShift AI specifics (KServe, etc.) vary by cluster version | Deploy fails | Detect cluster capabilities via `oc api-resources`; adapt deployment strategy |
| Large repos / monorepos | Slow analysis, token limits | Limit file reads to relevant files; use tree structure + targeted reads |
| Quay/GitLab auth issues | Workflow blocks | Validate credentials at startup before doing any work |
| Rate limits on LLM API | Slow execution | Use caching for repeated analysis patterns; batch where possible |
