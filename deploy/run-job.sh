#!/usr/bin/env bash
#
# Run an AutoPoC Job on Kubernetes.
#
# Usage:
#   ./deploy/run-job.sh <overlay> <project-name> <repo-url> [stop-after]
#
# Examples:
#   ./deploy/run-job.sh my-cluster my-project https://github.com/org/repo
#   ./deploy/run-job.sh my-cluster my-project https://github.com/org/repo build
#
# Prerequisites:
#   1. Create your overlay:
#      cp -r deploy/overlays/example deploy/overlays/my-cluster
#      cp deploy/overlays/my-cluster/secret.yaml.example deploy/overlays/my-cluster/secret.yaml
#      # Edit secret.yaml with real credentials
#
#   2. Deploy RBAC + Secret (one-time):
#      kubectl apply -k deploy/overlays/my-cluster
#
set -euo pipefail

OVERLAY="${1:?Usage: $0 <overlay> <project-name> <repo-url> [stop-after]}"
PROJECT_NAME="${2:?Usage: $0 <overlay> <project-name> <repo-url> [stop-after]}"
REPO_URL="${3:?Usage: $0 <overlay> <project-name> <repo-url> [stop-after]}"
STOP_AFTER="${4:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OVERLAY_DIR="${SCRIPT_DIR}/overlays/${OVERLAY}"

if [ ! -d "$OVERLAY_DIR" ]; then
    echo "Error: overlay directory not found: $OVERLAY_DIR"
    echo "Available overlays:"
    ls -1 "${SCRIPT_DIR}/overlays/" 2>/dev/null || echo "  (none)"
    exit 1
fi

# Generate a short suffix for the Job name to avoid collisions
SHORT_ID="$(date +%s | tail -c 5)"
JOB_SUFFIX="${PROJECT_NAME}-${SHORT_ID}"

echo "=== AutoPoC Job ==="
echo "Overlay:  ${OVERLAY}"
echo "Project:  ${PROJECT_NAME}"
echo "Repo:     ${REPO_URL}"
echo "Job:      autopoc-${JOB_SUFFIX}"
if [ -n "$STOP_AFTER" ]; then
    echo "Stop:     after ${STOP_AFTER}"
fi
echo ""

# Build the manifests with kustomize, then substitute placeholders
MANIFEST=$(kubectl kustomize "$OVERLAY_DIR" | \
    sed "s|JOB_SUFFIX|${JOB_SUFFIX}|g" | \
    sed "s|PLACEHOLDER_PROJECT|${PROJECT_NAME}|g" | \
    sed "s|PLACEHOLDER_REPO|${REPO_URL}|g")

# If stop-after is specified, patch the args
if [ -n "$STOP_AFTER" ]; then
    # The overlay may already have --stop-after in args; this is a safety net
    MANIFEST=$(echo "$MANIFEST" | sed "s|--stop-after.*|--stop-after\n            - \"${STOP_AFTER}\"|")
fi

# Apply — skip namespace/RBAC if they already exist (idempotent)
echo "$MANIFEST" | kubectl apply -f - 2>&1

echo ""
echo "=== Follow logs ==="
echo "kubectl logs -f job/autopoc-${JOB_SUFFIX} -n autopoc"
