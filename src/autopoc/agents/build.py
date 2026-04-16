"""Build agent — builds and pushes container images.

This agent shells out to podman to build the Dockerfile.ubi files generated
by the containerize agent. If a build fails, it uses an LLM to generate a
brief diagnosis to aid the retry loop.
"""

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from autopoc.config import AutoPoCConfig
from autopoc.llm import create_llm
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.podman_tools import kind_load_image, podman_build, podman_login, podman_push
from autopoc.tools.quay_tools import QuayClient

logger = logging.getLogger(__name__)

# Track which registries we've logged into during this session
_logged_in_registries: set[str] = set()


def _is_permanent_failure(error_msg: str) -> bool:
    """Detect if a build/push error is permanent (won't be fixed by Dockerfile changes).

    Permanent failures include:
    - Authentication/authorization errors
    - Network/registry unreachable
    - Missing podman binary
    - Disk full
    - Invalid registry URL

    Returns:
        True if the error is permanent and retrying won't help
    """
    error_lower = error_msg.lower()

    # Authentication/authorization failures
    if any(
        phrase in error_lower
        for phrase in [
            "unauthorized",
            "authentication required",
            "authentication failed",
            "login required",
            "access denied",
            "forbidden",
            "credentials",
            "401 unauthorized",
            "403 forbidden",
        ]
    ):
        return True

    # Network/connectivity issues
    if any(
        phrase in error_lower
        for phrase in [
            "connection refused",
            "network unreachable",
            "no route to host",
            "could not resolve host",
            "dial tcp",
            "i/o timeout",
        ]
    ):
        return True

    # Missing host tools or system errors
    # NOTE: "command not found" inside a Dockerfile RUN step (e.g., "sh: vitepress:
    # command not found") is a Dockerfile bug, NOT a permanent host failure.
    # Only treat it as permanent if it's about podman itself being missing.
    if any(
        phrase in error_lower
        for phrase in [
            "no such file or directory: 'podman'",
            "disk quota exceeded",
            "no space left on device",
        ]
    ):
        return True

    # "command not found" is permanent only if it's about the build tool itself,
    # not about a command inside a Dockerfile RUN step.
    # A Dockerfile "command not found" will appear inside "while running runtime"
    # or "building at STEP" context — that's a retryable Dockerfile issue.
    if "command not found" in error_lower:
        # If the error mentions a Dockerfile STEP, it's a build issue (retryable)
        if "step " in error_lower or "while running runtime" in error_lower:
            return False
        # Otherwise it's likely a missing host tool (permanent)
        return True

    return False


async def build_agent(
    state: PoCState,
    *,
    app_config: AutoPoCConfig | None = None,
    quay_client: QuayClient | None = None,
    llm=None,
) -> dict:
    """Build and push container images for all components.

    Args:
        state: Current pipeline state.
        app_config: Optional config override.
        quay_client: Optional Quay client override.
        llm: Optional LLM override.

    Returns:
        Partial state update.
    """
    project_name = state["project_name"]
    components = state.get("components", [])

    logger.info("Starting build phase for %d component(s)", len(components))

    if app_config is None:
        from autopoc.config import load_config

        app_config = load_config()

    owns_client = quay_client is None
    if quay_client is None:
        quay_client = QuayClient(app_config)

    clone_path = state.get("local_clone_path")
    if not clone_path:
        raise ValueError("Cannot build: local_clone_path is missing from state")

    repo_dir = Path(clone_path)
    built_images = list(state.get("built_images", []))
    retries = state.get("build_retries", 0)

    # Ensure we're logged in to the registry
    # Extract registry host from URL
    registry_url = app_config.quay_registry
    if "://" in registry_url:
        registry_host = registry_url.split("://", 1)[1]
    else:
        registry_host = registry_url

    # Check if we need to login (only once per session)
    global _logged_in_registries
    if registry_host not in _logged_in_registries:
        try:
            logger.info("Logging in to registry: %s", registry_host)
            tls_verify = not registry_url.startswith("http://")

            # Login to the registry using the Quay token
            # Quay OAuth tokens use '$oauthtoken' as username and the token as password
            podman_login(
                registry=registry_host,
                username="$oauthtoken",
                password=app_config.quay_token,
                tls_verify=tls_verify,
            )
            _logged_in_registries.add(registry_host)
        except Exception as e:
            error_msg = str(e)
            logger.error("Failed to login to registry: %s", error_msg)
            return {
                "current_phase": PoCPhase.BUILD,
                "error": f"Registry authentication failed: {error_msg}\n\n"
                "This is a permanent failure. Please check your QUAY_TOKEN in .env",
                "build_retries": retries,  # Don't increment - this isn't worth retrying
                "components": components,
                "built_images": built_images,
            }

    # Check if any component actually has a Dockerfile to build.
    # If containerize failed (e.g. poc_plan_error), no component will have a
    # dockerfile_ubi_path.  Propagate the upstream error instead of silently
    # declaring success.
    incoming_error = state.get("error")
    has_any_dockerfile = any(c.get("dockerfile_ubi_path") for c in components)
    if not has_any_dockerfile:
        msg = (
            incoming_error
            or "No Dockerfile.ubi files were generated — nothing to build. "
            "This usually means the containerize phase failed."
        )
        logger.error("Build skipped: %s", msg[:200])
        return {
            "current_phase": PoCPhase.BUILD,
            "error": msg,
            "build_retries": retries,
            "components": components,
            "built_images": built_images,
        }

    try:
        for comp in components:
            comp_name = comp["name"]

            # Skip if we already built this image in a previous attempt
            # or if the component lacks a dockerfile.
            dockerfile = comp.get("dockerfile_ubi_path")
            if not dockerfile:
                logger.info("Skipping build for %s: no dockerfile_ubi_path", comp_name)
                continue

            repo_name = f"{project_name}-{comp_name}"
            # Ensure Quay repo exists
            image_ref = quay_client.ensure_repo(app_config.quay_org, repo_name)
            full_tag = f"{image_ref}:latest"

            if full_tag in built_images:
                logger.info("Skipping build for %s: already built", comp_name)
                continue

            logger.info("Building image for %s: %s", comp_name, full_tag)

            try:
                # If the registry is HTTP (like local E2E), disable TLS verify for podman
                tls_verify = not app_config.quay_registry.startswith("http://")

                # Build the image
                podman_build.invoke(
                    {
                        "context_path": str(repo_dir),
                        "dockerfile": str(repo_dir / dockerfile),
                        "tag": full_tag,
                        "tls_verify": tls_verify,
                    }
                )
                logger.info("Build successful for %s", comp_name)

                # Push the image
                logger.info("Pushing image %s", full_tag)
                podman_push.invoke({"image": full_tag, "tls_verify": tls_verify})

                # Load image into kind cluster for local E2E testing
                # This makes the image available in kind's cache so it doesn't need to pull
                # from the registry (which may be localhost and unreachable from inside kind)
                try:
                    import shutil

                    if shutil.which("kind"):
                        logger.info("Loading image into kind cluster for local E2E testing")
                        kind_load_image(full_tag, cluster_name="autopoc-e2e")
                        logger.info("Image loaded into kind cluster")
                except Exception as kind_err:
                    # Don't fail the build if kind loading fails
                    # This is optional and only for local E2E testing
                    logger.warning(
                        "Failed to load image into kind cluster (non-fatal): %s", kind_err
                    )

                built_images.append(full_tag)
                comp["image_name"] = full_tag

            except Exception as e:
                error_log = str(e)
                logger.error(
                    "Build failed for %s: %s", comp_name, error_log[:500]
                )  # Log first 500 chars

                # Check if this is a permanent failure
                if _is_permanent_failure(error_log):
                    logger.error("Detected permanent failure - will not retry")
                    return {
                        "current_phase": PoCPhase.BUILD,
                        "error": f"Build failed for component '{comp_name}' with a permanent error.\n"
                        f"This error cannot be fixed by retrying or modifying the Dockerfile.\n\n"
                        f"Error:\n{error_log}\n\n"
                        f"Common causes:\n"
                        f"- Registry authentication failure (check QUAY_TOKEN)\n"
                        f"- Network connectivity issues\n"
                        f"- Registry not reachable\n"
                        f"- Missing system tools",
                        "build_retries": retries,  # Don't increment for permanent failures
                        "components": components,
                        "built_images": built_images,
                    }

                # Diagnose with LLM for fixable errors
                # IMPORTANT: Always create a fresh LLM instance for diagnosis to avoid
                # context overflow. The passed-in llm may have accumulated 200k+ tokens
                # from previous agents (intake, containerize, etc.)
                diagnosis_llm = create_llm()

                # Truncate error log to avoid context overflow
                # Large repos can generate massive build logs (100k+ tokens)
                # Keep last 10k chars which usually has the most relevant error
                max_error_length = 10000
                truncated_error = error_log
                if len(error_log) > max_error_length:
                    truncated_error = (
                        f"[Error log truncated - showing last {max_error_length} characters]\n\n"
                        f"...{error_log[-max_error_length:]}"
                    )
                    logger.info(
                        "Truncated error log from %d to %d characters for LLM diagnosis",
                        len(error_log),
                        len(truncated_error),
                    )

                sys_msg = SystemMessage(
                    content="You are an expert container build debugger. "
                    "Analyze the following podman build error and provide a concise, "
                    "1-2 sentence diagnosis of what went wrong and how to fix the Dockerfile."
                )
                user_msg = HumanMessage(
                    content=f"Build failed for {dockerfile}:\n\n{truncated_error}"
                )

                diagnosis_result = await diagnosis_llm.ainvoke([sys_msg, user_msg])
                diagnosis = diagnosis_result.content

                # Truncate error for state storage (containerize agent will see this)
                # Keep it concise so it doesn't bloat the state
                error_for_state = error_log
                if len(error_log) > 2000:
                    error_for_state = f"...{error_log[-2000:]}"

                error_state = (
                    f"Build failed for component '{comp_name}' using Dockerfile '{dockerfile}'.\n"
                    f"Diagnosis:\n{diagnosis}\n\n"
                    f"Raw Error:\n{error_for_state}"
                )

                return {
                    "current_phase": PoCPhase.BUILD,
                    "error": error_state,
                    "build_retries": retries + 1,
                    "components": components,  # To persist any image_name updates from successful builds
                    "built_images": built_images,
                }

        logger.info("All builds completed successfully")
        return {
            "current_phase": PoCPhase.BUILD,
            "error": None,
            "components": components,
            "built_images": built_images,
        }

    finally:
        if owns_client:
            quay_client.close()
