# Local E2E Testing

AutoPoC includes scripts for spinning up a complete local environment with GitLab, Quay, and Kubernetes -- no external services required.

## Setup

```bash
# 1. Start GitLab CE + Project Quay (takes 3-5 minutes for GitLab to initialize)
./scripts/setup-e2e.sh

# 2. Start a local Kubernetes cluster (kind or k3d)
./scripts/setup-local-k8s.sh

# Credentials are auto-written to .env.test
# AutoPoC uses .env.test automatically when it exists
```

## Run

```bash
# Run against a real repo using local infrastructure
autopoc run --name test-app --repo https://github.com/some/repo

# Run the E2E test suite
make test-e2e
```

## Cleanup

```bash
# Remove a single project's resources (GitLab project, Quay images, K8s namespace, work dir)
./scripts/cleanup-project.sh my-project

# Preview what would be deleted
./scripts/cleanup-project.sh my-project --dry-run

# Tear down all infrastructure
./scripts/teardown-local-k8s.sh
./scripts/teardown-e2e.sh
```

## What Gets Provisioned

| Service | URL | Purpose |
|---------|-----|---------|
| GitLab CE | `http://localhost:8929` | Git hosting, stores forked repos and generated Dockerfiles/manifests |
| Project Quay | `http://localhost:8080` | Container image registry |
| kind/k3d | `https://localhost:6443` | Local Kubernetes cluster for deployment testing |
