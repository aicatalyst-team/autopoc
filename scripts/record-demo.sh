#!/usr/bin/env bash
#
# Record a demo video for a completed AutoPoC deployment.
#
# Launches a Kubernetes Job that uses the autopoc-recorder image to generate
# a short demo video showing the OpenShift Console topology view alongside
# a terminal running PoC sanity tests.
#
# Usage:
#   scripts/record-demo.sh <project-name> [options]
#
# Examples:
#   scripts/record-demo.sh my-project
#   scripts/record-demo.sh my-project --dry-run
#   scripts/record-demo.sh my-project -n custom-namespace
#
# Prerequisites:
#   - oc login has been run (cluster access is active)
#   - The PoC deployment is still running in the target namespace
#   - autopoc-credentials Secret exists with console credentials
#   - autopoc-runner ServiceAccount + RBAC are deployed
#
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────
NAMESPACE="autopoc-test"
IMAGE="quay.io/aicatalyst/autopoc-recorder:latest"
DRY_RUN=false

# ── Usage ────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") <project-name> [options]

Record a demo video for a completed PoC deployment.

The PoC must have been previously run (poc-state.yaml must exist).
The deployment must still be active on the cluster.

Positional arguments:
  project-name          Name of the PoC project (matches the run-autopoc project name)

Options:
  -n, --namespace NS    Kubernetes namespace (default: autopoc-test)
  -i, --image IMAGE     Container image (default: quay.io/aicatalyst/autopoc-recorder:latest)
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

if [[ ${#POSITIONAL[@]} -lt 1 ]]; then
    echo "Error: project-name is required." >&2
    echo >&2
    usage 1
fi

PROJECT_NAME="${POSITIONAL[0]}"

# ── Sanity check ─────────────────────────────────────────────────────
if [[ "$DRY_RUN" == false ]]; then
    if ! oc whoami &>/dev/null; then
        echo "Error: not logged in to an OpenShift cluster. Run 'oc login' first." >&2
        exit 1
    fi
fi

# ── Job name ─────────────────────────────────────────────────────────
SHORT_ID="$(date +%s | tail -c 5)"
JOB_NAME="autopoc-record-${PROJECT_NAME}-${SHORT_ID}"

# ── Build container args ─────────────────────────────────────────────
PROMPT="Record demo video for ${PROJECT_NAME}"

# ── Generate manifest ────────────────────────────────────────────────
MANIFEST=$(cat <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: autopoc
    autopoc/component: recorder
    autopoc/project: "${PROJECT_NAME}"
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels:
        app: autopoc
        autopoc/component: recorder
        autopoc/project: "${PROJECT_NAME}"
    spec:
      restartPolicy: Never
      serviceAccountName: autopoc-runner
      containers:
        - name: recorder
          image: ${IMAGE}
          args:
            - "run"
            - "--dangerously-skip-permissions"
            - "${PROMPT}"
          env:
            # --- Project configuration ---
            - name: AUTOPOC_PROJECT_NAME
              value: "${PROJECT_NAME}"
            - name: AUTOPOC_WORK_DIR
              value: "/workspace"

            # --- LLM providers ---
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
            - name: GOOGLE_CLOUD_PROJECT
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
              value: "/etc/autopoc/google-sa/credentials.json"
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

            # --- OpenShift ---
            # NOTE: OPENSHIFT_API_URL and OPENSHIFT_TOKEN are NOT needed
            # when running in-cluster. kubectl/oc use the mounted
            # ServiceAccount token automatically. The console URL is
            # derived at runtime via:
            #   oc get consoles.config.openshift.io cluster -o jsonpath='{.status.consoleURL}'
            - name: OPENSHIFT_NAMESPACE_PREFIX
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: OPENSHIFT_NAMESPACE_PREFIX
                  optional: true

            # --- Console authentication (for demo recording) ---
            - name: OPENSHIFT_IDP_NAME
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: OPENSHIFT_IDP_NAME
                  optional: true
            - name: OPENSHIFT_CONSOLE_USERNAME
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: OPENSHIFT_CONSOLE_USERNAME
            - name: OPENSHIFT_CONSOLE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: OPENSHIFT_CONSOLE_PASSWORD

            # --- Google Drive (for video upload) ---
            - name: AUTOPOC_SHEET_CREDENTIALS
              value: "/etc/autopoc/google-sa/credentials.json"
            - name: GOOGLE_DOCS_FOLDER_ID
              valueFrom:
                secretKeyRef:
                  name: autopoc-credentials
                  key: GOOGLE_DOCS_FOLDER_ID
                  optional: true

            # --- Fork target (needed to locate poc-state.yaml) ---
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

          resources:
            requests:
              memory: "1Gi"
              cpu: "1"
            limits:
              memory: "4Gi"
              cpu: "4"

          volumeMounts:
            - name: work
              mountPath: /workspace
            - name: google-sa
              mountPath: /etc/autopoc/google-sa
              readOnly: true
            # Shared memory for Chromium (prevents crashes)
            - name: dshm
              mountPath: /dev/shm

      volumes:
        - name: work
          emptyDir: {}
        - name: google-sa
          secret:
            secretName: autopoc-google-sa
            optional: true
        # Chromium needs more than the default 64MB /dev/shm
        - name: dshm
          emptyDir:
            medium: Memory
            sizeLimit: 1Gi
EOF
)

# ── Apply or print ───────────────────────────────────────────────────
if [[ "$DRY_RUN" == true ]]; then
    echo "$MANIFEST"
    exit 0
fi

echo "=== AutoPoC Demo Recorder ==="
echo "Project:    ${PROJECT_NAME}"
echo "Namespace:  ${NAMESPACE}"
echo "Image:      ${IMAGE}"
echo "Job:        ${JOB_NAME}"
echo

echo "$MANIFEST" | oc apply -f -

echo
echo "Follow logs:"
echo "  oc logs -f job/${JOB_NAME} -n ${NAMESPACE}"
