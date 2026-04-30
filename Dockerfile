# AutoPoC — Multi-stage container build
#
# Stage 1: Build the shiv zipapp binary
# Stage 2: Minimal runtime image with kubectl + git
#
# Build:  podman build -t autopoc:latest .
# Run:    podman run --rm --env-file .env autopoc:latest run --name my-project --repo https://github.com/org/repo
#
# Required env vars at runtime — see deploy/secret.yaml.example

# ---------------------------------------------------------------------------
# Stage 1 — Builder
# ---------------------------------------------------------------------------
FROM registry.access.redhat.com/ubi9/python-312:latest AS builder

WORKDIR /build

# Install shiv (pinned version)
RUN pip install --no-cache-dir shiv==1.0.8

# Copy dependency lockfile first for layer caching
COPY requirements.lock pyproject.toml ./

# Copy source and build assets
COPY src/ src/
COPY Makefile ./

# Build the shiv zipapp binary
RUN make build

# ---------------------------------------------------------------------------
# Stage 2 — Runtime
# ---------------------------------------------------------------------------
FROM registry.access.redhat.com/ubi9/python-312:latest

LABEL io.k8s.description="AutoPoC — automated proof-of-concept pipeline agent" \
      io.openshift.tags="autopoc,langgraph,ai-agent" \
      maintainer="aicatalyst-team"

USER 0

# Apply security patches and remove unnecessary packages
RUN dnf update -y --security && \
    dnf remove -y vim-minimal vim-filesystem rsync && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# Install kubectl and oc
ARG KUBECTL_VERSION=v1.36.0
RUN curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl && \
    chmod +x /usr/local/bin/kubectl

ARG OC_VERSION=4.21.11
RUN curl -fsSL "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/${OC_VERSION}/openshift-client-linux.tar.gz" \
    | tar xzf - -C /usr/local/bin oc && \
    chmod +x /usr/local/bin/oc

# Copy the shiv binary from builder
COPY --from=builder /build/dist/autopoc /usr/local/bin/autopoc
RUN chmod +x /usr/local/bin/autopoc

# Create workspace directory writable by default user
RUN mkdir -p /workspace && chown 1001:0 /workspace

# Switch back to non-root user
USER 1001

WORKDIR /workspace

# Default working directory for cloned repos and temp files
ENV WORK_DIR=/workspace

ENTRYPOINT ["autopoc"]
CMD ["--help"]
