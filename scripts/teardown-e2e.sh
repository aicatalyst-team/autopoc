#!/usr/bin/env bash
#
# Tear down local E2E test infrastructure for AutoPoC.
#
# This script:
#   1. Stops and removes all containers from docker-compose.test.yml
#   2. Removes volumes (GitLab data)
#   3. Removes the .env.test file
#
# Usage:
#   ./scripts/teardown-e2e.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.test.yml"
ENV_TEST_FILE="$PROJECT_DIR/.env.test"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $*"; }

# --- Detect compose command ---
if command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v podman-compose &>/dev/null; then
    COMPOSE_CMD="podman-compose"
else
    echo "No compose command found, attempting manual cleanup..."
    docker rm -f autopoc-gitlab 2>/dev/null || true
    exit 0
fi

# --- Stop and remove containers + volumes ---
info "Stopping and removing E2E test containers..."
$COMPOSE_CMD -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true

# --- Remove .env.test ---
if [ -f "$ENV_TEST_FILE" ]; then
    info "Removing $ENV_TEST_FILE"
    rm -f "$ENV_TEST_FILE"
fi

# --- Clean up work directory ---
if [ -d "/tmp/autopoc-e2e" ]; then
    info "Cleaning up /tmp/autopoc-e2e"
    rm -rf /tmp/autopoc-e2e
fi

info "Teardown complete."
