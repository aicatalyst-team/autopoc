# 3. UBI Base Images for All Containers

Date: 2025-04

## Status

Accepted

## Context

Generated containers must run on OpenShift, which enforces:
- Arbitrary UID execution (containers run as random non-root UIDs)
- Security Context Constraints (SCCs)
- No privilege escalation

Standard Docker Hub images (python:3.x, node:20, alpine) don't meet these requirements without modification.

## Decision

All generated Dockerfiles use Red Hat Universal Base Images (UBI):
- Python: `registry.access.redhat.com/ubi9/python-312`
- Node: `registry.access.redhat.com/ubi9/nodejs-22`
- Go: `registry.access.redhat.com/ubi9/go-toolset`
- Java: `registry.access.redhat.com/ubi9/openjdk-21`

Deterministic fixups in `containerize_fixups.py` automatically replace non-UBI base images found in existing Dockerfiles.

## Alternatives Considered

- **Standard Docker Hub images**: Would require manual OpenShift-specific modifications for each project.
- **Adapting existing Dockerfiles as-is**: Fails on OpenShift due to root user assumptions, wrong package managers (apt-get), and privilege requirements.

## Consequences

- (+) OpenShift compatible out of the box (non-root USER 1001, group 0 permissions)
- (+) Consistent with RHOAI target platform
- (+) Deterministic fixup pipeline handles base image, package manager (apt-get -> microdnf), and permissions automatically
- (-) Larger images than alpine
- (-) Some niche OS packages unavailable in UBI repos
- (-) Port remapping needed (80 -> 8080 for non-root)
