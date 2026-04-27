"""Podman CLI tools for LangChain agents.

Provides build, push, inspect, and tag operations by shelling out to the podman CLI.
"""

import logging
import subprocess
from typing import Dict, Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

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
            raise RuntimeError(
                f"podman {' '.join(args)} failed with exit code {result.returncode}:\n{output}"
            )
        return output
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"podman {' '.join(args)} timed out after {timeout}s")


@tool
def podman_build(
    context_path: str,
    dockerfile: str,
    tag: str,
    build_args: Optional[Dict[str, str]] = None,
    tls_verify: bool = True,
) -> str:
    """Build a container image using podman.

    Args:
        context_path: Path to the build context directory.
        dockerfile: Path to the Dockerfile (relative to context or absolute).
        tag: Image tag (e.g. quay.io/org/repo:tag).
        build_args: Optional dictionary of build arguments.
        tls_verify: Whether to verify TLS certificates (useful for local testing).

    Returns:
        Build output.
    """
    args = ["build", "-f", dockerfile, "-t", tag]
    if not tls_verify:
        args.append("--tls-verify=false")
    if build_args:
        for k, v in build_args.items():
            args.extend(["--build-arg", f"{k}={v}"])
    args.append(context_path)

    return _run_podman(args, timeout=BUILD_TIMEOUT)


def podman_login(registry: str, username: str, password: str, tls_verify: bool = True) -> str:
    """Login to a container registry.

    Args:
        registry: Registry URL (e.g. 'quay.io' or 'localhost:8080')
        username: Registry username
        password: Registry password/token
        tls_verify: Whether to verify TLS certificates

    Returns:
        Login output
    """
    args = ["login", "--username", username, "--password-stdin"]
    if not tls_verify:
        args.append("--tls-verify=false")
    args.append(registry)

    cmd = ["podman"] + args
    try:
        result = subprocess.run(
            cmd,
            input=password,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode != 0:
            raise RuntimeError(f"podman login failed: {output}")
        logger.info("Successfully logged in to %s", registry)
        return output
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"podman login timed out after {DEFAULT_TIMEOUT}s")


@tool
def podman_push(image: str, tls_verify: bool = True) -> str:
    """Push a container image to a registry.

    Args:
        image: Image tag to push.
        tls_verify: Whether to verify TLS certificates (useful for local testing).

    Returns:
        Push output.
    """
    args = ["push"]
    if not tls_verify:
        args.append("--tls-verify=false")
    args.append(image)
    return _run_podman(args)


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


def kind_load_image(image: str, cluster_name: str = "autopoc-e2e") -> str:
    """Load a podman image into a kind cluster.

    This makes the image available in kind's local cache so it doesn't need
    to pull from an external registry.

    Args:
        image: Image tag to load (e.g., 'localhost:8080/org/repo:tag')
        cluster_name: Name of the kind cluster (default: 'autopoc-e2e')

    Returns:
        Success message
    """
    import tempfile
    from pathlib import Path

    logger.info("Loading image %s into kind cluster %s", image, cluster_name)

    # Save podman image to tar
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as f:
        tar_path = f.name

    try:
        # podman save <image> -o /tmp/image.tar
        logger.debug("Saving image to %s", tar_path)
        _run_podman(["save", image, "-o", tar_path])

        # kind load image-archive /tmp/image.tar --name <cluster>
        logger.debug("Loading tar into kind cluster")
        cmd = ["kind", "load", "image-archive", tar_path, "--name", cluster_name]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            raise RuntimeError(f"kind load failed: {result.stdout}\n{result.stderr}")

        logger.info("Successfully loaded %s into kind cluster %s", image, cluster_name)
        return f"Image {image} loaded into kind cluster {cluster_name}"

    finally:
        # Clean up tar file
        Path(tar_path).unlink(missing_ok=True)
