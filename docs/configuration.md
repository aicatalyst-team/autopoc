# Configuration

AutoPoC is configured via environment variables. Copy `.env.example` to `.env` and fill in the required values.

```bash
cp .env.example .env
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes* | Anthropic API key |
| `VERTEX_PROJECT` | Yes* | Google Cloud project ID (alternative to Anthropic key) |
| `VERTEX_LOCATION` | No | Vertex AI region (default: `us-east5`) |
| `LLM_BASE_URL` | Yes* | OpenAI-compatible endpoint (e.g. vLLM). Requires `LLM_MODEL` |
| `LLM_API_KEY` | No | API key for the OpenAI-compatible endpoint |
| `LLM_MODEL` | No | Model name (required with `LLM_BASE_URL`, otherwise optional) |
| `LLM_MAX_RETRIES` | No | Max retries for LLM API calls (default: `0`, fail fast) |
| `FORK_TARGET` | No | Fork destination: `gitlab` (default) or `github` |
| `GITLAB_URL` | When target=gitlab | Self-hosted GitLab URL |
| `GITLAB_TOKEN` | When target=gitlab | GitLab personal access token (api + read/write_repository scopes) |
| `GITLAB_GROUP` | When target=gitlab | GitLab group for forked repos (e.g. `poc-demos`) |
| `GITHUB_TOKEN` | When target=github | GitHub personal access token (repo scope) |
| `GITHUB_ORG` | No | GitHub org for forks (if unset, forks to authenticated user) |
| `QUAY_REGISTRY` | Yes | Container registry URL (e.g. `quay.io` or `http://localhost:8080`) |
| `QUAY_ORG` | Yes | Registry organization/namespace |
| `QUAY_TOKEN` | Yes | Registry OAuth or robot account token |
| `QUAY_USERNAME` | No | Registry auth username (e.g. `myuser+robotname` for robot accounts; defaults to `$oauthtoken`) |
| `OPENSHIFT_API_URL` | Yes | Kubernetes/OpenShift API server URL |
| `OPENSHIFT_TOKEN` | Yes | Kubernetes auth token |
| `OPENSHIFT_NAMESPACE_PREFIX` | No | Namespace prefix (default: `poc`) |
| `BUILD_STRATEGY` | No | Container build strategy: `podman` (default) or `openshift` (on-cluster builds) |
| `MAX_BUILD_RETRIES` | No | Build retry limit (default: `3`) |
| `MAX_DEPLOY_RETRIES` | No | Deploy/apply retry limit (default: `2`) |
| `MAX_CONTAINER_FIX_RETRIES` | No | Container fix escalation limit (default: `2`) |
| `AUTOPOC_SHEET_CREDENTIALS` | For run-sheet | Path to Google service account credentials JSON |
| `AUTOPOC_SHEET_ID` | For run-sheet | Google Sheet ID containing candidate projects |
| `AUTOPOC_PROJECT_NAME` | No | Env var fallback for `--name` |
| `AUTOPOC_REPO_URL` | No | Env var fallback for `--repo` |
| `OGX_BASE_URL` | No | OGX LLM proxy URL for PoC projects (see [LLM Proxy](llm-proxy.md)) |
| `OGX_MODEL` | No | Model name on OGX server (default: `qwen3-32b`) |
| `OGX_API_KEY` | No | API key for OGX server (default: `none`) |
| `WORK_DIR` | No | Local working directory (default: `/tmp/autopoc`) |

*One of `ANTHROPIC_API_KEY`, `VERTEX_PROJECT`, or `LLM_BASE_URL` is required.

## Executive presentation and silent video

Set `AUTOPOC_EXECUTIVE_IMAGE` in `autopoc-credentials` to the tested renderer
image **digest** (`quay.io/<org>/autopoc-executive-renderer@sha256:...`). The
Job/CronJob templates and launcher pass it to OpenCode. Without a configured
renderer, record the extension as skipped rather than claiming generated media.

`AUTOPOC_EXECUTIVE_NAMESPACE` defaults to the worker's namespace through the
Downward API. `AUTOPOC_EXECUTIVE_FOLDER_ID` selects the Drive destination;
otherwise the extension uses `GOOGLE_DOCS_FOLDER_ID`. Google credentials use
the existing `AUTOPOC_SHEET_CREDENTIALS` path and `autopoc-google-sa` Secret.
No public-sharing permissions are added by the uploader.

Install `deploy/executive/rbac.yaml` in that namespace and link the renderer
ServiceAccount to the configured registry pull Secret when the image is private.
The renderer has no workload API token or RoleBinding. The launcher has bounded
Job submission/read permissions; existing main-worker PoC permissions are
managed separately.

Build and publish through `make renderer-image` / `make renderer-image-push`
with `IMAGE_ORG` and `IMAGE_TAG`. Both the renderer and main AutoPoC worker
images must include the new Python tools and updated skill instructions.
Google TTS credentials are unnecessary in Phase 1; narration remains Phase 2.

The CLI now provides `capture-execution`, `evidence-create`, `evidence-verify`,
`executive-seal`, `executive-render`, `executive-dispatch`, `executive-status`,
`executive-reconcile` and `executive-recover`. See the
[renderer guide](../renderer/README.md) for local rendering, and the
[workflow reference](../.opencode/skills/run-poc/references/executive-summary.md)
for the narrative/review schema, dispatch and recovery commands.

Collection archives allowlisted state, staged report/plan/evaluation and indexed
original attempts. Raw responses, credential/configuration values and arbitrary
logs/media are excluded from this initial schema. Historical imports explicitly
retain gaps instead of replaying tests. Evidence ZIPs are limited to 20 MiB;
the sealed render envelope is limited to 24 MiB.

The first recovery commit also retains the verified sealed envelope in Git;
later checkpoints reference that immutable backup. Drive receives sealed inputs
before rendering and receives output binaries afterward. Per-output intent and
receipt slots permit recovery when an upload finishes before its receipt does.
Use `executive-reconcile` after worker deletion or after blog completion without
resetting PoC phases. Use explicit `executive-dispatch --retry` for a new bounded
render attempt, preserving prior revisions and valid outputs.

### Temporary local personal Drive access

The uploader also accepts an explicit `google.auth.credentials.Credentials`
object through `GoogleDriveService(credentials=credentials)`. A local desktop
OAuth flow may load authorized-user credentials using
`google.oauth2.credentials.Credentials.from_authorized_user_file`, requesting
only `https://www.googleapis.com/auth/drive.file`. The OAuth client's Google
Cloud project must have Google Drive API enabled. A private folder created by
that app is a suitable temporary destination.

Keep personal refresh tokens in a private local credential file (directory mode
0700, file mode 0600), outside Git. This local override does not change the
production service-account loader or mount a personal token in the cluster.
Repair `autopoc-google-sa` before unattended OCP publication. The published
renderer image built before the local OAuth addition continues to use service-account
credentials; rebuild before depending on the new injection API inside an image.
