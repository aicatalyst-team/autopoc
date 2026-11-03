#!/usr/bin/env python3
"""AutoPoC test script for the Omnigent server PoC on OpenShift.

Validates the deployed control plane over the OpenShift Route using only the
Python standard library. All five scenarios hit pre-auth endpoints, so no login
flow is required.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

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
                response_body = resp.read().decode(errors="replace")
                if status == expected_status:
                    if expected_content and expected_content not in response_body:
                        r = {"scenario_name": name, "status": "fail",
                             "output": response_body[:2000],
                             "error_message": f"Expected '{expected_content}' not in response",
                             "description": description,
                             "duration_seconds": round(time.time() - start, 2)}
                    else:
                        r = {"scenario_name": name, "status": "pass",
                             "output": response_body[:2000], "error_message": None,
                             "description": description,
                             "duration_seconds": round(time.time() - start, 2)}
                    results.append(r)
                    return r
                elif attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    r = {"scenario_name": name, "status": "fail",
                         "output": response_body[:2000],
                         "error_message": f"Expected {expected_status}, got {status}",
                         "description": description,
                         "duration_seconds": round(time.time() - start, 2)}
                    results.append(r)
                    return r
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode(errors="replace") if hasattr(e, "read") else ""
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            r = {"scenario_name": name, "status": "fail",
                 "output": (body_txt or "")[:2000],
                 "error_message": f"Expected {expected_status}, got HTTP {e.code}",
                 "description": description,
                 "duration_seconds": round(time.time() - start, 2)}
            results.append(r)
            return r
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  {name}: retry {attempt+1}/{MAX_RETRIES}: {e}", file=sys.stderr)
                time.sleep(RETRY_DELAY)
            else:
                r = {"scenario_name": name, "status": "error", "output": "",
                     "error_message": f"Unreachable after {MAX_RETRIES} attempts: {e}",
                     "description": description,
                     "duration_seconds": round(time.time() - start, 2)}
                results.append(r)
                return r
        except Exception as e:
            r = {"scenario_name": name, "status": "error", "output": "",
                 "error_message": str(e), "description": description,
                 "duration_seconds": round(time.time() - start, 2)}
            results.append(r)
            return r


if not SERVICE_URL:
    print(json.dumps({"results": [], "error": "No SERVICE_URL provided (arg or env)"}))
    sys.exit(1)

# === SCENARIOS (from poc-plan.md) ===
test_scenario("health-check",
              "Bare liveness + backing-store path",
              "GET", "/health",
              expected_status=200, expected_content="ok")

test_scenario("version-info",
              "Confirm omnigent package installed in the UBI image",
              "GET", "/api/version",
              expected_status=200, expected_content="version")

test_scenario("server-info",
              "Unauthenticated server capability/info endpoint",
              "GET", "/v1/info",
              expected_status=200, expected_content="server_version")

test_scenario("web-ui",
              "React SPA bundle served at the root",
              "GET", "/",
              expected_status=200, expected_content="html")

test_scenario("login-page",
              "Auth login page reachable (pre-auth surface)",
              "GET", "/login",
              expected_status=200, expected_content="html")
# === END SCENARIOS ===

passed = sum(1 for r in results if r["status"] == "pass")
print(json.dumps({"results": results,
                  "summary": {"total": len(results), "passed": passed,
                              "failed": len(results) - passed}}, indent=2))
sys.exit(1 if any(r["status"] in ("fail", "error") for r in results) else 0)
