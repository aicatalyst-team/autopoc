#!/usr/bin/env bash
#
# Setup local Kubernetes cluster for AutoPoC E2E testing
#
# This script creates a lightweight k3d cluster that runs alongside
# the GitLab/Quay containers for complete local E2E testing.
#
# Usage:
#   ./scripts/setup-local-k8s.sh
#
# Prerequisites:
#   - Docker running
#   - k3d installed (or we'll try kind as fallback)

set -euo pipefail

CLUSTER_NAME="autopoc-e2e"

echo "🚀 Setting up local Kubernetes cluster for AutoPoC E2E testing..."

# Check if k3d is available
if command -v k3d &> /dev/null; then
    echo "✓ Using k3d for local cluster"

    # Check if cluster already exists
    if k3d cluster list | grep -q "$CLUSTER_NAME"; then
        echo "✓ Cluster '$CLUSTER_NAME' already exists"
        echo "  To recreate: k3d cluster delete $CLUSTER_NAME"
    else
        echo "Creating k3d cluster '$CLUSTER_NAME'..."

        # Create cluster with:
        # - API on port 6550 (avoid conflicts)
        # - HTTP ingress on 8081 (avoid conflicts with Quay on 8080)
        # - Disable Traefik (we'll use NodePort services for E2E)
        k3d cluster create "$CLUSTER_NAME" \
            --api-port 6550 \
            --port "8081:30080@server:0" \
            --k3s-arg "--disable=traefik@server:0" \
            --wait

        echo "✓ k3d cluster created successfully"
    fi

    # Set kubectl context
    k3d kubeconfig merge "$CLUSTER_NAME" --kubeconfig-merge-default
    kubectl config use-context "k3d-$CLUSTER_NAME"

elif command -v kind &> /dev/null; then
    echo "✓ Using kind for local cluster"

    # Check if cluster already exists
    if kind get clusters 2>/dev/null | grep -q "$CLUSTER_NAME"; then
        echo "✓ Cluster '$CLUSTER_NAME' already exists"
        echo "  To recreate: kind delete cluster --name $CLUSTER_NAME"
    else
        echo "Creating kind cluster '$CLUSTER_NAME'..."

        # Create cluster with custom config
        cat <<EOF | kind create cluster --name "$CLUSTER_NAME" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30080
    hostPort: 8081
    protocol: TCP
EOF

        echo "✓ kind cluster created successfully"
    fi

    # Set kubectl context
    kubectl config use-context "kind-$CLUSTER_NAME"

else
    echo "❌ ERROR: Neither k3d nor kind is installed"
    echo ""
    echo "Please install one of:"
    echo "  k3d:  https://k3d.io/v5.6.0/#installation"
    echo "  kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
    exit 1
fi

# Verify cluster is ready
echo ""
echo "Waiting for cluster to be ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=60s

echo ""
echo "✅ Local Kubernetes cluster is ready!"
echo ""
kubectl cluster-info
echo ""
echo "Cluster name: $CLUSTER_NAME"
echo "Context: $(kubectl config current-context)"
echo ""
echo "To use this cluster:"
echo "  kubectl config use-context $(kubectl config current-context)"
echo ""
echo "To delete this cluster:"
if command -v k3d &> /dev/null; then
    echo "  k3d cluster delete $CLUSTER_NAME"
else
    echo "  kind delete cluster --name $CLUSTER_NAME"
fi
