# Error Triage for Apply Failures

When Phase 8 (Apply) fails, classify the error to determine the correct retry route.

## Deterministic Classification (check first)

These patterns can be classified without LLM analysis:

### fix-manifest (back to Phase 7: Deploy)

| Error Pattern | Meaning |
|---------------|---------|
| `forbidden:` or `cannot patch` or `cannot get` or `cannot create` | RBAC permission error |
| `namespace "X" not found` or `namespaces "X" not found` | Namespace doesn't exist |
| `field is immutable` or `field is forbidden` | Manifest field conflict |
| `is invalid:` | Manifest validation error |
| `already exists` (on create, not apply) | Resource conflict |

### fix-dockerfile (back to Phase 5: Containerize)

| Error Pattern | Meaning |
|---------------|---------|
| `CrashLoopBackOff` | Container keeps crashing |
| `ImagePullBackOff` or `ErrImagePull` | Can't pull the image |
| `command not found` (in pod logs) | Missing binary in container |
| `exec format error` | Wrong architecture or binary format |
| `ModuleNotFoundError` or `ImportError` (in pod logs) | Missing Python module |
| `No such file or directory` (in entrypoint) | Wrong CMD/ENTRYPOINT |
| `Permission denied` (on executable) | File permissions in container |
| `OOMKilled` | Container needs more memory (fix resource requests) |

## Ambiguous Errors

For errors that don't match the patterns above, analyze the error message:

1. **Check pod logs**: `kubectl logs <pod> -n <namespace>`
2. **Check pod events**: `kubectl describe pod <pod> -n <namespace>`
3. Determine if the issue is:
   - In the **manifest** (wrong config, missing env vars, wrong port) -> fix-manifest
   - In the **container** (missing dependency, wrong entrypoint, crash) -> fix-dockerfile
   - **Infrastructure** (node not ready, PVC not bound) -> fix-manifest

## Action Mapping

| Classification | Action | Route To | Counter |
|---------------|--------|----------|---------|
| fix-manifest | Fix K8s manifests | Phase 7 (Deploy) | deploy_retries |
| fix-dockerfile | Fix Dockerfile | Phase 5 (Containerize) | container_fix_retries |
| experiment | Try alternate Dockerfile | Phase 5 (with experiment tag) | container_fix_retries |

## Last Resort Escalation

If `deploy_retries` is exhausted but `container_fix_retries` is not:
- Escalate from fix-manifest to fix-dockerfile
- The assumption is that the manifest changes alone can't fix the problem
- Route to Phase 5 with the accumulated error context
