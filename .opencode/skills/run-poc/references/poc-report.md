# PoC Report Generation Instructions

Generate a comprehensive markdown PoC report summarizing the entire pipeline run.

## Report Structure

The report MUST include ALL of these sections:

### 1. Executive Summary
2-4 sentences covering:
- What project was evaluated
- PoC objectives
- Whether it succeeded or failed
- Key highlights or concerns

### 2. Project Analysis
- Repository URL and project name
- What the project does (repo_summary from state)
- Components table:

| Component | Language | Build System | ML Workload | Port |
|---|---|---|---|---|
| {name} | {language} | {build_system} | {is_ml_workload} | {port} |

- Project classification (poc_type)
- Technologies and frameworks

### 3. PoC Objectives
From the PoC plan:
- What we set out to prove
- Why relevant to OpenShift AI
- Infrastructure requirements identified

### 4. Pipeline Execution
Summary of each pipeline phase:
- **Intake**: What was discovered
- **Evaluate**: RHOAI fitness score
- **Fork**: Fork URL
- **PoC Plan**: Type, scenarios, infrastructure
- **Containerize**: Dockerfiles generated
- **Build**: Images built and pushed (with full image refs)
- **Deploy**: K8s resources created
- **Apply**: Routes/URLs
- **PoC Execute**: Test script and results

### 5. Test Results

| Scenario | Status | Duration | Details |
|---|---|---|---|
| {name} | PASS/FAIL/ERROR | {seconds}s | {brief detail} |

For failed scenarios: what went wrong, error messages, fix suggestions.

### 6. Infrastructure Deployed
- Kubernetes namespace
- Container images (with tags)
- K8s resources created
- Service URLs/routes
- Resource allocations
- Sidecars or PVCs

### 7. Recommendations
- Production readiness assessment
- Performance observations
- Security considerations
- Scalability notes
- Concrete next steps

### 8. Open Data Hub / OpenShift AI Considerations
- Relevant ODH components (ModelMesh, KServe, Data Science Pipelines, etc.)
- Migration path from vanilla K8s to ODH-managed deployment
- Recommendations for ODH-specific features

### 9. Appendix
- Links to artifacts (poc-plan.md, poc_test.py, Dockerfiles, manifests)
- Build/deploy errors encountered
- Retry attempts

## Mermaid Diagrams

Include inline Mermaid diagrams where they aid understanding. Good candidates:

- **Section 4 (Pipeline Execution)**: A flowchart showing the phases that ran and their pass/fail status
- **Section 6 (Infrastructure Deployed)**: A diagram showing the deployment topology (namespace, pods, services, PVCs, routes)
- **Section 2 (Project Analysis)**: A component architecture diagram (if the project has multiple interacting components)

Use the Red Hat brand theme in every diagram:
````
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#EE0000', 'primaryTextColor': '#fff', 'primaryBorderColor': '#A30000', 'lineColor': '#6A6E73', 'secondaryColor': '#F0F0F0', 'tertiaryColor': '#0066CC'}}}%%
graph LR
    A[Component] --> B[Component]
```
````

Choose the right diagram type:
- `graph TD` / `graph LR` for architecture and flow
- `sequenceDiagram` for request/response flows
- `flowchart` for pipelines with decision points

Do NOT force diagrams where they don't add value. A simple two-component project doesn't need an architecture diagram.

## Formatting Rules
- Use proper markdown (headers, tables, code blocks, bullet lists)
- Use checkmarks for pass and crosses for fail in tables
- Keep to 200-400 lines
- Use code blocks for URLs, file paths, commands
- Include actual values from the pipeline run, not placeholders
- Be objective -- if it failed, say so clearly and explain why
