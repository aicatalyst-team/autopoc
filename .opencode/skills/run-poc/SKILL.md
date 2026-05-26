---
name: run-poc
description: Run a full Proof-of-Concept pipeline for a GitHub repository on OpenShift AI. Clones the repo, analyzes it, forks to GitLab/GitHub, creates a PoC plan, containerizes with UBI images, builds and pushes to Quay, deploys to Kubernetes, runs validation tests, and generates a PoC report. Use this skill when asked to "run a PoC", "deploy a project to OpenShift", or given a GitHub URL to evaluate.
---

# run-poc

Automated Proof-of-Concept pipeline for deploying GitHub projects on OpenShift AI (Open Data Hub). Takes a repository URL and project name, then executes an 11-phase pipeline that ends with a validated deployment and comprehensive report.

## Before You Start

1. **Read the state file** if it exists: `$AUTOPOC_WORK_DIR/poc-state.yaml` (default work dir: `/workspace` in pods, `/tmp/autopoc` locally). If a state file exists with completed phases, resume from the last incomplete phase.

2. **Verify credentials** are available as environment variables:
   - LLM: `ANTHROPIC_API_KEY` or (`VERTEX_PROJECT` + `VERTEX_LOCATION`)
   - Fork target: `GITLAB_URL` + `GITLAB_TOKEN` + `GITLAB_GROUP` (or `GITHUB_TOKEN` + `GITHUB_ORG`)
   - Registry: `QUAY_ORG` + `QUAY_TOKEN` + `QUAY_USERNAME`
   - Cluster: `OPENSHIFT_TOKEN` + `OPENSHIFT_API_URL` (optional if in-cluster)

3. **Set up the work directory**:
   ```bash
   WORK_DIR="${AUTOPOC_WORK_DIR:-/tmp/autopoc}"
   mkdir -p "$WORK_DIR/repos"
   ```

## Pipeline Overview

```
Phase 1: Intake       -> Clone and analyze the repository          [MANDATORY]
Phase 2: Evaluate     -> Score RHOAI fitness                       [NON-BLOCKING]
Phase 3: Fork         -> Push to GitHub/GitLab                     [MANDATORY]
Phase 4: PoC Plan     -> Create plan with scenarios                [MANDATORY]
Phase 5: Containerize -> Write UBI-based Dockerfiles               [MANDATORY]
Phase 6: Build        -> Build + push images to Quay               [MANDATORY]
Phase 7: Deploy       -> Generate Kubernetes manifests             [MANDATORY]
Phase 8: Apply        -> kubectl apply + verify pods               [MANDATORY]
Phase 9: PoC Execute  -> Write and run test scripts                [MANDATORY]
Phase 10: PoC Report  -> Generate markdown report                  [NON-BLOCKING]
Phase 11: Blog Post   -> Generate developer blog (if tests pass)   [NON-BLOCKING]
```

### Phase Classification

**MANDATORY phases MUST succeed before continuing.** If a mandatory phase fails and retries are exhausted, **STOP the pipeline immediately.** Do NOT simulate, skip, or pretend the phase succeeded. Write the error to `poc-state.yaml` and exit.

**NON-BLOCKING phases** may fail without stopping the pipeline. If they fail, note the failure in state and continue to the next phase.

### Retry loops
- **Build retry**: Phase 6 fails -> back to Phase 5 (fix Dockerfile) -> Phase 6 again
- **Deploy retry**: Phase 8 fails with manifest issue -> back to Phase 7 (fix manifests) -> Phase 8
- **Container fix**: Phase 8 or 9 detects container issue -> back to Phase 5 (full rebuild cycle)

Read `references/retry-strategy.md` for the complete retry logic.

## State File

Maintain a progressive YAML state file at `$WORK_DIR/poc-state.yaml`. Read `references/state-schema.md` for the complete schema.

**Update the state file after completing each phase.** This is critical for:
- Tracking retry counters
- Providing context to later phases
- Enabling coarse resume if the pipeline is interrupted

## Phase 1: Intake

**Purpose**: Clone the repository and analyze its structure, components, and technologies.

### Steps

1. Clone the repository:
   ```bash
   git clone "$REPO_URL" "$WORK_DIR/repos/$PROJECT_NAME"
   ```

2. **Explore the repository** to understand its structure. Look at:
   - File tree (use `ls` or `find` to see the layout)
   - README.md (read it for project description, setup instructions, usage)
   - Build files (requirements.txt, package.json, go.mod, pyproject.toml, pom.xml, Cargo.toml)
   - Entry points (main.py, app.py, server.py, index.js, main.go, Dockerfile CMD/ENTRYPOINT)
   - Existing Dockerfiles and docker-compose.yml
   - CI/CD config (.github/workflows/, .gitlab-ci.yml)
   - Helm charts (Chart.yaml) or Kustomize (kustomization.yaml)

3. **Identify components**. Follow the analysis instructions in `references/intake.md`. For each component, determine:
   - name, language, build_system, entry_point, port
   - is_ml_workload (check for torch, tensorflow, transformers, etc.)
   - source_dir, existing_dockerfile

4. **Validate component paths**: For each component, verify `source_dir` exists on disk:
   ```bash
   ls "$WORK_DIR/repos/$PROJECT_NAME/$SOURCE_DIR"
   ```
   If it doesn't exist, look for the correct directory and adjust.

5. Update `poc-state.yaml` with the intake results.

### Exit condition
At least one component identified. If zero components found, set error and stop.

---

## Phase 2: Evaluate

**Purpose**: Score the project's fitness as an OpenShift AI proof-of-concept.

**This phase is NON-BLOCKING.** If evaluation fails, continue the pipeline.

### Steps

1. Read the strategy configuration files directly:
   - Active strategy: `cat $AUTOPOC_DATA_DIR/strategy_config.yaml` to get the strategy name
   - Strategy profile: `cat $AUTOPOC_DATA_DIR/strategies/<strategy-name>.yaml` for scoring dimensions
   - Strategy baseline: `cat $AUTOPOC_DATA_DIR/strategy-baseline.yaml` for strategy areas, capability labels, core products

2. **Score the project** against the strategy dimensions. Read the strategy YAML and the repo digest/summary from Phase 1. Score each dimension (audience_value, strategic_alignment, strategy_fit, platform_leverage, demo_potential) on a 0-20 scale.

3. Write the evaluation to `$WORK_DIR/repos/$PROJECT_NAME/.autopoc/rhoai-evaluation.md`.

4. Update `poc-state.yaml` with evaluation results.

### Exit condition
Evaluation written (or skipped on failure). Pipeline continues regardless.

---

## Phase 3: Fork

**Purpose**: Push the repository to the configured forge (GitHub or GitLab).

**This phase is MANDATORY.** If the fork fails, STOP the pipeline.

### Steps

1. Check fork target:
   ```bash
   echo "Fork target: ${AUTOPOC_FORK_TARGET:-github}"
   ```

2. **If `AUTOPOC_FORK_TARGET` is `github` (default):**

   Fork the repository using `gh`:
   ```bash
   gh repo fork "$OWNER/$REPO" --org "$GITHUB_ORG" --clone=false
   ```
   Then reconfigure remotes:
   ```bash
   cd "$WORK_DIR/repos/$PROJECT_NAME"
   git remote rename origin upstream 2>/dev/null || true
   git remote add origin "https://${GITHUB_TOKEN}@github.com/${GITHUB_ORG}/${REPO}.git"
   git push origin --all --force
   git push origin --tags --force
   ```

3. **If `AUTOPOC_FORK_TARGET` is `gitlab`:**

   Create the project on GitLab via REST API:
   ```bash
   GROUP_ID=$(curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
     "$GITLAB_URL/api/v4/groups?search=$GITLAB_GROUP" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

   curl -s -X POST -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
     "$GITLAB_URL/api/v4/projects" \
     -d "name=$PROJECT_NAME&namespace_id=$GROUP_ID&visibility=internal"

   cd "$WORK_DIR/repos/$PROJECT_NAME"
   git remote rename origin github 2>/dev/null || true
   git remote add origin "https://oauth2:${GITLAB_TOKEN}@${GITLAB_URL#https://}/${GITLAB_GROUP}/${PROJECT_NAME}.git" \
     2>/dev/null || git remote set-url origin "https://oauth2:${GITLAB_TOKEN}@${GITLAB_URL#https://}/${GITLAB_GROUP}/${PROJECT_NAME}.git"
   git push origin --all --force
   git push origin --tags --force
   ```

4. Update `poc-state.yaml` with fork URL and target.

### Exit condition
Fork URL recorded in state.

---

## Phase 4: PoC Plan

**Purpose**: Create a PoC plan with test scenarios and infrastructure requirements.

### Steps

1. Read the repo digest, component list, and evaluation from state.

2. **Generate the PoC plan** following the detailed instructions in `references/poc-plan.md`. This includes:
   - Classifying the project type (model-serving, rag, web-app, llm-app, etc.)
   - Determining infrastructure requirements (GPU, PVC, sidecars, resource profile)
   - Determining deployment model (Deployment vs Job vs CronJob)
   - Detecting LLM API dependencies
   - Defining 2-5 test scenarios

3. Write `poc-plan.md` to the repo root.

4. Optionally run Vale linting:
   ```bash
   vale --output=JSON "$WORK_DIR/repos/$PROJECT_NAME/poc-plan.md" 2>/dev/null || true
   ```

5. Commit to the `autopoc-artifacts` branch:
   ```bash
   cd "$WORK_DIR/repos/$PROJECT_NAME"
   CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
   git stash --quiet 2>/dev/null || true
   git checkout -B autopoc-artifacts
   git add poc-plan.md
   git commit -m "Add PoC plan" --allow-empty
   git push origin autopoc-artifacts --force
   git checkout "$CURRENT_BRANCH"
   git stash pop --quiet 2>/dev/null || true
   ```

6. Update `poc-state.yaml` with poc_type, scenarios, infrastructure, and poc_plan_path.

### Exit condition
PoC plan written with at least one scenario defined.

---

## Phase 5: Containerize

**Purpose**: Create UBI-based Dockerfiles for each PoC component.

### Steps

1. Read the PoC plan from state for infrastructure requirements and deployment model.

2. For each component that is part of the PoC (check `poc_plan.poc_components` if set, otherwise use all components):

   a. Read the component's existing Dockerfile (if any):
      ```bash
      cat "$WORK_DIR/repos/$PROJECT_NAME/$COMPONENT_DIR/Dockerfile" 2>/dev/null
      ```

   b. Read the component's dependency file (requirements.txt, package.json, etc.)

   c. **Generate `Dockerfile.ubi`** following the rules in `references/containerize.md` and `references/ubi-dockerfile-rules.md`. Key rules:
      - Use UBI base images (see mapping table in references)
      - Final USER must be 1001
      - Add `chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root` before final USER
      - Use dnf for full UBI images, microdnf for ubi-minimal
      - No privileged ports (80 -> 8080, 443 -> 8443)
      - Use CPU-only ML package variants unless GPU is needed
      - Set correct CMD/ENTRYPOINT based on deployment_model

   d. Write the Dockerfile:
      ```bash
      # Write Dockerfile.ubi to the component's source directory
      ```

   e. Create `.dockerignore` if it doesn't exist.

3. If this is a **retry entry** (build error or container fix from state), read the error context and fix the Dockerfile accordingly.

4. Commit and push:
   ```bash
   cd "$WORK_DIR/repos/$PROJECT_NAME"
   git add -A
   git commit -m "Add UBI Dockerfiles for PoC"
   git push origin HEAD --force
   ```

5. Update `poc-state.yaml` with Dockerfile paths.

### Exit condition
Every PoC component has a `Dockerfile.ubi` written and committed.

---

## Phase 6: Build

**Purpose**: Build container images and push to Quay registry.

### Build Strategy

Check the `BUILD_STRATEGY` environment variable to decide how to build:

- **`openshift`** (default in pods): Use `oc` to build on-cluster. The cluster does the build and pushes the image -- no local container runtime needed.
- **`podman`** (local/default if unset): Use `podman` to build locally, then push.

### Steps

1. (Optional) Quay repos are auto-created on push. If you want to pre-create:
   ```bash
   curl -s -X POST -H "Authorization: Bearer $QUAY_TOKEN" \
     "https://${QUAY_REGISTRY:-quay.io}/api/v1/repository" \
     -H "Content-Type: application/json" \
     -d '{"repository":"'"$PROJECT_NAME-$COMPONENT"'","namespace":"'"$QUAY_ORG"'","visibility":"public"}' \
     2>/dev/null || true
   ```

2. Determine the image tag:
   ```bash
   IMAGE_TAG="${QUAY_REGISTRY:-quay.io}/$QUAY_ORG/$PROJECT_NAME-$COMPONENT:latest"
   ```

3. **If `BUILD_STRATEGY` is `openshift`:**

   The builds namespace is derived from `OPENSHIFT_NAMESPACE_PREFIX` (defaults to `poc`):
   ```bash
   BUILDS_NS="${OPENSHIFT_NAMESPACE_PREFIX:-poc}-builds"
   ```

   a. Create the builds namespace and registry push secret:
      ```bash
      oc create namespace "$BUILDS_NS" --dry-run=client -o yaml | oc apply -f -

      oc create secret docker-registry autopoc-registry-push \
        --docker-server="${QUAY_REGISTRY:-quay.io}" \
        --docker-username="$QUAY_USERNAME" \
        --docker-password="$QUAY_TOKEN" \
        -n "$BUILDS_NS" --dry-run=client -o yaml | oc apply -f -
      ```

   b. Create a BuildConfig and start a binary build:
      ```bash
      # Create the BuildConfig (oc new-build creates it + an ImageStream)
      oc new-build --name="$PROJECT_NAME-$COMPONENT" \
        --binary --strategy=docker \
        --to-docker --to="$IMAGE_TAG" \
        --push-secret=autopoc-registry-push \
        -n "$BUILDS_NS" 2>&1 || true  # ignore "already exists" errors

      # Start binary build -- uploads local source, builds on cluster, pushes to registry
      oc start-build "$PROJECT_NAME-$COMPONENT" \
        --from-dir="$WORK_DIR/repos/$PROJECT_NAME/$COMPONENT_DIR" \
        --follow --wait \
        -n "$BUILDS_NS"
      ```

   c. Push is automatic -- the BuildConfig pushes to the registry as part of the build.

4. **If `BUILD_STRATEGY` is `podman` (or unset):**

   a. Log in to the registry:
      ```bash
      echo "$QUAY_TOKEN" | podman login "${QUAY_REGISTRY:-quay.io}" -u "$QUAY_USERNAME" --password-stdin
      ```

   b. Build the image:
      ```bash
      podman build -t "$IMAGE_TAG" -f Dockerfile.ubi "$WORK_DIR/repos/$PROJECT_NAME/$COMPONENT_DIR"
      ```

   c. Push the image:
      ```bash
      podman push "$IMAGE_TAG"
      ```

5. **On build failure:**
   - Read the error output
   - Check if it's a **permanent error** (authentication failure, network unreachable) -> FAIL
   - Check if retries are available (read `retries.build_retries` from state < `retries.max_build_retries`)
   - If retriable: increment `retries.build_retries`, record the error, go back to Phase 5
   - If retries exhausted: FAIL

6. Update `poc-state.yaml` with built images.

### Exit condition
All component images built and pushed successfully.

---

## Phase 7: Deploy

**Purpose**: Generate Kubernetes manifests for the deployment.

### Steps

1. Read built images, PoC plan infrastructure, and scenarios from state.

2. **Generate Kubernetes manifests** following `references/deploy.md`. Create files in `$WORK_DIR/repos/$PROJECT_NAME/kubernetes/`:
   - `namespace.yaml` (always first)
   - For each component based on deployment_model:
     - `deployment` + `listens_on_port`: Deployment + Service
     - `deployment` + no port: Deployment only (no Service)
     - `job`: One Job per test scenario
   - `secret.yaml` for sensitive env vars (API keys, tokens)
   - `pvc.yaml` if persistent storage needed

3. Handle **LLM proxy** if `infrastructure.needs_llm_api` is true:
   ```bash
   python -m autopoc.cli_tools llm-proxy '{"OPENAI_API_KEY": "required", "OPENAI_BASE_URL": ""}'
   ```
   Use the resolved env vars in the manifests.

4. Commit and push manifests:
   ```bash
   cd "$WORK_DIR/repos/$PROJECT_NAME"
   git add kubernetes/
   git commit -m "Add Kubernetes manifests"
   git push origin HEAD --force
   ```

5. If this is a **retry entry** (apply error from state), read the previous error and fix the manifests accordingly.

6. Update `poc-state.yaml` with manifests directory path.

### Exit condition
All manifest files written and committed.

---

## Phase 8: Apply

**Purpose**: Apply manifests to the Kubernetes cluster and verify deployment.

### Steps

1. Create the namespace:
   ```bash
   kubectl create namespace "poc-$PROJECT_NAME" --dry-run=client -o yaml | kubectl apply -f -
   ```

2. Apply manifests in order:
   ```bash
   # Namespace first
   kubectl apply -f "$WORK_DIR/repos/$PROJECT_NAME/kubernetes/namespace.yaml"
   # Then PVCs, secrets, deployments, services
   kubectl apply -f "$WORK_DIR/repos/$PROJECT_NAME/kubernetes/" -n "poc-$PROJECT_NAME"
   ```

3. Wait for rollout:
   ```bash
   # For Deployments
   kubectl rollout status deployment/$COMPONENT -n "poc-$PROJECT_NAME" --timeout=300s
   # For Jobs
   kubectl wait --for=condition=complete job/$JOB_NAME -n "poc-$PROJECT_NAME" --timeout=120s
   ```

4. Verify pods are healthy:
   ```bash
   kubectl get pods -n "poc-$PROJECT_NAME"
   ```
   Wait 15 seconds, then check again for CrashLoopBackOff, ImagePullBackOff, etc.

5. Get service URLs:
   ```bash
   kubectl get svc -n "poc-$PROJECT_NAME" -o json
   ```

6. **On failure:** Classify the error per `references/error-triage.md`:
   - RBAC forbidden -> fix-manifest (back to Phase 7)
   - Namespace not found -> fix-manifest (back to Phase 7)
   - CrashLoopBackOff -> fix-dockerfile (back to Phase 5)
   - ImagePullBackOff -> fix-dockerfile (back to Phase 5)
   - Command not found in logs -> fix-dockerfile (back to Phase 5)
   - Other -> analyze logs, classify, route accordingly

   Check retry counters per `references/retry-strategy.md`.

7. Update `poc-state.yaml` with deployed resources, routes, and any errors.

### Exit condition
All pods healthy and service URLs recorded.

---

## Phase 9: PoC Execute

**Purpose**: Generate and run test scripts to validate the deployment.

### Steps

1. Read scenarios and routes from state.

2. **Write a Python test script** (`poc_test.py`) following `references/poc-execute.md`:
   - Use only Python stdlib + `urllib.request`
   - Implement each scenario from the PoC plan
   - Include retry logic (services may take time to start)
   - Output structured JSON results to stdout

3. Execute the test script:
   ```bash
   cd "$WORK_DIR/repos/$PROJECT_NAME"
   python poc_test.py "$SERVICE_URL" 2>&1
   ```

4. Parse the JSON results from stdout.

5. If tests fail, debug with kubectl:
   ```bash
   kubectl get pods -n "poc-$PROJECT_NAME"
   kubectl logs deployment/$COMPONENT -n "poc-$PROJECT_NAME" --tail=50
   ```

6. **Detect container-level issues** in test failures:
   - "command not found" -> container fix (back to Phase 5)
   - "ModuleNotFoundError" -> container fix (back to Phase 5)
   - "CrashLoopBackOff" -> container fix (back to Phase 5)
   - "exec format error" -> container fix (back to Phase 5)
   Check `retries.container_fix_retries` < `retries.max_container_fix_retries`.

7. Commit test artifacts to the `autopoc-artifacts` branch:
   ```bash
   cd "$WORK_DIR/repos/$PROJECT_NAME"
   CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
   git stash --quiet 2>/dev/null || true
   git checkout -B autopoc-artifacts
   git add poc_test.py
   git commit -m "Add PoC test script" --allow-empty
   git push origin autopoc-artifacts --force
   git checkout "$CURRENT_BRANCH"
   git stash pop --quiet 2>/dev/null || true
   ```

8. Update `poc-state.yaml` with test results.

### Exit condition
Test results recorded in state (pass or fail).

---

## Phase 10: PoC Report

**Purpose**: Generate a comprehensive markdown report summarizing the entire pipeline run.

### Steps

1. Read all state data (all phases).

2. **Generate the report** following `references/poc-report.md`. Include:
   - Executive summary
   - Project analysis with component table
   - PoC objectives
   - Pipeline execution summary (each phase)
   - Test results table
   - Infrastructure deployed
   - Recommendations
   - ODH/OpenShift AI considerations
   - Appendix with links to artifacts

3. Write `poc-report.md`:
   ```bash
   # Write report to repo
   ```

4. Run Vale linting (optional):
   ```bash
   vale --output=JSON "$WORK_DIR/repos/$PROJECT_NAME/poc-report.md" 2>/dev/null || true
   ```

5. Commit to the `autopoc-artifacts` branch:
   ```bash
   cd "$WORK_DIR/repos/$PROJECT_NAME"
   CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
   git stash --quiet 2>/dev/null || true
   git checkout -B autopoc-artifacts
   git add poc-report.md
   git commit -m "Add PoC report" --allow-empty
   git push origin autopoc-artifacts --force
   git checkout "$CURRENT_BRANCH"
   git stash pop --quiet 2>/dev/null || true
   ```

6. Update `poc-state.yaml` with report path.

### Exit condition
Report written and committed.

---

## Phase 11: Blog Post (Conditional)

**Purpose**: Generate a developer blog post about the PoC deployment.

**Only execute this phase if a majority of test scenarios passed.**

### Steps

1. Count pass/fail from `poc_execute.results` in state.
2. If majority passed: invoke the `blog-create` skill with the PoC context.
3. The blog-create skill handles the full generation pipeline (draft, review loop, finalize).

### Exit condition
Blog post written (or phase skipped if tests didn't pass).

---

## Error Handling

**CRITICAL: Never simulate, fake, or pretend a failed phase succeeded.**

If a MANDATORY phase fails:
1. Record the error in `poc-state.yaml` (errors array + phase status = "failed")
2. **STOP the pipeline immediately.** Do not proceed to the next phase.
3. Report what failed and why in your final output.

If a NON-BLOCKING phase fails (Evaluate, PoC Report, Blog Post):
1. Record the failure in state
2. Continue to the next phase

### Phase classification reminder

| Phase | Classification |
|-------|---------------|
| 1. Intake | MANDATORY |
| 2. Evaluate | NON-BLOCKING |
| 3. Fork | MANDATORY |
| 4. PoC Plan | MANDATORY |
| 5. Containerize | MANDATORY |
| 6. Build | MANDATORY |
| 7. Deploy | MANDATORY |
| 8. Apply | MANDATORY |
| 9. PoC Execute | MANDATORY |
| 10. PoC Report | NON-BLOCKING |
| 11. Blog Post | NON-BLOCKING |

### General rules

- Always check exit codes after bash commands.
- Capture stderr alongside stdout for debugging: `command 2>&1`
- For kubectl commands, always specify the namespace explicitly.
- If a command times out, record the timeout in the error and decide whether to retry.

## Important Reminders

- **Update poc-state.yaml after every phase.** This is your persistent memory.
- **Always use absolute paths** for file operations and kubectl commands.
- **Never leave USER root** as the final Dockerfile directive.
- **Check retry counters before looping back** to a previous phase.
- **Git operations**: always push with `--force` to handle retry scenarios where commits are rewritten.
- **Never hallucinate success.** If a build fails, it failed. If an image doesn't exist, don't deploy it. If a pod is crashing, don't pretend tests passed.
