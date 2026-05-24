# AutoPoC — LangGraph Agent System Plan

## Overview

AutoPoC is a LangGraph-based multi-agent system that automates the end-to-end workflow of
taking an open-source project from GitHub and deploying it as a proof-of-concept on
OpenShift AI (Open Data Hub). The system uses Claude as its reasoning engine and interacts
with external systems (GitLab, Quay, OpenShift) primarily through CLI tools.

The agent is **PoC-intelligent**: it analyzes each repository to understand what would
constitute a meaningful proof of concept in the context of Open Data Hub / OpenShift AI,
generates a PoC plan that influences containerization and deployment, executes the PoC
with automated test scripts, and produces a comprehensive report.

**Input:** Project name + GitHub repo URL
**Output:** Running PoC on OpenShift AI, with all artifacts (PoC plan, forked repo, UBI-based
images, deployment manifests, test scripts, PoC report) committed and available.

> **Implementation plan:** See [implementation-plan.md](./implementation-plan.md) for the
> detailed, ordered task breakdown (56 tasks across 7 phases).

---

## Architecture

### High-Level Flow

```
┌─────────────┐
│   Intake     │
│   Agent      │
└──────┬───────┘
       │
┌──────▼──────┐
│  Evaluate    │            ← RHOAI fitness scoring (NEW)
│  Agent       │
└──────┬───────┘
       │
  ┌────┴────┐          ← fan-out (parallel)
  │         │
┌─▼───────┐ ┌▼──────────┐
│PoC Plan │ │  Fork &    │
│ Agent   │ │  Clone     │
└─┬───────┘ └┬──────────┘
  │          │
  └────┬─────┘            ← fan-in (join)
       │
┌──────▼──────┐    ┌─────────────┐
│ Containerize│◄──▶│  Build &    │    ← retry loop
│  (UBI)      │    │  Push       │
└─────────────┘    └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │  Deploy to  │◄──┐
                   │  OpenShift  │───┘  ← retry loop
                   │  AI         │
                   └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │ PoC Execute │
                   │  Agent      │
                   └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │ PoC Report  │
                   │  Agent      │
                   └─────────────┘
                          │
                     Shared State
                     (PoC Record)
```

After intake, the **Evaluate Agent** scores the project's fitness for OpenShift AI using
the strategy baseline in `data/strategy-baseline.yaml`. This evaluation is non-blocking —
if it fails, the pipeline continues. The scoring dimensions are read dynamically from the
active strategy profile (`data/strategies/redhat-ai-2026.yaml`).

The **PoC Plan Agent** runs in parallel with **Fork** after evaluation completes. Both write to
different state fields, so LangGraph's state merge combines their outputs before feeding into
**Containerize**. The PoC plan influences how Dockerfiles are built (e.g., including an
inference server) and how deployments are structured (e.g., sidecar containers, PVCs).

After deployment, the **PoC Execute Agent** generates and runs test scripts that exercise the
deployed service according to the PoC plan. Finally, the **PoC Report Agent** produces a
comprehensive markdown report summarizing results.

### Technology Stack

| Component       | Choice                                              |
|-----------------|-----------------------------------------------------|
| Framework       | Python 3.12+ with LangGraph                         |
| LLM             | Anthropic Claude (via `langchain-anthropic`)         |
| CLI Tools       | `git`, `podman`, `oc`, `helm`, `skopeo`, `kubectl`   |
| Secrets         | Environment variables (`.env` file via `python-dotenv`) |
| State           | LangGraph `StateGraph` with `TypedDict` state        |
| Interface       | CLI (`typer`)                                        |
| Testing         | `pytest` + `pytest-asyncio`                          |
| ODH/RHOAI       | ODH-aware planning; K8s-based deployment             |

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
│       ├── llm.py                # LLM factory (Anthropic / Vertex AI)
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── intake.py         # Repo analysis agent
│       │   ├── evaluate.py       # RHOAI fitness evaluation agent (NEW)
│       │   ├── poc_plan.py       # PoC plan generation agent
│       │   ├── fork.py           # GitLab/GitHub fork agent
│       │   ├── containerize.py   # Dockerfile.ubi generation agent
│       │   ├── build.py          # Image build & push agent
│       │   ├── deploy.py         # OpenShift deployment agent
│       │   ├── poc_execute.py    # PoC test execution agent
│       │   └── poc_report.py     # PoC report generation agent
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── git_tools.py      # git clone, push, branch operations
│       │   ├── gitlab_tools.py   # GitLab API (fork, create project)
│       │   ├── github_tools.py   # GitHub API (fork, wait, clone URL)
│       │   ├── podman_tools.py   # podman build, tag, push
│       │   ├── quay_tools.py     # Quay repo creation, image listing
│       │   ├── k8s_tools.py      # kubectl apply, get, logs, wait
│       │   ├── file_tools.py     # Read/write/search files in cloned repo
│       │   ├── template_tools.py # Jinja2 template rendering
│       │   ├── script_tools.py   # Script execution tool
│       │   └── strategy.py       # Strategy YAML loader (NEW)
│       ├── prompts/
│       │   ├── intake.md         # System prompt for intake analysis
│       │   ├── evaluate.md       # System prompt for RHOAI evaluation (NEW)
│       │   ├── poc_plan.md       # System prompt for PoC planning
│       │   ├── containerize.md   # System prompt for Dockerfile generation
│       │   ├── deploy.md         # System prompt for deployment planning
│       │   ├── poc_execute.md    # System prompt for PoC execution
│       │   ├── poc_report.md     # System prompt for PoC report
│       │   └── prefilter_pm_comments.md  # System prompt for PM comments parsing (NEW)
│       └── templates/
│           ├── Dockerfile.ubi.j2          # Jinja2 base UBI Dockerfile template
│           ├── Dockerfile.ubi-builder.j2  # Multi-stage builder template
│           ├── deployment.yaml.j2         # K8s Deployment template
│           ├── service.yaml.j2            # K8s Service template
│           └── helm/                      # Helm chart skeleton
│               └── templates/
├── tests/
│   ├── conftest.py
│   ├── test_intake.py
│   ├── test_containerize.py
│   ├── test_build.py
│   ├── test_deploy.py
│   ├── test_poc_plan.py          # PoC plan agent tests (NEW)
│   ├── test_poc_execute.py       # PoC execute agent tests (NEW)
│   ├── test_poc_report.py        # PoC report agent tests (NEW)
│   ├── test_script_tools.py      # Script execution tool tests (NEW)
│   ├── e2e/                      # End-to-end tests
│   └── fixtures/                 # Sample repos / Dockerfiles for testing
└── docs/
    └── (generated during development as needed)
```

---

## Shared State

All agents read from and write to a shared `PoCState` that flows through the LangGraph.

```python
from typing import TypedDict, Optional, Annotated
from enum import Enum

class PoCPhase(str, Enum):
    INTAKE = "intake"
    EVALUATE = "evaluate"          # RHOAI fitness evaluation (NEW)
    FORK = "fork"
    POC_PLAN = "poc_plan"
    CONTAINERIZE = "containerize"
    BUILD = "build"
    DEPLOY = "deploy"
    POC_EXECUTE = "poc_execute"
    POC_REPORT = "poc_report"
    DONE = "done"
    FAILED = "failed"

class ComponentInfo(TypedDict, total=False):
    name: str                          # e.g. "frontend", "api", "worker"
    language: str                      # e.g. "python", "node", "go", "java"
    build_system: str                  # e.g. "pip", "npm", "maven", "cargo"
    entry_point: str                   # e.g. "main.py", "dist/index.js"
    port: int | None                   # Exposed port, if applicable
    existing_dockerfile: str | None    # Path to existing Dockerfile, if any
    dockerfile_ubi_path: str           # Path where Dockerfile.ubi will be written
    image_name: str                    # Full quay.io/org/name:tag
    is_ml_workload: bool               # Whether this is an ML serving / pipeline component
    source_dir: str                    # Relative path within repo (e.g. "." or "api/")

class PoCScenario(TypedDict, total=False):
    """A single PoC test scenario defined by the PoC Plan agent."""
    name: str                          # e.g. "inference-test", "health-check"
    description: str                   # What this test verifies
    type: str                          # "http", "script", "cli"
    endpoint: str | None               # Target endpoint (if HTTP-based)
    input_data: str | None             # Sample input (prompt, query, etc.)
    expected_behavior: str             # What success looks like
    timeout_seconds: int               # Max wait time

class PoCInfrastructure(TypedDict, total=False):
    """Infrastructure requirements determined by the PoC Plan agent."""
    needs_inference_server: bool       # e.g. vLLM, TGI, Triton
    inference_server_type: str | None  # "vllm", "tgi", "triton", "custom"
    needs_vector_db: bool              # e.g. Milvus, ChromaDB, Qdrant
    vector_db_type: str | None         # "milvus", "chromadb", "qdrant", "in-memory"
    needs_embedding_model: bool        # Whether an embedding model is needed
    embedding_model: str | None        # e.g. "sentence-transformers/all-MiniLM-L6-v2"
    needs_gpu: bool                    # GPU resource requirements
    gpu_type: str | None               # "nvidia-a10g", "nvidia-t4", etc.
    needs_pvc: bool                    # Persistent storage for models/data
    pvc_size: str | None               # e.g. "10Gi", "50Gi"
    sidecar_containers: list[dict]     # Additional containers to deploy alongside
    extra_env_vars: dict[str, str]     # Environment variables for the main container
    odh_components: list[str]          # ODH components needed: "model-mesh", "kserve", etc.
    resource_profile: str              # "small", "medium", "large", "gpu"
    # Runtime / deployment model — guides containerize + deploy decisions
    deployment_model: str              # "deployment" | "job" | "cronjob" | "cli-only"
    listens_on_port: bool              # Whether the app binds to a network port
    long_running: bool                 # Whether it runs continuously vs exits
    entrypoint_suggestion: str | None  # Suggested ENTRYPOINT/CMD for Dockerfile
    test_strategy: str                 # "http" | "cli" | "exec"

class PoCResult(TypedDict, total=False):
    """Result of a single PoC test execution."""
    scenario_name: str
    status: str                        # "pass", "fail", "skip", "error"
    output: str                        # Captured output/response
    error_message: str | None          # Error details if failed
    duration_seconds: float            # How long it took

class RHOAIDimensionScore(TypedDict, total=False):        # NEW
    """Score for a single evaluation dimension."""
    name: str                          # e.g. "audience_value"
    score: int                         # 0 to max_score
    max_score: int                     # max possible for this dimension
    rationale: str                     # 1-2 sentence explanation

class RHOAIEvaluation(TypedDict, total=False):             # NEW
    """RHOAI fitness evaluation result for a project."""
    total_score: int                   # sum of dimension scores (0-100)
    max_possible_score: int            # sum of all max_scores
    dimensions: list[RHOAIDimensionScore]
    strategy_areas: list[str]          # matched official strategy areas
    relationship: str                  # relationship classification label
    capability_labels: list[str]       # matched capability labels from strategy
    rationale: str                     # overall 2-3 sentence assessment
    strengths: list[str]               # key strengths (2-4 items)
    risks: list[str]                   # key risks/concerns (1-3 items)
    strategy_name: str                 # which strategy profile was used
    strategy_version: str              # version of the strategy

class PoCState(TypedDict, total=False):
    # Input
    project_name: str
    source_repo_url: str               # GitHub URL

    # Phase tracking
    current_phase: PoCPhase
    error: str | None
    messages: Annotated[list, add_messages]  # LangGraph message history

    # Fork phase output
    gitlab_repo_url: str | None        # Deprecated — use fork_repo_url
    fork_repo_url: str | None          # URL of the fork (GitHub or GitLab)
    fork_target: str | None            # "github" or "gitlab"
    local_clone_path: str | None

    # Intake/analysis output
    repo_summary: str                  # LLM-generated summary of the repo
    components: list[ComponentInfo]    # Detected components/apps
    has_helm_chart: bool
    has_kustomize: bool
    has_compose: bool
    existing_ci_cd: str | None         # e.g. "github-actions", "gitlab-ci", etc.

    # RHOAI Evaluation output (NEW)
    rhoai_evaluation: RHOAIEvaluation  # RHOAI fitness evaluation result
    rhoai_evaluation_path: str         # Path to rhoai-evaluation.md in the repo

    # PoC Plan output
    poc_plan: str                      # Raw markdown content of the PoC plan
    poc_plan_path: str                 # Path to poc-plan.md in the repo
    poc_scenarios: list[PoCScenario]   # Structured test scenarios
    poc_infrastructure: PoCInfrastructure  # Infrastructure requirements
    poc_type: str                      # "model-serving", "rag", "training", "web-app", etc.

    # Build phase output
    built_images: list[str]            # List of pushed image refs
    build_retries: int                 # Current retry count

    # Deploy phase output
    deployed_resources: list[str]      # List of created K8s resources
    routes: list[str]                  # Accessible URLs
    deploy_retries: int                # Current retry count

    # PoC Execute output
    poc_results: list[PoCResult]       # Test execution results
    poc_script_path: str               # Path to generated test script

    # PoC Report output
    poc_report_path: str               # Path to poc-report.md in the repo
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

### Agent 1b: Evaluate Agent (`agents/evaluate.py`) — NEW

**Purpose:** Score a project's fitness as a PoC on OpenShift AI by consulting the
strategy baseline (`data/strategy-baseline.yaml`). Produces a numeric score (0-100)
with per-dimension breakdown, strategy area alignment, and relationship classification.

**Runs:** Sequentially after intake, before fork. Non-blocking — evaluation failure
does not stop the pipeline.

**Inputs:** `repo_digest`, `repo_summary`, `components[]`, `project_name`, `source_repo_url`

**Tools available:** None — one-shot LLM call only (same pattern as intake).

**LLM reasoning tasks:**
1. **Score each dimension** (read dynamically from strategy YAML):
   - `audience_value` — How valuable to RHOAI users/customers?
   - `strategic_alignment` — Alignment with the 4 official CY2026 strategy areas?
   - `strategy_fit` — Enriches vs. duplicates existing capabilities?
   - `platform_leverage` — Leverages RHOAI components (KServe, vLLM, pipelines, etc.)?
   - `demo_potential` — How compelling as a live PoC/demo?
2. **Identify strategy areas** this project is relevant to.
3. **Classify the relationship** using the 5-label taxonomy from the baseline.
4. **Match capability labels** from the strategy that apply.
5. **Assess strengths and risks** for RHOAI PoC.

**Strategy context:** The prompt includes the full strategy baseline (strategy areas,
capability labels, enrichment/duplication criteria, relationship rules, core products).
This is loaded at runtime from `data/strategy-baseline.yaml` via `tools/strategy.py`.

**Output:** `rhoai_evaluation` (TypedDict with scores + rationales), `rhoai_evaluation_path`
(path to `rhoai-evaluation.md` written in the repo directory).

---

### Agent 2: Fork Agent (`agents/fork.py`)

**Purpose:** Fork the GitHub repo to either an internal self-hosted GitLab instance or
to a GitHub organization/user account, depending on the configured `fork_target`.

**Inputs:** `source_repo_url`, `project_name`, `fork_target` (from config)

**Tools available:**
- **GitLab target:** `gitlab_create_project` — Create a new project in the target GitLab group (via API)
- **GitHub target:** `github_fork_repo` — Fork via GitHub API (`POST /repos/{owner}/{repo}/forks`)
- `git_clone` — Clone from GitHub
- `git_push_remote` — Add remote and push (GitLab only; GitHub fork copies automatically)

**Logic (mostly deterministic, minimal LLM needed):**

**GitLab target (default):**
1. Create a new project on GitLab under the configured group.
2. Clone from GitHub (if not already cloned by intake).
3. Rename `origin` to `github`, set `origin` to GitLab URL, add `gitlab` alias.
4. Push all branches and tags to GitLab.

**GitHub target:**
1. Parse `source_repo_url` to extract `{owner}/{repo}`.
2. Fork via GitHub API — optionally to a configured organization.
3. Wait for fork to be ready (async operation, poll until available).
4. Clone from the fork if not already cloned, or reconfigure remotes.
5. Remove the source remote entirely (safety: no path to push upstream).
6. Set `origin` to the fork URL with embedded token.
7. No explicit push needed — GitHub fork copies all branches/tags automatically.

**Output:** `fork_repo_url`, `fork_target`, `local_clone_path`
(Also sets `gitlab_repo_url` for backward compatibility when target is GitLab.)

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

### Agent 6: PoC Plan Agent (`agents/poc_plan.py`) — NEW

**Purpose:** Analyze the repository and intake results to determine what constitutes a
meaningful proof of concept for this project in the context of Open Data Hub / OpenShift AI.
This agent produces a PoC plan that influences downstream containerization and deployment.

**Runs:** In parallel with Fork (both depend only on intake output, not on each other).

**Inputs:** `source_repo_url`, `local_clone_path`, `repo_summary`, `components[]`

**Tools available:**
- `list_files` — Browse repo structure
- `read_file` — Read source code, configs, model files
- `search_files` — Search for patterns indicating ML workloads, APIs, etc.
- `write_file` — Write the poc-plan.md file

**LLM reasoning tasks:**

1. **Project classification (ODH context):**
   - Model serving (inference endpoint for a trained model)
   - RAG pipeline (retrieval-augmented generation)
   - Data pipeline (ETL, feature engineering, data processing)
   - Training job (model training/fine-tuning)
   - Notebook-based exploration (Jupyter/JupyterLab)
   - Web app with ML features (API with ML-backed endpoints)
   - Pure infrastructure component (operators, controllers, libraries)

2. **PoC definition — "What proves this works?"**
   - Model serving → deploy with inference server, send prompt, validate response
   - RAG → package with vector DB, provide embedding model, test retrieval + generation
   - Data pipeline → verify data flows end-to-end with sample data
   - Web app → verify endpoints respond, test key user flows
   - Training job → verify training starts, produces checkpoints/metrics

3. **Infrastructure requirements:**
   - Does the Dockerfile need an inference server (vLLM, TGI, Triton)?
   - Do we need sidecar containers (vector DB, Redis, etc.)?
   - Do we need PVCs for model weights or data?
   - Do we need GPU resources?
   - What ODH components are relevant (ModelMesh, KServe, Data Science Pipelines)?
   - What resource profile is needed (CPU/memory sizing)?

4. **Test scenario definition:**
   - Define 2-5 concrete, executable test scenarios
   - Each with: name, description, type, input data, expected behavior, timeout
   - Scenarios should be automatable (no manual steps)

**Output:** `poc-plan.md` written to the repo, plus structured state fields:
`poc_plan`, `poc_plan_path`, `poc_scenarios`, `poc_infrastructure`, `poc_type`

---

### Agent 7: PoC Execute Agent (`agents/poc_execute.py`) — NEW

**Purpose:** After deployment, generate and execute test scripts that exercise the deployed
service according to the PoC plan.

**Inputs:** `poc_plan`, `poc_scenarios`, `routes[]`, `deployed_resources[]`, `local_clone_path`

**Tools available:**
- `write_file` — Generate test scripts
- `read_file` — Read PoC plan, deployment artifacts
- `run_script` — Execute Python test scripts (NEW tool)
- `kubectl_get` — Check pod status
- `kubectl_logs` — Read pod logs for debugging

**LLM reasoning tasks:**

1. **Test script generation:**
   - Read the PoC plan and test scenarios from state
   - Read the deployed routes and service endpoints
   - Generate a Python test script (`poc_test.py`) that exercises each scenario:
     - For model serving: sends inference requests via `requests` or `urllib`
     - For RAG: ingests sample documents, queries, validates retrieval
     - For web apps: hits API endpoints, validates responses
     - For data pipelines: submits sample data, verifies processing
   - Include proper error handling, timeouts, and retry logic in the script
   - Include result collection in structured format (JSON output)

2. **Test execution:**
   - Execute the script via `run_script` tool
   - Capture stdout, stderr, and exit code
   - Parse structured results from script output
   - If tests fail due to service readiness, wait and retry

3. **Debugging:**
   - If tests fail, check pod logs via `kubectl_logs`
   - Determine if failure is transient (service starting) or permanent (bug)

**Output:** `poc_results[]`, `poc_script_path`. Test script committed to repo.

---

### Agent 8: PoC Report Agent (`agents/poc_report.py`) — NEW

**Purpose:** Generate a comprehensive PoC report in markdown format, summarizing what was
done, what worked, and providing recommendations.

**Inputs:** All state fields (full pipeline results)

**Tools available:**
- `write_file` — Write the poc-report.md file
- `read_file` — Read PoC plan, test scripts for reference

**LLM reasoning tasks:**
- Synthesize all pipeline results into a coherent narrative
- Generate structured sections: executive summary, objectives, infrastructure,
  test results, recommendations

**Output format (poc-report.md):**
- **Executive Summary** — 2-3 sentence overview of the PoC and its outcome
- **PoC Objectives** — What we set out to prove (from PoC plan)
- **Project Analysis** — Repository summary, components, technologies
- **Infrastructure Deployed** — Images built, manifests applied, resources created
- **Test Results** — Table with scenario name, status (pass/fail/skip), duration, details
- **Logs & Evidence** — Key log excerpts, response samples
- **Timing** — Duration of each pipeline phase
- **Recommendations** — Production readiness assessment, next steps, ODH/OpenShift AI notes
- **ODH/OpenShift AI Considerations** — Relevant ODH components, migration path

**Output:** `poc_report_path`. Report committed to repo.

---

## LangGraph Orchestration (`graph.py`)

The main graph wires the agents together as nodes with conditional edges. Key features:
- **RHOAI evaluation:** After intake, evaluate scores the project's OpenShift AI fitness
- **Parallel fan-out:** After evaluate, `poc_plan` and `fork` run concurrently
- **Fan-in join:** Both complete before containerize runs
- **Retry loops:** Build can loop back to containerize; deploy can retry
- **PoC tail:** After successful deploy, execute tests and generate report

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(PoCState)

# Add nodes
graph.add_node("intake", intake_agent)
graph.add_node("evaluate", evaluate_agent)       # NEW: RHOAI fitness scoring
graph.add_node("poc_plan", poc_plan_agent)        # parallel with fork
graph.add_node("fork", fork_agent)                # parallel with poc_plan
graph.add_node("containerize", containerize_agent)
graph.add_node("build", build_agent)
graph.add_node("deploy", deploy_agent)
graph.add_node("poc_execute", poc_execute_agent)
graph.add_node("poc_report", poc_report_agent)

# Sequential: intake → evaluate
graph.set_entry_point("intake")
graph.add_conditional_edges(
    "intake",
    route_after_intake,    # "evaluate" on success, "failed" on error
    {"evaluate": "evaluate", "failed": END},
)

# Fan-out: evaluate → [poc_plan, fork] in parallel
graph.add_conditional_edges(
    "evaluate",
    route_after_evaluate,  # always ["poc_plan", "fork"] (evaluate is non-blocking)
    {"poc_plan": "poc_plan", "fork": "fork", "failed": END},
)

# Fan-in: both poc_plan and fork feed into containerize
graph.add_edge("poc_plan", "containerize")
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

# Conditional: deploy can loop back or continue to PoC execution
graph.add_conditional_edges(
    "apply",
    route_after_apply,   # returns "poc_execute", "deploy", "containerize", or "failed"
    {
        "poc_execute": "poc_execute",   # success → run PoC tests
        "deploy": "deploy",            # inner retry loop
        "containerize": "containerize", # outer retry loop
        "failed": END,
    }
)

# PoC execution → report → END
graph.add_edge("poc_execute", "poc_report")
graph.add_edge("poc_report", END)
```

---

## Configuration (`config.py`)

```
# .env variables required:

# LLM
ANTHROPIC_API_KEY=sk-ant-...

# Fork target — where to push the forked repo
FORK_TARGET=gitlab              # "gitlab" (default) or "github"

# GitLab (required when FORK_TARGET=gitlab)
GITLAB_URL=https://gitlab.internal.example.com
GITLAB_TOKEN=glpat-...
GITLAB_GROUP=poc-demos          # Target group/org for forked repos

# GitHub (required when FORK_TARGET=github)
# GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# GITHUB_ORG=my-org             # Optional — if unset, forks to authenticated user

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

### Phase 4: Deploy (Week 4) ✅

**Goal:** Deploy to Kubernetes/OpenShift and verify.

| # | Task | Details |
|---|------|---------|
| 4.1 | Kubernetes tools ✅ | `tools/k8s_tools.py` — `kubectl` CLI wrappers for local K8s testing (k3d/minikube/kind). |
| 4.2 | K8s manifest templates ✅ | `templates/deployment.yaml.j2`, `service.yaml.j2` — Production-ready templates with security context. |
| 4.3 | Deploy agent ✅ | `agents/deploy.py` — Deployment strategy selection, manifest generation, apply, and verification. System prompt in `prompts/deploy.md`. |
| 4.4 | ML workload support | Deferred — basic resource sizing implemented, KServe support for future enhancement. |
| 4.5 | Full graph wiring ✅ | Complete `graph.py` with all agents and conditional edges including deploy node. |
| 4.6 | End-to-end test ✅ | Full pipeline E2E tests in `tests/e2e/test_e2e_full.py` validate entire flow. |

### Phase 5: Hardening (Week 5)

**Goal:** Error handling, logging, observability, and polish.

| # | Task | Details |
|---|------|---------|
| 5.1 | Structured logging ✅ | Centralized `logging_config.py` with Rich handler, verbose/normal modes, external logger suppression. |
| 5.2 | LangSmith tracing ✅ | Auto-configures when `LANGCHAIN_TRACING_V2=true`. `langgraph.json` for Studio. |
| 5.3 | State persistence ✅ | LangGraph checkpointing with SqliteSaver (optional) or MemorySaver fallback. `resume` and `status` commands. |
| 5.4 | Credential validation ✅ | `credentials.py` validates GitLab, Quay, Anthropic/Vertex at startup. Rich table output. |
| 5.5 | CLI polish ✅ | Panel-style output, thread IDs, elapsed time, `--skip-validation` flag. |
| 5.6 | Documentation | README with setup instructions, usage examples, architecture overview. |

### Phase 6: Local E2E Harness (Week 6) ✅

**Goal:** Provide end-to-end integration tests against real infrastructure running locally.

| # | Task | Details |
|---|------|---------|
| 6.1 | Docker-compose E2E test infrastructure ✅ | `docker-compose.test.yml`, `scripts/setup-e2e.sh`, `tests/e2e/test_e2e_intake_fork.py`. Sets up GitLab CE and Quay for testing. |
| 6.2 | Build & Push E2E tests ✅ | `tests/e2e/test_e2e_build.py` — Test the `build_agent` against the local Quay instance. |
| 6.3 | Deploy E2E tests ✅ | `tests/e2e/test_e2e_deploy.py`, `tests/e2e/test_e2e_full.py` — Test the `deploy_agent` and full graph against a local K8s cluster. |

### Phase 7: PoC Intelligence (Weeks 7-9) — NEW

**Goal:** Make the agent PoC-aware. Add intelligent PoC planning, execution, and reporting
with ODH/OpenShift AI context. Introduce parallel execution in the graph.

| # | Task | Details |
|---|------|---------|
| 7.1 | State updates ✅ | Add `PoCScenario`, `PoCInfrastructure`, `PoCResult` TypedDicts. Add `poc_plan`, `poc_scenarios`, `poc_infrastructure`, `poc_type`, `poc_results`, `poc_script_path`, `poc_report_path` to `PoCState`. New `PoCPhase` values. |
| 7.2 | PoC Plan system prompt ✅ | `prompts/poc_plan.md` — ODH-aware project classification, infrastructure requirements, scenario generation. |
| 7.3 | PoC Plan agent ✅ | `agents/poc_plan.py` — Reads repo + intake results, generates poc-plan.md, populates structured state. |
| 7.4 | PoC Plan tests ✅ | Unit tests with mocked LLM for PoC plan agent. |
| 7.5 | Parallel graph wiring ✅ | Update `graph.py` for fan-out (`intake → [poc_plan ∥ fork]`) and fan-in (`→ containerize`). |
| 7.6 | Update containerize ✅ | Enhance containerize prompt and agent to read `poc_infrastructure` from state and adjust Dockerfile (e.g., inference server, model packaging). |
| 7.7 | Update deploy ✅ | Enhance deploy prompt and agent to read `poc_infrastructure` from state and deploy sidecars, PVCs, extra resources. |
| 7.8 | Script execution tool ✅ | `tools/script_tools.py` — `run_script` tool for executing Python test scripts with timeout and output capture. |
| 7.9 | PoC Execute system prompt ✅ | `prompts/poc_execute.md` — Test script generation and execution instructions. |
| 7.10 | PoC Execute agent ✅ | `agents/poc_execute.py` — Generates and runs PoC test scripts based on scenarios. |
| 7.11 | PoC Execute tests ✅ | Unit tests with mocked LLM and mocked script execution. |
| 7.12 | PoC Report system prompt ✅ | `prompts/poc_report.md` — Report generation instructions with structured sections. |
| 7.13 | PoC Report agent ✅ | `agents/poc_report.py` — Generates comprehensive poc-report.md. |
| 7.14 | PoC Report tests ✅ | Unit tests for report generation. |
| 7.15 | Full graph wiring ✅ | Wire `poc_execute → poc_report → END` in graph.py. Update routing functions. |
| 7.16 | CLI updates ✅ | Display PoC plan summary, test results table, and report path in CLI output. |
| 7.17 | Integration tests ✅ | End-to-end graph test with all new nodes, including parallel execution. |
| 7.18 | Deployment model awareness ✅ | Add `deployment_model`, `listens_on_port`, `long_running`, `test_strategy` to `PoCInfrastructure`. Update poc_plan prompt with deployment model reasoning + CLI tool example. Update containerize + deploy prompts and agents to handle non-server workloads (CLI tools, Jobs, workers). Pass full poc-plan.md to downstream agents. |

### Phase 8: GitHub Fork Target Support

**Goal:** Add the ability to fork source repos to GitHub (in addition to GitLab).

See full details in implementation-plan.md.

### Phase 12: RHOAI Fitness Evaluation — NEW

**Goal:** Score each project's fitness for OpenShift AI PoC before forking. Strategy-driven
evaluation using `data/strategy-baseline.yaml`, with dynamic scoring dimensions from
the active strategy profile.

| # | Task | Details |
|---|------|---------|
| 12.1 | Strategy loader module | `tools/strategy.py` — load strategy config, active strategy, baseline YAML |
| 12.2 | State updates | `RHOAIDimensionScore`, `RHOAIEvaluation` TypedDicts, new `PoCState` fields, `PoCPhase.EVALUATE` |
| 12.3 | Evaluation system prompt | `prompts/evaluate.md` — template with placeholders for strategy content |
| 12.4 | Evaluate agent | `agents/evaluate.py` — one-shot LLM call, JSON parsing, markdown report |
| 12.5 | Graph integration | Add evaluate node between intake and fan-out, update routing |
| 12.6 | Markdown report | Write `rhoai-evaluation.md` to clone directory |
| 12.7 | Package data | Include `data/` in distribution via pyproject.toml |
| 12.8 | Strategy loader tests | Unit tests for all loader functions |
| 12.9 | Evaluate agent tests | Unit tests with mocked LLM (success, failure, edge cases) |
| 12.10 | CLI support | `--stop-after=evaluate`, evaluation display in output |

See [rhoai-evaluation-plan.md](./rhoai-evaluation-plan.md) for full details.

### Phase 13: Candidate Comparison for run-sheet — NEW

**Goal:** When `run-sheet` has multiple candidates, evaluate all of them and pick the
best-scoring one. Includes a cheap pre-filter (keyword matching + PM comments) to
bound cost before expensive clone-and-evaluate cycles.

| # | Task | Details |
|---|------|---------|
| 13.1 | Pre-filter: keywords | Keyword matching against strategy capability labels from sheet metadata |
| 13.2 | Pre-filter: PM comments | Batched LLM parse of `pm_comments` column for relevance signals |
| 13.3 | Candidate evaluator | `evaluate_candidates()` — partial pipeline runs (intake + evaluate) per candidate |
| 13.4 | Best selection | `select_best_candidate()` — pick highest-scoring candidate |
| 13.5 | CLI updates | `--max-candidates`, `--skip-evaluation`, comparison table display |
| 13.6 | Pre-filter tests | Unit tests for keyword matching and PM comments parsing |
| 13.7 | Comparison tests | Unit tests for evaluation orchestration and selection |
| 13.8 | Integration test | End-to-end test with mock sheet data and mocked LLM |

See [candidate-comparison-plan.md](./candidate-comparison-plan.md) for full details.

### Phase 14: OGX LLM Proxy for PoC Projects ✅

**Goal:** Deploy an OGX (formerly LlamaStack) server as an OpenAI-compatible LLM
proxy for PoC projects. Eliminates the need to hand real API keys to third-party
code by routing LLM requests through our own vLLM Qwen3-32B backend.

| # | Task | Details |
|---|------|---------|
| 14.1 | OGX image build ✅ | Build OGX from upstream Containerfile with UBI9 base, push to Quay |
| 14.2 | K8s deployment ✅ | Deploy OGX to cluster: Namespace, ConfigMap, Deployment, Service, model aliases |
| 14.3 | Config extension ✅ | Add `ogx_base_url`, `ogx_model`, `ogx_api_key` to AutoPoCConfig |
| 14.4 | State schema ✅ | Add `needs_llm_api`, `llm_env_pattern` to `PoCInfrastructure` |
| 14.5 | PoC Plan prompt ✅ | Add LLM API detection patterns, update examples |
| 14.6 | LLM proxy logic ✅ | `llm_proxy.py` — resolve env vars through OGX, unit tests |
| 14.7 | Deploy integration ✅ | Deploy agent calls `resolve_llm_env_vars()`, prompt update |
| 14.8 | E2E validation ✅ | Full pipeline test with LLM-dependent PoC project |

See [ogx-llm-proxy-plan.md](./ogx-llm-proxy-plan.md) for full details.

### Phase 15: Blog Post Generation ✅

**Goal:** Auto-generate a developer blog post from successful PoC results. Uses
a 3-reviewer autonomous review loop (architect, content, formatting) with
score-based exit. Produces blog-post.md, blog-seo.md, and blog-preview.html.

| # | Task | Details |
|---|------|---------|
| 15.1 | State + phase ✅ | Add `blog_post_path`, `blog_seo_path`, `blog_preview_path`, `BLOG_POST` phase |
| 15.2 | Draft prompt ✅ | System prompt for developer blog generation from PoC data |
| 15.3 | Reviewer prompts ✅ | Architect (35%), content (40%), formatting (25%) scoring rubrics |
| 15.4 | HTML template ✅ | Clean preview template with placeholder substitution |
| 15.5 | Agent implementation ✅ | Generate → review → revise loop, SEO, HTML preview, artifact commit |
| 15.6 | Graph integration ✅ | `route_after_poc_report` (majority-pass gate), `--stop-after` support |
| 15.7 | CLI display ✅ | Show blog artifact paths, skip message |
| 15.8 | Tests ✅ | Draft generation, review scoring, loop control, routing, non-blocking failures |

See [blog-post-plan.md](./blog-post-plan.md) for full details.

---

### Phase 15: Vale Prose Linting

**Goal:** Integrate Vale prose linting into the pipeline as a post-generation
revision loop. After each agent writes a markdown artifact, Vale runs and
findings are fed back to the LLM for revision (up to N rounds). Improves prose
quality using the Red Hat style guide while preserving technical accuracy.

| # | Task | Details |
|---|------|---------|
| 15.1 | Core vale module | `src/autopoc/vale.py` — `run_vale()`, `format_findings_prompt()`, `vale_lint_and_revise()` |
| 15.2 | Revision prompt | `src/autopoc/prompts/vale_revision.md` — conservative, selective revision instructions |
| 15.3 | State & config | `ValeFinding` TypedDict, `vale_results` state field, `max_vale_revisions` config |
| 15.4 | poc_report integration | Call `vale_lint_and_revise()` after report generation, before git commit |
| 15.5 | poc_plan integration | Call `vale_lint_and_revise()` after plan markdown generation, before git commit |
| 15.6 | Tests | `tests/test_vale.py` — mocked subprocess + LLM tests for all code paths |

See [vale-linting-plan.md](./vale-linting-plan.md) for full details.

---

Below are the original phase details (Phases 1-8). Phase 8 is shown in summary form
above; its full task listing follows.

### Phase 8: GitHub Fork Target Support (Original Details)

**Goal:** Add the ability to fork source repos to GitHub (in addition to GitLab). Uses the
GitHub API's fork endpoint to establish a true parent-child relationship. All downstream
agents push to the fork (whichever platform) instead of hardcoding GitLab.

| # | Task | Details |
|---|------|---------|
| 8.1 | Config updates ✅ | Add `fork_target`, `github_token`, `github_org` to `AutoPoCConfig`. Make GitLab fields optional when target is GitHub. Conditional validation. |
| 8.2 | State updates ✅ | Add `fork_repo_url` and `fork_target` to `PoCState`. Generalize away from `gitlab_repo_url`. |
| 8.3 | GitHub API client ✅ | `tools/github_tools.py` — `GitHubClient` class: `fork_repo`, `wait_for_fork`, `get_fork`, `get_clone_url`, `get_authenticated_user`. URL parser. |
| 8.4 | Credential validation ✅ | Add `check_github()` to `credentials.py`. Conditionally validate based on target. |
| 8.5 | Fork agent refactor ✅ | Branch fork agent by target: `_fork_to_github()` (API fork, wait, configure remotes, remove source remote) vs `_fork_to_gitlab()` (existing logic). |
| 8.6 | Git tools safety update ✅ | Remove `github.com` from `_BLOCKED_PUSH_HOSTS` (source remote removed instead). Update error messages to be target-agnostic. |
| 8.7 | Downstream agent updates ✅ | Change `containerize.py` and `deploy.md` from `remote="gitlab"` to `remote="origin"`. |
| 8.8 | CLI --target flag ✅ | Add `--target` option to `autopoc run`. Display fork target in output. |
| 8.9 | .env.example update ✅ | Document new GitHub env vars. |
| 8.10 | Tests ✅ | `test_github_tools.py`, `test_fork_github.py`, config test updates. |

---

## Key Design Decisions

### 1. Agent vs. Node

Not every step needs a full LLM-powered agent. The distinction:

| Step | Type | Rationale |
|------|------|-----------|
| Intake | **LLM Agent** | Needs to reason about repo structure, identify languages, components |
| Evaluate | **LLM Agent** | Scores RHOAI fitness against strategy baseline — one-shot, no tools |
| PoC Plan | **LLM Agent** | Heavy reasoning about what constitutes a valid PoC for this project |
| Fork | **Procedural Node** | Deterministic sequence of git/API commands |
| Containerize | **LLM Agent** | Heavy reasoning about Dockerfile creation/adaptation, now PoC-aware |
| Build | **Hybrid** | Procedural build, LLM only for error diagnosis |
| Deploy | **LLM Agent** | Needs to reason about deployment strategy, now PoC-aware |
| PoC Execute | **LLM Agent** | Generates and runs test scripts — needs reasoning about what to test |
| PoC Report | **LLM Agent** | Synthesizes all results into coherent narrative |

### 2. Why LangGraph over plain LangChain?

- **Cyclic flows:** Build failures loop back to containerize — LangGraph supports cycles natively.
- **Parallel execution:** PoC Plan and Fork run concurrently via fan-out/fan-in.
- **State management:** Shared typed state across all nodes.
- **Checkpointing:** Can resume interrupted runs.
- **Conditional routing:** Different paths based on what the intake agent discovers.

### 5. ODH-aware planning, K8s-based deployment

The PoC Plan agent understands ODH/OpenShift AI concepts (ModelMesh, KServe, Data Science
Pipelines, Notebooks) and references them in the plan. However, actual deployment uses
standard kubectl/K8s resources for portability. ODH-specific CRDs (InferenceService, etc.)
can be added incrementally as ODH clusters become available for testing.

### 6. RHOAI Evaluation: Strategy-Driven, Non-Blocking

The evaluate agent's scoring rubric is driven entirely by the strategy YAML files in
`data/`. Dimensions, weights, and criteria are loaded at runtime — changing the active
strategy (via `data/strategy_config.yaml`) automatically changes the evaluation without
code modifications. The evaluation is non-blocking: if the LLM call fails, the pipeline
continues with an empty evaluation. This is critical for reliability — we never want
scoring to prevent a PoC from running.

For `run-sheet` with multiple candidates, the evaluation is used for comparison. A cheap
pre-filter (keyword matching + optional PM comments LLM parse) narrows candidates before
expensive clone-and-evaluate cycles. This bounds the cost while still surfacing the
best-fit project.

### 7. Parallel fan-out/fan-in

PoC Plan and Fork are independent after intake: PoC Plan is LLM-bound (analyzing the repo),
Fork is I/O-bound (pushing to GitLab). Running them in parallel saves wall-clock time.
LangGraph's `Send` API handles fan-out, and the graph's natural edge convergence on
`containerize` handles fan-in (it waits for both upstream nodes to complete).

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
| PoC plan too ambitious for infra | Deploy/execute fails | Plan agent includes resource profile constraints; validate against cluster capacity |
| PoC test scripts fail on transient issues | False negatives | Built-in retry and wait logic in test scripts; readiness checks before testing |
| Parallel graph nodes cause state conflicts | Data corruption | PoC Plan and Fork write to disjoint state fields; LangGraph handles merge safely |
| Model files too large for container | Build fails / slow | PoC plan identifies model handling strategy (download at runtime vs. bake in) |
| RHOAI evaluation scoring inconsistent | Different scores for same project across runs | Clear rubric in prompt; per-dimension rationales provide transparency |
| Strategy YAML not found at runtime | Evaluate agent crashes | Graceful fallback — skip evaluation, pipeline continues |
| Too many candidates for evaluation | Expensive LLM calls | Pre-filter + configurable cap (default 5) bounds cost |
| PM comments unparseable | Bad pre-filter ranking | Fall back to keyword-only matching; PM boost is optional |
