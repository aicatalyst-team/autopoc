# PoC Execute Phase Instructions

Generate and run a Python test script that validates the deployed PoC service.

## Test Script Requirements

- **Python stdlib plus the installed AutoPoC capture helper** -- no `requests` or `httpx`
- Accept service URL as CLI argument or `SERVICE_URL` env var
- Implement each scenario from the PoC plan
- Include retry logic (services may take 30-60s to become ready)
- Output structured JSON results to stdout
- Exit 0 if all pass, 1 if any fail

## Test Script Template

Use the installed stdlib-only `autopoc.capture.AttemptRecorder` helper. It records every actual request before retrying; do not hide retries in stderr or retain response bodies.

```python
import json, os, sys
from autopoc.capture import AttemptRecorder

SERVICE_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SERVICE_URL", "")
recorder = AttemptRecorder.from_environment()
results = []

def test_scenario(name, description, method, path, body=None,
                  expected_status=200, expected_content=None, timeout=30):
    result = recorder.http(name, SERVICE_URL.rstrip("/") + path, method=method,
                           body=body, expected_status=expected_status,
                           expected_content=expected_content, timeout=timeout)
    results.append(result)
    return result

# Implement each planned scenario using its exact saved scenario name.
# Example: test_scenario("health", "Readiness", "GET", "/health")

print(json.dumps({"results": results}))
sys.exit(1 if any(r["status"] in ("fail", "error") for r in results) else 0)
```

Execute through `capture-execution --state "$WORK_DIR/poc-state.yaml" --script "$WORK_DIR/repos/$PROJECT_NAME/poc_test.py" --service-url "$SERVICE_URL"`. The wrapper assigns execution identity, keeps stdout JSON separate from private stderr, retains the test exit code and finalizes interrupted scenarios before retry/stop handling. Never redirect stderr into stdout.

For CLI/exec scenarios, call `recorder.record(name, "cli" or "exec", outcome, duration_seconds, error=sanitized_failure_category)` after each actual invocation, including each retry. Add only the terminal result for that scenario to stdout. Do not record commands, credentials or raw command output as failure text. Never synthesize attempt records from a final pass after the fact.

Keep planned names stable on retries. A changed test plan starts a new explicit run identity; do not silently mix different scenario sets.
## CLI Test Scenarios (for Jobs)

For `type: "cli"` scenarios, use kubectl to run the Job and check results:

```bash
# Apply the job manifest
kubectl apply -f kubernetes/{component}-{scenario}-job.yaml -n poc-{project_name}

# Wait for completion
kubectl wait --for=condition=complete job/{component}-{scenario} -n poc-{project_name} --timeout=120s

# Get logs
kubectl logs job/{component}-{scenario} -n poc-{project_name}

# Check exit code (succeeded vs failed)
kubectl get job/{component}-{scenario} -n poc-{project_name} -o jsonpath='{.status.succeeded}'
```

## Debugging Failures

If tests fail:
1. Check pod status: `kubectl get pods -n poc-{project_name}`
2. Check logs: `kubectl logs deployment/{component} -n poc-{project_name} --tail=50`
3. Check events: `kubectl describe pod -l app={component} -n poc-{project_name}`

## Container Issue Detection

After running tests, check if failures indicate container problems:
- "command not found" in test output or pod logs
- "ModuleNotFoundError" or "ImportError" in pod logs
- "CrashLoopBackOff" in pod status
- "exec format error" in pod events
- "No such file or directory" for entrypoint

If detected and `retries.container_fix_retries < retries.max_container_fix_retries`:
- Record the error with action `fix-dockerfile`
- Route back to Phase 5 (Containerize)

## Results Format

Update `poc_execute.results` in state with:
```yaml
results:
  - scenario_name: "health-check"
    status: "pass"          # pass | fail | error | skip
    output: "200 OK"
    error_message: null
    duration_seconds: 1.5
```
