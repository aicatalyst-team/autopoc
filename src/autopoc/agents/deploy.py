"""Deploy agent — generates K8s manifests for each component.

This agent creates Kubernetes manifests (Deployment, Service, Namespace, etc.)
based on the built images and PoC plan. It writes the manifests to the
`kubernetes/` directory, commits them, and pushes to GitLab.

It does NOT apply manifests to a cluster — that's the apply agent's job.
This mirrors the containerize/build split: containerize generates Dockerfiles,
build runs podman; deploy generates manifests, apply runs kubectl.
"""

import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from autopoc.config import AutoPoCConfig, load_config
from autopoc.context import make_context_trimmer
from autopoc.llm import create_llm
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.file_tools import list_files, read_file, search_files, write_file
from autopoc.tools.git_tools import git_commit, git_push
from autopoc.tools.template_tools import render_template

logger = logging.getLogger(__name__)

DEPLOY_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "deploy.md"

# Tools for manifest generation — file operations + templates + git only.
# No kubectl tools — that's the apply agent's responsibility.
DEPLOY_TOOLS = [
    read_file,
    write_file,
    list_files,
    search_files,
    render_template,
    git_commit,
    git_push,
]


async def deploy_agent(
    state: PoCState,
    app_config: AutoPoCConfig | None = None,
    llm: BaseChatModel | None = None,
) -> PoCState:
    """Generate Kubernetes manifests for all components.

    Args:
        state: Current pipeline state with built_images populated
        app_config: Configuration (optional, loads from env if not provided)
        llm: Language model (optional, creates default if not provided)

    Returns:
        Updated state with manifests written to kubernetes/ and committed
    """
    logger.info("=== Deploy Phase (manifest generation) ===")

    if not app_config:
        app_config = load_config()

    if not llm:
        llm = create_llm()

    system_prompt = DEPLOY_PROMPT_PATH.read_text()

    # Check prerequisites
    components = state.get("components", [])
    built_images = state.get("built_images", [])
    project_name = state.get("project_name", "unknown")
    local_clone_path = state.get("local_clone_path", "")

    if not components and not built_images:
        logger.error("No components or built images to deploy — cannot generate manifests")
        return {
            "current_phase": PoCPhase.DEPLOY,
            "error": (
                "No components or built images to deploy. "
                "Check earlier pipeline stages (intake, containerize, build)."
            ),
        }
    previous_error = state.get("error")
    deploy_retries = state.get("deploy_retries", 0)

    user_message = f"""Generate Kubernetes manifests for the following components:

Project: {project_name}
Namespace: {project_name}
Repository path: {local_clone_path}
Write manifests to: {local_clone_path}/kubernetes/

Components and their built images:
"""

    for component in components:
        comp_name = component.get("name", "unknown")
        matching_image = next((img for img in built_images if comp_name in img), None)
        user_message += f"\n- {comp_name}:"
        user_message += f"\n  Language: {component.get('language', 'unknown')}"
        user_message += f"\n  Port: {component.get('port', 'none')}"
        user_message += f"\n  Image: {matching_image or 'NOT FOUND'}"
        user_message += f"\n  ML workload: {component.get('is_ml_workload', False)}"

    user_message += (
        "\n\nGenerate and write all Kubernetes manifests to the kubernetes/ directory."
        "\nCommit the manifests and push to GitLab."
        "\nDo NOT apply manifests to a cluster — that is handled by the apply agent."
    )

    # Include PoC infrastructure requirements if available
    poc_infrastructure = state.get("poc_infrastructure")
    poc_type = state.get("poc_type")
    poc_scenarios = state.get("poc_scenarios", [])

    if poc_type:
        user_message += f"\n\n## PoC Context"
        user_message += f"\n**Project type:** {poc_type}"

    if poc_infrastructure:
        user_message += "\n\n## PoC Infrastructure Requirements"

        if poc_infrastructure.get("sidecar_containers"):
            user_message += "\n\n**Sidecar containers to deploy alongside main application:**"
            for sidecar in poc_infrastructure.get("sidecar_containers", []):
                name = sidecar.get("name", "unknown")
                image = sidecar.get("image", "unknown")
                port = sidecar.get("port", "")
                user_message += f"\n- {name}: image={image}"
                if port:
                    user_message += f", port={port}"

        if poc_infrastructure.get("needs_vector_db"):
            db_type = poc_infrastructure.get("vector_db_type", "in-memory")
            if db_type != "in-memory":
                user_message += (
                    f"\n\n**Vector database needed:** Include {db_type} manifests "
                    f"as a separate Deployment+Service in the same namespace."
                )

        if poc_infrastructure.get("needs_pvc"):
            pvc_size = poc_infrastructure.get("pvc_size", "10Gi")
            user_message += (
                f"\n\n**Persistent storage needed:** Create a PVC manifest with size {pvc_size}."
            )

        if poc_infrastructure.get("needs_gpu"):
            user_message += (
                "\n\n**GPU resources needed:** Add GPU resource requests "
                "(nvidia.com/gpu: 1) to the deployment manifest."
            )

        resource_profile = poc_infrastructure.get("resource_profile", "small")
        user_message += f"\n\n**Resource profile:** {resource_profile}"

        extra_env = poc_infrastructure.get("extra_env_vars", {})
        if extra_env:
            user_message += "\n\n**Extra environment variables for deployment:**"
            for key, value in extra_env.items():
                user_message += f"\n- {key}={value}"

        odh_components = poc_infrastructure.get("odh_components", [])
        if odh_components:
            user_message += f"\n\n**Relevant ODH components:** {', '.join(odh_components)}"
            user_message += (
                "\n(Deploy as standard K8s resources. Note ODH relevance for the report.)"
            )

        # Deployment model
        deployment_model = poc_infrastructure.get("deployment_model", "deployment")
        listens_on_port = poc_infrastructure.get("listens_on_port", True)
        long_running = poc_infrastructure.get("long_running", True)
        test_strategy = poc_infrastructure.get("test_strategy", "http")
        user_message += f"\n\n**Deployment model:** {deployment_model}"
        user_message += f"\n**Listens on port:** {listens_on_port}"
        user_message += f"\n**Long-running process:** {long_running}"
        user_message += f"\n**Test strategy:** {test_strategy}"

        if deployment_model == "cli-only":
            user_message += (
                "\n\n**CRITICAL:** This is a CLI tool. Do NOT create Deployment or Service manifests. "
                "Create only namespace.yaml and any required PVC/RBAC manifests."
            )
        elif deployment_model == "job":
            user_message += (
                "\n\n**CRITICAL:** Create a Job manifest instead of a Deployment. "
                "Do NOT create a Service manifest."
            )
        elif not listens_on_port:
            user_message += (
                "\n\n**NOTE:** This component does not listen on a port. "
                "Create a Deployment manifest but do NOT create a Service manifest. "
                "Use exec-based probes instead of HTTP probes."
            )

    # Include full PoC plan for context
    poc_plan_text = state.get("poc_plan", "")
    if poc_plan_text:
        user_message += "\n\n## Full PoC Plan\n" + poc_plan_text

    if poc_scenarios:
        user_message += "\n\n## PoC Test Scenarios (deployment must support these)"
        for scenario in poc_scenarios:
            user_message += (
                f"\n- **{scenario.get('name', '?')}:** {scenario.get('description', '')}"
            )
            endpoint = scenario.get("endpoint")
            if endpoint:
                user_message += f" (endpoint: {endpoint})"

    # If this is a retry after apply failure, include the error
    if previous_error and deploy_retries > 0:
        user_message += (
            f"\n\n**PREVIOUS APPLY ATTEMPT FAILED (retry {deploy_retries}):**\n"
            f"{previous_error}\n\n"
            "Please fix the manifests based on this error and re-commit."
        )

    # Create agent with manifest generation tools only
    agent = create_react_agent(
        model=llm,
        tools=DEPLOY_TOOLS,
        pre_model_hook=make_context_trimmer(),
    )

    logger.info("Invoking deploy agent for %d components", len(components))

    try:
        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ]
            },
            config={"recursion_limit": 60},
        )

        logger.info("Deploy (manifest generation) complete")

        return {
            "current_phase": PoCPhase.DEPLOY,
            "error": None,
        }

    except Exception as e:
        logger.error("Deploy (manifest generation) failed: %s", e, exc_info=True)

        return {
            "current_phase": PoCPhase.DEPLOY,
            "error": f"Manifest generation failed: {e}",
        }
