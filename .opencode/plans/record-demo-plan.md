# Record-Demo Feature — Design & Implementation Plan

## Progress

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Skill & References | Pending | SKILL.md + 3 reference files |
| Phase 2: Infrastructure | Pending | Dockerfile, launcher script |
| Phase 3: Tools & Config | Pending | Google Drive upload, config fields, CLI |
| Phase 4: State & Integration | Pending | State schema, AGENTS.md, test stubs |

---

## Overview

The `record-demo` feature generates a short demo video for a completed PoC
deployment. The video captures a side-by-side view of the OpenShift Console
(Developer Perspective — Topology view) and a web terminal running the PoC
sanity tests.

**Key constraints:**
- This is a real screen recording, NOT AI-generated video.
- The AI generates the *script* (Playwright automation code) that drives the
  browser and terminal; the video is the faithful capture of that execution.
- Runs in a Kubernetes pod (headless, no physical display).
- Assumes the PoC is already deployed on the cluster.
- Uploads the final video to Google Drive.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  K8s Pod (autopoc-recorder image)                               │
│                                                                 │
│  ┌──────────────────┐        ┌──────────────────┐               │
│  │ Playwright        │        │ Playwright        │               │
│  │ Context 1         │        │ Context 2         │               │
│  │ (headless)        │        │ (headless)        │               │
│  │                   │        │                   │               │
│  │ OpenShift Console │        │ ttyd              │               │
│  │ Topology View     │        │ (web terminal)    │               │
│  │                   │        │                   │               │
│  │ record_video_dir  │        │ record_video_dir  │               │
│  │  ↓                │        │  ↓                │               │
│  │ left.webm         │        │ right.webm        │               │
│  └──────────────────┘        └──────────────────┘               │
│           │                           │                          │
│           └─────────┬─────────────────┘                          │
│                     ▼                                            │
│  ffmpeg -filter_complex hstack → demo.webm (1920x1080)          │
│                                                                 │
│  OpenCode agent (generates + runs Playwright script)            │
│  ttyd -W -p 7681 bash (web terminal server)                     │
└─────────────────────────────────────────────────────────────────┘
```

### Recording Pipeline

1. **OpenCode** loads the `record-demo` skill.
2. Discovers project context from the **live cluster** (pods, services, ports,
   images) via kubectl. Optionally fetches the PoC report or test script from
   the GitHub `autopoc-artifacts` branch for narrative context.
3. **Generates a Playwright Python script** (`record.py`) customized per project.
5. The script:
   - Starts **ttyd** (web terminal on `localhost:7681`).
   - Launches **Chromium** via Playwright in **headless** mode (no display needed).
   - Creates two browser contexts, each with `record_video_dir` set so
     Playwright records each context's viewport as a WebM file.
   - Context 1: OpenShift Console → login via Keycloak → Topology view.
   - Context 2: ttyd web terminal → runs PoC sanity tests.
   - Waits for test completion, pauses to show results.
   - Closes both contexts (this finalizes the per-context WebM recordings).
   - Runs **ffmpeg** with an `hstack` filter to composite the two recordings
     into a single side-by-side `demo.webm` (1920x1080).
6. **Uploads** the video to Google Drive.
7. **Uploads** the video to Google Drive and reports results.

---

## Tool Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| Browser automation | **Playwright** (Python, Chromium, headless) | Controls browser contexts, navigation, typing; records each context via `record_video_dir` |
| Video compositing | **ffmpeg** (`-filter_complex hstack`) | Composites two per-context WebM recordings into a single side-by-side video |
| Web terminal | **ttyd** | Serves a bash session over HTTP/WebSocket via xterm.js |
| Video format | **WebM** (VP9 codec) | Output format — good compression, web-compatible |
| Upload | **Google Drive API** | Resumable upload of video to shared Drive folder |

### Why This Stack

- **Playwright headless + `record_video_dir`** (vs Xvfb + x11grab): Playwright
  natively records each browser context's viewport as a WebM file in headless
  mode. No virtual display (Xvfb), no screen capture (x11grab), no window
  positioning via CDP or JavaScript. Each context records independently, and
  ffmpeg composites them afterward with a simple `hstack` filter. This is
  simpler, more reliable in containers, and eliminates an entire class of
  positioning/display bugs.

- **ttyd** (vs VHS): Playwright controls everything — both the console and the
  terminal — in a single Python script. No separate `.tape` file, no VHS binary.
  xterm.js in the browser renders beautiful colored terminal output.

- **LLM-generated script** (vs static template): Each PoC has different test
  commands, different topology, different number of pods. The LLM customizes the
  script using a detailed reference template.

- **Separate container image**: Browser/video dependencies add ~400MB+. Keeping
  them out of the main autopoc image avoids bloating the PoC pipeline.

---

## Components

### 1. Skill — `.opencode/skills/record-demo/`

```
record-demo/
├── SKILL.md                              # Main skill instructions (5 phases)
└── references/
    ├── recording-script-template.md      # Playwright script reference/template
    ├── auth-providers.md                 # Login provider docs (Keycloak first)
    └── state-schema.md                   # demo_video state section schema
```

**5 Phases:**

| # | Phase | Classification | Purpose |
|---|-------|---------------|---------|
| 1 | Validate | MANDATORY | Discover deployment from cluster, verify health, check env vars |
| 2 | Script | MANDATORY | Generate Playwright recording script |
| 3 | Record | MANDATORY | Execute script, produce demo.webm |
| 4 | Upload | NON-BLOCKING | Upload video to Google Drive |
| 5 | Report | MANDATORY | Write summary of results |

### 2. Container Image — `Dockerfile.record-demo`

Separate image based on UBI9 with additional dependencies:

| Dependency | Purpose | Approx Size |
|------------|---------|-------------|
| Chromium (via Playwright) | Browser for automation (headless) | ~400MB |
| Playwright Python | Browser control + per-context video recording | ~5MB |
| ffmpeg | Video compositing (hstack two WebMs side-by-side) | ~80MB |
| ttyd | Web-based terminal server | ~2MB |
| kubectl, oc | Cluster CLI operations | ~120MB (shared with base) |
| OpenCode | Agent harness | ~50MB (shared with base) |
| Python + autopoc tools | Config, Drive upload | ~200MB (shared with base) |

Estimated total: ~850MB — 1.1GB.

### 3. Launcher Script — `scripts/record-demo.sh`

```bash
scripts/record-demo.sh <project-name> [options]
```

Generates a K8s Job that:
- Uses the `autopoc-recorder` image.
- Discovers PoC context from the live cluster (pods, services, ports).
- Mounts `autopoc-credentials` + video-specific credentials.
- Sets OpenCode prompt: `"Record demo video for <project-name>"`.
- Higher resource limits: 1Gi–4Gi memory (Chromium headless + ffmpeg compositing).

### 4. Google Drive Upload Tool — `src/autopoc/tools/google_drive_tools.py`

New module for uploading binary files (video) to Google Drive:
- Uses `MediaFileUpload` with `resumable=True`.
- MIME type: `video/webm`.
- No new OAuth scopes needed (`drive.file` is sufficient).
- Reuses existing service-account credential infrastructure.

### 5. CLI Command — `google-drive-upload`

New subcommand in `src/autopoc/cli_tools.py`:

```bash
python -m autopoc.cli_tools google-drive-upload \
  /path/to/demo.webm \
  --file-name "ProjectName Demo" \
  --credentials /path/to/sa.json \
  --folder-id <folder-id>
```

### 6. Config Fields — `src/autopoc/config.py`

New optional fields for OpenShift Console authentication:

```python
openshift_idp_name: str = "keycloak"
openshift_console_username: str | None = None
openshift_console_password: str | None = None
```

### 7. Output Artifacts

The recording produces:
- `$AUTOPOC_WORK_DIR/<project>/demo/record.py` — generated Playwright script
- `$AUTOPOC_WORK_DIR/<project>/demo/poc_test.sh` — generated test script
- `$AUTOPOC_WORK_DIR/<project>/demo/demo.webm` — final composited video
- Google Drive URL (if upload succeeds)

---

## Authentication Strategy

### Pluggable Auth Design

Login is implemented as a function with a provider dispatch:

```python
def login_to_console(page, console_url, idp_name, username, password):
    """Navigate to console, handle OAuth redirect, authenticate via IDP."""
```

**Keycloak provider** (first implementation):
1. Navigate to `console_url`.
2. Get redirected to OpenShift OAuth page.
3. Click the button matching `idp_name` (e.g., "keycloak").
4. Get redirected to Keycloak login form.
5. Fill `#username` and `#password`, click `#kc-login`.
6. Get redirected back to the console.

**Future providers** (not in scope now):
- htpasswd: Enter username/password directly on OAuth page.
- kubeadmin: Select kubeadmin IDP, enter password.

### Credentials

| Env Var | Purpose |
|---------|---------|
| `OPENSHIFT_IDP_NAME` | IDP button text on OAuth page (default: `keycloak`) |
| `OPENSHIFT_CONSOLE_USERNAME` | Username for the IDP login form |
| `OPENSHIFT_CONSOLE_PASSWORD` | Password for the IDP login form |

---

## Console URL Derivation

The OpenShift Console URL is derived from `OPENSHIFT_API_URL`:

```python
# OPENSHIFT_API_URL = "https://api.mycluster.example.com:6443"
# Console URL = "https://console-openshift-console.apps.mycluster.example.com"
```

Fallback: query the cluster directly:
```bash
oc get consoles.config.openshift.io cluster -o jsonpath='{.status.consoleURL}'
```

### Topology View URL

```
{console_url}/topology/ns/{namespace}
```

Where `namespace` is `poc-<project-name>`, derived from `AUTOPOC_PROJECT_NAME`.

---

## Video Specifications

| Property | Value |
|----------|-------|
| Resolution | 1920x1080 (Full HD) |
| Format | WebM (VP9 codec) |
| Layout | Side-by-side: 960x1080 per pane |
| Left pane | OpenShift Console — Topology view |
| Right pane | ttyd web terminal — running tests |
| Text overlays | None (raw capture) |
| Audio | None |
| Expected duration | 2–5 minutes |
| Expected file size | 20–50 MB |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenShift Console DOM changes between OCP versions | Broken selectors | Use `data-test` attributes (OCP's own e2e convention); document version-tested |
| Keycloak login form theme varies | Login automation fails | Use standard element IDs (`#username`, `#password`, `#kc-login`) which are stable across themes |
| High resource usage (Chromium headless + ffmpeg) | Pod OOM | Set generous limits (4Gi memory); profile and tune. Headless mode uses less memory than Xvfb + headed browser |
| Long-running tests extend video duration | Large files, timing issues | Use `PlaybackSpeed` in ffmpeg or cap recording duration |
| ttyd not available in UBI repos | Build failure | Install from GitHub releases binary |
| Playwright `record_video_dir` output resolution | Video quality varies | Set explicit `record_video_size` in context options to ensure 960x1080 per pane |

> **Note:** The headless recording approach (Playwright `record_video_dir` +
> ffmpeg hstack) is significantly simpler than the previous Xvfb + x11grab
> design. It eliminates virtual display management, window positioning (CDP),
> and real-time screen capture. Each browser context records independently,
> and compositing is a single ffmpeg post-processing step.

---

## Open Questions

1. **Video post-processing**: Should we trim dead time (e.g., waiting for
   login redirects)? Could use ffmpeg to speed up or cut segments. Deferred to
   future iteration.

2. **Playwright video codec control**: Playwright's `record_video_dir` uses
   VP8 by default. The ffmpeg hstack step can re-encode to VP9 for better
   compression. Verify quality and file size tradeoffs.
