"""Podman CLI tools for LangChain agents.

Provides build, push, inspect, and tag operations by shelling out to the podman CLI.
"""

import subprocess
from typing import Dict, Optional

from langchain_core.tools import tool

# Timeout for podman build (10 minutes)
BUILD_TIMEOUT = 600
# Timeout for other podman operations (2 minutes)
DEFAULT_TIMEOUT = 120


def _run_podman(
    args: list[str],
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Run a podman command and return its output.

    Args:
        args: Podman command arguments (without 'podman' prefix).
        timeout: Command timeout in seconds.

    Returns:
        Combined stdout and stderr.

    Raises:
        RuntimeError: If the podman command fails or times out.
    """
    cmd = ["podman"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode != 0:
            raise RuntimeError(f"podman {' '.join(args)} failed with exit code {result.returncode}:\n{output}")
        return output
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"podman {' '.join(args)} timed out after {timeout}s")


@tool
def podman_build(
    context_path: str,
    dockerfile: str,
    tag: str,
    build_args: Optional[Dict[str, str]] = None,
) -> str:
    """Build a container image using podman.

    Args:
        context_path: Path to the build context directory.
        dockerfile: Path to the Dockerfile (relative to context or absolute).
        tag: Image tag (e.g. quay.io/org/repo:tag).
        build_args: Optional dictionary of build arguments.

    Returns:
        Build output.
    """
    args = ["build", "-f", dockerfile, "-t", tag]
    if build_args:
        for k, v in build_args.items():
            args.extend(["--build-arg", f"{k}={v}"])
    args.append(context_path)

    return _run_podman(args, timeout=BUILD_TIMEOUT)


@tool
def podman_push(image: str) -> str:
    """Push a container image to a registry.

    Args:
        image: Image tag to push.

    Returns:
        Push output.
    """
    return _run_podman(["push", image])


@tool
def podman_inspect(image: str) -> str:
    """Inspect a container image.

    Args:
        image: Image tag to inspect.

    Returns:
        Image metadata as JSON string.
    """
    return _run_podman(["inspect", image])


@tool
def podman_tag(image: str, new_tag: str) -> str:
    """Tag an existing container image.

    Args:
        image: Existing image tag.
        new_tag: New tag to apply.

    Returns:
        Tag output.
    """
    return _run_podman(["tag", image, new_tag])
