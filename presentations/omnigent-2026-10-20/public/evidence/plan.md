# PoC Plan: omnigent

## Project Classification
- **Type:** `llm-app` (agent orchestration control plane: FastAPI server + React web UI)
- **Key Technologies:** Python 3.12, FastAPI, uvicorn, SQLAlchemy (SQLite/Postgres), Alembic, React/Vite web UI, pnpm, UBI 9
- **ODH Relevance:** Maps to the **Agentic AI** strategy area. Omnigent is a hostable,
  policy-governed agent orchestration layer (a "meta-harness"). Proving it runs as a
  durable, multi-user, UBI-packaged service on OpenShift validates the story that rich
  agent control planes can be deployed, governed, and scaled on Red Hat AI alongside
  Llama Stack / MCP.

## PoC Objectives
1. Prove the Omnigent **server** containerizes on UBI 9 and deploys as a single,
   non-root, self-contained pod on OpenShift (no external database dependency).
2. Prove the server boots, initializes its backing store (SQLite on a PVC), and serves
   its control-plane HTTP API (`/health`, `/api/version`, `/v1/info`) reliably.
3. Prove the built **web UI** bundle is served and reachable through an OpenShift Route.
4. Demonstrate the OpenShift-native deployment pattern (Deployment + Service + Route +
   PVC + probes + security context) that the project's own Kustomize overlays target.

## Infrastructure Requirements
- **Resource Profile:** `medium` (1Gi RAM, 1 CPU limit)
- **GPU Required:** no
- **Persistent Storage:** 10Gi PVC at `/data` (SQLite database + artifact store)
- **Sidecar Containers:** none (single pod; SQLite backend avoids a Postgres sidecar)
- **Backing store:** SQLite (`DATABASE_URL=sqlite:////data/omnigent.db`) — a fully
  supported Omnigent backend that keeps the PoC to a single pod. (Postgres is the
  production recommendation; see report.)
- **Auth:** `accounts` provider enabled, with a generated cookie secret; first-run
  admin is auto-created by the server.

## Test Scenarios
### Scenario 1: health-check
- **Description:** Bare liveness; also exercises the backing-store connection path.
- **Type:** http
- **Input:** `GET /health`
- **Expected:** HTTP 200 with JSON body `{"status": "ok"}`
- **Timeout:** 30

### Scenario 2: version-info
- **Description:** Confirms the `omnigent` package installed correctly in the UBI image.
- **Type:** http
- **Input:** `GET /api/version`
- **Expected:** HTTP 200 with a non-empty version string
- **Timeout:** 30

### Scenario 3: server-info
- **Description:** Unauthenticated server capability/info endpoint; validates config,
  auth subsystem, and feature snapshot wiring.
- **Type:** http
- **Input:** `GET /v1/info`
- **Expected:** HTTP 200 with JSON containing `accounts_enabled` and `server_version`
- **Timeout:** 30

### Scenario 4: web-ui
- **Description:** The React SPA bundle (built into the image) is served at the root.
- **Type:** http
- **Input:** `GET /`
- **Expected:** HTTP 200 with an HTML document (contains `<html` / app root markup)
- **Timeout:** 30

### Scenario 5: login-page
- **Description:** The auth login page is reachable (pre-auth surface of the accounts flow).
- **Type:** http
- **Input:** `GET /login`
- **Expected:** HTTP 200 (HTML login page served)
- **Timeout:** 30

## Dockerfile Considerations
- Reuse the project's existing **`deploy/docker/Dockerfile.ubi`** (UBI 9, multi-stage,
  non-root `USER 1001`, `/health` HEALTHCHECK). Build the **default `runtime`** target
  (the server); do not build the `host`/sandbox target for this PoC.
- Build context is the **repository root** (the Dockerfile `COPY`s `omnigent/`, `web/`,
  `sdks/`, `examples/`, `patches/`, `deploy/docker/entrypoint.py`, and the pnpm lockfile).
  Set the BuildConfig `dockerfilePath` to `deploy/docker/Dockerfile.ubi`.
- The image already runs as non-root (1001) and exposes port 8000 — no changes needed.
- Add a root-level `.dockerignore` to trim the build context (drop `tests/`, `docs/`,
  `dev/`, `designs/`, `feature-map/`, `integrations/`, `editors/`, `.github/`, `sdks/web-extension`, etc.)
  while keeping every path the Dockerfile `COPY`s.

## Deployment Considerations
- **deployment_model:** `deployment` (long-running web/API server), `listens_on_port: true` (8000).
- **Namespace:** `poc-omnigent`.
- **Resources:**
  - `PVC` `omnigent-data` (10Gi, default SC) mounted at `/data`.
  - `initContainer` (UBI 9, runs as root) that `chown`s `/data` to `1001:0` so the
    non-root server can write the SQLite DB and artifacts (block-CSI volumes are
    root-owned by default).
  - `Deployment` `omnigent`: image `quay.io/aicatalyst/omnigent-server:latest`,
    `runAsNonRoot: true`, `runAsUser: 1001`, port 8000, env from ConfigMap + Secret,
    `livenessProbe`/`readinessProbe` on `GET /health:8000`.
  - `Service` `omnigent` (ClusterIP, 80 → 8000).
  - `Route` `omnigent` (edge TLS) → `omnigent:80`.
  - `ConfigMap` `omnigent-config`: `HOST`, `PORT=8000`, `ARTIFACT_DIR=/data/artifacts`,
    `OMNIGENT_AUTH_ENABLED=1`, `OMNIGENT_AUTH_PROVIDER=accounts`,
    `OMNIGENT_ADMIN_CREDENTIALS_PATH=/data/admin-credentials`.
  - `Secret` `omnigent-secrets`: `DATABASE_URL=sqlite:////data/omnigent.db`,
    `OMNIGENT_ACCOUNTS_COOKIE_SECRET=<generated hex>`.
- **Test method:** HTTP requests against the Route URL (scenarios above). All five
  endpoints are pre-auth, so no login flow is required to validate the deployment.
