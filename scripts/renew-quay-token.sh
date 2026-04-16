#!/usr/bin/env bash
#
# Renew the Quay OAuth token and update .env accordingly.
#
# This script:
#   1. Checks the local Quay container is running and healthy
#   2. Generates a new OAuth access token via Quay's internal Python API
#   3. Verifies the token works against the Quay API
#   4. Updates QUAY_TOKEN in .env (and .env.test if it exists)
#
# Usage:
#   ./scripts/renew-quay-token.sh
#
# Prerequisites:
#   - The autopoc-quay container must be running (docker-compose.test.yml)
#   - curl must be installed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
ENV_TEST_FILE="$PROJECT_DIR/.env.test"

QUAY_CONTAINER="autopoc-quay"
QUAY_URL="http://localhost:8080"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# --- Preflight checks ---

if ! docker ps --format '{{.Names}}' | grep -q "^${QUAY_CONTAINER}$"; then
    error "Container '$QUAY_CONTAINER' is not running."
    error "Start it with: docker compose -f docker-compose.test.yml up -d"
    exit 1
fi

HTTP_CODE=$(curl -so /dev/null -w '%{http_code}' "$QUAY_URL/health/instance" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
    error "Quay is not healthy (HTTP $HTTP_CODE). Wait for it to start."
    exit 1
fi

info "Quay container is running and healthy."

# --- Read the old token (for display) ---
OLD_TOKEN=""
if [ -f "$ENV_FILE" ]; then
    OLD_TOKEN=$(grep -E '^QUAY_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)
fi

# --- Generate a new token via Quay's internal Python API ---
info "Generating new OAuth token inside Quay container..."

# The Python script runs inside the Quay container where Quay's full
# codebase is available.  It creates (or reuses) the autopoc user,
# the autopoc-test org, and the E2E OAuth application, then mints a
# fresh token with all scopes and a 10-year expiry.
SETUP_SCRIPT=$(cat << 'PYEOF'
import sys, os, logging
sys.path.insert(0, '/quay-registry')
os.chdir('/quay-registry')
logging.basicConfig(level=logging.ERROR)

from app import app
from data.model import user, organization, oauth
import auth.scopes

with app.app_context():
    # Ensure user exists
    u = user.get_user("autopoc")
    if not u:
        u = user.create_user("autopoc", "password", "test@autopoc.com")

    # Ensure org exists
    org = user.get_namespace_user("autopoc-test")
    if not org:
        org = organization.create_organization("autopoc-test", "org@autopoc.com", u)

    # Ensure OAuth application exists
    app_name = "AutoPoC E2E App"
    apps = oauth.list_applications_for_org(org)
    my_app = next((a for a in apps if a.name == app_name), None)
    if not my_app:
        my_app = oauth.create_application(org, app_name, "http://localhost", "http://localhost")

    # Generate a new token with all scopes, 10-year expiry
    all_scopes_str = ",".join(auth.scopes.ALL_SCOPES.keys())
    token_str = oauth.random_string_generator(40)()
    oauth.create_user_access_token(
        u,
        my_app.client_id,
        all_scopes_str,
        access_token=token_str,
        expires_in=315360000,  # ~10 years
    )
    print(token_str)
PYEOF
)

# Copy the script into the container and run it
echo "$SETUP_SCRIPT" | docker exec -i "$QUAY_CONTAINER" bash -c 'cat > /tmp/_renew_token.py'
NEW_TOKEN=$(docker exec "$QUAY_CONTAINER" python3 /tmp/_renew_token.py 2>/dev/null | tr -d '\r\n')
docker exec "$QUAY_CONTAINER" rm -f /tmp/_renew_token.py

if [ -z "$NEW_TOKEN" ]; then
    error "Failed to generate token. Run with DEBUGLOG to see errors:"
    error "  docker exec $QUAY_CONTAINER python3 /tmp/_renew_token.py"
    exit 1
fi

info "New token generated: ${NEW_TOKEN:0:10}..."

# --- Verify the new token works ---
info "Verifying new token against Quay API..."

VERIFY_CODE=$(curl -so /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $NEW_TOKEN" \
    "$QUAY_URL/api/v1/user/" 2>/dev/null || echo "000")

if [ "$VERIFY_CODE" != "200" ]; then
    error "Token verification failed (HTTP $VERIFY_CODE)."
    error "The token was generated but does not authenticate."
    exit 1
fi

VERIFY_USER=$(curl -sf -H "Authorization: Bearer $NEW_TOKEN" \
    "$QUAY_URL/api/v1/user/" 2>/dev/null | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('username','???'))" 2>/dev/null || echo "???")

info "Token verified: authenticates as user '$VERIFY_USER'."

# --- Update .env ---
update_env_file() {
    local file="$1"
    local token="$2"

    if [ ! -f "$file" ]; then
        return 1
    fi

    if grep -q '^QUAY_TOKEN=' "$file"; then
        # Replace existing QUAY_TOKEN line
        sed -i "s|^QUAY_TOKEN=.*|QUAY_TOKEN=${token}|" "$file"
        return 0
    else
        # Append if not present
        echo "QUAY_TOKEN=${token}" >> "$file"
        return 0
    fi
}

if update_env_file "$ENV_FILE" "$NEW_TOKEN"; then
    info "Updated $ENV_FILE"
else
    warn "$ENV_FILE not found, skipping."
fi

if update_env_file "$ENV_TEST_FILE" "$NEW_TOKEN"; then
    info "Updated $ENV_TEST_FILE"
fi

# --- Summary ---
echo ""
info "Quay token renewed successfully."
if [ -n "$OLD_TOKEN" ]; then
    info "  Old: ${OLD_TOKEN:0:10}..."
fi
info "  New: ${NEW_TOKEN:0:10}..."
info ""
info "Note: Old tokens remain valid until they expire."
info "      To revoke them, delete rows from the oauthaccesstoken table"
info "      in the Quay database."
