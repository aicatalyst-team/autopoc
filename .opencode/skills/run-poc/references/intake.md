# Intake Analysis Instructions

When analyzing the repository digest output, identify the following for each component.

## Component Detection

### Single-Component Repos
- One set of build files at root -> single component
- Name: use the repo/project name

### Monorepos
- Multiple build files in subdirectories -> monorepo
- Each subdirectory with its own `package.json`, `requirements.txt`, `go.mod`, etc. is a separate component
- Name: use the subdirectory name (e.g., "frontend", "api", "worker")

## Per-Component Analysis

For each component, determine:

| Field | How to Find |
|---|---|
| `name` | Subdirectory name or repo name |
| `language` | File extensions + build file type (`.py` = python, `.js`/`.ts` = javascript, `.go` = go) |
| `build_system` | Build file: `requirements.txt`/`pyproject.toml` = pip, `package.json` = npm, `go.mod` = go, `pom.xml` = maven, `Cargo.toml` = cargo |
| `entry_point` | Look for `main.py`, `app.py`, `server.py`, `index.js`, `main.go`, or Dockerfile CMD/ENTRYPOINT |
| `port` | Check EXPOSE in Dockerfile, or common patterns in code (8080, 3000, 5000, 8000). `null` for CLI tools/libraries |
| `is_ml_workload` | Check dependencies for: torch, tensorflow, keras, sklearn, transformers, onnx, vllm, langchain, chromadb, sentence-transformers |
| `source_dir` | Relative path within repo ("." for root, "frontend/" for subdirs) |
| `existing_dockerfile` | Path to Dockerfile if present, `null` otherwise |

## What to Skip

Do NOT include as components:
- Documentation sites (VitePress, Docusaurus, MkDocs, Jekyll, Hugo)
- Test directories
- Example/demo subdirectories (unless they ARE the main application)
- CI/CD configuration directories
- Build scripts directories

## Deployment Artifacts to Note

Record in state:
- `has_helm_chart`: true if `Chart.yaml` found
- `has_kustomize`: true if `kustomization.yaml` found
- `has_compose`: true if `docker-compose.yml` or `compose.yml` found
- `existing_ci_cd`: "github-actions" if `.github/workflows/`, "gitlab-ci" if `.gitlab-ci.yml`, etc.
