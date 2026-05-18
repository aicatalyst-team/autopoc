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
