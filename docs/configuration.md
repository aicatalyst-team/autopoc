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

## Executive presentation and video

Set `AUTOPOC_EXECUTIVE_IMAGE` in `autopoc-credentials` to the tested renderer
image **digest** (`quay.io/<org>/autopoc-executive-renderer@sha256:...`). The
Job/CronJob templates and launcher pass it to OpenCode. Without a configured
renderer, record the extension as skipped rather than claiming generated media.

Silent seals default to template revision 2 (Red Hat branding). Legacy narrated schema-2 seals use template 3; new generic schema-3 seals require
template 4 and input policy 2, with scene-plan schema 2. Build
and validate the new renderer image and upgrade the worker's sealing tools
together before changing `AUTOPOC_EXECUTIVE_IMAGE`. An older revision-1 image
cannot consume revision-2 inputs. Existing revision-1 checkpoints retain their
original renderer digest and remain recoverable; explicit legacy sealing uses
`executive-seal --template-version 1` with that original image. Never rewrite old
checkpoints or reuse their output directories to apply new branding.

Fonts, corporate logos and required notices are tracked in
`renderer/assets/redhat/`; the supplied PDF is a design reference under
`docs/branding/`. No operator-installed brand fonts, CDN or Brand Portal download
is needed at render time. Source/browser ZIPs include the local assets required
for subsequent offline generation and viewing over HTTP.

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
Google TTS is not used by Kokoro. Drive authorization is still required for durable
inputs and publication; a narration engine cannot fix invalid Drive credentials.

Set optional `AUTOPOC_EXECUTIVE_NARRATION=kokoro` in the same worker Secret to
select evidence-backed variable chapters and Heart (`af_heart`) narration.
Unset/`none` retains the silent path; other values are rejected by the workflow.
Job/CronJob templates and the launcher forward this setting. See
`.opencode/skills/run-poc/references/executive-narration.md` for authoring and
independent review. Select a renderer digest tested with the authored schema/template pair and the
exact packaged speech manifest; an image digest alone does not prove capability.
Schema 3 records a source-linked visible definition and credential-free HTTPS
repository metadata for any Git host. It shows every verified final scenario
once, in pages of at most five checks, preserving failure/error/skip/incomplete
outcomes. An empty inventory remains explicit. CLI/library stories do not imply
web UI or cluster deployment. Unknown source revisions are visibly disclosed.

Optional PNGs are staged locally with source/attribution/revision provenance;
`executive-visuals --manifest PATH --output PATH` packages the exact bytes without
network access. No browser installation in the worker is assumed. Capture gaps
use identity text or an evidence-backed diagram. Contextual current documentation
is not proof of a pinned run, and runtime screenshots are unsupported. Concept
art must be labeled conceptual. Four images maximum, 2 MiB per image, 4096 pixels
per side and 16 million decoded pixels fit within an 8 MiB expanded visuals ZIP;
24 MiB sealed-input and 20 MiB evidence limits still apply. Always provide the
archive, even with zero images, using `executive-seal --visuals PATH
--template-version 4`. Review schema 3 binds narrative/evidence/scenes/visuals
SHA-256 values from exact final bytes. Text-only review checks manifest and
captions; actual visual inspection is a separate acceptance record. Missing
configured-model access blocks genuine review, never justifies fake approval.
These local contracts do not establish that template-4 media or a deployed image
has passed acceptance. See the narration reference for the complete recipe and
worker-packaged synthetic examples; existing sealed media remains unchanged.

New narration follows simple technical English inspired by ASD-STE100: short
sentences, one main idea at a time, active voice and consistent terminology.
Necessary technical vocabulary is allowed; no controlled dictionary is enforced.
The author and reviewer apply this style before sealing. Existing videos and
recovery inputs keep their reviewed wording. Updated authoring guidance must be
included in the next worker build; it does not change an already deployed image.
No per-video model download is needed. CPU Kokoro dependencies/model/voice and
licenses are installed only in the separate renderer image at build time.

`src/autopoc/kokoro_lexicon.json` supplies pronunciations for coined names and
initialisms. It is applied only to the text handed to the engine: slides, the
transcript and the captions keep the exact reviewed wording, so editing it is
never a content change. Its SHA-256 is recorded as `narration.lexicon_sha256`
in `scenes.json`, so a changed pronunciation cannot reuse an approved scene
plan and must be re-reviewed; a plan without the field renders with no
overrides. Phoneme values must use Misaki's American English vocabulary —
unsupported symbols are dropped silently at inference, so they are rejected at
load. Entries are expected pronunciations, not measured ones; confirm each
during the acceptance listening pass.

Entries are selected from terms delivered narration actually speaks, and the
file's `selection` field records why each class is in or out. CamelCase product
names and common initialisms are deliberately absent because Misaki already
handles them. A digit-suffixed surface form needs its own entry: `UBI` does not
fire inside `UBI9`. When a render mispronounces a term, add that exact surface
form rather than rewording the reviewed script.

Narrated videos carry a sentence-level English `mov_text` caption track built
from the measured timeline, and `captions.vtt` is retained in
`executable-source.zip`. Cue text is the reviewed sentence with only WebVTT
markup characters escaped. Captions are sentence-level, not word-synchronized.

Verified sealed format determines a durable `render_policy` saved before upload
and Job submission. Narrated defaults: 3000s total renderer budget, 3600s Job
active deadline, 2 CPU/4Gi memory, 8Gi scratch and 10Gi ephemeral-storage
limit. A Job deadline runs from `startTime`, so scheduling and pulling the
renderer image consume it before rendering begins; the 600s of headroom keeps a
slow start from being reported as a render failure. Descriptors sealed with the
earlier 3120s deadline stay valid and dispatch with their own recorded value.
Legacy Jobs retain their 600s default and 1800s deadline ceiling. Resource
bounds are provisional until measured on the target cluster. `--wait-seconds`
remains 300 by default, accepting 0–600. Measured narrated renders took 352s on
OpenShift and 853s under the long stress case, so exceeding the worker wait is
the normal narrated flow, not an exception: late Jobs finish through
`executive-reconcile`, which needs a dispatch, a startup/resume or an explicit
command. There is no always-running collector, so report links are not updated
automatically; schedule the trigger before relying on unattended narration.
Resumes use saved image/mode/policy/launch configuration, ignoring later mode
and image environment changes and rejecting conflicting explicit launch values.
Legacy descriptors without a policy retain their original serialized identity.

`executive-render --timeout-seconds N` can lower a local format-specific budget;
remote Jobs must match the durable timeout exactly. Narrated source/video
ceilings are 512MiB/1GiB, selected by format and artifact kind, with hash and
exact size checks on upload/download. Failed narration publishes no successful
video link while preserving usable deck/PDF/source/summary. Recovery retains
reviewed scripts, timelines and audio, never calling a content model or PoC test
runner. Merge and live worker configuration changes require separate approval.

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

The Kokoro implementation has measured local and restricted-v2 OpenShift
acceptance, tracked in `docs/validation/kokoro-narration-2026-11-08.json` and
`docs/report-presentation-plan.md`. Keep rollout gates separate from encoding:
Drive authorization must work, the resulting narration needs human listening
review, and merge/live worker configuration requires explicit approval. A
successful local renderer or temporary acceptance Job does not publish Drive
artifacts or update the live worker.


On 10 November 2026 the user listened to actual pinned Heart samples and selected
“auto P-O-C” for the written name AutoPoC. The whole-name lexicon entry is
`ˈɔTOpˈiˈOsˈi`; the standalone PoC entry remains separate. The pinned model and
actual inline G2P preserve the `T` flap despite its absence from Misaki's exported
American vocabulary. Only that measured symbol extends the accepted inventory.
This changes synthesis only: reviewed sentences, transcript and captions retain
AutoPoC exactly. A changed lexicon requires a new sealed review hash. Previous
sealed inputs retain their original pronunciation identity and image pin.

Generic template-4 acceptance and fresh images are in progress. A local image
check does not establish fresh OpenShift deployment, Drive publication or human
listening acceptance of a full video. Existing delivered media is preserved.
