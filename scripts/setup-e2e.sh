#!/usr/bin/env bash
#
# Setup local E2E test infrastructure for AutoPoC.
#
# This script:
#   1. Starts GitLab CE via docker-compose
#   2. Waits for GitLab to become healthy
#   3. Creates a personal access token for the root user
#   4. Creates the "poc-demos" group
#   5. Writes credentials to .env.test
#
# Usage:
#   ./scripts/setup-e2e.sh
#
# Prerequisites:
#   - docker and docker-compose (or podman with podman-compose)
#   - curl and jq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.test.yml"
ENV_TEST_FILE="$PROJECT_DIR/.env.test"

GITLAB_URL="http://localhost:8929"
GITLAB_ROOT_PASSWORD="autopoc-test-password"
GITLAB_GROUP="poc-demos"
GITLAB_TOKEN_NAME="autopoc-e2e-token"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# --- Detect compose command ---
if command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v podman-compose &>/dev/null; then
    COMPOSE_CMD="podman-compose"
else
    error "No docker-compose, docker compose, or podman-compose found."
    exit 1
fi

info "Using compose command: $COMPOSE_CMD"

# --- Check for jq ---
if ! command -v jq &>/dev/null; then
    error "jq is required but not installed. Install it with: sudo dnf install jq"
    exit 1
fi

# --- Start services ---
info "Starting GitLab CE..."
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d

# --- Wait for GitLab to be healthy ---
# We check two things:
#   1. The container's health status (from docker healthcheck)
#   2. That the sign-in page is reachable via HTTP (no auth needed)
info "Waiting for GitLab to become healthy (this can take 3-5 minutes)..."

MAX_WAIT=600  # 10 minutes
ELAPSED=0
INTERVAL=10

while true; do
    # Try the sign-in page — no auth required, returns 200 when GitLab is ready
    HTTP_CODE=$(curl -so /dev/null -w '%{http_code}' "$GITLAB_URL/users/sign_in" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "200" ]; then
        info "GitLab is responding (HTTP $HTTP_CODE)!"
        break
    fi

    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        error "GitLab did not become healthy within ${MAX_WAIT}s"
        error "Last HTTP status: $HTTP_CODE"
        error "Check logs with: docker logs autopoc-gitlab"
        exit 1
    fi

    printf "  waiting... (%ds, HTTP %s)\n" "$ELAPSED" "$HTTP_CODE"
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

# --- Create personal access token via Rails runner ---
# This is the most reliable way to create a token in GitLab CE.
# The API requires authentication to create tokens, so we bootstrap via Rails.

info "Creating personal access token for root user..."

TOKEN_VALUE="glpat-autopoc-e2e-$(date +%s)"

docker exec autopoc-gitlab gitlab-rails runner "
  user = User.find_by_username('root')
  # Remove existing token with same name to make script idempotent
  user.personal_access_tokens.where(name: '${GITLAB_TOKEN_NAME}').each(&:revoke!)
  token = user.personal_access_tokens.create!(
    name: '${GITLAB_TOKEN_NAME}',
    scopes: [:api, :read_repository, :write_repository],
    expires_at: 365.days.from_now
  )
  token.set_token('${TOKEN_VALUE}')
  token.save!
  puts 'Token created successfully'
" 2>&1

if [ $? -ne 0 ]; then
    error "Failed to create token via Rails runner."
    error "GitLab may still be initializing. Try again in a minute."
    exit 1
fi

# --- Verify the token works ---
info "Verifying token..."
TOKEN_CHECK=$(curl -sf -H "PRIVATE-TOKEN: $TOKEN_VALUE" "$GITLAB_URL/api/v4/user" 2>/dev/null || echo "")

if echo "$TOKEN_CHECK" | jq -e '.username == "root"' >/dev/null 2>&1; then
    info "Token verified: user=root"
else
    warn "Token verification via /api/v4/user returned: $TOKEN_CHECK"
    warn "Trying /api/v4/version with auth..."

    VERSION_CHECK=$(curl -sf -H "PRIVATE-TOKEN: $TOKEN_VALUE" "$GITLAB_URL/api/v4/version" 2>/dev/null || echo "")
    if echo "$VERSION_CHECK" | jq -e '.version' >/dev/null 2>&1; then
        GITLAB_VER=$(echo "$VERSION_CHECK" | jq -r '.version')
        info "Token works! GitLab version: $GITLAB_VER"
    else
        error "Token verification failed."
        error "/api/v4/user response: $TOKEN_CHECK"
        error "/api/v4/version response: $VERSION_CHECK"
        error "You may need to wait longer for GitLab to fully initialize."
        exit 1
    fi
fi

# --- Create the poc-demos group ---
info "Creating group '$GITLAB_GROUP'..."

GROUP_RESPONSE=$(curl -s -X POST \
    -H "PRIVATE-TOKEN: $TOKEN_VALUE" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"$GITLAB_GROUP\", \"path\": \"$GITLAB_GROUP\", \"visibility\": \"internal\"}" \
    "$GITLAB_URL/api/v4/groups" 2>/dev/null || echo "")

if echo "$GROUP_RESPONSE" | jq -e '.id' >/dev/null 2>&1; then
    GROUP_ID=$(echo "$GROUP_RESPONSE" | jq -r '.id')
    info "Group created: $GITLAB_GROUP (id=$GROUP_ID)"
else
    # Group might already exist — check for it
    EXISTING_GROUP=$(curl -sf -H "PRIVATE-TOKEN: $TOKEN_VALUE" \
        "$GITLAB_URL/api/v4/groups?search=$GITLAB_GROUP" 2>/dev/null || echo "[]")

    GROUP_ID=$(echo "$EXISTING_GROUP" | jq -r '.[0].id // empty' 2>/dev/null || echo "")

    if [ -n "$GROUP_ID" ]; then
        info "Group already exists: $GITLAB_GROUP (id=$GROUP_ID)"
    else
        error "Failed to create or find group '$GITLAB_GROUP'"
        error "Create response: $GROUP_RESPONSE"
        error "Search response: $EXISTING_GROUP"
        exit 1
    fi
fi

# --- Wait for Quay to be healthy ---
info "Waiting for Quay to become healthy (can take 1-2 minutes for DB migrations)..."

QUAY_URL="http://localhost:8080"
ELAPSED=0
while true; do
    HTTP_CODE=$(curl -so /dev/null -w '%{http_code}' "$QUAY_URL/health/instance" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "200" ]; then
        info "Quay is responding (HTTP $HTTP_CODE)!"
        break
    fi

    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        error "Quay did not become healthy within ${MAX_WAIT}s"
        error "Last HTTP status: $HTTP_CODE"
        error "Check logs with: docker logs autopoc-quay"
        exit 1
    fi

    printf "  waiting... (%ds, HTTP %s)\n" "$ELAPSED" "$HTTP_CODE"
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

# --- Create Quay Token and Organization ---
info "Generating Quay OAuth token via internal script..."

cat << 'EOF' > /tmp/quay_setup.py
import sys
sys.path.insert(0, '/quay-registry')
import logging
logging.basicConfig(level=logging.ERROR)
from app import app
from data.model import user, organization, oauth
import auth.scopes

with app.app_context():
    # 1. Ensure user exists
    u = user.get_user("autopoc")
    if not u:
        u = user.create_user("autopoc", "password", "test@autopoc.com")

    # 2. Ensure org exists
    org = user.get_namespace_user("autopoc-test")
    if not org:
        org = organization.create_organization("autopoc-test", "org@autopoc.com", u)

    # 3. Create Application
    app_name = "AutoPoC E2E App"
    apps = oauth.list_applications_for_org(org)
    my_app = next((a for a in apps if a.name == app_name), None)
    if not my_app:
        my_app = oauth.create_application(org, app_name, "http://localhost", "http://localhost")

    # 4. Generate Token with all scopes
    all_scopes_str = ",".join(auth.scopes.ALL_SCOPES.keys())
    token_str = oauth.random_string_generator(40)()
    token_obj = oauth.create_user_access_token(
        u, 
        my_app.client_id, 
        all_scopes_str, 
        access_token=token_str, 
        expires_in=315360000
    )
    print(token_str)
EOF

docker cp /tmp/quay_setup.py autopoc-quay:/quay_setup.py
QUAY_TOKEN=$(docker exec autopoc-quay bash -c "PYTHONPATH=/quay-registry python /quay_setup.py" | tr -d '\r\n')

if [ -z "$QUAY_TOKEN" ]; then
    error "Failed to generate Quay token."
    exit 1
fi
info "Quay token generated: $QUAY_TOKEN"

# --- Podman login for E2E push access ---
if command -v podman &>/dev/null; then
    info "Logging podman into local Quay registry..."
    podman login --tls-verify=false -u autopoc -p password localhost:8080 || warn "Podman login failed, build/push tests may fail."
else
    warn "Podman CLI not found on host. Skipping podman login."
fi

# --- Write .env.test ---
info "Writing credentials to $ENV_TEST_FILE"

cat > "$ENV_TEST_FILE" <<EOF
# Auto-generated by scripts/setup-e2e.sh — do not commit
# Local E2E test credentials for AutoPoC

ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-sk-ant-placeholder}

GITLAB_URL=$GITLAB_URL
GITLAB_TOKEN=$TOKEN_VALUE
GITLAB_GROUP=$GITLAB_GROUP

QUAY_REGISTRY=http://localhost:8080
QUAY_ORG=autopoc-test
QUAY_TOKEN=$QUAY_TOKEN

OPENSHIFT_API_URL=https://localhost:6443
OPENSHIFT_TOKEN=not-needed-yet
OPENSHIFT_NAMESPACE_PREFIX=poc-test

MAX_BUILD_RETRIES=3
WORK_DIR=/tmp/autopoc-e2e
EOF

info "Setup complete!"
echo ""
info "GitLab CE is running at: $GITLAB_URL"
info "Root password: $GITLAB_ROOT_PASSWORD"
info "API token: $TOKEN_VALUE"
info "Group: $GITLAB_GROUP"
echo ""
info "To run E2E tests:"
info "  source .venv/bin/activate"
info "  pytest tests/e2e/ --e2e -v"
echo ""
info "To tear down:"
info "  ./scripts/teardown-e2e.sh"
