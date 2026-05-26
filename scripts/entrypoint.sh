#!/usr/bin/env bash
# Debug entrypoint -- dumps environment and config before running OpenCode.
set -euo pipefail

echo "=== AutoPoC OpenCode Entrypoint ==="
echo "Date: $(date -u)"
echo "Hostname: $(hostname)"
echo "User: $(id)"
echo "PWD: $(pwd)"
echo

echo "=== OpenCode version ==="
opencode --version 2>&1 || echo "opencode --version failed"
echo

echo "=== Key env vars ==="
echo "GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT:-<not set>}"
echo "VERTEX_PROJECT=${VERTEX_PROJECT:-<not set>}"
echo "VERTEX_LOCATION=${VERTEX_LOCATION:-<not set>}"
echo "GOOGLE_APPLICATION_CREDENTIALS=${GOOGLE_APPLICATION_CREDENTIALS:-<not set>}"
echo "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:+set (${#ANTHROPIC_API_KEY} chars)}"
echo "AUTOPOC_WORK_DIR=${AUTOPOC_WORK_DIR:-<not set>}"
echo "BUILD_STRATEGY=${BUILD_STRATEGY:-<not set>}"
echo "PYTHONPATH=${PYTHONPATH:-<not set>}"
echo

echo "=== SA credentials file ==="
if [ -f "${GOOGLE_APPLICATION_CREDENTIALS:-/nonexistent}" ]; then
    echo "File exists: $GOOGLE_APPLICATION_CREDENTIALS"
    echo "Size: $(wc -c < "$GOOGLE_APPLICATION_CREDENTIALS") bytes"
    # Show just the project_id and client_email (not secrets)
    python3 -c "
import json, sys
with open('$GOOGLE_APPLICATION_CREDENTIALS') as f:
    d = json.load(f)
print(f\"  type: {d.get('type')}\")
print(f\"  project_id: {d.get('project_id')}\")
print(f\"  client_email: {d.get('client_email')}\")
" 2>&1 || echo "  (failed to parse JSON)"
else
    echo "FILE NOT FOUND: ${GOOGLE_APPLICATION_CREDENTIALS:-<not set>}"
    echo "Contents of /etc/autopoc/google-sa/:"
    ls -la /etc/autopoc/google-sa/ 2>&1 || echo "  directory does not exist"
fi
echo

echo "=== OpenCode config ==="
cat /opt/autopoc/opencode.json 2>&1 || echo "(no opencode.json)"
echo

echo "=== Skills ==="
find /opt/autopoc/.opencode/skills -name "SKILL.md" 2>/dev/null || echo "no skills found"
echo

echo "=== Starting OpenCode ==="
exec opencode "$@"
