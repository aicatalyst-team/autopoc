# UBI Dockerfile Rules

All Dockerfiles MUST use Red Hat Universal Base Images (UBI) and follow OpenShift compatibility rules.

## UBI Base Image Mapping

| Source Image | UBI Equivalent |
|---|---|
| `python:3.x` / `python:3.x-slim` | `registry.access.redhat.com/ubi9/python-312` |
| `node:2x` / `node:2x-slim` / `node:2x-alpine` | `registry.access.redhat.com/ubi9/nodejs-22` |
| `golang:1.2x` | `registry.access.redhat.com/ubi9/go-toolset` |
| `eclipse-temurin` / `openjdk` | `registry.access.redhat.com/ubi9/openjdk-21` |
| `rust` | `registry.access.redhat.com/ubi9/ubi-minimal` + `microdnf install` |
| `alpine` / `ubuntu` / `debian` | `registry.access.redhat.com/ubi9/ubi-minimal` |
| `nginx` | `registry.access.redhat.com/ubi9/nginx-124` |
| Multi-stage runtime (binaries) | `registry.access.redhat.com/ubi9/ubi-minimal` |
| Multi-stage runtime (JARs) | `registry.access.redhat.com/ubi9/openjdk-21-runtime` |
| GPU / CUDA workloads | `nvcr.io/nvidia/cuda:12.x-runtime-ubi9` (keep as-is) |

## Package Manager Rules

| Image Type | Package Manager | Never Use |
|---|---|---|
| Full UBI (`ubi9/python-*`, `ubi9/nodejs-*`, `ubi9/go-toolset`, etc.) | `dnf` | `microdnf` |
| Minimal UBI (`ubi9/ubi-minimal`) | `microdnf` | `dnf` |

When adapting existing Dockerfiles:
- `apt-get install` -> `dnf install -y PKG && dnf clean all`
- `apk add` -> `dnf install -y PKG && dnf clean all`
- `yum install` -> `dnf install -y PKG && dnf clean all`

**curl on nodejs images**: UBI nodejs images have `curl-minimal` pre-installed. Do NOT install full `curl` -- it conflicts. Use `--allowerasing` only if you absolutely need full curl.

## OpenShift Compatibility (MANDATORY)

### 1. Final USER must be 1001
```dockerfile
# WRONG - leaves root as final user
USER 0
RUN dnf install -y gcc && dnf clean all

# CORRECT - switches back to non-root
USER 0
RUN dnf install -y gcc && dnf clean all
USER 1001
```

### 2. Arbitrary UID Support
Before the final `USER 1001`, add:
```dockerfile
RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root
```
This allows OpenShift's random UID assignment to work (the random UID is in group 0).

### 3. No Privileged Ports
- Port 80 -> 8080
- Port 443 -> 8443
- Any port < 1024 -> use a port >= 1024

### 4. Root-Only Operations
UBI images default to non-root (UID 1001). Package installation needs `USER 0`:
```dockerfile
USER 0
RUN dnf install -y gcc python3-devel && dnf clean all
USER 1001
```

### 5. WORKDIR
Use `/opt/app-root/src` as the working directory.

## Single-Stage vs Multi-Stage

- **Single-stage**: Interpreted languages (Python, Node.js, Ruby) -- no compilation step.
- **Multi-stage**: Compiled languages (Go, Java, Rust, C/C++) -- builder + minimal runtime.

## ML Workload: GPU vs CPU Packages

Use CPU-only package variants unless `infrastructure.needs_gpu` is explicitly true:

| Package | CPU (default) | GPU |
|---|---|---|
| faiss | `faiss-cpu` | `faiss-gpu` |
| torch | `torch --extra-index-url https://download.pytorch.org/whl/cpu` | `torch` |
| onnxruntime | `onnxruntime` | `onnxruntime-gpu` |
| tensorflow | `tensorflow-cpu` | `tensorflow` |

**`faiss` does not exist on PyPI.** Always use `faiss-cpu` or `faiss-gpu`.

**torch CPU**: `--index-url` replaces PyPI entirely. Other packages in the same `pip install` line won't be found. Install torch separately or use `--extra-index-url`.

Always use `pip install --no-cache-dir` for large ML dependencies to keep image size down.

## Runtime Execution Model

Check `deployment_model` from the PoC plan:

| deployment_model | listens_on_port | Dockerfile Pattern |
|---|---|---|
| `deployment` | `true` | CMD starts server, add `EXPOSE <port>` |
| `deployment` | `false` | CMD starts worker, no EXPOSE |
| `job` | N/A | ENTRYPOINT = CLI binary, CMD = `["--help"]`, no EXPOSE |

### Entrypoint Dependencies
If CMD/ENTRYPOINT references a CLI tool (streamlit, uvicorn, gunicorn, flask, celery, gradio), ensure it's **explicitly pip-installed**. Don't assume it's a transitive dependency.

## .dockerignore

Always create `.dockerignore` in the component's directory:
```
.git
*.md
LICENSE
kubernetes/
poc-plan.md
tests/
docs/
__pycache__/
node_modules/
.env*
*.pyc
```

## Build Error Retry Context

When re-entering Phase 5 after a build failure, check the error in `poc-state.yaml`:
- **COPY file not found**: Check if `source_dir` prefix is needed on COPY paths
- **Missing system dep**: Add `dnf install -y <package>`
- **Permission denied**: Ensure `chgrp -R 0` covers the affected directory
- **Package not found**: Check package name, add correct index URL for ML packages

## Runtime Container Fix Context

When re-entering Phase 5 after apply/test failure with `fix-dockerfile` action:
- **Missing Python module**: Add to `pip install` in Dockerfile
- **Command not found**: Install the binary (`dnf install` or `pip install`)
- **Permission denied**: Fix file permissions with `chgrp`/`chmod`
- **Wrong entrypoint**: Fix CMD/ENTRYPOINT based on the error
- **OOMKilled**: Increase resource limits in manifest (this is actually a deploy fix, not dockerfile)

## Installing Software Priority

1. **System package manager** (`dnf`/`microdnf`): For system libraries and tools
2. **Language package manager** (`pip`, `npm`, `cargo`, `go install`): For application dependencies
3. **curl binary download (last resort)**: Place in `/usr/local/bin/`. Never use `curl | bash` (installs to `$HOME/.xxx/bin` which breaks across USER switches)
4. **bun**: Install via `npm install -g bun`, NOT via `curl bun.sh/install`
