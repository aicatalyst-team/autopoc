# OpenCode Harness Rewrite: Architecture Design

> **Status**: DESIGN PHASE
> **Author**: OpenCode Agent
> **Date**: 2026-05-25
> **ADR**: This document supersedes the LangGraph orchestration (ADR-0001) and agent type taxonomy (ADR-0002)

## 1. Executive Summary

Replace the LangGraph-based multi-agent pipeline with an **OpenCode skill-driven architecture** where OpenCode itself is the orchestration harness. The pipeline logic, retry strategies, and tool usage remain the same, but the execution model changes fundamentally:

| Aspect | Current (LangGraph) | New (OpenCode Harness) |
|--------|---------------------|----------------------|
| Orchestration | LangGraph StateGraph with routing functions | OpenCode following skill instructions |
| Agent runtime | LangChain ReAct agents with tool bindings | OpenCode using bash commands directly |
| State | PoCState TypedDict flowing through graph nodes | Progressive YAML file (`poc-state.yaml`) |
| Tools | Python @tool decorators (LangChain) | bash: git, kubectl, podman, curl + Python scripts |
| Retry logic | Graph routing functions with counters | Skill instructions + state file counters |
| LLM calls | Per-agent LLM instances (Anthropic/Vertex/OpenAI) | OpenCode IS the LLM |
| Container image | shiv binary + CLI entrypoint | OpenCode binary + skill files |
| Invocation | `autopoc run --name X --repo Y` | `scripts/run-autopoc.sh <name> <url>` -> pod with OpenCode |

### Three Skills

| Skill | Purpose | Invocation |
|-------|---------|------------|
| `run-poc` | Full PoC pipeline for a single project | Pod via `scripts/run-autopoc.sh` |
| `run-sheet` | Sheet-driven batch candidate evaluation + PoC execution | CronJob or manual |
| `blog-create` | Blog post generation with review loop | Invoked by `run-poc` or standalone |

---

## 2. Architecture Overview

### 2.1 Execution Model

```
User runs: scripts/run-autopoc.sh my-project https://github.com/org/repo
  |
  v
K8s Job created in namespace "autopoc"
  |
  v
Pod starts with OpenCode container image (UBI9 + opencode + kubectl + podman + vale)
  |
  v
OpenCode launches with: opencode run --dangerously-skip-permissions "Run PoC for <name> from <url>"
  |
  v
OpenCode auto-discovers .opencode/skills/run-poc/SKILL.md (via skill description matching)
OpenCode loads the skill and follows its instructions
  |
  v
OpenCode follows the skill instructions:
  Phase 1: Intake (clone repo, analyze with repo_digest.py, summarize)
  Phase 2: Evaluate (score RHOAI fitness)
  Phase 3: Fork (push to GitLab/GitHub)
  Phase 4: PoC Plan (create plan + scenarios + infrastructure)
  Phase 5: Containerize (write UBI Dockerfiles)
  Phase 6: Build (podman build + push to Quay)
  Phase 7: Deploy (write K8s manifests)
  Phase 8: Apply (kubectl apply + verify)
  Phase 9: PoC Execute (write + run test scripts)
  Phase 10: PoC Report (generate markdown report)
  Phase 11: Blog Post (invoke blog-create skill)
  |
  v
State persisted to poc-state.yaml at each phase
Pod exits with success/failure
```

### 2.2 What OpenCode Replaces

**Removed entirely:**
- `src/autopoc/graph.py` -- LangGraph pipeline definition
- `src/autopoc/state.py` -- PoCState TypedDict
- `src/autopoc/cli.py` -- Typer CLI entry points
- `src/autopoc/cli_batch.py` -- Batch CLI logic
- `src/autopoc/llm.py` -- LLM factory (OpenCode IS the LLM)
- `src/autopoc/context.py` -- Context trimming (OpenCode handles this)
- `src/autopoc/debug.py` -- Debug utilities (OpenCode has its own)
- All agent files in `src/autopoc/agents/` -- replaced by skill instructions
- All LangChain @tool decorators -- replaced by bash commands

**Retained as standalone Python scripts (called via `python script.py`):**
- `src/autopoc/tools/repo_digest.py` -- repo analysis (deterministic, no LLM)
- `src/autopoc/tools/strategy.py` -- RHOAI strategy loader (deterministic)
- `src/autopoc/tools/vale_lint.py` -- Vale linting (deterministic)
- `src/autopoc/tools/quay_tools.py` -- Quay API client (ensure repo exists)
- `src/autopoc/tools/gitlab_tools.py` -- GitLab API client (create project)
- `src/autopoc/tools/github_tools.py` -- GitHub API client (fork repo)
- `src/autopoc/tools/build_strategy.py` -- Build strategy abstraction
- `src/autopoc/tools/llm_proxy.py` -- OGX env var resolution
- `src/autopoc/sheet.py` -- Google Sheet reader/writer

**Retained as data files:**
- `src/autopoc/prompts/` -- used as reference material in skill instructions
- `src/autopoc/templates/` -- Jinja2 templates (may be used by scripts)
- `data/` -- strategy YAML files

**Retained as-is:**
- `deploy/` -- K8s manifests (updated for new image)
- `scripts/` -- operational scripts (updated)

### 2.3 Why Standalone Scripts Instead of MCP

The user chose bash commands over MCP tools. However, some operations are complex enough that raw bash would be fragile (e.g., GitLab API calls, Quay repo creation, repo digest generation). These are kept as **standalone Python CLI scripts** that OpenCode invokes via bash:

```bash
# Instead of MCP tool call:
python -m autopoc.tools.repo_digest /path/to/repo

# Instead of LangChain @tool:
python -m autopoc.tools.gitlab_client create-project my-project

# Instead of complex bash:
python -m autopoc.tools.quay_client ensure-repo autopoc my-project
```

Each script is a thin CLI wrapper around the existing Python function, using `argparse` or `click` for argument parsing and JSON output to stdout.

---

## 3. State File Design (`poc-state.yaml`)

### 3.1 Format

Progressive YAML that grows as phases complete. Human-readable, easy to edit for debugging.

```yaml
# poc-state.yaml -- Auto-generated by OpenCode run-poc skill
# Updated after each phase completion

project:
  name: "my-project"
  source_repo_url: "https://github.com/org/repo"
  started_at: "2026-05-25T10:00:00Z"
  current_phase: "containerize"  # last completed or in-progress phase

# Phase 1: Intake
intake:
  status: "completed"
  local_clone_path: "/workspace/repos/my-project"
  repo_digest_path: "/workspace/repos/my-project/.autopoc/repo-digest.md"
  repo_summary: "A FastAPI ML model serving application with PyTorch backend..."
  components:
    - name: "api"
      language: "python"
      build_system: "pip"
      entry_point: "serve.py"
      port: 8000
      source_dir: "."
      existing_dockerfile: "Dockerfile"
      is_ml_workload: true

# Phase 2: Evaluate
evaluate:
  status: "completed"
  total_score: 78
  max_possible_score: 100
  relationship: "direct"
  strategy_areas: ["model-serving", "inference"]
  evaluation_path: "/workspace/repos/my-project/.autopoc/rhoai-evaluation.md"

# Phase 3: Fork
fork:
  status: "completed"
  fork_repo_url: "https://gitlab.example.com/autopoc/my-project"
  fork_target: "gitlab"

# Phase 4: PoC Plan
poc_plan:
  status: "completed"
  poc_type: "model-serving"
  poc_plan_path: "/workspace/repos/my-project/.autopoc/poc-plan.md"
  scenarios:
    - name: "health-check"
      description: "Verify /health endpoint returns 200"
      type: "http"
      endpoint: "/health"
      timeout_seconds: 30
    - name: "inference"
      description: "Send sample input and verify prediction"
      type: "http"
      endpoint: "/predict"
      input_data: '{"features": [1.0, 2.0, 3.0]}'
      expected_behavior: "Returns JSON with prediction field"
      timeout_seconds: 60
  infrastructure:
    needs_gpu: false
    needs_pvc: false
    resource_profile: "medium"
    needs_llm_api: false
    deployment_model: "deployment"
    port_listening: true

# Phase 5: Containerize
containerize:
  status: "completed"
  dockerfiles:
    - component: "api"
      path: "/workspace/repos/my-project/Dockerfile.ubi"
      base_image: "registry.access.redhat.com/ubi9/python-312"

# Phase 6: Build
build:
  status: "completed"
  images:
    - component: "api"
      image: "quay.io/autopoc/my-project-api:latest"
  build_retries: 0

# Phase 7: Deploy
deploy:
  status: "completed"
  manifests_dir: "/workspace/repos/my-project/kubernetes/"

# Phase 8: Apply
apply:
  status: "completed"
  namespace: "poc-my-project"
  deployed_resources:
    - "deployment/my-project-api"
    - "service/my-project-api"
  routes:
    - name: "my-project-api"
      url: "http://my-project-api.poc-my-project.svc:8000"

# Phase 9: PoC Execute
poc_execute:
  status: "in_progress"
  test_script_path: "/workspace/repos/my-project/.autopoc/poc_test.py"
  results: []

# Retry state
retries:
  build_retries: 0
  max_build_retries: 3
  deploy_retries: 0
  max_deploy_retries: 3
  container_fix_retries: 0
  max_container_fix_retries: 2

# Error tracking
errors: []
  # - phase: "build"
  #   message: "podman build failed: pip install torch could not find..."
  #   action: "retry"  # retry | fix-dockerfile | fix-manifest | fail
```

### 3.2 State File Operations

OpenCode reads and updates the state file using standard tools:
- **Read**: `cat poc-state.yaml` or OpenCode's Read tool
- **Update**: OpenCode's Write/Edit tool to update specific fields
- **Parse**: `python -c "import yaml; ..."` for programmatic access if needed

The skill instructions tell OpenCode to update the state file after each phase.

---

## 4. Skill Design: `run-poc`

### 4.1 Directory Structure

```
.opencode/skills/run-poc/
  SKILL.md                    # Main skill instructions
  references/
    intake.md                 # Phase 1 detailed instructions
    evaluate.md               # Phase 2 detailed instructions
    fork.md                   # Phase 3 detailed instructions
    poc-plan.md               # Phase 4 detailed instructions (adapted from prompts/poc_plan.md)
    containerize.md           # Phase 5 detailed instructions (adapted from prompts/containerize.md)
    build.md                  # Phase 6 detailed instructions
    deploy.md                 # Phase 7 detailed instructions (adapted from prompts/deploy.md)
    apply.md                  # Phase 8 detailed instructions (adapted from prompts/apply.md)
    poc-execute.md            # Phase 9 detailed instructions (adapted from prompts/poc_execute.md)
    poc-report.md             # Phase 10 detailed instructions (adapted from prompts/poc_report.md)
    state-schema.md           # State file format and update rules
    retry-strategy.md         # Retry loop logic and error classification
    ubi-dockerfile-rules.md   # UBI base image, package manager, OpenShift UID rules
    error-triage.md           # Error classification rules for apply failures
```

### 4.2 SKILL.md Overview

The main SKILL.md will:
1. Define the pipeline phases in order
2. Tell OpenCode to create and maintain `poc-state.yaml`
3. Reference phase-specific instructions from `references/`
4. Define retry loop behavior
5. Define phase transitions and error handling
6. Tell OpenCode when to invoke the `blog-create` skill

### 4.3 Phase-by-Phase Design

Each phase maps to the current agent but with OpenCode doing the work directly:

#### Phase 1: Intake
- Clone the repo: `git clone <url> /workspace/repos/<name>`
- Run repo digest: `python -m autopoc.tools.repo_digest /workspace/repos/<name>`
- OpenCode analyzes the digest output and identifies components
- Update `poc-state.yaml` with components, summary, etc.

#### Phase 2: Evaluate
- OpenCode reads the strategy YAML: `python -m autopoc.tools.strategy load`
- OpenCode scores the project against dimensions (it IS the LLM)
- Write `rhoai-evaluation.md`
- Non-blocking: failure here does not stop the pipeline

#### Phase 3: Fork
- Create project: `python -m autopoc.tools.gitlab_client create-project <name>` or `python -m autopoc.tools.github_client fork <owner> <repo>`
- Add remote: `git remote add gitlab <url>` (or rename origin)
- Push: `git push gitlab --all && git push gitlab --tags`

#### Phase 4: PoC Plan
- OpenCode reads the repo digest, components, and strategy evaluation
- OpenCode generates the PoC plan (JSON + markdown) following `references/poc-plan.md`
- Writes `poc-plan.md` and updates state with scenarios/infrastructure
- Optionally runs Vale: `vale --output=JSON poc-plan.md`

#### Phase 5: Containerize
- For each component, OpenCode writes `Dockerfile.ubi` following `references/containerize.md`
- Rules from `references/ubi-dockerfile-rules.md` are applied during generation
- No post-processing script -- the skill instructions encode all fixup rules
- Commit and push: `git add Dockerfile.ubi && git commit -m "..." && git push`

#### Phase 6: Build
- Ensure Quay repo: `python -m autopoc.tools.quay_client ensure-repo <org> <name>`
- Login: `podman login quay.io -u <user> -p <token>`
- Build: `podman build -t quay.io/<org>/<name>:latest -f Dockerfile.ubi .`
- Push: `podman push quay.io/<org>/<name>:latest`
- On failure: OpenCode diagnoses the error, updates state, decides retry vs fail

#### Phase 7: Deploy
- OpenCode generates K8s manifests (namespace, deployment, service, etc.) following `references/deploy.md`
- Writes to `kubernetes/` directory
- Resolves LLM env vars if needed: `python -m autopoc.tools.llm_proxy resolve-env <env_vars_json>`
- Commits and pushes manifests

#### Phase 8: Apply
- Create namespace: `kubectl create namespace poc-<name> --dry-run=client -o yaml | kubectl apply -f -`
- Apply manifests: `kubectl apply -f kubernetes/ -n poc-<name>`
- Wait for rollout: `kubectl rollout status deployment/<name> -n poc-<name> --timeout=300s`
- Verify pods: `kubectl get pods -n poc-<name>`
- Get service URL: `kubectl get svc -n poc-<name> -o json`
- On failure: classify error per `references/error-triage.md`, update state, route to retry

#### Phase 9: PoC Execute
- OpenCode writes a Python test script (`poc_test.py`) using only stdlib
- Runs it: `python poc_test.py`
- Parses results from stdout
- Uses `kubectl logs` and `kubectl get pods` to debug failures
- Detects container-level issues and signals container fix loop

#### Phase 10: PoC Report
- OpenCode generates the markdown report following `references/poc-report.md`
- Runs Vale linting if available
- Commits to `autopoc-artifacts` branch

#### Phase 11: Blog Post (conditional)
- If majority of tests passed, invoke the `blog-create` skill
- The blog-create skill handles the full blog generation pipeline

### 4.4 Retry Loop Design

The skill instructions encode retry logic as decision trees:

```
BUILD RETRY LOOP:
  If build fails:
    1. Read the error message
    2. Check retries.build_retries < retries.max_build_retries
    3. If permanent error (auth, network, missing podman): FAIL
    4. If retriable: increment build_retries, go back to Phase 5 (Containerize)
       - The error context is in poc-state.yaml for OpenCode to read
    5. If retries exhausted: FAIL

DEPLOY RETRY LOOP:
  If apply fails:
    1. Classify error per references/error-triage.md
    2. If fix-manifest:
       - increment deploy_retries, go back to Phase 7 (Deploy)
    3. If fix-dockerfile:
       - increment container_fix_retries, go back to Phase 5 (Containerize)
       - reset build_retries and deploy_retries to 0
    4. If experiment:
       - same as fix-dockerfile but use :experiment-N tags
    5. If all retries exhausted: FAIL

POC EXECUTE -> CONTAINER FIX:
  If test failures indicate container issues (command not found, ModuleNotFoundError):
    1. increment container_fix_retries, go back to Phase 5
    2. reset build_retries and deploy_retries to 0
```

---

## 5. Skill Design: `run-sheet`

### 5.1 Directory Structure

```
.opencode/skills/run-sheet/
  SKILL.md                    # Main skill instructions
  references/
    sheet-reader.md           # How to read and filter Google Sheet candidates
    candidate-evaluation.md   # How to evaluate and rank candidates
    prefilter.md             # Heuristic pre-filtering rules
```

### 5.2 Flow

1. Read sheet: `python -m autopoc.tools.sheet_reader --sheet-id <id> --credentials <path>`
2. Filter to actionable GitHub repos
3. Pre-filter using keyword matching (no LLM)
4. For top candidates: run partial pipeline (intake + evaluate) for scoring
5. Rank candidates by RHOAI score
6. For the top N: invoke the `run-poc` skill for each
7. Write results back: `python -m autopoc.tools.sheet_writer --sheet-id <id> --results <json>`

### 5.3 Candidate Evaluation

OpenCode performs the evaluation itself (it IS the LLM). For each candidate:
1. Clone and run repo_digest
2. Analyze the digest and score against strategy dimensions
3. Select the top candidate(s)
4. Run full `run-poc` for each winner

---

## 6. Skill Design: `blog-create`

### 6.1 Source

Copied from `solaius/ai-asset-registry/.claude/skills/blog-create/` with minimal adaptation:

**Adaptations needed:**
- Remove Google Workspace MCP references (not available in pod)
- Remove Playwright MCP references (not available in pod)
- Adjust file paths from `docs/blogs/` to `/workspace/repos/<name>/.autopoc/blog/`
- Remove qualifying questions (Phase 1) -- input comes from PoC results, not user interaction
- Auto-fill abstract from PoC report data
- Keep the 4-reviewer loop using OpenCode's Task tool (sub-agents)
- Keep the HTML preview generation
- Keep Vale linting integration

### 6.2 Directory Structure

```
.opencode/skills/blog-create/
  SKILL.md                    # Adapted from ai-asset-registry
  assets/
    blog-template.html        # HTML preview template (copied from ai-asset-registry)
  references/
    scoring.md                # Scoring rules (copied from ai-asset-registry)
    reviewer-architect.md     # Structure reviewer (copied)
    reviewer-content.md       # Content reviewer (copied)
    reviewer-formatting.md    # Formatting reviewer (copied)
    reviewer-image.md         # Image reviewer (copied)
    html-preview-guide.md     # HTML conversion guide (copied)
```

### 6.3 PoC-Specific Adaptations

When invoked from `run-poc`, the blog-create skill receives context from the PoC state:
- Project name, repo URL, fork URL
- Components and their analysis
- PoC plan and scenarios
- Test results (pass/fail)
- Infrastructure deployed
- Routes and URLs

This replaces the qualifying phase -- the abstract is auto-generated from PoC results.

---

## 7. Container Image Design

### 7.1 Dockerfile

Extend the existing UBI9 image to include OpenCode:

```dockerfile
# Stage 1: Existing AutoPoC tooling
FROM registry.access.redhat.com/ubi9/python-312:latest AS tools

USER 0

# Install system tools (same as current Dockerfile)
RUN dnf install -y --nodocs git && dnf clean all

# Install kubectl
ARG KUBECTL_VERSION=v1.36.0
RUN curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    -o /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl

# Install oc (OpenShift CLI)
ARG OC_VERSION=4.21.11
RUN curl -fsSL "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/${OC_VERSION}/openshift-client-linux.tar.gz" \
    | tar xzf - -C /usr/local/bin oc && chmod +x /usr/local/bin/oc

# Install vale
ARG VALE_VERSION=3.14.2
RUN curl -fsSL "https://github.com/errata-ai/vale/releases/download/v${VALE_VERSION}/vale_${VALE_VERSION}_Linux_64-bit.tar.gz" \
    | tar xzf - -C /usr/local/bin vale && chmod +x /usr/local/bin/vale

# Install OpenCode
ARG OPENCODE_VERSION=latest
RUN curl -fsSL "https://github.com/anomalyco/opencode/releases/download/${OPENCODE_VERSION}/opencode_Linux_x86_64.tar.gz" \
    | tar xzf - -C /usr/local/bin opencode && chmod +x /usr/local/bin/opencode

# Install Python dependencies (for standalone scripts)
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock

# Copy project files
COPY src/ /opt/autopoc/src/
COPY data/ /opt/autopoc/data/
COPY .opencode/ /opt/autopoc/.opencode/
COPY opencode.json /opt/autopoc/opencode.json

# Setup workspace
RUN mkdir -p /workspace && chgrp -R 0 /workspace && chmod -R g=u /workspace
RUN chgrp -R 0 /opt/autopoc && chmod -R g=u /opt/autopoc

WORKDIR /opt/autopoc
USER 1001

ENV PYTHONPATH=/opt/autopoc/src
ENV AUTOPOC_DATA_DIR=/opt/autopoc/data
ENV AUTOPOC_WORK_DIR=/workspace

ENTRYPOINT ["opencode"]
```

### 7.2 OpenCode Configuration (`opencode.json`)

```jsonc
{
  "$schema": "https://opencode.ai/config.schema.json",
  "provider": {
    // LLM provider configured via env vars:
    // ANTHROPIC_API_KEY or VERTEX_PROJECT + VERTEX_LOCATION
  },
  "skills": {
    "run-poc": {
      "path": ".opencode/skills/run-poc/SKILL.md",
      "description": "Run a full PoC pipeline for a GitHub repository"
    },
    "run-sheet": {
      "path": ".opencode/skills/run-sheet/SKILL.md",
      "description": "Read PoC candidates from Google Sheet and run pipelines"
    },
    "blog-create": {
      "path": ".opencode/skills/blog-create/SKILL.md",
      "description": "Generate a developer blog post from PoC results"
    }
  }
}
```

---

## 8. Kubernetes Manifests

### 8.1 Job (ad-hoc single project)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: autopoc-${JOB_SUFFIX}
  namespace: autopoc
spec:
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      serviceAccountName: autopoc-runner
      containers:
        - name: autopoc
          image: quay.io/autopoc/autopoc-opencode:latest
          args:
            - "--skill"
            - "run-poc"
            - "--prompt"
            - "Run PoC for ${PROJECT_NAME} from ${REPO_URL}"
          env:
            # LLM provider
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: ANTHROPIC_API_KEY
            # ... (same env vars as current job.yaml)
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "4Gi"
              cpu: "2"
          volumeMounts:
            - name: workspace
              mountPath: /workspace
      volumes:
        - name: workspace
          emptyDir: {}
      restartPolicy: Never
  backoffLimit: 0
```

### 8.2 CronJob (scheduled sheet processing)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: autopoc-daily
  namespace: autopoc
spec:
  schedule: "0 0 * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: autopoc-runner
          containers:
            - name: autopoc
              image: quay.io/autopoc/autopoc-opencode:latest
              args:
                - "--skill"
                - "run-sheet"
                - "--prompt"
                - "Read candidates from Google Sheet and run PoCs for the top picks"
              env:
                # ... (same env vars as current cronjob.yaml)
              volumeMounts:
                - name: workspace
                  mountPath: /workspace
                - name: google-sa
                  mountPath: /etc/autopoc/google-sa
                  readOnly: true
          volumes:
            - name: workspace
              emptyDir: {}
            - name: google-sa
              secret:
                secretName: autopoc-google-sa
          restartPolicy: Never
```

---

## 9. Scripts

### 9.1 `scripts/run-autopoc.sh`

Updated to create a Job that runs OpenCode instead of the autopoc CLI:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="${1:?Usage: run-autopoc.sh <project-name> <repo-url>}"
REPO_URL="${2:?Usage: run-autopoc.sh <project-name> <repo-url>}"

NAMESPACE="${NAMESPACE:-autopoc}"
IMAGE="${IMAGE:-quay.io/autopoc/autopoc-opencode:latest}"

# Generate Job manifest and apply
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: autopoc-${PROJECT_NAME}-$(date +%s)
  namespace: ${NAMESPACE}
spec:
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      serviceAccountName: autopoc-runner
      containers:
        - name: autopoc
          image: ${IMAGE}
          args: ["--skill", "run-poc", "--prompt", "Run PoC for ${PROJECT_NAME} from ${REPO_URL}"]
          envFrom:
            - secretRef:
                name: autopoc-credentials
          resources:
            requests: { memory: "512Mi", cpu: "500m" }
            limits: { memory: "4Gi", cpu: "2" }
          volumeMounts:
            - { name: workspace, mountPath: /workspace }
      volumes:
        - { name: workspace, emptyDir: {} }
      restartPolicy: Never
  backoffLimit: 0
EOF

echo "Job created. Watch with: kubectl logs -f job/autopoc-${PROJECT_NAME}-... -n ${NAMESPACE}"
```

---

## 10. Standalone Python Scripts

### 10.1 Script Interface Design

Each retained Python module gets a `__main__.py` or CLI entry point:

| Script | Command | Input | Output |
|--------|---------|-------|--------|
| `repo_digest` | `python -m autopoc.tools.repo_digest <repo_path>` | Path to cloned repo | Markdown digest to stdout |
| `gitlab_client` | `python -m autopoc.tools.gitlab_client <action> [args]` | action: create-project, get-project, project-exists | JSON to stdout |
| `github_client` | `python -m autopoc.tools.github_client <action> [args]` | action: fork, get-fork, wait-for-fork | JSON to stdout |
| `quay_client` | `python -m autopoc.tools.quay_client <action> [args]` | action: ensure-repo, repo-exists | JSON to stdout |
| `strategy` | `python -m autopoc.tools.strategy <action>` | action: load, load-baseline, dimensions | JSON/YAML to stdout |
| `llm_proxy` | `python -m autopoc.tools.llm_proxy <env_vars_json>` | JSON of env vars | Resolved env vars JSON to stdout |
| `sheet_reader` | `python -m autopoc.tools.sheet_reader [args]` | --sheet-id, --credentials | JSON array of candidates to stdout |
| `sheet_writer` | `python -m autopoc.tools.sheet_writer [args]` | --sheet-id, --credentials, --results | Status message |
| `vale_runner` | `python -m autopoc.tools.vale_runner <file>` | Path to markdown file | JSON findings to stdout |
| `artifacts` | `python -m autopoc.tools.artifacts <clone_path> <files...>` | Clone path + file list | Commits to autopoc-artifacts branch |

### 10.2 Implementation Pattern

```python
# src/autopoc/tools/repo_digest.py
# ... existing build_repo_digest function ...

if __name__ == "__main__":
    import sys
    import json
    
    repo_path = sys.argv[1]
    digest = build_repo_digest(repo_path)
    print(digest)
```

For more complex tools:

```python
# src/autopoc/tools/gitlab_client.py
# ... existing GitLabClient class ...

def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create-project", "get-project", "project-exists"])
    parser.add_argument("name")
    args = parser.parse_args()
    
    client = GitLabClient.from_env()  # reads GITLAB_URL, GITLAB_TOKEN, GITLAB_GROUP from env
    
    if args.action == "create-project":
        result = client.create_project(args.name)
        print(json.dumps(result))
    elif args.action == "get-project":
        result = client.get_project(args.name)
        print(json.dumps(result))
    elif args.action == "project-exists":
        exists = client.project_exists(args.name)
        print(json.dumps({"exists": exists}))

if __name__ == "__main__":
    main()
```

---

## 11. Test Strategy

### 11.1 What Changes

**Removed:**
- All graph tests (`test_graph_poc.py`, `test_graph_partial.py`, `test_retry_loop.py`) -- no more LangGraph
- All agent tests (`test_intake.py`, `test_containerize.py`, etc.) -- no more agent functions
- LLM-related tests (`test_llm_fallback.py`) -- OpenCode handles LLM
- CLI tests (`test_cli_logging.py`, `test_cli_run_sheet.py`) -- no more Typer CLI
- Context management tests -- OpenCode handles context

**Retained and adapted:**
- Tool tests (`test_file_tools.py`, `test_git_tools.py`, etc.) -- still testing the same functions
- API client tests (`test_gitlab_tools.py`, `test_github_tools.py`, `test_quay_tools.py`) -- still testing API clients
- Strategy/config tests (`test_strategy.py`, `test_config.py`) -- still testing config
- Sheet tests (`test_sheet.py`, `test_prefilter.py`) -- still testing sheet logic
- Containerize fixup tests (`test_containerize_extraction.py`) -- if fixup rules are in skill, these become reference validation tests

**New tests:**
- **Standalone script tests**: Test CLI wrappers for each Python script (`python -m autopoc.tools.repo_digest`)
- **State file tests**: Test YAML state file read/write/update operations
- **Skill validation tests**: Validate that skill files are well-formed, reference existing files, and contain required sections
- **Integration tests**: Test full phase sequences using OpenCode in a test harness

### 11.2 Test Pyramid

```
                    /\
                   /  \     E2E: Full pipeline in kind cluster
                  /    \    (rare, expensive, CI-only)
                 /------\
                /        \   Integration: Phase sequences
               /          \  (OpenCode + mock infra)
              /------------\
             /              \  Unit: Standalone scripts, state file,
            /                \ API clients, tool functions
           /------------------\
```

---

## 12. Migration Path

### Phase 1: Foundation (skill files + scripts)
1. Create `.opencode/skills/run-poc/SKILL.md` and references
2. Create `.opencode/skills/run-sheet/SKILL.md` and references
3. Copy and adapt `.opencode/skills/blog-create/` from ai-asset-registry
4. Add CLI wrappers to retained Python tools
5. Create `opencode.json` configuration
6. Write `poc-state.yaml` schema documentation

### Phase 2: Container image
1. Update `Dockerfile` to include OpenCode binary
2. Update Makefile targets for new image
3. Test image build and basic OpenCode invocation

### Phase 3: K8s manifests + scripts
1. Update `deploy/base/job.yaml` for OpenCode
2. Update `deploy/base/cronjob.yaml` for OpenCode
3. Update `scripts/run-autopoc.sh` for OpenCode
4. Test Job creation and pod lifecycle

### Phase 4: Cleanup
1. Remove LangGraph dependencies from `pyproject.toml`
2. Remove agent files, graph.py, state.py, cli.py
3. Remove obsolete tests
4. Update `requirements.lock`
5. Write new tests for scripts and skill validation

### Phase 5: Validation
1. Run full E2E pipeline with OpenCode
2. Validate retry loops work via skill instructions
3. Validate sheet processing works
4. Validate blog generation works

---

## 13. Dependency Changes

### Removed
- `langgraph` (and `langgraph-checkpoint-sqlite`)
- `langchain`, `langchain-core`, `langchain-anthropic`, `langchain-openai`, `langchain-google-vertexai`
- `typer`, `rich` (CLI framework)

### Retained
- `httpx` (API clients)
- `pydantic`, `pydantic-settings` (config validation, kept lightweight)
- `PyYAML` (state file)
- `Jinja2` (templates, if scripts use them)
- `google-api-python-client` (sheet integration)

### Added
- None (OpenCode is a system binary, not a Python dependency)

---

## 14. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenCode context window overflow during long pipelines | Medium | Skill instructs OpenCode to use state file as memory, reference files lazily |
| Retry loops may not work as reliably with LLM-driven decisions | Medium | State file tracks exact retry counts, skill instructions are explicit about decision tree |
| Dockerfile fixup rules in skill instructions may be missed by LLM | High | Encode rules as a checklist in `references/ubi-dockerfile-rules.md` with concrete examples |
| bash commands may fail silently | Medium | Skill instructs OpenCode to always check exit codes and capture stderr |
| Pod resource limits may not be enough for OpenCode | Low | Start with 4Gi RAM, monitor and adjust |
| OpenCode binary size adds to image | Low | Go binaries are ~50MB, acceptable |
| Loss of checkpointing/resume capability | Medium | State file provides coarse checkpointing; full resume requires re-running from last completed phase |

---

## 15. Open Questions

1. **OpenCode CLI invocation**: What is the exact CLI syntax for running OpenCode with a skill in non-interactive mode? Need to verify: `opencode --skill run-poc --prompt "..."` or similar.

2. **OpenCode sub-agent for blog reviewers**: The blog-create skill uses 4 parallel sub-agent reviewers. Does OpenCode support spawning sub-agents from within a skill? (The Task tool suggests yes.)

3. **OpenCode in headless/non-interactive mode**: When running in a pod, OpenCode needs to run without a TTY. Need to verify headless mode support.

4. **OpenCode version pinning**: How to pin the OpenCode binary version in the Dockerfile for reproducible builds?

5. **OpenCode config for LLM provider**: How does OpenCode configure its LLM provider via env vars? Need to check if `ANTHROPIC_API_KEY` is auto-detected or requires explicit config in `opencode.json`.
