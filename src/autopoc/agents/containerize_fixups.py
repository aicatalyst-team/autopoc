"""Deterministic Dockerfile fixups for UBI compatibility and OpenShift."""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _uses_minimal_base(content: str) -> bool:
    """Check if a Dockerfile uses a UBI minimal base image.

    UBI minimal images (ubi9-minimal, ubi9/minimal) ship microdnf
    instead of dnf. All other UBI images use dnf.
    """
    for line in content.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("FROM "):
            from_image = line.strip()[5:].split()[0].lower()
            if "minimal" in from_image:
                return True
    return False


# Non-UBI base image → UBI equivalent mapping.
# Used by _fixup_dockerfile to enforce UBI base images.
_UBI_IMAGE_MAP: list[tuple[re.Pattern, str]] = [
    # Python
    (re.compile(r"python:\d[\w.-]*", re.IGNORECASE), "registry.access.redhat.com/ubi9/python-312"),
    # Node.js
    (re.compile(r"node:\d[\w.-]*", re.IGNORECASE), "registry.access.redhat.com/ubi9/nodejs-22"),
    # Go
    (re.compile(r"golang:\d[\w.-]*", re.IGNORECASE), "registry.access.redhat.com/ubi9/go-toolset"),
    # Java
    (
        re.compile(r"(?:eclipse-temurin|openjdk|amazoncorretto)[\w.:-]*", re.IGNORECASE),
        "registry.access.redhat.com/ubi9/openjdk-21",
    ),
    # Nginx
    (re.compile(r"nginx[\w.:-]*", re.IGNORECASE), "registry.access.redhat.com/ubi9/nginx-124"),
    # Generic distros
    (
        re.compile(r"(?:alpine|ubuntu|debian|centos)[\w.:-]*", re.IGNORECASE),
        "registry.access.redhat.com/ubi9/ubi-minimal",
    ),
]


def _fixup_base_image(content: str, filename: str) -> str:
    """Replace non-UBI base images with UBI equivalents.

    The containerize prompt tells the LLM to use UBI images, but
    weaker models sometimes ignore this. Enforce it deterministically.
    """
    lines = content.split("\n")
    fixed_lines = []
    applied = False

    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            image = parts[1] if len(parts) > 1 else ""

            # Skip if already a UBI or Red Hat image
            if "redhat.com" in image or "ubi" in image.lower():
                fixed_lines.append(line)
                continue

            # Skip NVIDIA CUDA images (legitimate non-UBI for GPU)
            if "nvcr.io" in image or "nvidia" in image.lower():
                fixed_lines.append(line)
                continue

            # Try to match against known non-UBI images
            for pattern, ubi_image in _UBI_IMAGE_MAP:
                if pattern.fullmatch(image) or pattern.fullmatch(image.split("/")[-1]):
                    # Preserve any AS alias
                    rest = " ".join(parts[2:]) if len(parts) > 2 else ""
                    new_from = f"FROM {ubi_image}"
                    if rest:
                        new_from += f" {rest}"
                    fixed_lines.append(new_from)
                    logger.info(
                        "Dockerfile fixup: replaced non-UBI base '%s' with '%s' in %s",
                        image,
                        ubi_image,
                        filename,
                    )
                    applied = True
                    break
            else:
                # No match — leave as-is but warn
                if "." not in image and ":" in image:
                    # Looks like a Docker Hub short name (e.g. "ruby:3.2")
                    logger.warning(
                        "Dockerfile has non-UBI base image '%s' with no known mapping in %s",
                        image,
                        filename,
                    )
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)

    return "\n".join(fixed_lines) if applied else content


def _fixup_dockerfile(dockerfile_path: Path) -> None:
    """Apply deterministic fixes to a generated Dockerfile.

    LLMs (especially non-Claude models) frequently generate Dockerfiles
    with known errors. Rather than relying on the LLM to get these right,
    we fix them post-hoc:

    - Non-UBI base images: Replace with UBI equivalents.
    - Package manager mismatch: UBI9 full images use dnf, UBI9 minimal
      images use microdnf. LLMs often confuse the two.
    - Permission errors: commands like chgrp/chmod or npm run build need
      correct USER context. Ensure operations that require root run as
      USER 0, and fix ownership before switching to non-root.
    """
    content = dockerfile_path.read_text(encoding="utf-8")
    original = content

    # Replace non-UBI base images first (affects subsequent fixups)
    content = _fixup_base_image(content, dockerfile_path.name)

    # Fix package manager per stage (multi-stage aware)
    content = _fixup_package_manager(content, dockerfile_path.name)

    # Fix permission issues: ensure chgrp/chmod runs as root
    content = _fixup_permissions(content, dockerfile_path.name)

    if content != original:
        dockerfile_path.write_text(content, encoding="utf-8")


def _fixup_package_manager(content: str, filename: str) -> str:
    """Fix package manager commands per build stage in multi-stage Dockerfiles.

    In multi-stage Dockerfiles, each FROM starts a new stage with a
    different base image. Full UBI images use dnf, minimal images use
    microdnf. The fixup must track which stage each RUN line belongs to.
    """
    lines = content.split("\n")
    fixed_lines = []
    current_base_is_minimal = False
    applied = False

    for line in lines:
        stripped = line.strip().upper()

        # Track FROM directives to know which base image we're in
        if stripped.startswith("FROM "):
            image = line.strip()[5:].split()[0].lower()
            current_base_is_minimal = "minimal" in image
            fixed_lines.append(line)
            continue

        # Fix package manager in RUN lines based on current stage
        if stripped.startswith("RUN "):
            if current_base_is_minimal and "dnf " in line and "microdnf" not in line:
                # Minimal stage but using dnf → replace with microdnf
                fixed_line = re.sub(r"\bdnf\b", "microdnf", line)
                if fixed_line != line:
                    logger.info(
                        "Dockerfile fixup: replaced dnf with microdnf (minimal stage) in %s",
                        filename,
                    )
                    applied = True
                    fixed_lines.append(fixed_line)
                    continue
            elif not current_base_is_minimal and "microdnf" in line:
                # Full stage but using microdnf → replace with dnf
                fixed_line = line.replace("microdnf", "dnf")
                if fixed_line != line:
                    logger.info(
                        "Dockerfile fixup: replaced microdnf with dnf (full stage) in %s",
                        filename,
                    )
                    applied = True
                    fixed_lines.append(fixed_line)
                    continue

        fixed_lines.append(line)

    return "\n".join(fixed_lines) if applied else content


def _fixup_permissions(content: str, filename: str) -> str:
    """Fix permission-related issues in Dockerfiles for OpenShift.

    OpenShift runs containers with an arbitrary UID (e.g. 1000620000) but
    always in GID 0. The correct pattern for file permissions is:
        chgrp -R 0 <path> && chmod -R g=u <path>
    This must run as USER 0 (root).

    UBI images default to non-root (UID 1001). Commands that require root:
    - dnf/microdnf install (package installation)
    - chgrp/chmod (permission changes)

    Handles three common LLM mistakes:
    1. dnf/microdnf install without USER 0: wrap with USER 0 before, restore after.
    2. chgrp/chmod without USER 0: wrap with USER 0 before, restore after.
    3. npm/bun install as root creates node_modules owned by root, then
       USER switch to non-root breaks npm run build. Fix by adding
       chgrp/chmod g=u for node_modules before the USER switch (still as root).
    """
    lines = content.split("\n")
    fixed_lines = []
    current_user = None  # Track the current USER directive
    npm_installed_as_root = False
    applied_fix = False
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip().upper()

        # Track USER directives
        if stripped.startswith("USER "):
            user_val = line.strip()[5:].strip()
            # Detect USER switch from root to non-root
            if (
                current_user in ("0", "root")
                and user_val not in ("0", "root")
                and npm_installed_as_root
            ):
                # Fix node_modules permissions using OpenShift-safe pattern:
                # chgrp to GID 0 + chmod g=u, so any arbitrary UID in GID 0 can write.
                # This runs before the USER switch, so we're still root.
                fixed_lines.append(
                    "RUN chgrp -R 0 /opt/app-root/src/node_modules && "
                    "chmod -R g=u /opt/app-root/src/node_modules || true"
                )
                logger.info(
                    "Dockerfile fixup: added chgrp/chmod g=u for node_modules before USER %s in %s",
                    user_val,
                    filename,
                )
                applied_fix = True
                npm_installed_as_root = False
            current_user = user_val

        # Detect npm install/ci running as root
        if stripped.startswith("RUN ") and current_user in ("0", "root"):
            if any(cmd in stripped for cmd in ("NPM INSTALL", "NPM CI", "BUN INSTALL")):
                npm_installed_as_root = True

        # Detect commands that require root but are running as non-root.
        # None means no USER directive seen yet — UBI images default to
        # non-root (UID 1001), so treat None as non-root.
        if stripped.startswith("RUN ") and current_user not in ("0", "root"):
            needs_root = (
                "CHGRP " in stripped
                or "CHMOD " in stripped
                or "DNF " in stripped
                or "MICRODNF " in stripped
                or "YUM " in stripped
            )
            if needs_root:
                # Insert USER 0 before the RUN command.
                # For multi-line RUN commands (with \ continuations), collect
                # all continuation lines before inserting USER after.
                fixed_lines.append("USER 0")
                fixed_lines.append(line)
                while line.rstrip().endswith("\\") and i + 1 < len(lines):
                    i += 1
                    line = lines[i]
                    fixed_lines.append(line)
                fixed_lines.append("USER %s" % (current_user or "1001"))
                logger.info(
                    "Dockerfile fixup: wrapped root-required command with USER 0 in %s",
                    filename,
                )
                applied_fix = True
                i += 1
                continue

        fixed_lines.append(line)
        i += 1

    if applied_fix:
        return "\n".join(fixed_lines)
    return content
