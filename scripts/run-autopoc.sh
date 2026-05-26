#!/usr/bin/env bash
#
# Run an AutoPoC pipeline as a Kubernetes Job (OpenCode harness).
#
# Usage:
#   scripts/run-autopoc.sh <project-name> <repo-url> [options]
#
# Examples:
#   scripts/run-autopoc.sh my-project https://github.com/org/repo
#   scripts/run-autopoc.sh my-project https://github.com/org/repo --dry-run
#
# Prerequisites (assumed already in place):
#   - oc login has been run (cluster access is active)
#   - The target namespace exists
#   - autopoc-credentials Secret exists in the namespace
#   - autopoc-runner ServiceAccount + RBAC are deployed
#
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────
NAMESPACE="autopoc-test"
IMAGE="quay.io/aicatalyst/autopoc-opencode:latest"
DRY_RUN=false

# ── Usage ────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") <project-name> <repo-url> [options]

Run the autopoc pipeline as a Kubernetes Job.

Positional arguments:
  project-name          Name for this PoC run
  repo-url              Upstream repository URL to process

Options:
  -n, --namespace NS    Kubernetes namespace (default: autopoc-test)
  -i, --image IMAGE     Container image (default: quay.io/aicatalyst/autopoc-opencode:latest)
      --dry-run         Print the Job manifest without applying
  -h, --help            Show this help message
EOF
    exit "${1:-0}"
}

# ── Arg parsing ──────────────────────────────────────────────────────
POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)        usage ;;
        -n|--namespace)   NAMESPACE="$2"; shift 2 ;;
        -i|--image)       IMAGE="$2"; shift 2 ;;
        --dry-run)        DRY_RUN=true; shift ;;
        -*)               echo "Unknown option: $1" >&2; echo >&2; usage 1 ;;
        *)                POSITIONAL+=("$1"); shift ;;
    esac
done

if [[ ${#POSITIONAL[@]} -lt 2 ]]; then
    echo "Error: project-name and repo-url are required." >&2
    echo >&2
    usage 1
fi

PROJECT_NAME="${POSITIONAL[0]}"
REPO_URL="${POSITIONAL[1]}"

# ── Sanity check ─────────────────────────────────────────────────────
if [[ "$DRY_RUN" == false ]]; then
    if ! oc whoami &>/dev/null; then
        echo "Error: not logged in to an OpenShift cluster. Run 'oc login' first." >&2
        exit 1
    fi
fi

# ── Job name ─────────────────────────────────────────────────────────
SHORT_ID="$(date +%s | tail -c 5)"
JOB_NAME="autopoc-${PROJECT_NAME}-${SHORT_ID}"

# ── Build container args ─────────────────────────────────────────────
# OpenCode runs in non-interactive mode with the run-poc skill
PROMPT="Run PoC for ${PROJECT_NAME} from ${REPO_URL}"

# ── Generate manifest ────────────────────────────────────────────────
MANIFEST=$(cat <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: autopoc
    autopoc/project: "${PROJECT_NAME}"
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels:
        app: autopoc
        autopoc/project: "${PROJECT_NAME}"
    spec:
      restartPolicy: Never
      serviceAccountName: autopoc-runner
      containers:
        - name: autopoc
          image: ${IMAGE}
          args:
            - "run"
            - "--dangerously-skip-permissions"
            - "${PROMPT}"
          env:
            # --- Project configuration ---
            - name: AUTOPOC_PROJECT_NAME
              value: "${PROJECT_NAME}"
            - name: AUTOPOC_REPO_URL
              value: "${REPO_URL}"
            - name: BUILD_STRATEGY
              value: "openshift"
            - name: AUTOPOC_WORK_DIR
              value: "/workspace"

            # --- Google Sheet (for run-sheet, optional) ---
            - name: AUTOPOC_SHEET_ID
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: AUTOPOC_SHEET_ID
                  optional: true
            - name: AUTOPOC_SHEET_CREDENTIALS
              value: "/etc/autopoc/google-sa/credentials.json"

            # --- LLM providers (configure one in the secret) ---
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: ANTHROPIC_API_KEY
                  optional: true
            - name: VERTEX_PROJECT
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: VERTEX_PROJECT
                  optional: true
            - name: VERTEX_LOCATION
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: VERTEX_LOCATION
                  optional: true
            - name: GOOGLE_APPLICATION_CREDENTIALS
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: GOOGLE_APPLICATION_CREDENTIALS
                  optional: true
            - name: LLM_BASE_URL
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: LLM_BASE_URL
                  optional: true
            - name: LLM_API_KEY
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: LLM_API_KEY
                  optional: true
            - name: LLM_MODEL
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: LLM_MODEL
                  optional: true

            # --- Fork target ---
            - name: FORK_TARGET
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: FORK_TARGET
                  optional: true
            - name: GITHUB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: GITHUB_TOKEN
                  optional: true
            - name: GITHUB_ORG
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: GITHUB_ORG
                  optional: true
            - name: GITLAB_URL
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: GITLAB_URL
                  optional: true
            - name: GITLAB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: GITLAB_TOKEN
                  optional: true
            - name: GITLAB_GROUP
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: GITLAB_GROUP
                  optional: true

            # --- Quay registry ---
            - name: QUAY_REGISTRY
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: QUAY_REGISTRY
                  optional: true
            - name: QUAY_ORG
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: QUAY_ORG
            - name: QUAY_TOKEN
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: QUAY_TOKEN
            - name: QUAY_USERNAME
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: QUAY_USERNAME
                  optional: true

            # --- OpenShift ---
            - name: OPENSHIFT_API_URL
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: OPENSHIFT_API_URL
                  optional: true
            - name: OPENSHIFT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: OPENSHIFT_TOKEN
                  optional: true
            - name: OPENSHIFT_NAMESPACE_PREFIX
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: OPENSHIFT_NAMESPACE_PREFIX
                  optional: true

            # --- Tuning ---
            - name: MAX_BUILD_RETRIES
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: MAX_BUILD_RETRIES
                  optional: true

          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2"

          volumeMounts:
            - name: work
              mountPath: /workspace
            - name: google-sa
              mountPath: /etc/autopoc/google-sa
              readOnly: true

      volumes:
        - name: work
          emptyDir: {}
        - name: google-sa
          secret:
            secretName: autopoc-google-sa
            optional: true
EOF
)

# ── Apply or print ───────────────────────────────────────────────────
if [[ "$DRY_RUN" == true ]]; then
    echo "$MANIFEST"
    exit 0
fi

echo "=== AutoPoC Job ==="
echo "Project:    ${PROJECT_NAME}"
echo "Repo:       ${REPO_URL}"
echo "Namespace:  ${NAMESPACE}"
echo "Image:      ${IMAGE}"
echo "Job:        ${JOB_NAME}"
echo

echo "$MANIFEST" | oc apply -f -

echo
echo "Follow logs:"
echo "  oc logs -f job/${JOB_NAME} -n ${NAMESPACE}"
