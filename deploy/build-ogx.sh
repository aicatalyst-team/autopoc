#!/usr/bin/env bash
# Build and push the OGX (formerly LlamaStack) container image on UBI9.
#
# Uses our own slim Dockerfile (deploy/ogx/Dockerfile.ubi) which installs
# OGX from PyPI on top of ubi9/python-312.  No upstream clone needed.
#
# Usage:
#   ./deploy/build-ogx.sh              # build only
#   ./deploy/build-ogx.sh --push       # build and push
#
# Environment:
#   CONTAINER_CMD  - podman or docker (default: podman)
#   IMAGE_REGISTRY - registry hostname (default: quay.io)
#   IMAGE_ORG      - registry org/user (default: autopoc)
#   OGX_VERSION    - ogx PyPI version to pin (default: latest)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Configuration ---
OGX_VERSION="${OGX_VERSION:-}"
CONTAINER_CMD="${CONTAINER_CMD:-podman}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-quay.io}"
IMAGE_ORG="${IMAGE_ORG:-autopoc}"
IMAGE_NAME="ogx"

PUSH=false

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --push)
            PUSH=true
            shift
            ;;
        --version)
            OGX_VERSION="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: $0 [--push] [--version <pypi-version>]" >&2
            exit 1
            ;;
    esac
done

if [[ -n "${OGX_VERSION}" ]]; then
    IMAGE_TAG_VERSION="${IMAGE_REGISTRY}/${IMAGE_ORG}/${IMAGE_NAME}:ubi9-${OGX_VERSION}"
else
    IMAGE_TAG_VERSION="${IMAGE_REGISTRY}/${IMAGE_ORG}/${IMAGE_NAME}:ubi9-latest"
fi
IMAGE_TAG_LATEST="${IMAGE_REGISTRY}/${IMAGE_ORG}/${IMAGE_NAME}:ubi9-latest"

echo "=== Building OGX on UBI9 ==="
echo "  OGX version: ${OGX_VERSION:-latest (unpinned)}"
echo "  Output:      ${IMAGE_TAG_VERSION}"
echo ""

# --- Build ---
BUILD_ARGS=()
if [[ -n "${OGX_VERSION}" ]]; then
    BUILD_ARGS+=(--build-arg "OGX_VERSION=${OGX_VERSION}")
fi

${CONTAINER_CMD} build \
    -f "${SCRIPT_DIR}/ogx/Dockerfile.ubi" \
    "${BUILD_ARGS[@]}" \
    -t "${IMAGE_TAG_VERSION}" \
    "${SCRIPT_DIR}/ogx/"

# Tag as latest (if building a pinned version)
if [[ "${IMAGE_TAG_VERSION}" != "${IMAGE_TAG_LATEST}" ]]; then
    ${CONTAINER_CMD} tag "${IMAGE_TAG_VERSION}" "${IMAGE_TAG_LATEST}"
    echo "Tagged: ${IMAGE_TAG_LATEST}"
fi

echo "Built: ${IMAGE_TAG_VERSION}"

# --- Push ---
if [[ "${PUSH}" == "true" ]]; then
    echo ""
    echo "Pushing images..."
    ${CONTAINER_CMD} push "${IMAGE_TAG_VERSION}"
    echo "Pushed: ${IMAGE_TAG_VERSION}"
    if [[ "${IMAGE_TAG_VERSION}" != "${IMAGE_TAG_LATEST}" ]]; then
        ${CONTAINER_CMD} push "${IMAGE_TAG_LATEST}"
        echo "Pushed: ${IMAGE_TAG_LATEST}"
    fi
fi

echo ""
echo "Done."
