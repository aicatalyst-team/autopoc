# Demo Video State Schema

This section is added to `poc-state.yaml` when the `record-demo` skill runs.

## Schema

```yaml
demo_video:
  status: "pending"         # pending | in_progress | completed | failed | skipped
  script_path: ""           # Path to generated Playwright script (record.py)
  video_path: ""            # Local path to recorded video file
  drive_url: ""             # Google Drive URL after upload (empty if not uploaded)
  duration_seconds: 0       # Video duration in seconds (from ffprobe)
  resolution: "1920x1080"   # Video resolution
  format: "webm"            # Video container format
```

## Field Descriptions

### `status`

| Value | Meaning |
|-------|---------|
| `pending` | Demo video has not been recorded yet |
| `in_progress` | Recording is in progress |
| `completed` | Video recorded (and optionally uploaded) successfully |
| `failed` | Recording or a mandatory phase failed |
| `skipped` | Recording was explicitly skipped |

### `script_path`

Absolute path to the generated Playwright Python script. Set in Phase 2
(Script). Example: `/workspace/my-project/demo/record.py`

### `video_path`

Absolute path to the output video file. Set in Phase 3 (Record).
Example: `/workspace/my-project/demo/demo.webm`

### `drive_url`

Google Drive web view URL for the uploaded video. Set in Phase 4 (Upload).
If upload failed, set to `"upload_failed"`. If upload was skipped (no
credentials), remains empty.

### `duration_seconds`

Duration of the video in seconds, extracted from `ffprobe` output. Set in
Phase 3 (Record).

### `resolution`

Video resolution as `WIDTHxHEIGHT`. Always `"1920x1080"` in the current
implementation.

### `format`

Video container format. Always `"webm"` in the current implementation.

---

## Lifecycle

```
Phase 1 (Validate):
  demo_video.status = "in_progress"

Phase 2 (Script):
  demo_video.script_path = "/workspace/project/demo/record.py"

Phase 3 (Record):
  demo_video.video_path = "/workspace/project/demo/demo.webm"
  demo_video.duration_seconds = 120
  demo_video.resolution = "1920x1080"
  demo_video.format = "webm"

Phase 4 (Upload):
  demo_video.drive_url = "https://drive.google.com/file/d/.../view"

Phase 5 (Update):
  demo_video.status = "completed"
```

On failure at any mandatory phase:
```
demo_video.status = "failed"
errors:
  - phase: "record"
    message: "Playwright script failed: console login timeout"
    action: "fail"
    timestamp: "2025-01-15T10:30:00Z"
```

---

## Integration with Existing State

The `demo_video` section sits alongside the existing PoC state sections:

```yaml
project:
  name: "my-project"
  ...
intake:
  ...
evaluate:
  ...
# ... other phases ...
poc_report:
  status: "completed"
  report_path: "/workspace/my-project/poc-report.md"
blog_post:
  status: "completed"
  blog_path: "/workspace/my-project/blog/final.md"
demo_video:                    # ← New section
  status: "completed"
  script_path: "/workspace/my-project/demo/record.py"
  video_path: "/workspace/my-project/demo/demo.webm"
  drive_url: "https://drive.google.com/file/d/abc123/view"
  duration_seconds: 150
  resolution: "1920x1080"
  format: "webm"
retries:
  ...
errors: []
```
