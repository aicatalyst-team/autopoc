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
- Assumes the PoC is already deployed (reads existing `poc-state.yaml`).
- Uploads the final video to Google Drive.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  K8s Pod (autopoc-recorder image)                           │
│                                                             │
│  ┌──────────────────────────────────────────────────┐       │
│  │  Xvfb (virtual display :99, 1920x1080)           │       │
│  │                                                  │       │
│  │  ┌──────────────┐  ┌───────────────────┐         │       │
│  │  │ Chromium      │  │ Chromium          │         │       │
│  │  │ Window 1      │  │ Window 2          │         │       │
│  │  │ (960x1080)    │  │ (960x1080)        │         │       │
│  │  │               │  │                   │         │       │
│  │  │ OpenShift     │  │ ttyd              │         │       │
│  │  │ Console       │  │ (web terminal)    │         │       │
│  │  │ Topology View │  │ Running tests     │         │       │
│  │  │               │  │                   │         │       │
│  │  └──────────────┘  └───────────────────┘         │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  ffmpeg -f x11grab -i :99 → demo.webm                      │
│                                                             │
│  OpenCode agent (generates + runs Playwright script)        │
│  ttyd -W -p 7681 bash (web terminal server)                 │
└─────────────────────────────────────────────────────────────┘
```

### Recording Pipeline

1. **OpenCode** loads the `record-demo` skill.
2. Reads `poc-state.yaml` for project context (namespace, routes, test script).
3. Optionally reads the blog post or PoC report for narrative context.
4. **Generates a Playwright Python script** (`record.py`) customized per project.
5. The script:
   - Starts **Xvfb** (virtual display at `:99`, 1920x1080).
   - Starts **ttyd** (web terminal on `localhost:7681`).
   - Starts **ffmpeg** x11grab capturing the virtual display.
   - Launches **Chromium** via Playwright (non-headless, displayed on Xvfb).
   - Opens two windows, positioned side-by-side (960x1080 each).
   - Window 1: OpenShift Console → login via Keycloak → Topology view.
   - Window 2: ttyd web terminal → runs PoC sanity tests.
   - Waits for test completion, pauses to show results.
   - Stops ffmpeg, producing `demo.webm`.
6. **Uploads** the video to Google Drive.
7. **Updates** `poc-state.yaml` with video info.

---

## Tool Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| Virtual display | **Xvfb** (`xorg-x11-server-Xvfb`) | Provides a pixel buffer for the browser to render into |
| Browser automation | **Playwright** (Python, Chromium) | Controls browser windows, navigation, typing |
| Screen capture | **ffmpeg** (`-f x11grab`) | Captures the entire virtual display as video |
| Web terminal | **ttyd** | Serves a bash session over HTTP/WebSocket via xterm.js |
| Video format | **WebM** (VP9 codec) | Output format — good compression, web-compatible |
| Upload | **Google Drive API** | Resumable upload of video to shared Drive folder |

### Why This Stack

- **Xvfb + x11grab** (vs separate recordings + compositing): A single virtual
  display with two positioned windows gives one unified video without complex
  FFmpeg filter chains. The positioning is deterministic.

- **ttyd** (vs VHS): Playwright controls everything — both the console and the
  terminal — in a single Python script. No separate `.tape` file, no VHS binary,
  no FFmpeg compositing. xterm.js in the browser renders beautiful colored
  terminal output.

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
| 1 | Validate | MANDATORY | Verify poc-state.yaml, deployment health, env vars |
| 2 | Script | MANDATORY | Generate Playwright recording script |
| 3 | Record | MANDATORY | Execute script, produce demo.webm |
| 4 | Upload | NON-BLOCKING | Upload video to Google Drive |
| 5 | Update | MANDATORY | Update poc-state.yaml with artifacts |

### 2. Container Image — `Dockerfile.record-demo`

Separate image based on UBI9 with additional dependencies:

| Dependency | Purpose | Approx Size |
|------------|---------|-------------|
| Chromium (via Playwright) | Browser for automation | ~400MB |
| Playwright Python | Browser control library | ~5MB |
| Xvfb (`xorg-x11-server-Xvfb`) | Virtual display | ~30MB |
| ffmpeg | Screen capture + encoding | ~80MB |
| ttyd | Web-based terminal server | ~2MB |
| kubectl, oc | Cluster CLI operations | ~120MB (shared with base) |
| OpenCode | Agent harness | ~50MB (shared with base) |
| Python + autopoc tools | Config, Drive upload | ~200MB (shared with base) |

Estimated total: ~900MB — 1.2GB.

### 3. Launcher Script — `scripts/record-demo.sh`

```bash
scripts/record-demo.sh <project-name> [options]
```

Generates a K8s Job that:
- Uses the `autopoc-recorder` image.
- Reads existing `poc-state.yaml` from a shared PVC or ConfigMap.
- Mounts `autopoc-credentials` + video-specific credentials.
- Sets OpenCode prompt: `"Record demo video for <project-name>"`.
- Higher resource limits: 1Gi–4Gi memory (Chromium + Xvfb + ffmpeg).

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

### 7. State Extension — `poc-state.yaml`

New `demo_video` section:

```yaml
demo_video:
  status: "pending"       # pending | in_progress | completed | failed | skipped
  script_path: ""         # Path to generated record.py
  video_path: ""          # Local path to recorded video
  drive_url: ""           # Google Drive URL after upload
  duration_seconds: 0
  resolution: "1920x1080"
  format: "webm"
```

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

Where `namespace` comes from `poc-state.yaml` → `apply.namespace`.

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
| High resource usage (Chromium + Xvfb + ffmpeg) | Pod OOM | Set generous limits (4Gi memory); profile and tune |
| Long-running tests extend video duration | Large files, timing issues | Use `PlaybackSpeed` in ffmpeg or cap recording duration |
| ttyd not available in UBI repos | Build failure | Install from GitHub releases binary |

---

## Open Questions

1. **PVC sharing**: How does the record-demo pod access `poc-state.yaml` from
   the previous PoC run? Options: shared PVC, ConfigMap, or re-read from the
   fork repo where state was committed.

2. **Fallback if side-by-side fails**: If window positioning is unreliable,
   fall back to sequential recording (show topology first, then switch to
   terminal). The skill instructions should document this fallback.

3. **Video post-processing**: Should we trim dead time (e.g., waiting for
   login redirects)? Could use ffmpeg to speed up or cut segments. Deferred to
   future iteration.
