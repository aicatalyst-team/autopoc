---
name: record-demo
description: Record a demo video of a completed PoC deployment on OpenShift. Captures a side-by-side view of the OpenShift Console topology and a terminal running sanity tests. Uses Playwright headless with record_video_dir, ffmpeg hstack compositing, and ttyd in a container. Uploads to Google Drive. Use this skill when asked to "record a demo", "create a demo video", or "capture a demo" for an existing PoC project.
---

# Record-Demo Skill

Record a short demo video for a completed PoC deployment. The video captures a
side-by-side view of the OpenShift Console (Topology view) and a web terminal
running the PoC sanity tests.

## Prerequisites

- A completed PoC run with `poc-state.yaml` present in the working directory.
- The PoC deployment is still active on the cluster (pods running, services
  accessible).
- Required environment variables are set (see Phase 1).

## Invocation

This skill is triggered by the `record-demo` launcher script:

```bash
scripts/record-demo.sh <project-name>
```

Or directly via OpenCode:

```
Record demo video for <project-name>
```

The skill expects `AUTOPOC_PROJECT_NAME` to be set in the environment.

---

## Phase 1: Validate ✦ MANDATORY

**Goal:** Confirm all prerequisites are met before generating the recording
script.

### Steps

1. **Read `poc-state.yaml`** from `$AUTOPOC_WORK_DIR/poc-state.yaml`.
   - FAIL if the file does not exist.
   - FAIL if `poc_execute.status` is not `completed`.
   - WARN if `poc_execute.results` contains any `fail` or `error` scenarios
     (recording will still proceed — failed tests are valid demo content).

2. **Extract required context from state:**
   - `project.name` — project name.
   - `apply.namespace` — Kubernetes namespace where the PoC is deployed.
   - `apply.routes` — any routes/URLs exposed by the deployment.
   - `poc_execute.test_script_path` — path to the test script.
   - `poc_execute.results` — test scenario names and outcomes.
   - `intake.components` — component names and ports.
   - `intake.repo_summary` — brief project description.

3. **Verify the deployment is still alive:**
   ```bash
   kubectl get pods -n <namespace> --no-headers
   ```
   - FAIL if no pods are running.
   - Log the pod names and statuses.

4. **Verify required environment variables:**
   - `OPENSHIFT_CONSOLE_URL` — console URL (injected by `record-demo.sh`).
   - `OPENSHIFT_CONSOLE_USERNAME` — for console login.
   - `OPENSHIFT_CONSOLE_PASSWORD` — for console login.
   - `OPENSHIFT_IDP_NAME` — identity provider name (default: `keycloak`).
   - FAIL if console credentials or console URL are missing.

5. **Grant the console user view access to the PoC namespace:**
   The console user needs `view` access to see the Topology view.
   This is done per-recording since each PoC uses a different namespace.
   ```bash
   oc adm policy add-role-to-user view "$OPENSHIFT_CONSOLE_USERNAME" -n <namespace>
   ```
   This uses the pod's ServiceAccount (autopoc-runner) which has permission
   to create RoleBindings.

6. **Verify console is reachable:**
   ```bash
   curl -sSk -o /dev/null -w '%{http_code}' "$OPENSHIFT_CONSOLE_URL"
   ```
   Expect a redirect (302) or success (200).

7. **Check for blog post or PoC report** (optional context):
   - Look for `blog_post.blog_path` or `poc_report.report_path` in state.
   - If present, read the file for additional narrative context when generating
     the script. This is optional — the recording works without it.

8. **Set state:**
   ```yaml
   demo_video:
     status: "in_progress"
   ```

### Failure Behavior

If validation fails, set:
```yaml
demo_video:
  status: "failed"
```
And add an error entry. Do NOT proceed to Phase 2.

---

## Phase 2: Script ✦ MANDATORY

**Goal:** Generate a Playwright Python script that automates the recording.

### Context for Script Generation

Load the reference template from `references/recording-script-template.md`.
This template provides the complete structure. You **customize** the following
project-specific parts:

- **Console URL and namespace** for the Topology view.
- **Login credentials** and IDP name.
- **Terminal commands** — the test script path and any setup commands.
- **Wait conditions** — what patterns to look for in terminal output to know
  tests are done (e.g., `"passed"`, `"failed"`, `"results"`).
- **Timing** — how long to pause on the topology view, how long tests take.

### Script Generation Rules

1. **Read** `references/recording-script-template.md` for the script structure.
2. **Read** `references/auth-providers.md` for the login implementation.
3. **Generate** a complete Python script at
   `$AUTOPOC_WORK_DIR/<project>/demo/record.py`.
4. The script MUST be **self-contained** — no imports from the autopoc package.
   It should only depend on:
   - `playwright` (Python package, pre-installed in the container).
   - Python stdlib (`subprocess`, `time`, `os`, `signal`, `json`, `pathlib`).
5. The script MUST handle cleanup (kill ttyd) even on failure.
   No Xvfb or ffmpeg processes to manage during recording — Playwright records
   each context natively via `record_video_dir`, and ffmpeg runs only once as
   a post-processing step.
6. The script MUST exit with code 0 on success, non-zero on failure.

### What the Script Does

The generated script follows this sequence:

```
1. Start ttyd on port 7681 (writable mode, bash shell)
2. Wait 2s for ttyd to initialize
3. Launch Chromium via Playwright in headless mode (no display needed)
4. Create two browser contexts with record_video_dir:
   - Context 1 (left pane):  viewport 960x1080, records to left.webm
   - Context 2 (right pane): viewport 960x1080, records to right.webm
5. Context 1: Navigate to console → login → topology view
   - Wait for topology to render
   - Pause 5s to show the topology
6. Context 2: Navigate to ttyd (http://localhost:7681)
   - Wait for terminal prompt
   - Type and execute the test commands
   - Wait for tests to complete
7. Pause 5s to show final state (both contexts still recording)
8. Close both contexts (this finalizes the WebM recordings)
9. Close the browser
10. Kill ttyd
11. Run ffmpeg hstack to composite left.webm + right.webm → demo.webm (1920x1080)
12. Output the video path
```

### Output

- File: `$AUTOPOC_WORK_DIR/<project>/demo/record.py`
- Update state:
  ```yaml
  demo_video:
    script_path: "<path to record.py>"
  ```

---

## Phase 3: Record ✦ MANDATORY

**Goal:** Execute the Playwright script to produce the demo video.

### Steps

1. **Create the output directory:**
   ```bash
   mkdir -p $AUTOPOC_WORK_DIR/<project>/demo
   ```

2. **Install Playwright browsers** (if not already installed):
   ```bash
   playwright install chromium
   ```
   Note: In the container image, browsers are pre-installed. This step is a
   safety net.

3. **Execute the recording script:**
   ```bash
   python $AUTOPOC_WORK_DIR/<project>/demo/record.py
   ```
   - No `DISPLAY` variable needed — Playwright runs in headless mode.
   - Timeout: **10 minutes** maximum. If the script hasn't finished, kill it.

4. **Verify the output:**
   - Check that `demo.webm` exists at the expected path.
   - Check file size is reasonable (> 100KB, < 500MB).
   - Optionally probe with ffmpeg:
     ```bash
     ffprobe -v quiet -print_format json -show_format demo.webm
     ```

5. **Update state:**
   ```yaml
   demo_video:
     video_path: "<path to demo.webm>"
     duration_seconds: <from ffprobe>
     resolution: "1920x1080"
     format: "webm"
   ```

### Failure Handling

If the recording script fails:
1. Check stderr/stdout for error messages.
2. Common failures:
   - **Console login failed**: Check credentials, IDP name, console URL.
   - **Topology didn't load**: Namespace might be wrong, or no resources in the
     namespace. Verify with `kubectl get all -n <namespace>`.
   - **ttyd connection failed**: ttyd might not have started. Check if port 7681
     is listening.
   - **ffmpeg hstack failed**: Check that both per-context WebM files were
     created. Verify libvpx codec is available.
   - **Timeout**: Tests took too long. Consider reducing test scope or
     increasing the timeout.
3. Set `demo_video.status: "failed"` and add error to `errors[]`.
4. Do NOT retry automatically — the user should review the error and re-run.

---

## Phase 4: Upload ✦ NON-BLOCKING

**Goal:** Upload the recorded video to Google Drive.

### Steps

1. **Check prerequisites:**
   - `demo_video.video_path` exists and is a valid file.
   - `AUTOPOC_SHEET_CREDENTIALS` or credentials path is available.
   - `GOOGLE_DOCS_FOLDER_ID` is set (upload to same folder as blog docs).

2. **Upload using the CLI tool:**
   ```bash
   python -m autopoc.cli_tools google-drive-upload \
     <video_path> \
     --file-name "[AutoPoC] <project_name> Demo Video" \
     --credentials <credentials_path> \
     --folder-id <folder_id>
   ```

3. **Parse the JSON output** for the Drive URL.

4. **Update state:**
   ```yaml
   demo_video:
     drive_url: "<Google Drive URL>"
   ```

### Failure Handling

If upload fails:
- Log the error but do NOT fail the pipeline.
- The video is still available locally at `demo_video.video_path`.
- Set `demo_video.drive_url: "upload_failed"`.

---

## Phase 5: Update ✦ MANDATORY

**Goal:** Finalize the state file and report results.

### Steps

1. **Update `poc-state.yaml`:**
   ```yaml
   demo_video:
     status: "completed"
   ```

2. **Write a summary** to stdout:
   ```
   === Demo Video Recording Complete ===
   Project:    <project_name>
   Video:      <video_path>
   Duration:   <duration>s
   Resolution: 1920x1080
   Format:     WebM
   Drive URL:  <drive_url or "not uploaded">
   ```

3. **Commit state** (if in a git repo context):
   ```bash
   cd $AUTOPOC_WORK_DIR && git add poc-state.yaml && \
     git commit -m "record-demo: completed for <project_name>"
   ```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AUTOPOC_PROJECT_NAME` | Yes | — | Project name |
| `AUTOPOC_WORK_DIR` | No | `/tmp/autopoc` | Working directory |
| `OPENSHIFT_CONSOLE_URL` | Yes | — | Console URL (injected by `record-demo.sh`) |
| `OPENSHIFT_CONSOLE_USERNAME` | Yes | — | Console login username |
| `OPENSHIFT_CONSOLE_PASSWORD` | Yes | — | Console login password |
| `OPENSHIFT_IDP_NAME` | No | `keycloak` | IDP button name on OAuth page |
| `AUTOPOC_SHEET_CREDENTIALS` | No | — | Path to Google SA credentials |
| `GOOGLE_DOCS_FOLDER_ID` | No | — | Google Drive folder for upload |

`OPENSHIFT_API_URL` and `OPENSHIFT_TOKEN` are NOT needed when running as a
pod. kubectl/oc use the mounted ServiceAccount token automatically.
`OPENSHIFT_CONSOLE_URL` is derived by `record-demo.sh` from the caller's
`oc` session and injected into the Job manifest.

---

## Fallback: Sequential Recording

If the side-by-side compositing produces unexpected results (e.g., mismatched
durations between the two context recordings), fall back to a **sequential**
recording using a single browser context with `record_video_dir`:

1. Record the OpenShift Console topology view (full viewport, ~15s).
2. Navigate the same page to the ttyd terminal.
3. Run the tests and record until completion.

This produces a single video with a natural page navigation transition. No
ffmpeg compositing step is needed. Modify the generated script to use a single
browser context instead of two.

The LLM should note this option in the generated script as a commented-out
alternative path.
