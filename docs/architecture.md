# Architecture

AutoPoC is an OpenCode agent-based system that follows detailed skill instructions to execute proof-of-concept deployments. The system uses a single OpenCode agent with skill-driven architecture rather than multiple specialized agents.

## Pipeline Overview

```
intake -> evaluate -> fork -> poc_plan -> containerize -> build -> deploy -> apply -> poc_execute -> poc_report -> blog
```

The pipeline consists of 11 sequential phases executed by OpenCode following skill instructions, with built-in retry logic for build and deployment failures.

## State Management

OpenCode maintains progressive state in YAML files rather than shared memory. The primary state file is `poc-state.yaml` which tracks progress through each phase.

Key state fields:

| Field | Set by | Description |
|-------|--------|-------------|
| `project_name` | intake | User-provided project name |
| `source_repo_url` | intake | GitHub URL |
| `current_phase` | each phase | Tracks current pipeline position |
| `repo_digest` | intake | Procedural text summary of the repo (~10KB) |
| `components` | intake | Detected components (name, language, port, etc.) |
| `evaluation_score` | evaluate | Strategic fitness score (0-10) |
| `evaluation_reasons` | evaluate | Detailed scoring rationale |
| `forked_repo_url` | fork | GitLab/GitHub fork URL |
| `poc_type` | poc_plan | Project classification (model-serving, rag, llm-app, etc.) |
| `poc_components` | poc_plan | Which components are relevant for the PoC |
| `poc_infrastructure` | poc_plan | Infrastructure needs (GPU, vector DB, PVC, deployment model) |
| `poc_scenarios` | poc_plan | Test scenarios to run |
| `built_images` | build | Pushed image references |
| `deployed_resources` | apply | Created K8s resources |
| `routes` | apply | Accessible URLs |
| `poc_results` | poc_execute | Test execution results (pass/fail per scenario) |
| `build_retries` | build | Number of build retry attempts |
| `deploy_retries` | deploy | Number of deployment retry attempts |

## Skills and Phases in Detail

### run-poc Skill

The main skill provides OpenCode with detailed instructions for executing an 11-phase PoC pipeline. Each phase includes:

- **Detailed instructions** for what OpenCode should accomplish
- **Expected inputs** and **outputs** for the phase
- **Error handling** guidance and retry logic
- **State management** requirements for YAML updates

### Phase 1: Intake

**Purpose:** Clone repository and build comprehensive analysis

**Process:**
1. Clone the GitHub repository to local working directory
2. Run `python -m autopoc.tools.repo_digest` to generate structural summary
3. Use OpenCode's analysis capabilities to identify components, languages, and build systems
4. Update `poc-state.yaml` with repository analysis results

**Key outputs:** `repo_digest`, `components`, `technology_stack`

### Phase 2: Evaluate  

**Purpose:** Strategic evaluation of project fitness for OpenShift AI

**Process:**
1. Use strategic evaluation framework from `data/strategies/` YAML files
2. Score project on multiple dimensions (0-10 scale)
3. Generate detailed rationale for scoring decisions
4. Store evaluation results for later PoC report inclusion

**Key outputs:** `evaluation_score`, `evaluation_reasons`, `evaluation_summary`

### Phase 3: Fork

**Purpose:** Create tracked copy of repository on GitLab/GitHub

**Process:**
1. Use GitLab or GitHub API to fork/create project copy
2. Set up git remotes and push source code
3. Store forked repository URL for build context
4. Ensure proper access permissions for CI/CD

**Key outputs:** `forked_repo_url`, `fork_api_details`

### Phase 4: PoC Plan

**Purpose:** Generate strategic PoC plan with infrastructure requirements

**Process:**
1. Analyze repository digest and components for project classification
2. Determine deployment model (service, job, cli-only)
3. Identify infrastructure needs (GPU, storage, vector DB)
4. Create comprehensive test scenarios for validation
5. Generate detailed PoC plan markdown document

**Key outputs:** `poc_type`, `poc_infrastructure`, `poc_scenarios`, `poc_components`

### Phase 5: Containerize

**Purpose:** Generate UBI-based Dockerfiles for OpenShift compatibility

**Process:**
1. Analyze each PoC-relevant component for language and framework
2. Generate appropriate UBI-based Dockerfile using templates
3. Handle Python, Node.js, Go, Java with OpenShift-compatible settings
4. Ensure non-root user and proper security contexts
5. Commit Dockerfiles to forked repository

**Key outputs:** `dockerfiles_created`, `containerization_strategy`

**Retry logic:** On build failures, receives error messages and improves Dockerfiles

### Phase 6: Build

**Purpose:** Build and push container images to registry

**Process:**
1. Run `podman build` for each component with Dockerfile
2. Push successful builds to Quay.io registry
3. Track build logs and handle failures appropriately
4. Classify failures as permanent vs. retriable

**Key outputs:** `built_images`, `build_logs`, `build_retries`

**Retry logic:** Retriable failures loop back to containerize phase with error context

### Phase 7: Deploy

**Purpose:** Generate Kubernetes deployment manifests

**Process:**
1. Create namespace, deployment, service, and route manifests
2. Configure based on PoC plan infrastructure requirements
3. Handle GPU requests, PVC mounts, and service exposure
4. Validate manifest syntax and OpenShift compatibility

**Key outputs:** `k8s_manifests`, `deployment_strategy`

### Phase 8: Apply

**Purpose:** Deploy manifests to Kubernetes cluster

**Process:**
1. Apply manifests in dependency order (namespace → PVC → deployment → service)
2. Wait for pod rollouts and readiness
3. Extract accessible routes and service endpoints
4. Verify deployment health and capture logs

**Key outputs:** `deployed_resources`, `routes`, `deploy_retries`

**Retry logic:** Failures loop back to deploy phase for manifest fixes

### Phase 9: PoC Execute

**Purpose:** Run comprehensive test scenarios against deployed application

**Process:**
1. Execute test scenarios defined in PoC plan
2. Run HTTP requests, CLI commands, or exec-based tests
3. Capture test outputs and measure performance
4. Generate pass/fail results for each scenario

**Key outputs:** `poc_results`, `test_logs`, `performance_metrics`

### Phase 10: PoC Report

**Purpose:** Generate comprehensive PoC report with results

**Process:**
1. Aggregate all pipeline data and test results
2. Create structured markdown report with findings
3. Include deployment details, test outcomes, and recommendations
4. Store report for stakeholder review

**Key outputs:** `poc_report_path`, `report_summary`

### Phase 11: Blog (Optional)

**Purpose:** Generate developer blog post about the PoC

**Process:**
1. Transform PoC results into engaging blog content
2. Use multi-reviewer pipeline for quality improvement
3. Create developer-focused narrative about the experience
4. Include technical insights and lessons learned

**Key outputs:** `blog_post`, `publication_ready_content`

## Skill-Driven Execution

OpenCode follows detailed skill instructions that include:

### Error Handling and Retry Logic

Each phase includes comprehensive error handling instructions:

- **Build failures:** Retry up to 3 times, with Dockerfile improvements based on error analysis
- **Deploy failures:** Retry up to 2 times, with manifest corrections
- **Apply failures:** Retry with corrected resource definitions
- **State tracking:** All retry counts and error details preserved in YAML state

### Progressive State Management

OpenCode updates the `poc-state.yaml` file after each phase completion:

```yaml
project_name: example-project
source_repo_url: https://github.com/org/repo
current_phase: containerize
build_retries: 1
components:
  - name: api-server
    language: python
    port: 8000
```

### Working Directory Structure

All operations occur under `/tmp/autopoc/` with organized subdirectories:

```
/tmp/autopoc/
├── repos/{project_name}/          # Cloned source repository
├── poc-state.yaml                # Progressive state file
├── poc-plan.md                   # Generated PoC strategy
├── dockerfiles/                  # Generated Dockerfiles
├── manifests/                    # Kubernetes manifests
├── test-scripts/                 # Generated test scenarios
└── reports/                      # PoC reports and logs
```

## Available Skills

The system provides three specialized skills:

### run-poc Skill
- **Location:** `.opencode/skills/run-poc/`
- **Purpose:** Complete 11-phase PoC pipeline execution
- **Features:** Progressive state tracking, retry logic, comprehensive error handling
- **Reference files:** 14+ supporting files with detailed instructions

### run-sheet Skill  
- **Location:** `.opencode/skills/run-sheet/`
- **Purpose:** Batch processing of PoC candidates from Google Sheets
- **Features:** Project evaluation, ranking, automated PoC execution

### blog-create Skill
- **Location:** `.opencode/skills/blog-create/`  
- **Purpose:** Generate developer blog posts from PoC results
- **Features:** Multi-reviewer pipeline, iterative content improvement

## Configuration

Configuration is handled through environment variables and Kubernetes secrets:

- **LLM Access:** Anthropic API key or Vertex AI project credentials
- **Container Registry:** Quay.io organization and token
- **Source Control:** GitLab/GitHub API access for forking
- **Cluster Access:** OpenShift/Kubernetes API credentials

See `deploy/secrets.yaml.example` for required environment variables.

## Templates

Jinja2 templates in `src/autopoc/templates/`:

- `Dockerfile.ubi.j2` -- Single-stage UBI Dockerfile
- `Dockerfile.ubi-builder.j2` -- Multi-stage builder pattern  
- `deployment.yaml.j2` -- Kubernetes Deployment
- `service.yaml.j2` -- Kubernetes Service

OpenCode uses these templates through bash commands and file operations during the containerize and deploy phases.
