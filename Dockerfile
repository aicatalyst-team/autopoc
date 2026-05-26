# AutoPoC — OpenCode-based PoC pipeline container
#
# OpenCode is the orchestration harness; Python tools provide API clients
# and utilities. kubectl, oc, podman, vale, and git are available as CLI tools.
#
# Build:  podman build -t autopoc-opencode:latest .
# Run:    podman run --rm --env-file .env autopoc-opencode:latest \
#           run --dangerously-skip-permissions "Run PoC for my-project from https://github.com/org/repo"
#
# Required env vars at runtime — see deploy/overlays/example/secret.yaml.example

FROM registry.access.redhat.com/ubi9/python-312:latest

LABEL io.k8s.description="AutoPoC — OpenCode-driven PoC pipeline for OpenShift AI" \
      io.openshift.tags="autopoc,opencode,ai-agent" \
      maintainer="aicatalyst-team"

USER 0

# Apply security patches and remove unnecessary packages
RUN dnf update -y --security && \
    dnf remove -y vim-minimal vim-filesystem rsync && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# ---------------------------------------------------------------------------
# System tools: kubectl, oc, vale, opencode
# ---------------------------------------------------------------------------

# Install kubectl
ARG KUBECTL_VERSION=v1.36.0
RUN curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    -o /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl

# Install oc (OpenShift CLI)
ARG OC_VERSION=4.21.11
RUN curl -fsSL "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/${OC_VERSION}/openshift-client-linux.tar.gz" \
    | tar xzf - -C /usr/local/bin oc && chmod +x /usr/local/bin/oc

# Install vale (prose linter)
ARG VALE_VERSION=3.14.2
RUN curl -fsSL "https://github.com/errata-ai/vale/releases/download/v${VALE_VERSION}/vale_${VALE_VERSION}_Linux_64-bit.tar.gz" \
    | tar xzf - -C /usr/local/bin vale && chmod +x /usr/local/bin/vale

# Install OpenCode
RUN curl -fsSL https://opencode.ai/install | bash

# ---------------------------------------------------------------------------
# Python tools (standalone scripts used by OpenCode via bash)
# ---------------------------------------------------------------------------

# Copy dependency lockfile for layer caching
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && rm /tmp/requirements.lock

# Copy project source (tools, config, prompts, templates)
COPY src/ /opt/autopoc/src/
COPY data/ /opt/autopoc/data/

# Copy OpenCode skills and configuration
COPY .opencode/ /opt/autopoc/.opencode/
COPY opencode.json /opt/autopoc/opencode.json
COPY AGENTS.md /opt/autopoc/AGENTS.md

# ---------------------------------------------------------------------------
# Workspace and permissions
# ---------------------------------------------------------------------------

# Create workspace directory writable by default user
RUN mkdir -p /workspace && chown 1001:0 /workspace && chmod 775 /workspace

# Vale prose linting config and styles
COPY .vale.ini /opt/autopoc/.vale.ini
COPY .vale/styles/ /opt/autopoc/.vale/styles/

# Ensure project files are accessible
RUN chgrp -R 0 /opt/autopoc && chmod -R g=u /opt/autopoc

# Switch to non-root user
USER 1001

# Set git identity for artifact commits inside the container
RUN git config --global user.email "autopoc@autopoc.local" && \
    git config --global user.name "AutoPoC Agent"

WORKDIR /opt/autopoc

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

ENV PYTHONPATH=/opt/autopoc/src
ENV AUTOPOC_DATA_DIR=/opt/autopoc/data
ENV AUTOPOC_WORK_DIR=/workspace

# OpenCode runs in non-interactive mode with all permissions auto-approved
ENTRYPOINT ["opencode"]
CMD ["run", "--dangerously-skip-permissions", "Show available skills and current status"]
