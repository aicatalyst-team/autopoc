#!/usr/bin/env bash
#
# Teardown local Kubernetes cluster for AutoPoC E2E testing
#
# Usage:
#   ./scripts/teardown-local-k8s.sh

set -euo pipefail

CLUSTER_NAME="autopoc-e2e"

echo "🗑️  Tearing down local Kubernetes cluster..."

if command -v k3d &> /dev/null; then
    if k3d cluster list | grep -q "$CLUSTER_NAME"; then
        echo "Deleting k3d cluster '$CLUSTER_NAME'..."
        k3d cluster delete "$CLUSTER_NAME"
        echo "✓ k3d cluster deleted"
    else
        echo "No k3d cluster '$CLUSTER_NAME' found"
    fi
elif command -v kind &> /dev/null; then
    if kind get clusters 2>/dev/null | grep -q "$CLUSTER_NAME"; then
        echo "Deleting kind cluster '$CLUSTER_NAME'..."
        kind delete cluster --name "$CLUSTER_NAME"
        echo "✓ kind cluster deleted"
    else
        echo "No kind cluster '$CLUSTER_NAME' found"
    fi
else
    echo "Neither k3d nor kind found - nothing to clean up"
fi

echo "✅ Local Kubernetes cluster teardown complete"
