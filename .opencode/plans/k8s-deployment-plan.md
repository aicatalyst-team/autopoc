# AutoPoC — Kubernetes Deployment Plan

> Containerize the AutoPoC agent, enable Kubernetes Job deployment, and prepare
> for OpenShift Build integration and Google Sheet–driven batch runs.
>
> See [plan.md](./plan.md) for overall architecture and [implementation-plan.md](./implementation-plan.md)
> for the original implementation phases.

---

## Overview

This plan covers the work needed to run AutoPoC as a **Kubernetes Job** (and
eventually a CronJob). The agent currently runs as a CLI tool on a developer
workstation. The goal is to package it as a container image that can be deployed
to OpenShift/Kubernetes, with project input coming from environment variables
(and later from a Google Cloud Sheet).

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Container install strategy | Shiv binary (multi-stage build) | Consistent with existing release artifacts; single-file binary keeps the runtime image clean |
| Base image | `registry.access.redhat.com/ubi9/python-312` | RHEL-compatible, matches OpenShift target, includes git and Python |
| Project input for K8s Jobs | Environment variables (`AUTOPOC_PROJECT_NAME`, `AUTOPOC_REPO_URL`) | Kubernetes-native, easy to set in Job specs, ConfigMaps, Secrets |
| Container build strategy | OpenShift Builds (replacing podman) | Avoids privileged containers; more OpenShift-native for K8s context |
| Google Sheet integration | `autopoc run-sheet` subcommand (stub for now) | Separate command keeps concerns clean; future CronJob entry point |
| Podman in container image | **Not included** | OpenShift Builds replace podman; avoids privileged container requirement |

---

## Task Index

| Phase | Tasks | Summary |
|-------|-------|---------|
| **1. Containerize** | 1.1–1.3 | Dockerfile, .dockerignore, Makefile image targets |
| **2. Env Var Input** | 2.1 | CLI fallback from --name/--repo to env vars |
| **3. run-sheet Stub** | 3.1 | Stub subcommand for future Google Sheet integration |
| **4. Build Strategy** | 4.1–4.5 | Abstract build strategy, podman impl, OpenShift stub, config, agent refactor |
| **5. K8s Manifests** | 5.1–5.2 | Job manifest, example Secret |
| **6. Tests** | 6.1–6.4 | CLI env var tests, build strategy tests, lint, image build |

---

## Progress

| Phase | Status | Tasks Done |
|-------|--------|------------|
| **1. Containerize** | ✅ DONE | 3/3 |
| **2. Env Var Input** | ✅ DONE | 1/1 |
| **3. run-sheet Stub** | CANCELLED | — (not needed) |
| **4. Build Strategy** | ✅ DONE | 5/5 (+ robot account support, --stop-after, build history limits) |
| **5. K8s Manifests** | ✅ DONE | 2/2 |
| **6. Tests** | ✅ DONE | 3/4 (build strategy tests, CLI tests, lint/test pass; image verified locally) |

---

## Phase 1: Containerize the Agent

### Task 1.1 — Create Dockerfile

**File:** `Dockerfile` (new)

Multi-stage build:

**Stage 1 — Builder:**
- Base: `registry.access.redhat.com/ubi9/python-312`
- Install `shiv` and project dependencies from `requirements.lock`
- Copy source tree, run `make build` to produce `dist/autopoc` shiv binary
- The builder stage does not need kubectl/git — only Python and build tools

**Stage 2 — Runtime:**
- Base: `registry.access.redhat.com/ubi9/python-312`
- Install runtime dependencies:
  - `kubectl` — download from official release URL, verify checksum
  - `git` — should already be in UBI Python image, verify
- Copy `dist/autopoc` from builder stage
- No podman needed (OpenShift Builds will replace it)
- Set `WORKDIR /workspace`
- Set `ENTRYPOINT ["./autopoc"]`
- Set `CMD ["--help"]`
- Run as non-root user (UID 1001, already default in UBI Python images)

**Labels:**
- `io.k8s.description`, `io.openshift.tags`, `maintainer`, version from build arg

**Size target:** < 500MB (UBI Python base is ~350MB)

### Task 1.2 — Create .dockerignore

**File:** `.dockerignore` (new)

Exclude:
```
.git
.env
.env.*
dist/
build/
*.egg-info
__pycache__
.pytest_cache
nohup.out
tests/
docs/
.opencode/
*.md
!README.md
```

Keep `requirements.lock`, `pyproject.toml`, `Makefile`, `src/` — needed for build.

### Task 1.3 — Add Makefile image targets

**File:** `Makefile` (modified)

New variables:
```makefile
IMAGE_REGISTRY ?= quay.io
IMAGE_ORG      ?= autopoc
IMAGE_NAME     ?= autopoc
IMAGE_TAG      ?= latest
IMAGE          = $(IMAGE_REGISTRY)/$(IMAGE_ORG)/$(IMAGE_NAME):$(IMAGE_TAG)
```

New targets:
```
make image       — Build container image with podman/docker
make image-push  — Push image to registry
```

Implementation:
```makefile
.PHONY: image
image: ## Build container image
	podman build -t $(IMAGE) .

.PHONY: image-push
image-push: ## Push container image to registry
	podman push $(IMAGE)
```

---

## Phase 2: Environment Variable Input

### Task 2.1 — Add env var fallback for --name and --repo

**File:** `src/autopoc/cli.py` (modified)

Currently `--name` and `--repo` are required `typer.Option` arguments. Change them to:

```python
name: Annotated[str | None, typer.Option(
    "--name", "-n",
    envvar="AUTOPOC_PROJECT_NAME",
    help="Project name (or set AUTOPOC_PROJECT_NAME env var)",
)] = None

repo: Annotated[str | None, typer.Option(
    "--repo", "-r",
    envvar="AUTOPOC_REPO_URL",
    help="GitHub repo URL (or set AUTOPOC_REPO_URL env var)",
)] = None
```

Add validation at the start of the `run` function:
```python
if not name:
    console.print("[red]Error: --name or AUTOPOC_PROJECT_NAME is required[/red]")
    raise typer.Exit(code=1)
if not repo:
    console.print("[red]Error: --repo or AUTOPOC_REPO_URL is required[/red]")
    raise typer.Exit(code=1)
```

This way:
- CLI users: `autopoc run --name foo --repo https://...` (unchanged)
- K8s Jobs: Set `AUTOPOC_PROJECT_NAME` and `AUTOPOC_REPO_URL` env vars in the Job spec
- Precedence: CLI args > env vars (Typer's default behavior)

---

## Phase 3: `run-sheet` Stub Command

### Task 3.1 — Add `autopoc run-sheet` subcommand

**File:** `src/autopoc/cli.py` (modified)

Add a new Typer command:

```python
@app.command("run-sheet")
def run_sheet(
    sheet_id: Annotated[str | None, typer.Option(
        "--sheet-id",
        help="Google Sheet ID containing projects to PoC",
    )] = None,
    credentials: Annotated[str | None, typer.Option(
        "--credentials",
        help="Path to Google service account credentials JSON",
    )] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run AutoPoC for projects listed in a Google Sheet.

    This command reads project names and repository URLs from a Google Cloud
    Sheet and runs the full pipeline for each project. Intended for use as
    a Kubernetes CronJob.

    NOT YET IMPLEMENTED — see project roadmap for tracking.
    """
    console.print(
        "[yellow]The 'run-sheet' command is not yet implemented.[/yellow]\n"
        "This will read projects from a Google Sheet and run the PoC pipeline "
        "for each one.\n"
        "See the project roadmap for implementation tracking."
    )
    raise typer.Exit(code=1)
```

This establishes:
- The CLI contract (`autopoc run-sheet --sheet-id XXXX --credentials /path/to/sa.json`)
- A clear "not implemented" message with exit code 1
- The parameter interface for future implementation

---

## Phase 4: OpenShift Build Strategy

### Task 4.1 — Create BuildStrategy abstract base class

**File:** `src/autopoc/tools/build_strategy.py` (new)

```python
from abc import ABC, abstractmethod

class BuildStrategy(ABC):
    """Abstract interface for container image build strategies."""

    @abstractmethod
    async def build(
        self,
        context_dir: str,
        dockerfile: str,
        image_tag: str,
        **kwargs,
    ) -> tuple[bool, str]:
        """Build a container image.

        Returns:
            (success, log_output) tuple
        """
        ...

    @abstractmethod
    async def push(self, image_tag: str, **kwargs) -> tuple[bool, str]:
        """Push a container image to a registry.

        Returns:
            (success, log_output) tuple
        """
        ...

    @abstractmethod
    async def login(
        self, registry: str, username: str, password: str, **kwargs
    ) -> None:
        """Authenticate to a container registry."""
        ...
```

### Task 4.2 — Extract current podman logic into PodmanBuildStrategy

**File:** `src/autopoc/tools/build_strategy.py` (modified)

Wrap the existing `podman_build`, `podman_push`, and `podman_login` functions
from `src/autopoc/tools/podman_tools.py` into a `PodmanBuildStrategy` class
implementing the `BuildStrategy` interface.

The existing functions remain available for backward compatibility, but the
build agent will use the strategy interface.

### Task 4.3 — Create OpenShiftBuildStrategy stub

**File:** `src/autopoc/tools/build_strategy.py` (modified)

```python
class OpenShiftBuildStrategy(BuildStrategy):
    """Build container images using OpenShift BuildConfig / oc start-build.

    NOT YET IMPLEMENTED — requires oc CLI and OpenShift cluster with build
    capabilities.
    """

    async def build(self, context_dir, dockerfile, image_tag, **kwargs):
        raise NotImplementedError(
            "OpenShift Build strategy is not yet implemented. "
            "Set BUILD_STRATEGY=podman to use podman builds, or see the "
            "project roadmap for OpenShift Build implementation tracking."
        )

    async def push(self, image_tag, **kwargs):
        raise NotImplementedError("OpenShift Build strategy is not yet implemented.")

    async def login(self, registry, username, password, **kwargs):
        raise NotImplementedError("OpenShift Build strategy is not yet implemented.")
```

### Task 4.4 — Add BUILD_STRATEGY config field

**File:** `src/autopoc/config.py` (modified)

Add to `AutoPoCConfig`:

```python
build_strategy: str = "podman"  # "podman" or "openshift"
```

Env var: `BUILD_STRATEGY`

Add validation: must be one of `"podman"`, `"openshift"`.

### Task 4.5 — Refactor build_agent to use strategy interface

**File:** `src/autopoc/agents/build.py` (modified)

Replace direct calls to `podman_build()`, `podman_push()`, `podman_login()`
with calls through the `BuildStrategy` interface.

Add a factory function:

```python
def get_build_strategy(config: AutoPoCConfig) -> BuildStrategy:
    if config.build_strategy == "podman":
        return PodmanBuildStrategy()
    elif config.build_strategy == "openshift":
        return OpenShiftBuildStrategy()
    else:
        raise ValueError(f"Unknown build strategy: {config.build_strategy}")
```

The build agent receives the strategy (or creates one from config) and uses it
throughout. This is a refactor of the existing code, not new functionality —
behavior with `BUILD_STRATEGY=podman` (the default) must be identical to the
current behavior.

---

## Phase 5: Kubernetes Job Manifests

### Task 5.1 — Create Kubernetes Job manifest

**File:** `deploy/job.yaml` (new)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: autopoc-${PROJECT_NAME}
  labels:
    app: autopoc
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        app: autopoc
    spec:
      restartPolicy: Never
      containers:
        - name: autopoc
          image: quay.io/autopoc/autopoc:latest
          args: ["run"]
          env:
            - name: AUTOPOC_PROJECT_NAME
              value: "${PROJECT_NAME}"
            - name: AUTOPOC_REPO_URL
              value: "${REPO_URL}"
            - name: BUILD_STRATEGY
              value: "openshift"
            # Credentials from Secret
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: ANTHROPIC_API_KEY
            # ... (all other credential env vars from Secret)
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2"
          volumeMounts:
            - name: work
              mountPath: /workspace
      volumes:
        - name: work
          emptyDir: {}
```

Include comments explaining each section and how to customize.

### Task 5.2 — Create example Secret manifest

**File:** `deploy/secret.yaml.example` (new)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: autopoc-credentials
type: Opaque
stringData:
  ANTHROPIC_API_KEY: "sk-ant-..."
  FORK_TARGET: "github"
  GITHUB_TOKEN: "ghp_..."
  GITHUB_ORG: "my-org"
  QUAY_ORG: "my-org"
  QUAY_TOKEN: "..."
  OPENSHIFT_API_URL: "https://api.cluster.example.com:6443"
  OPENSHIFT_TOKEN: "sha256~..."
```

Include comments explaining which fields are required vs optional, and a
warning not to commit this file with real values.

---

## Phase 6: Tests and Validation

### Task 6.1 — Test env var fallback in CLI

**File:** `tests/test_cli.py` (new or modified)

Test cases:
- `--name` and `--repo` via CLI args (current behavior, should still work)
- `AUTOPOC_PROJECT_NAME` and `AUTOPOC_REPO_URL` env vars when CLI args omitted
- CLI args take precedence over env vars
- Missing both CLI and env var → exit code 1 with error message
- `run-sheet` command prints not-implemented message and exits with code 1

### Task 6.2 — Test build strategy selection

**File:** `tests/test_build_strategy.py` (new)

Test cases:
- `get_build_strategy("podman")` returns `PodmanBuildStrategy`
- `get_build_strategy("openshift")` returns `OpenShiftBuildStrategy`
- `get_build_strategy("invalid")` raises `ValueError`
- `OpenShiftBuildStrategy.build()` raises `NotImplementedError`
- `PodmanBuildStrategy.build()` delegates to `podman_build()` (mock test)
- Config validation accepts `"podman"` and `"openshift"`, rejects others

### Task 6.3 — Lint and test pass

Run `make lint` and `make test` — all checks must pass with the new code.

### Task 6.4 — Container image builds

Run `make image` — verify the Dockerfile builds successfully and the shiv
binary works inside the container:

```bash
podman run --rm autopoc:latest --help
podman run --rm autopoc:latest run --help
```

---

## Deferred / Future Work

These items are explicitly **out of scope** for this plan:

| Item | Description | Depends On |
|------|-------------|------------|
| **OpenShift Build implementation** | Implement `OpenShiftBuildStrategy.build()` and `.push()` using `oc start-build` / `BuildConfig`. Requires designing how to create BuildConfigs, handle image streams, and stream build logs. | Phase 4 (strategy interface) |
| **`autopoc run-sheet` implementation** | Google Sheets API integration — read project list from a sheet, iterate over rows, run pipeline for each. Requires Google service account, Sheets API client, error handling for partial failures. | Phase 3 (stub command) |
| **CronJob manifest** | `deploy/cronjob.yaml` — scheduled runs using `run-sheet`. | `run-sheet` implementation |
| **Image signing / attestation** | Sign container images with cosign / Sigstore for supply chain security. | Phase 1 (container image) |
| **Helm chart** | Package Job/CronJob/Secret/RBAC as a Helm chart for easier deployment. | Phase 5 (manifests) |
| **RBAC / ServiceAccount** | Define minimal RBAC for the autopoc ServiceAccount if it needs to interact with the K8s API from within the cluster. | Phase 5 |
