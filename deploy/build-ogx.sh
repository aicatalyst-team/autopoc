#!/usr/bin/env bash
# Build and push the OGX (formerly LlamaStack) container image on UBI9.
#
# The upstream Containerfile already supports UBI9 via its dnf code path,
# so we use it directly with a UBI9 base image argument.
#
# Usage:
#   ./deploy/build-ogx.sh              # build only
#   ./deploy/build-ogx.sh --push       # build and push
#   ./deploy/build-ogx.sh --version v0.8.0  # override version
#
# Environment:
#   CONTAINER_CMD  - podman or docker (default: podman)
#   IMAGE_REGISTRY - registry hostname (default: quay.io)
#   IMAGE_ORG      - registry org/user (default: autopoc)

set -euo pipefail

# --- Configuration ---
OGX_VERSION="${OGX_VERSION:-v0.8.0}"
OGX_REPO="https://github.com/meta-llama/llama-stack.git"
BASE_IMAGE="registry.access.redhat.com/ubi9/python-312:latest"
DISTRO_NAME="starter"

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
            echo "Usage: $0 [--push] [--version <tag>]" >&2
            exit 1
            ;;
    esac
done

IMAGE_TAG_VERSION="${IMAGE_REGISTRY}/${IMAGE_ORG}/${IMAGE_NAME}:ubi9-${OGX_VERSION}"
IMAGE_TAG_LATEST="${IMAGE_REGISTRY}/${IMAGE_ORG}/${IMAGE_NAME}:ubi9-latest"

echo "=== Building OGX ${OGX_VERSION} on UBI9 ==="
echo "  Base image:  ${BASE_IMAGE}"
echo "  Distribution: ${DISTRO_NAME}"
echo "  Output:      ${IMAGE_TAG_VERSION}"
echo ""

# --- Clone upstream ---
TMPDIR=$(mktemp -d)
trap "rm -rf ${TMPDIR}" EXIT

echo "Cloning OGX ${OGX_VERSION}..."
git clone --depth 1 --branch "${OGX_VERSION}" "${OGX_REPO}" "${TMPDIR}/ogx"
echo ""

# --- Build ---
echo "Building container image..."
${CONTAINER_CMD} build \
    -f "${TMPDIR}/ogx/containers/Containerfile" \
    --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
    --build-arg "DISTRO_NAME=${DISTRO_NAME}" \
    -t "${IMAGE_TAG_VERSION}" \
    "${TMPDIR}/ogx"

# Tag as latest
${CONTAINER_CMD} tag "${IMAGE_TAG_VERSION}" "${IMAGE_TAG_LATEST}"

echo ""
echo "Built: ${IMAGE_TAG_VERSION}"
echo "Tagged: ${IMAGE_TAG_LATEST}"

# --- Push ---
if [[ "${PUSH}" == "true" ]]; then
    echo ""
    echo "Pushing images..."
    ${CONTAINER_CMD} push "${IMAGE_TAG_VERSION}"
    ${CONTAINER_CMD} push "${IMAGE_TAG_LATEST}"
    echo "Pushed: ${IMAGE_TAG_VERSION}"
    echo "Pushed: ${IMAGE_TAG_LATEST}"
fi

echo ""
echo "Done."
