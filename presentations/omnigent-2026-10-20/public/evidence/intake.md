# Omnigent — Intake Digest

- **Repo**: https://github.com/omnigent-ai/omnigent
- **License**: Apache 2.0
- **Description**: Open-source "meta-harness" providing a common orchestration
  layer over AI coding agents (Claude Code, Codex, Cursor, OpenCode, Hermes,
  Pi, and custom YAML agents). Swap/combine harnesses, enforce policies and
  sandboxing, and collaborate from any device.

## Repository layout (monorepo)

| Path | Purpose |
|------|---------|
| `omnigent/` | Main Python package: server, CLI, harnesses, stores, policies, runner |
| `omnigent/server/` | FastAPI server (app.py, routes, managed hosts, scheduler) |
| `omnigent/db/` | SQLAlchemy stores + Alembic migrations (SQLite/Postgres/CockroachDB) |
| `deploy/docker/` | Dockerfile, Dockerfile.ubi, entrypoint.py, docker-compose, config |
| `deploy/kubernetes/` | Kustomize base + overlays (postgres, openshift, openshift-postgres, sandbox-runners, argocd) |
| `web/` | React/Vite web UI (built into the server image) |
| `sdks/python-client/` | `omnigent-client` Python SDK |
| `examples/` | Example agents (polly, debby, deep-research, mcp-registry) |
| `editors/vscode/`, `sdks/web-extension/` | Editor/extension integrations (not part of server PoC) |

## Deployable component: omnigent-server

- **Language**: Python 3.12
- **Build system**: pip / uv (pyproject.toml + setup.py, setuptools backend)
- **Entry point**: `deploy/docker/entrypoint.py` (Docker `CMD ["python", "/app/entrypoint.py"]`)
- **Port**: 8000 (HTTP; `/health` liveness, `/api/version`, `/v1/info`, web UI at `/`)
- **Existing Dockerfile**: `deploy/docker/Dockerfile.ubi` (UBI 9, two targets: `runtime`/server default, `host`/sandbox)
- **ML workload**: No (orchestration layer; talks to LLM APIs/gateway but does not serve models)

## Deployment artifacts

- Kustomize: **yes** (`deploy/kubernetes/` — base + `openshift`/`openshift-postgres` overlays with Routes + security contexts)
- docker-compose: **yes** (`deploy/docker/docker-compose.yaml`)
- Helm chart: no
- CI/CD: GitHub Actions (`.github/workflows/`)

## Operational notes

- Server runs in **external-runner** mode: it coordinates sessions and accepts
  runner WebSocket tunnels; it does not spawn harness subprocesses itself.
- Backing store: `DATABASE_URL` (Postgres **or** SQLite — both fully supported;
  SQLite uses WAL + tuned pool). Artifact store on a local dir / PVC.
- Auth: `accounts` provider (multi-user, invite-based) or OIDC; first-run admin
  is auto-created. Cookie secret via `OMNIGENT_ACCOUNTS_COOKIE_SECRET`.
- UBI image already runs as non-root (USER 1001) with a `/health` check —
  OpenShift-ready out of the box.
