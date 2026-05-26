# Retry Strategy

This document defines the retry loops, error classification, and decision trees for the PoC pipeline.

## Three Retry Loops

### 1. Build Retry Loop (Phase 5 <-> Phase 6)

```
Phase 5: Containerize -> Phase 6: Build
                           |
                    [build fails]
                           |
                    Is it permanent? ----YES----> FAIL (stop pipeline)
                           |
                          NO
                           |
                    build_retries < max? --NO--> FAIL
                           |
                         YES
                           |
                    Increment build_retries
                    Record error in state
                           |
                    Go back to Phase 5 (with error context)
```

**Permanent build errors** (do NOT retry):
- Authentication failure (401, 403 from registry)
- Network unreachable (DNS resolution failure, connection refused to registry)
- `podman` / `buildah` not found (missing binary)
- Registry does not exist

**Retriable build errors** (loop back to Phase 5):
- Package not found (`pip install` / `npm install` / `dnf install` failure)
- COPY failed (file not found in build context)
- Build command failed (compilation error)
- Any other non-permanent error

### 2. Deploy Retry Loop (Phase 7 <-> Phase 8)

```
Phase 7: Deploy -> Phase 8: Apply
                      |
               [apply fails]
                      |
               Classify error (see error-triage.md)
                      |
        +-------------+-------------+
        |                           |
   fix-manifest                fix-dockerfile / experiment
        |                           |
   deploy_retries < max?     container_fix_retries < max?
        |                           |
       YES                        YES
        |                           |
   Increment deploy_retries   Increment container_fix_retries
   Back to Phase 7            Reset build_retries = 0
                              Reset deploy_retries = 0
                              Back to Phase 5
```

### 3. PoC Execute -> Container Fix (Phase 9 -> Phase 5)

```
Phase 9: PoC Execute
        |
   [test failures with container indicators]
        |
   container_fix_retries < max? --NO--> Continue to Phase 10
        |
       YES
        |
   Increment container_fix_retries
   Reset build_retries = 0
   Reset deploy_retries = 0
   Back to Phase 5
```

**Container issue indicators in test output:**
- "command not found"
- "ModuleNotFoundError" / "ImportError"
- "No module named"
- "CrashLoopBackOff"
- "exec format error"
- "Permission denied" (on executable)

## Decision Tree Summary

When an error occurs at Phase 6 (Build):
```
1. Is error permanent (auth/network/binary)? -> FAIL
2. Is build_retries < max_build_retries (default 3)? -> Increment, Phase 5
3. Otherwise -> FAIL
```

When an error occurs at Phase 8 (Apply):
```
1. Classify error (see error-triage.md)
2. If fix-manifest:
   a. Is deploy_retries < max_deploy_retries (default 3)? -> Increment, Phase 7
   b. Is container_fix_retries < max_container_fix_retries (default 2)? -> Escalate to Phase 5
   c. Otherwise -> FAIL
3. If fix-dockerfile or experiment:
   a. Is container_fix_retries < max_container_fix_retries? -> Increment, Phase 5, reset inner counters
   b. Otherwise -> FAIL
```

When a container issue is detected at Phase 9 (PoC Execute):
```
1. Is container_fix_retries < max_container_fix_retries? -> Increment, Phase 5, reset inner counters
2. Otherwise -> Continue to Phase 10 with partial results
```

## Counter Management

| Counter | Incremented by | Reset by | Default Max |
|---------|---------------|----------|-------------|
| `build_retries` | Phase 6 on retriable failure | Container fix loop entry (Phase 5 re-entry from 8/9) | 3 |
| `deploy_retries` | Phase 8 on fix-manifest | Container fix loop entry | 3 |
| `container_fix_retries` | Phase 8 on fix-dockerfile/experiment, Phase 9 on container issue | Never reset | 2 |
| `experiment_tag_counter` | Phase 6 when action is "experiment" | Never reset | N/A |

## Experiment Mode

When `container_fix_action` is "experiment":
- Build images with tag `:experiment-N` instead of `:latest`
- Preserves the known-working `:latest` image
- If experiment succeeds, the `:experiment-N` tag becomes the active image
- If experiment fails, can roll back to `:latest`

The `experiment_tag_counter` tracks the experiment number.
