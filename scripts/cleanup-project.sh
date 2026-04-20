#!/usr/bin/env bash
#
# Clean up all resources for a single AutoPoC project.
#
# This script removes:
#   1. The local work directory (/tmp/autopoc[-e2e]/<project>)
#   2. The GitLab project (poc-demos/<project>)
#   3. The Kubernetes namespace (<project>)
#   4. All Quay image repos matching <project>-*
#
# Usage:
#   ./scripts/cleanup-project.sh <project-name>
#
# Options:
#   --env-file <path>   Path to env file (default: auto-detect .env.test or .env)
#   --dry-run           Show what would be deleted without doing it
#   --yes               Skip confirmation prompt
#
# Prerequisites:
#   - curl and jq
#   - kubectl (for K8s namespace cleanup)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# --- Parse arguments ---
PROJECT_NAME=""
ENV_FILE=""
DRY_RUN=false
SKIP_CONFIRM=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --yes|-y)
            SKIP_CONFIRM=true
            shift
            ;;
        -*)
            error "Unknown option: $1"
            echo "Usage: $0 <project-name> [--env-file <path>] [--dry-run] [--yes]"
            exit 1
            ;;
        *)
            if [ -z "$PROJECT_NAME" ]; then
                PROJECT_NAME="$1"
            else
                error "Unexpected argument: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "$PROJECT_NAME" ]; then
    error "Project name is required."
    echo "Usage: $0 <project-name> [--env-file <path>] [--dry-run] [--yes]"
    exit 1
fi

# --- Check for jq ---
if ! command -v jq &>/dev/null; then
    error "jq is required but not installed. Install it with: sudo dnf install jq"
    exit 1
fi

# --- Load env file ---
if [ -z "$ENV_FILE" ]; then
    if [ -f "$PROJECT_DIR/.env.test" ]; then
        ENV_FILE="$PROJECT_DIR/.env.test"
    elif [ -f "$PROJECT_DIR/.env" ]; then
        ENV_FILE="$PROJECT_DIR/.env"
    fi
fi

if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
    info "Loading config from $ENV_FILE"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
else
    warn "No env file found. Using environment variables."
fi

# --- Resolve config (env vars with defaults) ---
GITLAB_URL="${GITLAB_URL:-http://localhost:8929}"
GITLAB_TOKEN="${GITLAB_TOKEN:-}"
GITLAB_GROUP="${GITLAB_GROUP:-poc-demos}"

QUAY_REGISTRY="${QUAY_REGISTRY:-http://localhost:8080}"
QUAY_ORG="${QUAY_ORG:-autopoc-test}"
QUAY_TOKEN="${QUAY_TOKEN:-}"

WORK_DIR="${WORK_DIR:-/tmp/autopoc}"

# --- Summary ---
echo ""
info "Project:        $PROJECT_NAME"
info "GitLab:         $GITLAB_URL / $GITLAB_GROUP/$PROJECT_NAME"
info "Quay:           $QUAY_REGISTRY / $QUAY_ORG/${PROJECT_NAME}-*"
info "K8s namespace:  $PROJECT_NAME"
info "Work dir:       $WORK_DIR/$PROJECT_NAME"
if $DRY_RUN; then
    warn "DRY RUN — no changes will be made"
fi
echo ""

# --- Confirmation ---
if ! $SKIP_CONFIRM && ! $DRY_RUN; then
    read -rp "Delete all resources for '$PROJECT_NAME'? [y/N] " answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        info "Aborted."
        exit 0
    fi
fi

ERRORS=0

# --- 1. Delete local work directory ---
info "--- Work directory ---"
for dir in "$WORK_DIR/$PROJECT_NAME" "/tmp/autopoc/$PROJECT_NAME" "/tmp/autopoc-e2e/$PROJECT_NAME"; do
    if [ -d "$dir" ]; then
        if $DRY_RUN; then
            info "[dry-run] Would remove: $dir"
        else
            rm -rf "$dir"
            info "Removed $dir"
        fi
    fi
done

# --- 2. Delete GitLab project ---
info "--- GitLab ---"
if [ -z "$GITLAB_TOKEN" ]; then
    warn "GITLAB_TOKEN not set, skipping GitLab cleanup."
else
    ENCODED_PATH=$(printf '%s' "$GITLAB_GROUP/$PROJECT_NAME" | jq -sRr @uri)
    PROJECT_RESPONSE=$(curl -sf -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
        "$GITLAB_URL/api/v4/projects/$ENCODED_PATH" 2>/dev/null || echo "")

    if [ -n "$PROJECT_RESPONSE" ]; then
        PROJECT_ID=$(echo "$PROJECT_RESPONSE" | jq -r '.id // empty' 2>/dev/null || echo "")
        if [ -n "$PROJECT_ID" ]; then
            if $DRY_RUN; then
                info "[dry-run] Would delete GitLab project: $GITLAB_GROUP/$PROJECT_NAME (id=$PROJECT_ID)"
            else
                DELETE_RESPONSE=$(curl -s -o /dev/null -w '%{http_code}' -X DELETE \
                    -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
                    "$GITLAB_URL/api/v4/projects/$PROJECT_ID?permanently_remove=true&full_path=$ENCODED_PATH" \
                    2>/dev/null || echo "000")
                if [ "$DELETE_RESPONSE" = "202" ] || [ "$DELETE_RESPONSE" = "204" ]; then
                    info "Permanently deleted GitLab project: $GITLAB_GROUP/$PROJECT_NAME (id=$PROJECT_ID)"
                else
                    error "Failed to delete GitLab project (HTTP $DELETE_RESPONSE)"
                    ERRORS=$((ERRORS + 1))
                fi
            fi
        else
            info "GitLab project not found: $GITLAB_GROUP/$PROJECT_NAME"
        fi
    else
        info "GitLab project not found: $GITLAB_GROUP/$PROJECT_NAME"
    fi
fi

# --- 3. Delete Kubernetes namespace ---
info "--- Kubernetes ---"
if command -v kubectl &>/dev/null; then
    NS_EXISTS=$(kubectl get namespace "$PROJECT_NAME" --no-headers 2>/dev/null || echo "")
    if [ -n "$NS_EXISTS" ]; then
        if $DRY_RUN; then
            info "[dry-run] Would delete K8s namespace: $PROJECT_NAME"
        else
            if kubectl delete namespace "$PROJECT_NAME" --ignore-not-found=true 2>/dev/null; then
                info "Deleted K8s namespace: $PROJECT_NAME"
            else
                error "Failed to delete K8s namespace: $PROJECT_NAME"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    else
        info "K8s namespace not found: $PROJECT_NAME"
    fi
else
    warn "kubectl not found, skipping K8s cleanup."
fi

# --- 4. Delete Quay image repos ---
info "--- Quay ---"
if [ -z "$QUAY_TOKEN" ]; then
    warn "QUAY_TOKEN not set, skipping Quay cleanup."
else
    # List all repos in the org, filter by project prefix
    REPOS_RESPONSE=$(curl -sf -H "Authorization: Bearer $QUAY_TOKEN" \
        "$QUAY_REGISTRY/api/v1/repository?namespace=$QUAY_ORG" 2>/dev/null || echo "")

    if [ -n "$REPOS_RESPONSE" ]; then
        REPOS=$(echo "$REPOS_RESPONSE" | jq -r \
            ".repositories[].name | select(. == \"$PROJECT_NAME\" or startswith(\"${PROJECT_NAME}-\"))" \
            2>/dev/null || echo "")

        if [ -z "$REPOS" ]; then
            info "No Quay repos found matching: ${PROJECT_NAME}[-*]"
        else
            for repo in $REPOS; do
                if $DRY_RUN; then
                    info "[dry-run] Would delete Quay repo: $QUAY_ORG/$repo"
                else
                    DELETE_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X DELETE \
                        -H "Authorization: Bearer $QUAY_TOKEN" \
                        "$QUAY_REGISTRY/api/v1/repository/$QUAY_ORG/$repo" 2>/dev/null || echo "000")
                    if [ "$DELETE_CODE" = "204" ] || [ "$DELETE_CODE" = "200" ]; then
                        info "Deleted Quay repo: $QUAY_ORG/$repo"
                    else
                        error "Failed to delete Quay repo $QUAY_ORG/$repo (HTTP $DELETE_CODE)"
                        ERRORS=$((ERRORS + 1))
                    fi
                fi
            done
        fi
    else
        warn "Could not list Quay repos (is the registry running?)"
    fi
fi

# --- Done ---
echo ""
if [ "$ERRORS" -gt 0 ]; then
    error "Cleanup completed with $ERRORS error(s)."
    exit 1
else
    info "Cleanup complete for project '$PROJECT_NAME'."
fi
