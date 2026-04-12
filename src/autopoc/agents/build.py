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
from autopoc.tools.podman_tools import podman_build, podman_push
from autopoc.tools.quay_tools import QuayClient

logger = logging.getLogger(__name__)


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

                built_images.append(full_tag)
                comp["image_name"] = full_tag

            except Exception as e:
                error_log = str(e)
                logger.error("Build failed for %s", comp_name)

                # Diagnose with LLM
                if llm is None:
                    llm = create_llm()

                sys_msg = SystemMessage(
                    content="You are an expert container build debugger. "
                    "Analyze the following podman build error and provide a concise, "
                    "1-2 sentence diagnosis of what went wrong and how to fix the Dockerfile."
                )
                user_msg = HumanMessage(content=f"Build failed for {dockerfile}:\n\n{error_log}")

                diagnosis_result = await llm.ainvoke([sys_msg, user_msg])
                diagnosis = diagnosis_result.content

                error_state = (
                    f"Build failed for component '{comp_name}' using Dockerfile '{dockerfile}'.\n"
                    f"Diagnosis:\n{diagnosis}\n\n"
                    f"Raw Error:\n{error_log}"
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
