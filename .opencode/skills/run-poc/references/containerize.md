# Containerize Phase Instructions

Create `Dockerfile.ubi` files using Red Hat UBI base images, compatible with OpenShift.

## Full rules in `ubi-dockerfile-rules.md`

Read `references/ubi-dockerfile-rules.md` for the complete UBI base image mapping, package manager rules, OpenShift compatibility requirements, and ML package variants.

## Process for Each Component

1. **Read existing Dockerfile** (if any) for reference
2. **Read dependency files** (requirements.txt, package.json, etc.)
3. **Determine base image** from UBI mapping table
4. **Determine single-stage vs multi-stage** (interpreted = single, compiled = multi)
5. **Write Dockerfile.ubi** applying all UBI/OpenShift rules
6. **Create .dockerignore** if missing

## Dockerfile Structure (Single-Stage, Python Example)

```dockerfile
FROM registry.access.redhat.com/ubi9/python-312

WORKDIR /opt/app-root/src

# Copy dependency file first (for layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# OpenShift compatibility
RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root

EXPOSE 8080

USER 1001

CMD ["python", "app.py"]
```

## Dockerfile Structure (Multi-Stage, Go Example)

```dockerfile
# Builder stage
FROM registry.access.redhat.com/ubi9/go-toolset AS builder

WORKDIR /opt/app-root/src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /opt/app-root/myapp .

# Runtime stage
FROM registry.access.redhat.com/ubi9/ubi-minimal

COPY --from=builder /opt/app-root/myapp /usr/local/bin/myapp

RUN chgrp -R 0 /usr/local/bin/myapp && chmod -R g=u /usr/local/bin/myapp

USER 1001

ENTRYPOINT ["myapp"]
```

## Node.js Example

```dockerfile
FROM registry.access.redhat.com/ubi9/nodejs-22

WORKDIR /opt/app-root/src

COPY package*.json ./
RUN npm ci --production

COPY . .

# node_modules needs group 0 permissions
RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root

EXPOSE 3000

USER 1001

CMD ["node", "server.js"]
```

## CLI Tool / Job Example

```dockerfile
FROM registry.access.redhat.com/ubi9/python-312

WORKDIR /opt/app-root/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chgrp -R 0 /opt/app-root && chmod -R g=u /opt/app-root

# No EXPOSE - CLI tools don't listen on ports

USER 1001

ENTRYPOINT ["python", "-m", "mytool"]
CMD ["--help"]
```

## Handling Build Error Retries

When re-entering this phase after a build failure (check `errors` in state):
- Read the error message
- Fix the specific issue (missing package, wrong path, permission error)
- Regenerate only the failed component's Dockerfile

## Handling Container Fix (from Apply/Test)

When re-entering this phase from Phase 8 or 9 (check `errors` in state for `fix-dockerfile` action):
- Read the runtime error (pod logs, test output)
- Fix the root cause (missing module, wrong entrypoint, missing binary)
- If action is "experiment": note that build will use `:experiment-N` tag
