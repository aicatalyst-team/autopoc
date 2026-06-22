# State File Schema (`poc-state.yaml`)

The state file is a progressive YAML document that grows as pipeline phases complete. It serves as persistent memory across phases and enables coarse-grained resume.

## Location

```
$AUTOPOC_WORK_DIR/poc-state.yaml
```

Default: `/workspace/poc-state.yaml` (in pods) or `/tmp/autopoc/poc-state.yaml` (local).

## Schema

```yaml
# Core project identity
project:
  name: ""                    # Project name (from input)
  source_repo_url: ""         # Original GitHub URL
  started_at: ""              # ISO 8601 timestamp
  current_phase: ""           # Last completed or in-progress phase name

# Phase 1: Intake
intake:
  status: "pending"           # pending | in_progress | completed | failed
  local_clone_path: ""        # Absolute path to cloned repo
  repo_digest_path: ""        # Path to generated repo digest
  repo_summary: ""            # 2-3 sentence project summary
  components:                 # Array of detected components
    - name: ""                # Component name
      language: ""            # Primary language (python, javascript, go, java, rust)
      build_system: ""        # Build tool (pip, npm, maven, cargo, go)
      entry_point: ""         # Main file or command
      port: null              # Network port (null if CLI/library)
      source_dir: "."         # Relative dir within repo
      existing_dockerfile: null  # Path to existing Dockerfile or null
      is_ml_workload: false   # Has ML/AI dependencies
  has_helm_chart: false
  has_kustomize: false
  has_compose: false
  existing_ci_cd: null        # github-actions | gitlab-ci | jenkins | null

# Phase 2: Evaluate (non-blocking)
evaluate:
  status: "pending"
  total_score: 0
  max_possible_score: 100
  relationship: ""            # direct | adjacent | ecosystem | distant
  strategy_areas: []          # e.g., ["model-inference", "agentic-ai"]
  capability_labels: []
  rationale: ""
  strengths: []
  risks: []
  evaluation_path: ""         # Path to rhoai-evaluation.md

# Phase 3: Fork
fork:
  status: "pending"
  fork_repo_url: ""           # URL of the fork
  fork_target: ""             # gitlab | github
  gitlab_repo_url: ""         # GitLab-specific URL (if applicable)

# Phase 4: PoC Plan
poc_plan:
  status: "pending"
  poc_type: ""                # model-serving | rag | web-app | llm-app | etc.
  poc_plan_path: ""           # Path to poc-plan.md
  poc_components: []          # Component names relevant for PoC
  scenarios:                  # Test scenarios
    - name: ""
      description: ""
      type: ""                # http | cli | exec
      endpoint: null          # HTTP endpoint path (for http type)
      input_data: null        # CLI command or HTTP body
      expected_behavior: ""
      timeout_seconds: 30
  infrastructure:
    needs_inference_server: false
    inference_server_type: null
    needs_vector_db: false
    vector_db_type: null
    needs_embedding_model: false
    embedding_model: null
    needs_gpu: false
    gpu_type: null
    needs_pvc: false
    pvc_size: null
    sidecar_containers: []
    extra_env_vars: {}
    resource_profile: "small"  # small | medium | large | gpu
    deployment_model: "deployment"  # deployment | job | cronjob
    listens_on_port: true
    long_running: true
    entrypoint_suggestion: null
    test_strategy: "http"      # http | cli | exec
    needs_llm_api: false
    llm_env_pattern: null      # openai | anthropic | langchain | custom | null

# Phase 5: Containerize
containerize:
  status: "pending"
  dockerfiles:                # One per component
    - component: ""           # Component name
      path: ""                # Path to Dockerfile.ubi
      base_image: ""          # UBI base image used

# Phase 6: Build
build:
  status: "pending"
  images:                     # Built container images
    - component: ""
      image: ""               # Full image reference (quay.io/org/name:tag)

# Phase 7: Deploy
deploy:
  status: "pending"
  manifests_dir: ""           # Path to kubernetes/ directory

# Phase 8: Apply
apply:
  status: "pending"
  namespace: ""               # K8s namespace (poc-<project_name>)
  deployed_resources: []      # e.g., ["deployment/api", "service/api"]
  routes: []                  # Service URLs
    # - name: ""
    #   url: ""

# Phase 9: PoC Execute
poc_execute:
  status: "pending"
  test_script_path: ""        # Path to poc_test.py
  results:                    # Test results
    - scenario_name: ""
      status: ""              # pass | fail | error | skip
      output: ""
      error_message: null
      duration_seconds: 0

# Phase 10: PoC Report
poc_report:
  status: "pending"
  report_path: ""             # Path to poc-report.md

# Phase 11: Blog Post (conditional)
blog_post:
  status: "pending"           # pending | completed | skipped
  blog_path: ""
  seo_path: ""
  preview_path: ""

# Demo video recording (populated by record-demo skill, not part of the
# standard run-poc pipeline — included here for state file completeness)
demo_video:
  status: "pending"           # pending | in_progress | completed | failed | skipped
  script_path: ""             # Path to generated Playwright script (record.py)
  video_path: ""              # Local path to recorded video file
  drive_url: ""               # Google Drive URL after upload
  duration_seconds: 0         # Video duration in seconds
  resolution: "1920x1080"     # Video resolution
  format: "webm"              # Video container format

# Retry tracking
retries:
  build_retries: 0
  max_build_retries: 3
  deploy_retries: 0
  max_deploy_retries: 3
  container_fix_retries: 0
  max_container_fix_retries: 2
  experiment_tag_counter: 0

# Error history
errors: []
  # - phase: ""
  #   message: ""
  #   action: ""              # retry | fix-dockerfile | fix-manifest | fail
  #   timestamp: ""
```

## Update Rules

1. **Set status to "in_progress"** when starting a phase.
2. **Set status to "completed"** when a phase succeeds.
3. **Set status to "failed"** when a phase fails unrecoverably.
4. **Update `project.current_phase`** to the current phase name.
5. **Append errors** to the `errors` array (don't overwrite previous errors).
6. **Increment retry counters** before looping back to a previous phase.
7. **Reset inner retry counters** when entering the container fix outer loop:
   - When going back to Phase 5 from Phase 8 or 9: reset `build_retries` and `deploy_retries` to 0.

## Resume Logic

When resuming from a state file:
1. Find the last phase with `status: "completed"`.
2. Start execution from the next phase.
3. If a phase has `status: "in_progress"`, re-run it from the beginning.
4. If a phase has `status: "failed"`, check if retries are available and route accordingly.
