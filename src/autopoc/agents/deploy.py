"""Deploy agent — generates K8s manifests and deploys to cluster.

This agent analyzes the built images and creates appropriate Kubernetes
resources (Deployment, Service) for each component, then applies them
to the target cluster.
"""

import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from autopoc.config import AutoPoCConfig, load_config
from autopoc.llm import create_llm
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.file_tools import read_file, write_file
from autopoc.tools.git_tools import git_commit, git_push
from autopoc.tools.k8s_tools import (
    kubectl_apply,
    kubectl_apply_from_string,
    kubectl_create_namespace,
    kubectl_get,
    kubectl_get_service_url,
    kubectl_logs,
    kubectl_wait_for_rollout,
)
from autopoc.tools.template_tools import render_template

logger = logging.getLogger(__name__)

DEPLOY_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "deploy.md"


async def deploy_agent(
    state: PoCState,
    app_config: AutoPoCConfig | None = None,
    llm: BaseChatModel | None = None,
) -> PoCState:
    """Deploy built images to Kubernetes cluster.

    Args:
        state: Current pipeline state with built_images populated
        app_config: Configuration (optional, loads from env if not provided)
        llm: Language model (optional, creates default if not provided)

    Returns:
        Updated state with deployed_resources and routes populated
    """
    logger.info("=== Deploy Phase ===")

    if not app_config:
        app_config = load_config()

    # NOTE: Create a fresh LLM instance to avoid context overflow.
    # Each agent starts with a clean message history.
    if not llm:
        llm = create_llm()

    # Load system prompt
    system_prompt = DEPLOY_PROMPT_PATH.read_text()

    # Build user message with context
    components = state.get("components", [])
    built_images = state.get("built_images", [])
    project_name = state["project_name"]
    local_clone_path = state.get("local_clone_path", "")
    previous_error = state.get("error")
    deploy_retries = state.get("deploy_retries", 0)

    user_message = f"""Deploy the following components to Kubernetes:

Project: {project_name}
Namespace: {project_name}
Repository path: {local_clone_path}

Components and their built images:
"""

    for component in components:
        comp_name = component.get("name", "unknown")
        # Find the matching image from built_images
        matching_image = next(
            (img for img in built_images if comp_name in img),
            None,
        )

        user_message += f"\n- {comp_name}:"
        user_message += f"\n  Language: {component.get('language', 'unknown')}"
        user_message += f"\n  Port: {component.get('port', 'none')}"
        user_message += f"\n  Image: {matching_image or 'NOT FOUND'}"
        user_message += f"\n  ML workload: {component.get('is_ml_workload', False)}"

    user_message += "\n\nGenerate and apply Kubernetes manifests for all components."
    user_message += "\nCommit the manifests to the repo and return the accessible URLs."

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
            for sidecar in poc_infrastructure["sidecar_containers"]:
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
                    f"\n\n**Vector database needed:** Deploy {db_type} as a separate "
                    f"pod/service in the same namespace."
                )

        if poc_infrastructure.get("needs_pvc"):
            pvc_size = poc_infrastructure.get("pvc_size", "10Gi")
            user_message += (
                f"\n\n**Persistent storage needed:** Create a PVC with size {pvc_size} "
                f"for model weights or data."
            )

        if poc_infrastructure.get("needs_gpu"):
            gpu_type = poc_infrastructure.get("gpu_type", "nvidia")
            user_message += (
                f"\n\n**GPU resources needed:** Add GPU resource requests "
                f"(nvidia.com/gpu: 1) to the deployment."
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
            user_message += "\n(For this PoC, deploy as standard K8s resources. Note the ODH relevance for the report.)"

        # Deployment model — CRITICAL for deciding what K8s resources to create
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
                "\n\n**CRITICAL:** This is a CLI tool. Do NOT create a Deployment or Service. "
                "The container will exit immediately and CrashLoopBackOff if deployed as a Deployment. "
                "Test the image by running commands via `kubectl run --rm`. "
                "Create only the namespace, ServiceAccount/RBAC, and any required PVCs."
            )
        elif deployment_model == "job":
            user_message += (
                "\n\n**CRITICAL:** This should be deployed as a Kubernetes Job, not a Deployment. "
                "Do NOT create a Service. Set backoffLimit and activeDeadlineSeconds appropriately."
            )
        elif not listens_on_port:
            user_message += (
                "\n\n**NOTE:** This component does not listen on a port. "
                "Create a Deployment (it runs continuously) but do NOT create a Service. "
                "Use exec-based probes instead of HTTP probes."
            )

    # Include full PoC plan for additional context
    poc_plan_text = state.get("poc_plan", "")
    if poc_plan_text:
        user_message += "\n\n## Full PoC Plan\n" + poc_plan_text

    if poc_scenarios:
        user_message += "\n\n## PoC Test Scenarios (deployment must support these)"
        for scenario in poc_scenarios:
            user_message += (
                f"\n- **{scenario.get('name', '?')}:** {scenario.get('description', '')}"
            )
            if scenario.get("endpoint"):
                user_message += f" (endpoint: {scenario['endpoint']})"

    # If this is a retry, include the previous error
    if previous_error and deploy_retries > 0:
        user_message += f"\n\n**PREVIOUS DEPLOYMENT ATTEMPT FAILED (retry {deploy_retries}):**\n{previous_error}"
        user_message += "\n\nPlease analyze the error and fix the manifests accordingly."

    # Create agent with deployment tools
    tools = [
        kubectl_create_namespace,
        kubectl_apply,
        kubectl_apply_from_string,
        kubectl_get,
        kubectl_logs,
        kubectl_wait_for_rollout,
        kubectl_get_service_url,
        read_file,
        write_file,
        render_template,
        git_commit,
        git_push,
    ]

    agent = create_react_agent(model=llm, tools=tools)

    logger.info("Invoking deploy agent for %d components", len(components))

    try:
        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ]
            },
            config={"recursion_limit": 40},
        )

        # Extract deployed resources and routes from agent's response
        # The agent should have used the tools to deploy and capture this info
        # For now, we'll extract from the final message or tool calls

        deployed_resources = []
        routes = []

        # Parse tool calls to extract deployed resources
        messages = result.get("messages", [])
        for msg in messages:
            # Check tool calls for kubectl_apply or kubectl_wait_for_rollout
            if hasattr(msg, "tool_calls"):
                for tool_call in msg.tool_calls:
                    if tool_call["name"] == "kubectl_apply":
                        # Extract resource from manifest path
                        manifest_path = tool_call["args"].get("manifest_path", "")
                        if manifest_path:
                            # Infer resource type from filename
                            if "deployment" in manifest_path:
                                resource_name = Path(manifest_path).stem.replace("-deployment", "")
                                deployed_resources.append(f"deployment/{resource_name}")
                            elif "service" in manifest_path:
                                resource_name = Path(manifest_path).stem.replace("-service", "")
                                deployed_resources.append(f"service/{resource_name}")

            # Check for kubectl_get_service_url results
            if hasattr(msg, "content") and isinstance(msg.content, str):
                if msg.content.startswith("http://") or msg.content.startswith("https://"):
                    routes.append(msg.content)

        # If we didn't extract resources from tool calls, infer from components
        if not deployed_resources:
            for component in components:
                comp_name = component.get("name", "")
                deployed_resources.extend([f"deployment/{comp_name}", f"service/{comp_name}"])

        logger.info(
            "Deployment complete: %d resources, %d routes", len(deployed_resources), len(routes)
        )

        # Clear error on success
        return {
            "current_phase": PoCPhase.DEPLOY,
            "deployed_resources": deployed_resources,
            "routes": routes,
            "error": None,
        }

    except Exception as e:
        logger.error("Deploy failed: %s", e, exc_info=True)

        # Increment retry counter
        current_retries = state.get("deploy_retries", 0)

        return {
            "current_phase": PoCPhase.DEPLOY,
            "deployed_resources": [],
            "routes": [],
            "error": f"Deployment failed: {e}",
            "deploy_retries": current_retries + 1,
        }
