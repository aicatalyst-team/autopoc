# AutoPoC — Implementation Plan

> Detailed, ordered task breakdown for implementing the AutoPoC LangGraph agent system.
> See [plan.md](./plan.md) for architecture and design decisions.

---

## Task Index

| Phase | Tasks | Summary |
|-------|-------|---------|
| **1. Foundation** | 1–11 | Scaffolding, config, state, CLI, file/git tools, intake agent |
| **2. Fork & Containerize** | 12–22 | GitLab tools, fork agent, Dockerfile templates, containerize agent, partial graph |
| **3. Build & Push** | 23–28 | Podman/Quay tools, build agent, retry loop |
| **4. Deploy** | 29–34 | OpenShift tools, K8s templates, deploy agent, full graph |
| **5. Hardening** | 35–36 | Logging, tracing, credential validation, CLI polish, checkpointing |
| **6. Local E2E Harness** | 37–39 | Docker-compose test infra with GitLab CE/Quay, E2E test suite |
| **7. PoC Intelligence** | 40–56 | PoC plan agent, parallel graph, containerize/deploy PoC-awareness, PoC execute, PoC report |

**Critical path:** 1 → 2 → 4 → 6,7 → 9 → 13,18 → 20 → 25 → 27 → 33 → 34 → 40 → 42 → 44 → 45,46 → 49 → 54

---

## Progress

| Phase | Status | Tasks Done | Tests |
|-------|--------|------------|-------|
| **1. Foundation** | **COMPLETE** | 11/11 | 49 passing |
| **2. Fork & Containerize** | **COMPLETE** | 11/11 | 24 passing |
| **3. Build & Push** | **COMPLETE** | 6/6 | 6 passing |
| **4. Deploy** | **COMPLETE** | 4/6 | E2E (with --e2e) |
| **5. Hardening** | Pending | 0/2 | — |
| **6. Local E2E Harness** | **COMPLETE** | 3/3 | 7 passing (with --e2e) |
| **7. PoC Intelligence** | In Progress | 15/17 | 44 passing |

---

## Phase 1: Foundation

### Task 1 — Project scaffolding ✅

**Files:** `pyproject.toml`, `src/autopoc/__init__.py`, all `__init__.py` files for
subpackages (`agents/`, `tools/`, `prompts/`, `templates/`)

**Depends on:** nothing

**Work:**
- Create `pyproject.toml` with project metadata, dependencies, dev dependencies,
  and `[project.scripts]` entry point (`autopoc = "autopoc.cli:app"`).
- Create `src/autopoc/` package with `__init__.py`.
- Create empty `__init__.py` in `agents/`, `tools/`.
- Create `prompts/` and `templates/` directories.
- Create `tests/` directory with empty `__init__.py`.

**Dependencies (pyproject.toml):**
```toml
[project]
dependencies = [
    "langgraph>=0.2",
    "langchain-anthropic>=0.3",
    "langchain-core>=0.3",
    "typer>=0.12",
    "python-dotenv>=1.0",
    "jinja2>=3.1",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "rich>=13.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.6",
]
```

**Acceptance criteria:**
- `pip install -e ".[dev]"` succeeds
- `python -c "import autopoc"` succeeds
- `pytest` runs (0 tests collected, no errors)

**Implementation notes:**
- Added `pydantic-settings>=2.0` to dependencies (required for Task 2's `BaseSettings`).
- Added `norecursedirs = ["tests/fixtures"]` to pytest config to prevent fixture
  test files from being collected as real tests.
- Uses `hatchling` as build backend.

---

### Task 2 — Config module ✅

**Files:** `src/autopoc/config.py`, `.env.example`

**Depends on:** Task 1

**Work:**
- Define `AutoPoCConfig` as a Pydantic `BaseSettings` model with fields:
  - `anthropic_api_key: str`
  - `gitlab_url: str`
  - `gitlab_token: str`
  - `gitlab_group: str`
  - `quay_registry: str` (default: `"quay.io"`)
  - `quay_org: str`
  - `quay_token: str`
  - `openshift_api_url: str`
  - `openshift_token: str`
  - `openshift_namespace_prefix: str` (default: `"poc"`)
  - `max_build_retries: int` (default: `3`)
  - `work_dir: str` (default: `"/tmp/autopoc"`)
- Use `pydantic-settings` with `env_prefix=""` so vars map directly.
- Create `.env.example` with all variables documented.

**Acceptance criteria:**
- Config loads from env vars or `.env` file.
- Missing required vars raise `ValidationError` with clear field name.
- Defaults work for optional fields.

**Implementation notes:**
- Added `masked_summary()` method to `AutoPoCConfig` for safe display of secrets
  in CLI output (shows first/last 4 chars, masks the rest).

---

### Task 3 — Config tests ✅

**Files:** `tests/conftest.py`, `tests/test_config.py`

**Depends on:** Task 2

**Work:**
- `conftest.py`: shared fixtures (e.g., `tmp_path`, mock env vars).
- `test_config.py`:
  - Test loading with all vars set → valid config.
  - Test missing required var → `ValidationError` naming the field.
  - Test defaults applied when optional vars omitted.

**Acceptance criteria:**
- All tests pass with `pytest tests/test_config.py`.

**Implementation notes:**
- 9 tests: covers all vars set, minimal vars with defaults, missing required vars,
  multiple missing vars, int parsing, default overrides, secret masking (full and partial).

---

### Task 4 — State definitions ✅

**Files:** `src/autopoc/state.py`

**Depends on:** Task 1

**Work:**
- Define `PoCPhase` enum: `INTAKE`, `FORK`, `CONTAINERIZE`, `BUILD`, `DEPLOY`, `DONE`, `FAILED`.
- Define `ComponentInfo` as a `TypedDict`:
  - `name`, `language`, `build_system`, `entry_point`, `port`, `existing_dockerfile`,
    `dockerfile_ubi_path`, `image_name`, `is_ml_workload`.
- Define `PoCState` as a `TypedDict`:
  - Input fields: `project_name`, `source_repo_url`
  - Phase tracking: `current_phase`, `error`, `messages`
  - Fork output: `gitlab_repo_url`, `local_clone_path`
  - Intake output: `repo_summary`, `components`, `has_helm_chart`, `has_kustomize`,
    `has_compose`, `existing_ci_cd`
  - Build output: `built_images`, `build_retries`
  - Deploy output: `deployed_resources`, `routes`

**Acceptance criteria:**
- All types importable: `from autopoc.state import PoCState, ComponentInfo, PoCPhase`
- Type checker (`pyright` or `mypy`) passes on a file that uses them.

**Implementation notes:**
- Used `total=False` on both `ComponentInfo` and `PoCState` TypedDicts so fields
  can be populated progressively as the pipeline advances.
- Added `source_dir` field to `ComponentInfo` (relative path within repo for monorepos).
- Used `Annotated[list, add_messages]` for the `messages` field to support LangGraph's
  message accumulation pattern.
- Added `build_retries: int` to `PoCState` for retry loop tracking.

---

### Task 5 — CLI entry point ✅

**Files:** `src/autopoc/cli.py`

**Depends on:** Tasks 2, 4

**Work:**
- Create `typer.Typer()` app.
- `run` command with options:
  - `--name` / `-n`: project name (required)
  - `--repo` / `-r`: GitHub repo URL (required)
- On invocation:
  - Load config (fail fast if env vars missing).
  - Print loaded config summary (masked secrets).
  - Create initial `PoCState` with inputs populated.
  - Print "Would run graph here" (stub — wired in Task 21).
- Register as `[project.scripts] autopoc = "autopoc.cli:app"` in pyproject.toml.

**Acceptance criteria:**
- `autopoc run --name test --repo https://github.com/x/y` prints config and initial state.
- `autopoc run` without args shows help/error.
- `autopoc --help` works.

**Implementation notes:**
- Uses `typer.Option` with `Annotated` syntax (modern typer pattern).
- Config summary displayed via `rich.Table` with masked secrets.
- Initializes a complete `PoCState` with all fields set to defaults.
- Graph invocation is stubbed with a TODO for Task 21.

---

### Task 6 — File tools ✅

**Files:** `src/autopoc/tools/file_tools.py`, `tests/test_file_tools.py`

**Depends on:** Task 1

**Work:**
- Implement as `@tool`-decorated functions (LangChain tool interface):
  - `list_files(path: str, pattern: str = "**/*") -> str` — Recursive listing, returns
    newline-separated paths. Optionally filter by glob pattern.
  - `read_file(path: str) -> str` — Read and return file contents. Cap at 50KB with
    truncation notice.
  - `write_file(path: str, content: str) -> str` — Write content to file, create parent
    dirs. Return confirmation.
  - `search_files(path: str, pattern: str, file_glob: str = "**/*") -> str` — Grep for
    regex pattern across files. Return matches with file:line format.
- All tools take absolute paths. Include input validation (path traversal protection).

**Tests:**
- Create temp directory with sample files.
- Test `list_files` returns expected structure.
- Test `read_file` on existing and missing files.
- Test `write_file` creates file and parent dirs.
- Test `search_files` finds matches across files.
- Test path traversal is rejected.

**Acceptance criteria:**
- All tools work as LangChain tools (`tool.invoke({"path": ...})` works).
- All tests pass.

**Implementation notes:**
- `list_files` and `search_files` skip hidden directories (`.git/`, etc.) automatically.
- `search_files` caps at 200 matches to avoid overwhelming LLM context.
- `read_file` truncates at 50KB with a notice.
- 17 tests covering all tools including edge cases (empty dirs, invalid regex,
  hidden dir skipping, parent dir creation).

---

### Task 7 — Git tools ✅

**Files:** `src/autopoc/tools/git_tools.py`, `tests/test_git_tools.py`

**Depends on:** Task 1

**Work:**
- Implement as `@tool`-decorated functions:
  - `git_clone(url: str, dest: str) -> str` — Clone repo. Return path.
  - `git_add_remote(repo_path: str, name: str, url: str) -> str` — Add remote.
  - `git_push(repo_path: str, remote: str = "origin", branch: str = "main") -> str` — Push.
  - `git_commit(repo_path: str, message: str, files: list[str] | None = None) -> str` —
    Stage files (or all), commit.
  - `git_checkout_branch(repo_path: str, branch: str, create: bool = False) -> str`
- All shell out to `git` via `subprocess.run` with timeout, capture stderr.
- Return stdout on success, raise `ToolException` with stderr on failure.

**Tests:**
- Use `tmp_path` to create bare repos and test clone/push/commit.
- Test clone of a local bare repo.
- Test commit + verify with `git log`.
- Test add remote + verify with `git remote -v`.

**Acceptance criteria:**
- Tools work end-to-end with local git repos.
- Errors are captured and returned cleanly.
- All tests pass.

**Implementation notes:**
- `_run_git()` helper handles subprocess execution, timeout, and error formatting.
- `git_push` renamed the `branch` parameter to `ref` to support `--all` and `--tags`.
- `git_clone` returns early with a message if dest already exists (idempotent).
- `git_add_remote` checks if remote already exists before adding (idempotent).
- 9 tests using real temp git repos (bare + cloned).

---

### Task 8 — Intake system prompt ✅

**Files:** `src/autopoc/prompts/intake.md`

**Depends on:** nothing

**Work:**
- Write system prompt instructing the LLM to:
  - First call `list_files` to get repo structure.
  - Identify language(s) by looking for: `requirements.txt`, `setup.py`, `pyproject.toml`,
    `package.json`, `go.mod`, `pom.xml`, `build.gradle`, `Cargo.toml`, `Gemfile`, etc.
  - For each component found, determine: name, language, build system, entry point, port.
  - Check for ML indicators: `model`, `inference`, `serve`, `predict` in filenames or
    imports; ML libraries in dependencies (torch, tensorflow, sklearn, transformers, etc.).
  - Check for existing deployment: `Dockerfile*`, `docker-compose*`, `helm/`, `Chart.yaml`,
    `kustomization.yaml`, `.github/workflows/`, `.gitlab-ci.yml`.
  - Return structured JSON output matching `ComponentInfo[]` schema.
- Include 2-3 few-shot examples of expected output.

**Acceptance criteria:**
- Prompt is clear, specific, and includes output schema.
- Examples cover: single Python app, multi-component Node+Python repo, ML project.

**Implementation notes:**
- 180+ line prompt with detailed instructions for a 6-step analysis process.
- Includes 3 few-shot examples matching the 3 test fixtures.
- Strict JSON-only output requirement (no surrounding text).
- Covers monorepo detection, ML workload indicators, CI/CD identification.

---

### Task 9 — Intake agent ✅

**Files:** `src/autopoc/agents/intake.py`

**Depends on:** Tasks 4, 6, 7, 8

**Work:**
- Create intake agent function `async def intake_agent(state: PoCState) -> PoCState`:
  - Load system prompt from `prompts/intake.md`.
  - Initialize `ChatAnthropic` with Claude model.
  - If `local_clone_path` not set, clone the repo using `git_clone`.
  - Create a LangGraph ReAct agent (`create_react_agent`) with tools:
    `list_files`, `read_file`, `search_files`.
  - Invoke agent with the system prompt.
  - Parse structured output into `components[]`, `repo_summary`, and boolean flags.
  - Return updated state.
- Include output parsing logic (LLM returns JSON, parse into `ComponentInfo` list).
- Handle edge cases: empty repo, very large repo (limit file listing depth).

**Acceptance criteria:**
- Given a cloned repo path, agent returns populated state with components.
- Works with Claude API (manual test).
- Structured output parsing handles valid and malformed LLM responses.

**Implementation notes:**
- Agent accepts an optional `llm` parameter for dependency injection in tests.
- `_parse_intake_output()` handles markdown code fences (`\`\`\`json ... \`\`\``)
  that LLMs often wrap around JSON output.
- `_validate_component()` provides safe defaults for all fields (graceful degradation
  if LLM omits fields).
- Handles multi-part content blocks from Claude responses (list of text blocks).
- Returns a partial state dict (not full `PoCState`) for LangGraph node compatibility.

---

### Task 10 — Intake test fixtures ✅

**Files:** `tests/fixtures/` directory with 3 sample repos

**Depends on:** nothing

**Work:**
- Create 3 minimal fixture repos (just files, not real git repos):
  - `tests/fixtures/python-flask-app/` — Simple Flask app:
    - `app.py`, `requirements.txt`, `Dockerfile`, `README.md`
  - `tests/fixtures/node-monorepo/` — Two components, no Dockerfile:
    - `frontend/package.json`, `frontend/src/index.js`
    - `api/package.json`, `api/src/server.js`
    - `docker-compose.yml`
  - `tests/fixtures/ml-serving/` — ML model server:
    - `model/serve.py`, `model/requirements.txt` (includes torch, fastapi)
    - `Dockerfile`, `kubernetes/deployment.yaml`

**Acceptance criteria:**
- Fixtures are realistic enough to exercise intake detection logic.
- Each fixture has a known expected output (documented in test).

**Implementation notes:**
- Flask fixture includes: `app.py` (with port 5000), `requirements.txt`, `Dockerfile`,
  `README.md`, `tests/test_app.py`.
- Node monorepo includes: `frontend/` and `api/` with separate `package.json` files,
  `docker-compose.yml`. API uses Express on port 3001.
- ML serving includes: `model/serve.py` (FastAPI + PyTorch), `model/requirements.txt`,
  `Dockerfile`, `kubernetes/deployment.yaml`, `kubernetes/service.yaml`.

---

### Task 11 — Intake integration tests ✅

**Files:** `tests/test_intake.py`

**Depends on:** Tasks 9, 10

**Work:**
- Test `intake_agent` against each fixture.
- Use `FakeListChatModel` from `langchain_core.language_models.fake` or `unittest.mock`
  to mock LLM responses with pre-recorded JSON outputs.
- Verify:
  - Python fixture: 1 component, language=python, existing Dockerfile detected.
  - Node monorepo: 2 components (frontend + api), no Dockerfiles, docker-compose detected.
  - ML serving: 1 component, `is_ml_workload=True`, existing Dockerfile + K8s manifests detected.

**Acceptance criteria:**
- All 3 fixture tests pass.
- Tests don't require real LLM API calls.

**Implementation notes:**
- Used `unittest.mock.patch` on `create_react_agent` rather than `FakeListChatModel`,
  since ReAct agents require tool-call-formatted responses that fake models don't
  produce well.
- 14 tests total: 5 for `_parse_intake_output`, 4 for `_validate_component`,
  5 for the full agent flow (3 fixture scenarios + clone path preservation +
  malformed LLM output handling).
- Tests verify correct component detection, ML workload flagging, docker-compose
  detection, and graceful degradation on bad LLM output.

---

## Phase 2: Fork & Containerize

### Task 12 — GitLab tools ✅

**Files:** `src/autopoc/tools/gitlab_tools.py`, `tests/test_gitlab_tools.py`

**Depends on:** Task 2

**Work:**
- Implement:
  - `gitlab_create_project(name: str, group: str) -> dict` — POST to
    `/api/v4/projects` with `namespace_id` from group. Return project info dict.
  - `gitlab_get_project(group: str, name: str) -> dict | None` — GET project by
    namespace/name. Return None if not found.
  - `gitlab_project_exists(group: str, name: str) -> bool` — Convenience wrapper.
- Use `httpx` for HTTP calls. Read `gitlab_url` and `gitlab_token` from config.
- NOT decorated as `@tool` (used procedurally by fork agent, not by LLM).

**Tests:**
- Mock `httpx` responses.
- Test create returns project URL.
- Test get existing vs. missing project.
- Test auth header is set correctly.

**Acceptance criteria:**
- All functions work against mocked GitLab API.
- Tests pass.

---

### Task 13 — Fork agent ✅

**Files:** `src/autopoc/agents/fork.py`, `tests/test_fork.py`

**Depends on:** Tasks 7, 12

**Work:**
- Implement `async def fork_agent(state: PoCState) -> PoCState`:
  - Check if project already exists on GitLab → skip if so.
  - Create project on GitLab via `gitlab_create_project`.
  - If repo not yet cloned (`local_clone_path` is None), clone from GitHub.
  - Add GitLab remote: `git_add_remote(path, "gitlab", gitlab_url)`.
  - Push all branches: `git_push(path, "gitlab", "--all")`.
  - Push tags: `git_push(path, "gitlab", "--tags")`.
  - Update state: `gitlab_repo_url`, `local_clone_path`.
- This is a procedural node, no LLM calls.

**Tests:**
- Mock GitLab API + use temp git repos.
- Test happy path: project created, repo pushed.
- Test idempotency: project already exists, skip creation.
- Test clone reuse: if `local_clone_path` already set, don't re-clone.

**Acceptance criteria:**
- Fork agent successfully mirrors a repo to a mocked GitLab.
- Tests pass.

---

### Task 14 — Dockerfile template (single-stage) ✅

**Files:** `src/autopoc/templates/Dockerfile.ubi.j2`

**Depends on:** Task 1

**Work:**
- Jinja2 template for interpreted languages (Python, Node, Ruby):
  ```dockerfile
  FROM {{ base_image }}

  LABEL maintainer="autopoc" \
        io.openshift.tags="{{ language }}" \
        io.k8s.description="AutoPoC-generated UBI image for {{ component_name }}"

  WORKDIR /opt/app-root/src

  {% if system_packages %}
  USER 0
  RUN microdnf install -y {{ system_packages | join(' ') }} && microdnf clean all
  USER 1001
  {% endif %}

  COPY {{ copy_source | default('.') }} .

  {% if install_cmd %}
  RUN {{ install_cmd }}
  {% endif %}

  {% if expose_port %}
  EXPOSE {{ expose_port }}
  {% endif %}

  # OpenShift: support arbitrary UIDs
  RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root

  USER 1001

  CMD {{ cmd }}
  ```
- Keep it thin — just the boilerplate that must be consistent.

**Acceptance criteria:**
- Template renders to a valid Dockerfile with sample variables.

---

### Task 15 — Dockerfile template (multi-stage) ✅

**Files:** `src/autopoc/templates/Dockerfile.ubi-builder.j2`

**Depends on:** Task 1

**Work:**
- Jinja2 template for compiled languages (Go, Java, Rust):
  ```dockerfile
  # Builder stage
  FROM {{ builder_image }} AS builder
  WORKDIR /build
  COPY . .
  RUN {{ build_cmd }}

  # Runtime stage
  FROM {{ runtime_image }}
  LABEL ...
  WORKDIR /opt/app-root/src
  COPY --from=builder {{ build_artifact }} .
  {% if expose_port %}
  EXPOSE {{ expose_port }}
  {% endif %}
  RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root
  USER 1001
  CMD {{ cmd }}
  ```

**Acceptance criteria:**
- Template renders to a valid multi-stage Dockerfile.

---

### Task 16 — Template rendering utility ✅

**Files:** `src/autopoc/tools/template_tools.py`, `tests/test_template_tools.py`

**Depends on:** Tasks 14, 15

**Work:**
- `render_template(template_name: str, **variables) -> str`:
  - Load template from `src/autopoc/templates/` using Jinja2 `PackageLoader` or
    `FileSystemLoader`.
  - Render with provided variables.
  - Return rendered string.
- Decorate as `@tool` for LLM use (the containerize agent can call it).

**Tests:**
- Test rendering single-stage template with Python variables.
- Test rendering multi-stage template with Go variables.
- Test missing variable raises clear error.

**Acceptance criteria:**
- Templates render correctly.
- Tests pass.

---

### Task 17 — Containerize system prompt ✅

**Files:** `src/autopoc/prompts/containerize.md`

**Depends on:** nothing

**Work:**
- System prompt instructing the LLM to generate `Dockerfile.ubi` for each component.
- Include:
  - **UBI image mapping table:**
    | Source image | UBI equivalent |
    |---|---|
    | `python:3.x` | `registry.access.redhat.com/ubi9/python-312` |
    | `node:2x` | `registry.access.redhat.com/ubi9/nodejs-22` |
    | `golang:1.x` | `registry.access.redhat.com/ubi9/go-toolset` |
    | `openjdk` / `eclipse-temurin` | `registry.access.redhat.com/ubi9/openjdk-21` |
    | `alpine` / `ubuntu` / `debian` | `registry.access.redhat.com/ubi9/ubi-minimal` |
  - **Package manager mapping:** `apt-get` → `microdnf`, `apk` → `microdnf`
  - **OpenShift compatibility checklist:**
    - Final stage must run as non-root (USER 1001)
    - Directories writable by group 0
    - No privileged ports (use 8080 instead of 80, 8443 instead of 443)
    - Support arbitrary UIDs via `chgrp -R 0 && chmod -R g=u`
  - **Decision criteria:** When to use single-stage vs multi-stage
  - **ML workload patterns:** CUDA base images, model file handling
  - **Instructions:** Use `render_template` tool when the pattern matches a template,
    otherwise generate Dockerfile from scratch. Always write result with `write_file`.

**Acceptance criteria:**
- Prompt covers all necessary rules and mappings.
- Includes clear instructions for both "adapt existing" and "create from scratch" paths.

---

### Task 18 — Containerize agent ✅

**Files:** `src/autopoc/agents/containerize.py`

**Depends on:** Tasks 4, 6, 16, 17

**Work:**
- Implement `async def containerize_agent(state: PoCState) -> PoCState`:
  - Load system prompt from `prompts/containerize.md`.
  - Initialize `ChatAnthropic`.
  - For each component in `state["components"]`:
    - Build a user message with component info + any previous build errors
      (for retry loop support).
    - Create ReAct agent with tools: `read_file`, `write_file`, `list_files`,
      `search_files`, `render_template`.
    - Invoke agent — it reads the repo, generates Dockerfile.ubi, writes it.
    - Update `component["dockerfile_ubi_path"]` with the written path.
  - After all components processed:
    - `git_commit` all new Dockerfile.ubi files.
    - `git_push` to GitLab.
  - Return updated state.
- Handle retry context: if `state["error"]` contains a build error from a previous
  attempt, include it in the user message so the LLM can fix the issue.

**Acceptance criteria:**
- Agent generates Dockerfile.ubi for each component and commits/pushes.
- On retry (error in state), agent receives error context.
- Works with Claude API (manual test).

---

### Task 19 — Containerize tests ✅

**Files:** `tests/test_containerize.py`

**Depends on:** Tasks 10, 18

**Work:**
- Test against fixture repos with mocked LLM:
  - **Python fixture (has Dockerfile):** Verify LLM receives existing Dockerfile content,
    verify output Dockerfile.ubi uses UBI base image.
  - **Node monorepo (no Dockerfile):** Verify Dockerfile.ubi created for each component.
  - **ML serving:** Verify ML-specific considerations in prompt context.
- Test retry path: set `state["error"]` with a build error, verify it appears in
  the agent's prompt.

**Acceptance criteria:**
- Tests pass with mocked LLM.
- Dockerfile.ubi files are written to correct paths.

---

### Task 20 — Graph: intake through containerize ✅

**Files:** `src/autopoc/graph.py`

**Depends on:** Tasks 9, 13, 18

**Work:**
- Create `build_graph() -> CompiledGraph`:
  - `StateGraph(PoCState)`
  - Add nodes: `intake`, `fork`, `containerize`
  - Set entry point: `intake`
  - Add edges: `intake → fork → containerize`
  - Compile graph.
- Export compiled graph as `app` for CLI to invoke.

**Acceptance criteria:**
- `build_graph()` returns a compiled graph.
- Graph can be visualized (`.get_graph().draw_mermaid()`).
- Invoking with initial state runs all 3 nodes in sequence.

---

### Task 21 — Wire CLI to graph ✅

**Files:** Update `src/autopoc/cli.py`

**Depends on:** Tasks 5, 20

**Work:**
- Replace stub in `run` command:
  - Import `build_graph` from `graph.py`.
  - Create initial `PoCState` from CLI args.
  - Invoke graph: `result = graph.invoke(initial_state)`.
  - Print results using `rich` (phase, components found, Dockerfiles created).

**Acceptance criteria:**
- `autopoc run --name test --repo <url>` runs the full intake→fork→containerize pipeline.
- Progress is printed to console.

---

### Task 22 — Integration test: intake through containerize ✅

**Files:** `tests/test_graph_partial.py`

**Depends on:** Task 20

**Work:**
- End-to-end test with mocked LLM and mocked GitLab:
  - Create a temp repo (git init + sample files).
  - Invoke graph with `source_repo_url` pointing to temp repo.
  - Verify: intake populated components, fork "pushed" to GitLab, containerize
    wrote Dockerfile.ubi files.
- Use `unittest.mock.patch` for GitLab API and LLM calls.

**Acceptance criteria:**
- Test passes end-to-end without real external calls.
- State transitions are correct: INTAKE → FORK → CONTAINERIZE.

---

## Phase 3: Build & Push

### Task 23 — Podman tools ✅

**Files:** `src/autopoc/tools/podman_tools.py`, `tests/test_podman_tools.py`

**Depends on:** Task 2

**Work:**
- Implement as `@tool`-decorated functions:
  - `podman_build(context_path: str, dockerfile: str, tag: str, build_args: dict | None = None) -> str`
    — Run `podman build -f <dockerfile> -t <tag> <context>`. Return build output.
  - `podman_push(image: str) -> str` — Run `podman push <image>`. Return output.
  - `podman_inspect(image: str) -> str` — Return image metadata as JSON string.
  - `podman_tag(image: str, new_tag: str) -> str` — Tag image.
- All shell out via `subprocess.run` with timeout (10 min for build).
- Capture and return both stdout and stderr.

**Tests:**
- Mock `subprocess.run`.
- Verify correct command construction for each tool.
- Test build failure returns stderr in a parseable format.

**Acceptance criteria:**
- Tools construct correct podman commands.
- Error output is captured cleanly.
- Tests pass.

---

### Task 24 — Quay tools ✅

**Files:** `src/autopoc/tools/quay_tools.py`, `tests/test_quay_tools.py`

**Depends on:** Task 2

**Work:**
- Implement (NOT `@tool` — used procedurally):
  - `quay_ensure_repo(org: str, name: str) -> str` — Check if Quay repo exists
    (GET `/api/v1/repository/{org}/{name}`). If not, create it
    (POST `/api/v1/repository`). Return repo URL.
  - `quay_repo_exists(org: str, name: str) -> bool`
- Use `httpx` with Quay token from config.

**Tests:**
- Mock HTTP responses.
- Test repo exists → skip creation.
- Test repo missing → create.

**Acceptance criteria:**
- Functions work against mocked Quay API.
- Tests pass.

---

### Task 25 — Build agent ✅

**Files:** `src/autopoc/agents/build.py`

**Depends on:** Tasks 4, 23, 24

**Work:**
- Implement `async def build_agent(state: PoCState) -> PoCState`:
  - For each component in `state["components"]`:
    - Determine image tag: `quay.io/{org}/{project}-{component}:latest`
    - Ensure Quay repo exists via `quay_ensure_repo`.
    - Run `podman_build` with the component's `dockerfile_ubi_path`.
    - If build succeeds:
      - Run `podman_push`.
      - Add image ref to `state["built_images"]`.
    - If build fails:
      - Store build error log in `state["error"]`.
      - Increment `state["build_retries"]`.
      - Use LLM to generate a brief diagnosis of the error (small focused call,
        not a full agent — just `llm.invoke()` with the error log).
      - Set `state["current_phase"] = PoCPhase.BUILD` (for routing logic).
      - Return early (conditional edge will route to containerize or fail).
  - If all components built successfully, clear error, set phase to BUILD.

**Acceptance criteria:**
- Successful build: images are pushed, `built_images` populated.
- Failed build: error is stored with diagnosis, retries incremented.
- Partial success: some components built, others failed.

---

### Task 26 — Build agent tests ✅

**Files:** `tests/test_build.py`

**Depends on:** Task 25

**Work:**
- Mock `subprocess.run` for podman, mock `httpx` for Quay.
- Test success: all components build and push → `built_images` populated.
- Test failure: podman build returns non-zero → error stored, retries incremented.
- Test partial: 2 components, one succeeds, one fails.
- Test retry counter: verify `build_retries` increments correctly.

**Acceptance criteria:**
- All test cases pass.

---

### Task 27 — Graph: add build node + retry edge ✅

**Files:** Update `src/autopoc/graph.py`

**Depends on:** Tasks 20, 25, 18

**Work:**
- Add `build` node to graph.
- Add edge: `containerize → build`.
- Implement `route_after_build(state: PoCState) -> str`:
  - If `state["error"]` is None → return `"deploy"` (all built).
  - If `state["build_retries"] < state config max_retries` → return `"containerize"` (retry).
  - Else → return `"failed"` (exhausted retries).
- Add conditional edges from `build`:
  - `"deploy"` → deploy node (added in Phase 4, wire to END for now)
  - `"containerize"` → containerize node (retry loop)
  - `"failed"` → END

**Acceptance criteria:**
- Graph compiles with build node and conditional edges.
- Retry loop is functional: build failure → containerize → build.
- Max retries terminates the loop.

---

### Task 28 — Retry loop integration test ✅

**Files:** `tests/test_retry_loop.py`

**Depends on:** Task 27

**Work:**
- Test the build → containerize → build retry cycle:
  - Mock first build to fail, containerize to "fix" the Dockerfile, second build to succeed.
  - Verify graph traverses: containerize → build (fail) → containerize → build (succeed) → END.
- Test retry exhaustion:
  - Mock all builds to fail.
  - Verify graph stops after `max_build_retries` iterations.

**Acceptance criteria:**
- Retry loop works correctly.
- Exhaustion terminates cleanly.
- Tests pass.

---

## Phase 4: Deploy

### Task 29 — Kubernetes/OpenShift tools ✅

**Files:** `src/autopoc/tools/k8s_tools.py` (simplified for E2E testing)

**Depends on:** Task 2

**Work:**
- Implemented kubectl-based tools for local E2E testing (k3d/minikube/kind):
  - `kubectl_apply(manifest_path: str, namespace: str) -> str`
  - `kubectl_apply_from_string(manifest: str, namespace: str) -> str`
  - `kubectl_create_namespace(name: str) -> str`
  - `kubectl_get(resource: str, name: str, namespace: str) -> str`
  - `kubectl_logs(pod: str, namespace: str, tail: int = 100) -> str`
  - `kubectl_wait_for_rollout(deployment: str, namespace: str, timeout: int = 300) -> str`
  - `kubectl_get_service_url(service: str, namespace: str) -> str`
  - `kubectl_delete(resource: str, name: str, namespace: str) -> str`

**Implementation notes:**
- Created k8s_tools.py with kubectl instead of oc for local testing
- Full OpenShift tools (oc, helm) can be added later for production use
- All functions use subprocess to run kubectl commands
- Proper timeout handling and error capture

**Acceptance criteria:**
- ✅ All tools construct correct `kubectl` commands
- Tools work against local K8s clusters (k3d/minikube/kind)

---

### Task 30 — K8s manifest templates ✅

**Files:** `src/autopoc/templates/deployment.yaml.j2`, `service.yaml.j2`

**Depends on:** Task 1

**Work:**
- **deployment.yaml.j2:**
  - Variables: `name`, `namespace`, `project_name`, `image`, `port`, `replicas`, `env_vars`,
    `resources`, `liveness_probe`, `readiness_probe`.
  - Includes: `securityContext` for OpenShift compatibility (non-root, drop all capabilities).
- **service.yaml.j2:**
  - Variables: `name`, `namespace`, `project_name`, `port`, `target_port`, `service_type`.
  - Supports ClusterIP, NodePort, or LoadBalancer.

**Implementation notes:**
- Route template skipped for now (OpenShift-specific, not needed for local K8s)
- Templates are production-ready with proper security context
- Support for resource requests/limits, health probes, environment variables

**Acceptance criteria:**
- ✅ Templates render to valid YAML
- ✅ Security context ensures non-root execution
- Templates work with both OpenShift and standard Kubernetes

---

### Task 31 — Helm chart skeleton

**Files:** `src/autopoc/templates/helm/Chart.yaml.j2`, `values.yaml.j2`,
`templates/deployment.yaml`, `templates/service.yaml`, `templates/route.yaml`

**Depends on:** Task 30

**Work:**
- Minimal Helm chart that wraps the same resources as Task 30.
- `Chart.yaml.j2`: name, version, appVersion parameterized.
- `values.yaml.j2`: image repo/tag, replicas, port, resources, route enabled/host.
- `templates/`: Standard Helm templates referencing `.Values`.
- The Jinja2 rendering creates a ready-to-use Helm chart directory, then Helm's own
  templating takes over at install time.

**Acceptance criteria:**
- Rendered chart passes `helm lint`.
- `helm template` produces valid YAML.

---

### Task 32 — Deploy system prompt ✅

**Files:** `src/autopoc/prompts/deploy.md`

**Depends on:** nothing

**Work:**
- Comprehensive system prompt (180+ lines) instructing the LLM to deploy components to Kubernetes.
- Includes:
  - **Strategy selection rules:**
    - Check for existing Helm charts, Kustomize overlays, or raw manifests
    - Adapt existing artifacts or generate from scratch using templates
  - **Resource sizing heuristics:**
    - Web frontend: 128Mi RAM / 100m CPU, limits 256Mi / 500m
    - API server: 256Mi RAM / 200m CPU, limits 512Mi / 1000m
    - ML inference: 1Gi RAM / 500m CPU, limits 2Gi / 2000m
  - **Probe patterns by framework:**
    - Flask/FastAPI: `GET /health`
    - Express: `GET /healthz`
    - Generic: TCP socket check
  - **ML/AI considerations:** Higher resources, GPU support, model storage
  - **Post-deploy tasks:** Commit manifests, wait for rollout, verify pods, get URLs

**Acceptance criteria:**
- ✅ Prompt covers all deployment strategies
- ✅ Includes framework-specific health check patterns
- ✅ Provides clear instructions for manifest generation and verification

---

### Task 33 — Deploy agent ✅

**Files:** `src/autopoc/agents/deploy.py`

**Depends on:** Tasks 4, 6, 16, 29, 30, 32

**Work:**
- Implemented `async def deploy_agent(state: PoCState) -> PoCState`:
  - Creates namespace using project name
  - Loads system prompt from `prompts/deploy.md`
  - Initializes ChatAnthropic with Claude 3.5 Sonnet
  - Creates ReAct agent with tools: `read_file`, `write_file`, `render_template`,
    `kubectl_apply`, `kubectl_apply_from_string`, `kubectl_create_namespace`,
    `kubectl_get`, `kubectl_logs`, `kubectl_wait_for_rollout`, `kubectl_get_service_url`,
    `git_commit`, `git_push`
  - Builds user message with component details and built images
  - Invokes agent to generate/apply manifests
  - Parses agent results to extract deployed resources and routes
  - Updates state with `deployed_resources`, `routes`, and any errors

**Implementation notes:**
- Uses kubectl tools instead of oc for local E2E testing
- Graceful error handling with try/except around agent invocation
- Extracts deployment info from tool calls and agent messages
- Falls back to inferring resources from components if tool parsing fails

**Acceptance criteria:**
- ✅ Agent can deploy components to local Kubernetes
- ✅ Returns deployed resources and accessible URLs
- ✅ Handles deployment failures gracefully

---

### Task 34 — Complete graph + end-to-end test ✅

**Files:** Updated `src/autopoc/graph.py`

**Depends on:** Tasks 27, 33

**Work:**
- ✅ Added `deploy` node to graph
- ✅ Implemented `route_after_deploy(state: PoCState) -> str`:
  - If `state["routes"]` exists and no error → return `"done"`
  - Otherwise → return `"failed"`
- ✅ Added conditional edges from `deploy` node
- ✅ Updated `route_after_build` to route to `"deploy"` instead of END
- ✅ Complete graph: intake → fork → containerize ⟲ build → deploy → END

**Implementation notes:**
- Full graph now supports the complete pipeline
- Build can loop back to containerize on failure (retry logic)
- Deploy marks final completion or failure
- Graph docstring updated to reflect full pipeline

**Acceptance criteria:**
- ✅ Full graph compiles without errors
- ✅ All conditional edges properly configured
- ✅ Graph supports intake through deployment
- E2E tests validate full pipeline (see Task 39)

---

## Phase 5: Hardening & Polish

### Task 35 — Logging, tracing, credential validation

**Files:** Update `src/autopoc/config.py`, `src/autopoc/graph.py`, all agents

**Depends on:** Task 34

**Work:**
- **Structured logging:**
  - Add `rich` logging handler with structured output.
  - Each agent logs: phase entry/exit, tool calls, LLM invocations, errors.
  - Include context: project name, component name, phase.
- **LangSmith & LangGraph Studio tracing:**
  - If `LANGCHAIN_TRACING_V2=true` is set, traces are automatically sent to LangSmith.
  - Add `LANGCHAIN_PROJECT` default to `"autopoc"`.
  - Add a `langgraph.json` configuration file at the root to enable tracing and execution via LangGraph Studio desktop app.
  - Document the tracing options in `.env.example`.
- **Credential validation:**
  - Add `validate_credentials()` function called at startup (before graph runs):
    - GitLab: `GET /api/v4/user` with token → verify 200.
    - Quay: `GET /api/v1/user/` with token → verify auth works.
    - OpenShift: `oc whoami` → verify logged in.
    - Anthropic: quick `llm.invoke("test")` or just validate key format.
  - Print status for each service. Fail fast if critical ones are down.

**Acceptance criteria:**
- Logs are structured and readable.
- Startup validates all credentials before doing work.
- Tracing works when LangSmith env vars are set.

---

### Task 36 — CLI polish + state persistence

**Files:** Update `src/autopoc/cli.py`, `src/autopoc/graph.py`

**Depends on:** Tasks 34, 35

**Work:**
- **Rich CLI output:**
  - Progress panel showing current phase + component being processed.
  - Phase completion checkmarks.
  - Summary table at end: components, images, routes, errors.
  - Elapsed time.
- **State persistence / checkpointing:**
  - Add LangGraph `SqliteSaver` or `MemorySaver` as checkpointer.
  - Assign `thread_id` per run (e.g., `{project_name}-{timestamp}`).
  - Add `autopoc resume --thread-id <id>` command to resume a failed run.
  - Store checkpoints in `{work_dir}/checkpoints/`.
- **Additional CLI commands:**
  - `autopoc status --thread-id <id>` — Show state of a previous/running run.
  - `autopoc list` — List recent runs from checkpoint store.

**Acceptance criteria:**
- CLI output is clear and informative.
- A run can be interrupted and resumed from the last completed phase.
- Summary report is printed at the end of each run.

---

## Phase 6: Local E2E Harness

### Task 37 — Docker-compose E2E test infrastructure ✅

**Files:** `docker-compose.test.yml`, `scripts/setup-e2e.sh`, `scripts/teardown-e2e.sh`,
`tests/e2e/conftest.py`, `tests/e2e/test_e2e_intake_fork.py`

**Depends on:** Phase 2 complete (at minimum Tasks 12, 13, 20)

**Work:**
- Create `docker-compose.test.yml` with:
  - GitLab CE container (port 8080, SSH on 2222)
  - Volume mounts for persistence during test run
- Create `scripts/setup-e2e.sh`:
  - Starts docker-compose
  - Waits for GitLab health check (`/api/v4/version`)
  - Creates a test user and personal access token via GitLab API / Rails console
  - Creates the target group for forked repos
  - Writes credentials to `.env.test`
- Create `scripts/teardown-e2e.sh`:
  - `docker-compose -f docker-compose.test.yml down -v`
- Create `tests/e2e/conftest.py`:
  - Skip all tests unless `--e2e` flag is passed
  - Load config from `.env.test`
  - Fixture to provide a real GitLab-connected config
- Create `tests/e2e/test_e2e_intake_fork.py`:
  - Clone a small public GitHub repo
  - Run intake agent (with real or mocked LLM)
  - Run fork agent against local GitLab
  - Verify project exists on local GitLab via API
  - Verify all branches/tags were pushed
- Later phases can extend with:
  - Local Docker registry for build & push E2E (Phase 3)
  - MicroShift / Kind for deploy E2E (Phase 4)

**Acceptance criteria:**
- `scripts/setup-e2e.sh` starts GitLab CE and creates test credentials.
- `pytest tests/e2e/ --e2e` runs against local GitLab and passes.
- `scripts/teardown-e2e.sh` cleans up completely.
- Default `pytest` (without `--e2e`) skips all E2E tests.

---

### Task 38 — Build & Push E2E tests ✅

**Files:** `tests/e2e/test_e2e_build.py`

**Depends on:** Tasks 28, 37

**Work:**
- Create `tests/e2e/test_e2e_build.py` to test the build phase.
- Pass state (either generated from intake/fork or mocked) into the `build_agent`.
- Verify that `podman` can build the image based on the generated Dockerfile.
- Verify the image is successfully pushed to the local Quay.io instance (configured via E2E setup).
- Clean up local podman images after test to save disk space.

**Acceptance criteria:**
- `pytest tests/e2e/test_e2e_build.py --e2e` successfully builds and pushes the image.
- The image appears in the local Quay instance.

---

### Task 39 — Deploy E2E tests & Full Pipeline Run ✅

**Files:** `tests/e2e/test_e2e_deploy.py`, `tests/e2e/test_e2e_full.py`

**Depends on:** Tasks 34, 38

**Work:**
- ✅ Created `tests/e2e/test_e2e_deploy.py`:
  - `test_deploy_to_k8s`: Tests deploy agent against local K8s cluster
  - `test_deploy_handles_missing_cluster`: Tests error handling when cluster unavailable
  - Uses mock built images (nginx:alpine) for isolated deploy testing
  - Includes kubectl availability check and namespace cleanup fixtures
- ✅ Created `tests/e2e/test_e2e_full.py`:
  - `test_full_pipeline_intake_to_deploy`: Runs complete pipeline (Intake → Deploy)
  - `test_pipeline_with_build_retry`: Tests build retry loop with intentionally broken Dockerfile
  - Creates realistic sample Flask app repository for testing
  - Validates all phases: intake detection, GitLab fork, Dockerfile.ubi generation,
    image build/push, Kubernetes deployment
  - Comprehensive cleanup fixtures for GitLab projects, Quay repos, and K8s namespaces

**Implementation notes:**
- Tests require kubectl and a local K8s cluster (k3d/minikube/kind)
- Tests gracefully skip if cluster is unavailable
- Full pipeline test marked as `@pytest.mark.slow` (takes several minutes with real LLM)
- Tests validate state transitions, resource creation, and error handling
- 4 new E2E tests added (2 in test_e2e_deploy.py, 2 in test_e2e_full.py)

**Acceptance criteria:**
- ✅ `pytest tests/e2e/ --e2e` collects all tests successfully
- ✅ Tests skip gracefully without kubectl/cluster
- ✅ Deploy tests validate manifest application
- ✅ Full pipeline test validates end-to-end flow
- Tests require real LLM calls for full validation (can be mocked for CI)

---

## Phase 7: PoC Intelligence

### Task 40 — State updates for PoC intelligence ✅

**Files:** `src/autopoc/state.py`

**Depends on:** Task 4

**Work:**
- Add new `PoCPhase` values: `POC_PLAN`, `POC_EXECUTE`, `POC_REPORT`
- Add new TypedDicts:
  - `PoCScenario` — structured test scenario (name, description, type, endpoint,
    input_data, expected_behavior, timeout_seconds)
  - `PoCInfrastructure` — infrastructure requirements (needs_inference_server,
    inference_server_type, needs_vector_db, vector_db_type, needs_embedding_model,
    embedding_model, needs_gpu, gpu_type, needs_pvc, pvc_size, sidecar_containers,
    extra_env_vars, odh_components, resource_profile)
  - `PoCResult` — test execution result (scenario_name, status, output,
    error_message, duration_seconds)
- Add new fields to `PoCState`:
  - `poc_plan: str` — raw markdown content
  - `poc_plan_path: str` — file path in repo
  - `poc_scenarios: list[PoCScenario]` — structured test scenarios
  - `poc_infrastructure: PoCInfrastructure` — infrastructure requirements
  - `poc_type: str` — project classification
  - `poc_results: list[PoCResult]` — test execution results
  - `poc_script_path: str` — path to generated test script
  - `poc_report_path: str` — path to generated report

**Acceptance criteria:**
- All types importable: `from autopoc.state import PoCScenario, PoCInfrastructure, PoCResult`
- Existing tests still pass (backward compatible — all new fields use `total=False`)

---

### Task 41 — PoC Plan system prompt ✅

**Files:** `src/autopoc/prompts/poc_plan.md`

**Depends on:** nothing

**Work:**
- Write system prompt instructing the LLM to:
  1. **Classify the project** in the context of ODH/OpenShift AI:
     - Model serving (inference endpoint)
     - RAG pipeline (retrieval-augmented generation)
     - Data pipeline (ETL, feature engineering)
     - Training job (model training/fine-tuning)
     - Notebook-based exploration
     - Web app with ML features
     - Infrastructure component (operator, controller, library)
  2. **Define what "proving it works" means** for this type of project:
     - Model serving → deploy with inference server, send prompt, validate response
     - RAG → package with vector DB, embedding model, test retrieval + generation
     - Data pipeline → verify data flows with sample data
     - Web app → verify endpoints respond, test key flows
     - Training → verify training starts, produces checkpoints
  3. **Determine infrastructure requirements** that affect Dockerfile and deployment:
     - Inference server needs (vLLM, TGI, Triton, custom)
     - Sidecar containers (vector DB, Redis, etc.)
     - PVCs for model weights or data
     - GPU resources
     - ODH component references (ModelMesh, KServe, DSP)
     - Resource profile (CPU/memory sizing)
  4. **Define 2-5 concrete test scenarios** with:
     - name, description, type, endpoint, input_data, expected_behavior, timeout
- Include ODH component reference table
- Include resource profile guidelines
- Include 2-3 few-shot examples (model serving, RAG, web app)

**Acceptance criteria:**
- Prompt produces structured JSON output matching `PoCScenario[]` and `PoCInfrastructure` schemas
- Prompt includes ODH-aware classification and infrastructure planning
- Prompt instructs writing poc-plan.md to the repo

---

### Task 42 — PoC Plan agent ✅

**Files:** `src/autopoc/agents/poc_plan.py`

**Depends on:** Tasks 40, 41, 6

**Work:**
- Implement `async def poc_plan_agent(state: PoCState) -> dict`:
  - Load system prompt from `prompts/poc_plan.md`
  - Create fresh LLM instance via `create_llm()`
  - Build user message with:
    - `repo_summary` from intake
    - `components[]` with detected languages, ML workloads, ports
    - `local_clone_path` for tool access
  - Create ReAct agent with tools: `list_files`, `read_file`, `search_files`, `write_file`
  - Invoke agent — it reads the repo deeper, generates poc-plan.md, writes it
  - Parse structured output into `poc_scenarios`, `poc_infrastructure`, `poc_type`
  - Return partial state update
- Implement helper functions:
  - `_parse_poc_plan_output(raw: str) -> dict` — parse JSON from LLM output
  - `_validate_scenario(s: dict) -> PoCScenario` — validate/normalize scenario
  - `_validate_infrastructure(i: dict) -> PoCInfrastructure` — validate/normalize infra

**Acceptance criteria:**
- Agent generates poc-plan.md and writes it to the repo
- Structured state fields are populated: `poc_plan`, `poc_scenarios`, `poc_infrastructure`
- Agent can run in parallel with fork (no shared mutable state dependencies)

---

### Task 43 — PoC Plan tests ✅

**Files:** `tests/test_poc_plan.py`

**Depends on:** Tasks 42, 10

**Work:**
- Test against fixture repos with mocked LLM:
  - **Python Flask app:** Classified as "web-app", scenarios include health check + API test
  - **ML serving:** Classified as "model-serving", infrastructure includes inference server
  - **Node monorepo:** Classified as "web-app", multi-component scenarios
- Test helper functions:
  - `_parse_poc_plan_output` with valid JSON, markdown-wrapped JSON, malformed JSON
  - `_validate_scenario` with complete and partial scenario dicts
  - `_validate_infrastructure` with complete and partial infra dicts
- Test poc-plan.md is written to correct path

**Acceptance criteria:**
- All tests pass with mocked LLM
- Correct classification and scenario generation for each fixture type

---

### Task 44 — Parallel graph: fan-out / fan-in ✅

**Files:** `src/autopoc/graph.py`

**Depends on:** Tasks 42, 34

**Work:**
- Modify `build_graph()` to support parallel execution:
  - Add `poc_plan` node
  - Replace `graph.add_edge("intake", "fork")` with fan-out:
    ```python
    graph.add_conditional_edges(
        "intake",
        lambda _: ["poc_plan", "fork"],
    )
    ```
  - Add fan-in edges:
    ```python
    graph.add_edge("poc_plan", "containerize")
    graph.add_edge("fork", "containerize")
    ```
    LangGraph will wait for both `poc_plan` and `fork` to complete before
    running `containerize` (natural join semantics).
  - Remove old `graph.add_edge("intake", "fork")` and `graph.add_edge("fork", "containerize")`
- Update `route_after_deploy` to route to `"poc_execute"` instead of `"done"` on success
- Verify existing tests still pass (graph structure change is backward compatible
  for state flow since poc_plan writes to new fields that don't conflict with fork)

**Acceptance criteria:**
- Graph compiles with parallel structure
- `poc_plan` and `fork` can run concurrently
- `containerize` waits for both to complete
- Existing retry loops still work
- Graph visualization shows the parallel structure

---

### Task 45 — Update containerize for PoC awareness ✅

**Files:** `src/autopoc/prompts/containerize.md`, `src/autopoc/agents/containerize.py`

**Depends on:** Tasks 42, 18

**Work:**
- **Prompt updates (`containerize.md`):**
  - Add new section: "## PoC Infrastructure Requirements"
  - Instructions to check `poc_infrastructure` for:
    - If `needs_inference_server` → include inference server (vLLM, TGI, Triton) in
      Dockerfile or as a separate stage
    - If `needs_vector_db` with `in-memory` → include vector DB library (ChromaDB, FAISS)
      in dependencies
    - If `needs_embedding_model` → include embedding model download or mount point
    - If `needs_gpu` → use CUDA-capable base image
    - If extra env vars specified → set them in Dockerfile
  - Add examples for each infrastructure type
- **Agent updates (`containerize.py`):**
  - In `_build_user_message()`, include `poc_infrastructure` and `poc_type` from state
  - If poc_plan is available, include relevant sections in the user message
  - Preserve backward compatibility (poc_plan fields may be absent for existing flows)

**Acceptance criteria:**
- Containerize agent reads poc_infrastructure and adjusts Dockerfile generation
- Backward compatible: works without poc_plan in state
- Existing containerize tests still pass

---

### Task 46 — Update deploy for PoC awareness ✅

**Files:** `src/autopoc/prompts/deploy.md`, `src/autopoc/agents/deploy.py`

**Depends on:** Tasks 42, 33

**Work:**
- **Prompt updates (`deploy.md`):**
  - Add new section: "## PoC Infrastructure Deployment"
  - Instructions to check `poc_infrastructure` for:
    - If `sidecar_containers` → deploy them alongside main containers
    - If `needs_vector_db` with non-in-memory → deploy separate vector DB pod/service
    - If `needs_pvc` → create PersistentVolumeClaim with specified size
    - If `needs_gpu` → add GPU resource requests to deployment
    - If `odh_components` specified → add relevant labels/annotations
    - If `resource_profile` specified → use corresponding resource sizing
  - Add deployment patterns for each infrastructure type
- **Agent updates (`deploy.py`):**
  - In `_build_user_message()`, include `poc_infrastructure` and `poc_scenarios` from state
  - Include the poc_plan markdown content for full context
  - Preserve backward compatibility

**Acceptance criteria:**
- Deploy agent reads poc_infrastructure and creates appropriate resources
- Sidecar containers, PVCs, GPU resources deployed when specified
- Backward compatible: works without poc_plan in state
- Existing deploy tests still pass

---

### Task 47 — Script execution tool ✅

**Files:** `src/autopoc/tools/script_tools.py`, `tests/test_script_tools.py`

**Depends on:** Task 1

**Work:**
- Implement `@tool`-decorated function:
  - `run_script(script_path: str, timeout: int = 300, args: str = "") -> str`
    - Execute a Python script via `subprocess.run`
    - Capture stdout + stderr
    - Enforce timeout (default 5 minutes)
    - Return structured output: exit code, stdout, stderr
    - Handle common failure modes: script not found, permission denied, timeout
- Security considerations:
  - Only execute scripts within the work directory
  - Path validation (no traversal)
  - Timeout enforcement

**Tests:**
- Test successful script execution
- Test script failure (non-zero exit)
- Test timeout handling
- Test path validation (reject paths outside work dir)
- Test missing script

**Acceptance criteria:**
- Tool executes Python scripts safely with timeout
- Output is captured and returned in structured format
- Path traversal is prevented
- All tests pass

---

### Task 48 — PoC Execute system prompt ✅

**Files:** `src/autopoc/prompts/poc_execute.md`

**Depends on:** nothing

**Work:**
- System prompt instructing the LLM to:
  1. **Read the PoC plan** from state (poc_plan and poc_scenarios)
  2. **Read deployment info** from state (routes, deployed_resources)
  3. **Generate a Python test script** (`poc_test.py`) that:
     - Imports `requests`, `json`, `time`, `sys`
     - For each scenario in poc_scenarios:
       - Implements the test according to scenario type
       - Includes retry logic for service readiness (exponential backoff)
       - Captures timing information
       - Outputs structured JSON results to stdout
     - Handles errors gracefully
     - Returns non-zero exit code if any test fails
  4. **Execute the script** via `run_script` tool
  5. **Parse results** from script output
  6. **Debug failures** if needed:
     - Check pod status via `kubectl_get`
     - Read pod logs via `kubectl_logs`
     - Determine if failure is transient or permanent
- Include test script template / example
- Include patterns for common PoC types (HTTP inference, RAG query, health check)

**Acceptance criteria:**
- Prompt covers test script generation for all major PoC types
- Includes structured output format for result parsing
- Includes debugging/retry guidance

---

### Task 49 — PoC Execute agent ✅

**Files:** `src/autopoc/agents/poc_execute.py`

**Depends on:** Tasks 40, 47, 48

**Work:**
- Implement `async def poc_execute_agent(state: PoCState) -> dict`:
  - Load system prompt from `prompts/poc_execute.md`
  - Create fresh LLM instance
  - Build user message with:
    - `poc_plan` — the full PoC plan markdown
    - `poc_scenarios` — structured test scenarios
    - `routes` — deployed service URLs
    - `deployed_resources` — K8s resources created
    - `local_clone_path` — where to write test script
  - Create ReAct agent with tools:
    - `write_file`, `read_file` — for test script
    - `run_script` — execute the test script
    - `kubectl_get`, `kubectl_logs` — for debugging
  - Invoke agent
  - Parse execution results into `PoCResult[]`
  - Commit test script to repo
  - Return partial state: `poc_results`, `poc_script_path`
- Implement helpers:
  - `_parse_poc_results(output: str) -> list[PoCResult]` — parse JSON results from script output

**Acceptance criteria:**
- Agent generates a working test script based on PoC scenarios
- Script is executed and results captured
- Results are structured as `PoCResult[]`
- Test script is committed to repo

---

### Task 50 — PoC Execute tests ✅

**Files:** `tests/test_poc_execute.py`

**Depends on:** Task 49

**Work:**
- Test with mocked LLM and mocked script execution:
  - Verify test script generation for model serving scenario
  - Verify test script generation for web app scenario
  - Verify result parsing from script output (pass/fail/error cases)
  - Verify error handling when script times out
  - Verify debugging flow (kubectl_logs called on failure)
- Test `_parse_poc_results` with valid JSON, malformed output, empty output

**Acceptance criteria:**
- All tests pass with mocked LLM and subprocess
- Correct result parsing for all outcome types

---

### Task 51 — PoC Report system prompt ✅

**Files:** `src/autopoc/prompts/poc_report.md`

**Depends on:** nothing

**Work:**
- System prompt instructing the LLM to generate a comprehensive PoC report:
  - **Executive Summary** — 2-3 sentences: what was tested, overall outcome
  - **PoC Objectives** — from poc_plan: what we set out to prove
  - **Project Analysis** — repo_summary, components, technologies detected
  - **Infrastructure Deployed** — images built, K8s resources created, routes
  - **Test Results** — markdown table with columns:
    | Scenario | Status | Duration | Details |
  - **Logs & Evidence** — key excerpts from test output, response samples
  - **Timing** — pipeline phase durations
  - **Recommendations** — production readiness, next steps, improvements
  - **ODH/OpenShift AI Considerations** — relevant ODH components, migration path
- Structured data sections should use markdown tables and code blocks
- Include example report structure

**Acceptance criteria:**
- Prompt produces a well-structured markdown report
- All sections are covered with appropriate detail

---

### Task 52 — PoC Report agent ✅

**Files:** `src/autopoc/agents/poc_report.py`

**Depends on:** Tasks 40, 51

**Work:**
- Implement `async def poc_report_agent(state: PoCState) -> dict`:
  - Load system prompt from `prompts/poc_report.md`
  - Create fresh LLM instance
  - Build user message with ALL relevant state fields:
    - Project info: `project_name`, `source_repo_url`
    - Analysis: `repo_summary`, `components`, `poc_type`
    - Plan: `poc_plan`, `poc_scenarios`, `poc_infrastructure`
    - Build: `built_images`
    - Deploy: `deployed_resources`, `routes`
    - Execute: `poc_results`, `poc_script_path`
    - Errors: `error`, `build_retries`, `deploy_retries`
  - Create ReAct agent with tools: `write_file`, `read_file`
  - Invoke agent — it generates poc-report.md and writes it
  - Commit report to repo
  - Return partial state: `poc_report_path`

**Acceptance criteria:**
- Agent generates a comprehensive poc-report.md
- Report includes all pipeline results and recommendations
- Report is committed to repo

---

### Task 53 — PoC Report tests ✅

**Files:** `tests/test_poc_report.py`

**Depends on:** Task 52

**Work:**
- Test with mocked LLM:
  - Verify report is generated with all sections
  - Verify all state fields are included in user message
  - Verify report is written to correct path
  - Test with partial state (some phases failed)
  - Test with full state (all phases succeeded)

**Acceptance criteria:**
- All tests pass with mocked LLM
- Report handles both success and partial failure states

---

### Task 54 — Complete graph wiring ✅

**Files:** `src/autopoc/graph.py`

**Depends on:** Tasks 44, 49, 52

**Work:**
- Add `poc_execute` and `poc_report` nodes to graph
- Update `route_after_deploy`:
  - On success: route to `"poc_execute"` instead of `"done"`
  - On retry: route to `"deploy"` (unchanged)
  - On failure: route to END (unchanged)
- Add edges:
  - `poc_execute → poc_report`
  - `poc_report → END`
- Update graph docstring and log message

**Acceptance criteria:**
- Full graph: `intake → [poc_plan ∥ fork] → containerize ⟲ build → deploy ⟲ poc_execute → poc_report → END`
- All routing functions work correctly
- Graph compiles and visualizes correctly

---

### Task 55 — CLI updates for PoC output ✅

**Files:** `src/autopoc/cli.py`

**Depends on:** Tasks 54

**Work:**
- Update `run` command output to display:
  - PoC type classification
  - PoC plan summary (first paragraph or objectives)
  - Test results table (scenario name, status, duration)
  - PoC report file path
  - Updated initial state with new fields (poc_plan, poc_scenarios, etc.)
- Add color coding for test results (green=pass, red=fail, yellow=skip)

**Acceptance criteria:**
- CLI displays PoC-specific output when poc_plan is present
- Test results are shown in a readable table
- Backward compatible: old runs without PoC fields still display correctly

---

### Task 56 — Integration tests for PoC Intelligence

**Files:** `tests/test_graph_poc.py`

**Depends on:** Task 54

**Work:**
- End-to-end graph test with all new nodes (mocked LLM):
  - Verify parallel execution: poc_plan and fork both run after intake
  - Verify containerize receives poc_infrastructure in state
  - Verify deploy receives poc_infrastructure in state
  - Verify poc_execute runs after successful deploy
  - Verify poc_report runs after poc_execute
  - Verify state contains all new fields at end
- Test failure modes:
  - Build failure → retry → success → poc_execute → poc_report
  - Deploy failure → retry exhausted → END (no poc_execute/report)

**Acceptance criteria:**
- Full graph traversal works end-to-end with mocked agents
- Parallel fan-out/fan-in is verified
- State transitions are correct through all new nodes

---

## Testing Strategy Summary

| Layer | What | How | Command |
|-------|------|-----|---------|
| **Unit** | Individual tools (file, git, podman, script) | Temp dirs, mocked subprocess | `pytest` |
| **Unit** | Config, state | Direct instantiation | `pytest` |
| **Agent** | Each agent in isolation (incl. poc_plan, poc_execute, poc_report) | Mocked LLM, mocked external tools | `pytest` |
| **Integration** | Partial graph (intake→fork→containerize) | Mocked LLM + GitLab, real git on temp repos | `pytest` |
| **Integration** | Full graph with PoC nodes | All mocks, verify parallel execution | `pytest` |
| **Local E2E** | Pipeline against local Docker services | GitLab CE in Docker, real git, real/mocked LLM | `pytest tests/e2e/ --e2e` |
| **Live E2E** | Full pipeline against real services | Real LLM, real GitLab/Quay/OpenShift | Manual with real `.env` |

Default `pytest` runs all mocked tests (fast, no external dependencies).
Local E2E requires `docker-compose.test.yml` running and `--e2e` flag.

---

## Estimated Effort

| Phase | Tasks | Estimated days |
|-------|-------|---------------|
| 1. Foundation | 1–11 | 4–5 days |
| 2. Fork & Containerize | 12–22 | 4–5 days |
| 3. Build & Push | 23–28 | 3 days |
| 4. Deploy | 29–34 | 4–5 days |
| 5. Hardening | 35–36 | 2–3 days |
| 6. Local E2E Harness | 37–39 | 1–2 days |
| 7. PoC Intelligence | 40–56 | 8–12 days |
| **Total** | **56 tasks** | **~27–36 days** |

### Phase 7 Work Streams (can be parallelized)

| Stream | Tasks | Description | Estimated days |
|--------|-------|-------------|---------------|
| A: PoC Plan | 40, 41, 42, 43 | State + prompt + agent + tests | 3 days |
| B: Graph + Integration | 44, 45, 46 | Parallel graph, containerize/deploy updates | 2-3 days |
| C: PoC Execute | 47, 48, 49, 50 | Script tool + prompt + agent + tests | 3 days |
| D: PoC Report | 51, 52, 53 | Prompt + agent + tests | 1-2 days |
| E: Wiring + CLI | 54, 55, 56 | Full graph, CLI updates, integration tests | 2 days |

**Critical path for Phase 7:** A → B → C → E (Stream D can run in parallel with C)
