# PoC Execute Phase Instructions

Generate and run a Python test script that validates the deployed PoC service.

## Test Script Requirements

- **Python stdlib only** -- use `urllib.request`, no `requests` or `httpx`
- Accept service URL as CLI argument or `SERVICE_URL` env var
- Implement each scenario from the PoC plan
- Include retry logic (services may take 30-60s to become ready)
- Output structured JSON results to stdout
- Exit 0 if all pass, 1 if any fail

## Test Script Template

```python
#!/usr/bin/env python3
"""AutoPoC Test Script"""
import json, os, sys, time, urllib.request, urllib.error

SERVICE_URL = os.environ.get("SERVICE_URL", sys.argv[1] if len(sys.argv) > 1 else "")
MAX_RETRIES = 5
RETRY_DELAY = 10
results = []

def test_scenario(name, description, method, path, body=None,
                  expected_status=200, expected_content=None, timeout=30):
    url = f"{SERVICE_URL.rstrip('/')}{path}"
    start = time.time()
    for attempt in range(MAX_RETRIES):
        try:
            if body:
                data = json.dumps(body).encode() if isinstance(body, dict) else body.encode()
                req = urllib.request.Request(url, data=data, method=method)
                req.add_header("Content-Type", "application/json")
            else:
                req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                response_body = resp.read().decode()
                if status == expected_status:
                    if expected_content and expected_content not in response_body:
                        r = {"scenario_name": name, "status": "fail",
                             "output": response_body[:2000],
                             "error_message": f"Expected '{expected_content}' not in response",
                             "duration_seconds": round(time.time()-start, 2)}
                    else:
                        r = {"scenario_name": name, "status": "pass",
                             "output": response_body[:2000], "error_message": None,
                             "duration_seconds": round(time.time()-start, 2)}
                    results.append(r); return r
                elif attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY); continue
                else:
                    r = {"scenario_name": name, "status": "fail",
                         "output": response_body[:2000],
                         "error_message": f"Expected {expected_status}, got {status}",
                         "duration_seconds": round(time.time()-start, 2)}
                    results.append(r); return r
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  Retry {attempt+1}/{MAX_RETRIES}: {e}", file=sys.stderr)
                time.sleep(RETRY_DELAY)
            else:
                r = {"scenario_name": name, "status": "error", "output": "",
                     "error_message": f"Unreachable after {MAX_RETRIES} attempts: {e}",
                     "duration_seconds": round(time.time()-start, 2)}
                results.append(r); return r
        except Exception as e:
            r = {"scenario_name": name, "status": "error", "output": "",
                 "error_message": str(e),
                 "duration_seconds": round(time.time()-start, 2)}
            results.append(r); return r

# === SCENARIOS ===
# Fill in based on poc_plan.scenarios from state

# === END SCENARIOS ===

print(json.dumps({"results": results}, indent=2))
sys.exit(1 if any(r["status"] in ("fail", "error") for r in results) else 0)
```

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
