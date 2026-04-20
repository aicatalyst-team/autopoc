# Architecture

AutoPoC is a LangGraph-based pipeline of specialized agents. Each agent is a node in a state graph, reading from and writing to a shared `PoCState` TypedDict.

## Pipeline Overview

```
intake -> [poc_plan || fork] -> containerize <-> build -> deploy -> apply <-> poc_execute -> poc_report -> END
```

The pipeline has two parallel branches after intake (`poc_plan` and `fork` run concurrently), two retry loops (build and apply), and a linear tail for PoC execution and reporting.

## State

All agents share a single `PoCState` (defined in `state.py`). It's a `TypedDict` with `total=False` -- fields are populated progressively as agents execute.

Key state fields:

| Field | Set by | Description |
|-------|--------|-------------|
| `project_name` | CLI | User-provided project name |
| `source_repo_url` | CLI | GitHub URL |
| `repo_digest` | intake | Procedural text summary of the repo (~10KB) |
| `components` | intake | Detected components (name, language, port, etc.) |
| `poc_type` | poc_plan | Project classification (model-serving, rag, llm-app, etc.) |
| `poc_components` | poc_plan | Which components are relevant for the PoC |
| `poc_infrastructure` | poc_plan | Infrastructure needs (GPU, vector DB, PVC, deployment model) |
| `poc_scenarios` | poc_plan | Test scenarios to run |
| `built_images` | build | Pushed image references |
| `deployed_resources` | apply | Created K8s resources |
| `routes` | apply | Accessible URLs |
| `poc_results` | poc_execute | Test execution results (pass/fail per scenario) |
| `error` | any | Set on failure, checked by routing functions |

## Agents in Detail

### Intake (non-agentic)

**File:** `agents/intake.py`

Not a ReAct agent. Uses a two-step process:

1. **Repo digest** (`tools/repo_digest.py`): Procedurally scans the cloned repo and builds a ~10KB text summary. Reads the file tree, primary build file (pyproject.toml, package.json, etc.), README, entry point headers, existing Dockerfiles, and CI/CD config. Also detects documentation sites (VitePress, Docusaurus, etc.) to exclude them from components. No LLM calls. Runs in under 1 second.

2. **One-shot LLM call**: Sends the digest to the LLM with a simplified prompt. The LLM produces a JSON analysis of components, languages, build systems, and ports. One call, ~5 seconds.

**Why not agentic:** Earlier versions used a ReAct agent with file-reading tools. The LLM would explore the repo, reading 5-15 files, and occasionally exhaust its step budget before producing output. The procedural digest approach is simpler, faster, cheaper, and more reliable.

### PoC Plan (one-shot + fallback)

**File:** `agents/poc_plan.py`

Two-phase approach:

1. **Phase 1 (one-shot):** Single LLM call with the repo digest + intake results. The LLM produces a `poc-plan.md` markdown document and a JSON object with `poc_type`, `infrastructure`, `poc_components`, and `scenarios`. No tools needed in ~90% of cases.

2. **Phase 2 (ReAct fallback):** Only triggered when phase 1 fails to produce test scenarios. Creates a ReAct agent with file tools (`read_file`, `search_files`, `write_file`) for deeper analysis. Receives phase 1's partial output to avoid re-doing work.

The PoC plan determines:
- **Deployment model:** `deployment` (long-running server), `job` (batch), `cli-only` (CLI tool -- no Deployment/Service)
- **Infrastructure:** GPU needs, vector DB, PVC, embedding models, sidecar containers
- **Test scenarios:** HTTP requests, CLI commands, or exec-based tests
- **PoC components:** Which components to actually containerize (skips docs sites, example apps, etc.)

### Fork

**File:** `agents/fork.py`

Pushes the source repo to a self-hosted GitLab instance using the GitLab API. Creates the project in a configured group, sets up the git remote, and pushes. Runs in parallel with PoC Plan.

### Containerize (ReAct agent)

**File:** `agents/containerize.py`

A ReAct agent with file tools + template rendering. For each PoC-relevant component:

1. Reads the source code and build files
2. Generates a `Dockerfile.ubi` using UBI (Red Hat Universal Base Image) base images
3. Handles Python, Node.js, Go, Java with OpenShift-compatible settings (non-root, security context)
4. Writes the Dockerfile, commits, and pushes to GitLab

Respects the `deployment_model` from the PoC plan: CLI tools get `ENTRYPOINT/CMD` with no `EXPOSE`, servers get the appropriate port exposed.

On build failures, the pipeline routes back here with the error message. The agent reads the error and modifies the Dockerfile to fix it.

### Build

**File:** `agents/build.py`

Not a ReAct agent. Procedural:

1. For each component with a Dockerfile, runs `podman build`
2. Pushes the image to the Quay registry
3. Loads the image into kind (for local E2E testing)
4. On failure, classifies errors as permanent (auth, network) vs. retryable (Dockerfile bugs)
5. For retryable errors, uses an LLM to diagnose the build log and stores the diagnosis for the containerize agent

### Deploy (ReAct agent)

**File:** `agents/deploy.py`

Generates Kubernetes manifests based on the built images and PoC plan. Creates:

- `namespace.yaml`
- `deployment.yaml` / `job.yaml` (depending on deployment model)
- `service.yaml` (only for components that listen on ports)
- `pvc.yaml` (if persistent storage needed)

Commits manifests to the GitLab repo. Does NOT apply them -- that's the apply agent's job.

### Apply (ReAct agent)

**File:** `agents/apply.py`

Applies the manifests generated by deploy:

1. `kubectl apply` in dependency order (namespace -> RBAC -> PVC -> Deployment -> Service)
2. `kubectl wait` for rollouts
3. Verifies pods are running
4. Extracts service URLs (NodePort for local, Route for OpenShift)

On failure, returns the error (with pod logs) and the pipeline routes back to deploy to fix manifests.

### PoC Execute (ReAct agent)

**File:** `agents/poc_execute.py`

Runs the test scenarios defined by the PoC plan. Generates and executes test scripts using `curl`, `kubectl run`, or `kubectl exec` depending on the test strategy.

### PoC Report (one-shot, no tools)

**File:** `agents/poc_report.py`

Non-agentic. All data comes from pipeline state -- the LLM receives the full context (components, images, manifests, test results, logs) and produces a structured markdown report in a single call. The report is written to disk procedurally.

## Routing and Retry Logic

Defined in `graph.py`:

```python
route_after_intake(state):
    if error: return ["failed"]     # -> END
    return ["poc_plan", "fork"]     # parallel fan-out

route_after_build(state):
    if error is None: return "deploy"
    if retries < max: return "containerize"  # fix Dockerfile, rebuild
    return "failed"                          # -> END

route_after_apply(state):
    if error is None: return "poc_execute"
    if container_fix_action == "fix-dockerfile":
        if container_fix_retries < max: return "containerize"  # outer loop
    if retries < max: return "deploy"        # inner loop: fix manifests
    return "failed"                          # -> END
```

## Context Management

Agents that use ReAct (`containerize`, `deploy`, `apply`, `poc_execute`, `poc_report`) have a `pre_model_hook` that prevents token overflow. The hook (`context.py`) runs before each LLM call and:

1. Estimates total token count (pessimistic: 2 chars/token)
2. If over budget (120K estimated tokens), truncates older tool results to 300-char previews
3. If still over, drops entire tool groups (always as atomic AIMessage + ToolMessage pairs to preserve API invariants)
4. If still over, progressively truncates the most recent tool results (4K -> 2K -> 1K -> 500 chars)

This is a safety net -- with procedural pre-processing (repo digest) and one-shot LLM calls, most agents don't accumulate enough context to trigger compaction.

## Configuration

`config.py` uses Pydantic Settings to load from environment variables. See `.env.example` for all options.

The `AutoPoCConfig` class validates at startup and provides a `masked_summary()` method for displaying config without exposing secrets.

## Credential Validation

`credentials.py` validates GitLab, Quay, and LLM credentials at pipeline start:

- **GitLab:** `GET /api/v4/user` with the token
- **Quay:** `GET /api/v1/user/` with Bearer token
- **LLM:** API key format check (Anthropic) or project/location check (Vertex AI)

Results are displayed as a Rich table. Failures warn but don't hard-block (use `--skip-validation` to bypass).

## Templates

Jinja2 templates in `templates/`:

- `Dockerfile.ubi.j2` -- Single-stage UBI Dockerfile
- `Dockerfile.ubi-builder.j2` -- Multi-stage builder pattern
- `deployment.yaml.j2` -- Kubernetes Deployment
- `service.yaml.j2` -- Kubernetes Service

Agents can use these via the `render_template` tool, or generate manifests from scratch.
