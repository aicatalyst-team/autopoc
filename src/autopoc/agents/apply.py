"""Apply agent — applies pre-generated K8s manifests to a cluster and verifies.

This agent is the operational counterpart to the deploy agent. The deploy agent
generates manifests (like containerize generates Dockerfiles), and this agent
applies them (like build runs podman build). This separation keeps each agent
focused and reduces context overflow risk.

When the apply agent detects a failure, it uses an LLM to **triage** the error
into one of three categories:

- ``fix-manifest`` — The container image is fine, the K8s manifest has a bug
  (wrong port, missing env var, wrong resource limits). The pipeline loops back
  to the deploy agent (inner loop).
- ``fix-dockerfile`` — The container image itself is broken (missing dependency,
  wrong entrypoint, crash on import). The pipeline escalates to the containerize
  agent (outer loop) and overwrites ``:latest``.
- ``experiment`` — The base image is correct but we need a variant for this
  deployment context (different CMD, extra runtime package). The pipeline
  escalates to containerize and builds with an ``:experiment-N`` tag so
  ``:latest`` stays clean.
"""

import json
import logging
import re
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.prebuilt import create_react_agent

from autopoc.config import AutoPoCConfig, load_config
from autopoc.context import make_context_trimmer
from autopoc.llm import create_llm
from autopoc.state import PoCPhase, PoCState, PoCStateUpdate
from autopoc.tools.file_tools import list_files, read_file
from autopoc.tools.k8s_tools import (
    _run_kubectl,
    kubectl_apply,
    kubectl_apply_from_string,
    kubectl_create_namespace,
    kubectl_get,
    kubectl_get_service_url,
    kubectl_logs,
    kubectl_wait_for_rollout,
)

logger = logging.getLogger(__name__)

# Valid triage actions returned by _triage_apply_error
_VALID_TRIAGE_ACTIONS = {"fix-manifest", "fix-dockerfile", "experiment"}

# Pod phases/states that indicate a container-level problem (not a manifest issue)
_UNHEALTHY_WAITING_REASONS = {
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ErrImagePull",
    "CreateContainerConfigError",
    "RunContainerError",
    "InvalidImageName",
}

APPLY_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "apply.md"

# Seconds to wait before checking pod health after apply reports success.
# Gives pods time to start and potentially crash.
_POD_HEALTH_CHECK_DELAY = 15


def _check_pod_health(namespace: str) -> str | None:
    """Check if pods in the namespace are healthy after deployment.

    Returns an error description if unhealthy pods are found, None if all OK.
    This catches CrashLoopBackOff and similar issues that ``kubectl rollout
    status`` doesn't reliably detect (it can return success if the pod starts
    briefly before crashing).
    """
    import time

    time.sleep(_POD_HEALTH_CHECK_DELAY)

    try:
        output = _run_kubectl(["get", "pods", "-n", namespace, "-o", "json"], check=False)
        if not output.strip():
            return None

        pods = json.loads(output)
        items = pods.get("items", [])
        if not items:
            return None

        unhealthy = []
        for pod in items:
            pod_name = pod.get("metadata", {}).get("name", "unknown")
            statuses = pod.get("status", {}).get("containerStatuses", [])
            for cs in statuses:
                waiting = cs.get("state", {}).get("waiting", {})
                reason = waiting.get("reason", "")
                if reason in _UNHEALTHY_WAITING_REASONS:
                    message = waiting.get("message", "")
                    unhealthy.append(f"{pod_name}: {reason} — {message}")

            # Also check init container statuses
            init_statuses = pod.get("status", {}).get("initContainerStatuses", [])
            for cs in init_statuses:
                waiting = cs.get("state", {}).get("waiting", {})
                reason = waiting.get("reason", "")
                if reason in _UNHEALTHY_WAITING_REASONS:
                    message = waiting.get("message", "")
                    unhealthy.append(f"{pod_name} (init): {reason} — {message}")

        if not unhealthy:
            return None

        # Get logs from the first unhealthy pod for diagnosis
        first_pod = unhealthy[0].split(":")[0]
        try:
            logs = _run_kubectl(["logs", first_pod, "-n", namespace, "--tail=50"], check=False)
        except Exception:
            logs = "(failed to fetch logs)"

        return (
            "Pods unhealthy after deployment:\n"
            + "\n".join(f"  - {u}" for u in unhealthy)
            + f"\n\nLogs from {first_pod}:\n{logs}"
        )

    except Exception as e:
        logger.debug("Pod health check failed: %s (continuing)", e)
        return None


# Tools for the apply agent — cluster operations + file reading (no writing)
APPLY_TOOLS = [
    kubectl_create_namespace,
    kubectl_apply,
    kubectl_apply_from_string,
    kubectl_get,
    kubectl_logs,
    kubectl_wait_for_rollout,
    kubectl_get_service_url,
    read_file,
    list_files,
]


def _extract_final_ai_content(messages: list) -> str:
    """Extract text content from the last AIMessage with non-empty content."""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, list):
            content = "".join(
                part["text"] if isinstance(part, dict) and "text" in part else str(part)
                for part in content
            )
        if isinstance(content, str) and content.strip():
            return content
    return ""


def _parse_apply_output(raw_output: str, messages: list) -> dict:
    """Parse the apply agent's output to extract resources and routes.

    Tries to find a JSON object in the output. Falls back to extracting
    from tool call results in the message history.
    """
    # Try to parse JSON from the final message
    text = raw_output.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return {
                "deployed_resources": data.get("deployed_resources", []),
                "routes": data.get("routes", []),
                "error": data.get("error"),
            }
        except json.JSONDecodeError:
            pass

    # Fallback: extract from tool calls in messages
    deployed_resources = []
    routes = []

    for msg in messages:
        if hasattr(msg, "tool_calls"):
            for tool_call in msg.tool_calls:
                if tool_call["name"] == "kubectl_apply":
                    manifest_path = tool_call["args"].get("manifest_path", "")
                    if manifest_path:
                        if "deployment" in manifest_path:
                            resource_name = Path(manifest_path).stem.replace("-deployment", "")
                            deployed_resources.append(f"deployment/{resource_name}")
                        elif "service" in manifest_path:
                            resource_name = Path(manifest_path).stem.replace("-service", "")
                            deployed_resources.append(f"service/{resource_name}")
                        elif "namespace" in manifest_path:
                            resource_name = Path(manifest_path).stem.replace("-namespace", "")
                            deployed_resources.append(f"namespace/{resource_name}")
                        elif "job" in manifest_path:
                            resource_name = Path(manifest_path).stem.replace("-job", "")
                            deployed_resources.append(f"job/{resource_name}")

        # Check for URLs in tool results
        if hasattr(msg, "content") and isinstance(msg.content, str):
            content = msg.content
            if content.startswith("http://") or content.startswith("https://"):
                routes.append(content.strip())

    return {
        "deployed_resources": deployed_resources,
        "routes": routes,
        "error": None,
    }


async def _triage_apply_error(error_text: str) -> str:
    """Classify an apply/runtime error to decide where to route the fix.

    First applies deterministic pattern matching for known error types
    (RBAC, namespace issues) that the LLM consistently misclassifies.
    Falls through to a lightweight LLM call for ambiguous errors.

    Returns one of:
    - ``fix-manifest``  — K8s manifest issue (wrong port, missing env var, RBAC)
    - ``fix-dockerfile`` — Container image is broken (missing dep, wrong entrypoint)
    - ``experiment``    — Image is fine as-is, but needs a variant for this context
    """
    # ── Deterministic pre-checks for patterns the LLM gets wrong ──
    error_lower = error_text.lower()

    # RBAC forbidden errors: "cannot <verb> resource ... is forbidden"
    if "cannot " in error_lower and "forbidden" in error_lower:
        logger.info("Triage: deterministic — RBAC forbidden → fix-manifest")
        return "fix-manifest"

    # Namespace not found
    if "namespace" in error_lower and "not found" in error_lower:
        logger.info("Triage: deterministic — namespace not found → fix-manifest")
        return "fix-manifest"

    # Container crash / image issues — always a Dockerfile problem
    if "crashloopbackoff" in error_lower:
        logger.info("Triage: deterministic — CrashLoopBackOff → fix-dockerfile")
        return "fix-dockerfile"

    if "imagepullbackoff" in error_lower or "errimagepull" in error_lower:
        logger.info("Triage: deterministic — ImagePullBackOff → fix-dockerfile")
        return "fix-dockerfile"

    if "command not found" in error_lower or "exec format error" in error_lower:
        logger.info("Triage: deterministic — command/exec error → fix-dockerfile")
        return "fix-dockerfile"

    # ── Fall through to LLM for ambiguous errors ──
    triage_llm = create_llm()

    prompt = (
        "You are a Kubernetes deployment triage specialist.\n\n"
        "A container was deployed to Kubernetes and failed. Classify the root cause "
        "into EXACTLY ONE of these categories. Respond with ONLY the category label "
        "on a single line — no explanation, no markdown, just the label.\n\n"
        "Categories:\n"
        "- **fix-manifest** — The container image itself is fine, but the Kubernetes "
        "manifest is wrong. Examples: wrong port number in Service, missing environment "
        "variable in the manifest, wrong resource limits, RBAC / ServiceAccount issue, "
        "wrong namespace reference, missing ConfigMap or Secret manifest, wrong "
        "image pull policy.\n"
        "- **fix-dockerfile** — The container image is broken and needs to be rebuilt. "
        "Examples: ImportError / ModuleNotFoundError (missing Python dependency), "
        "missing system library, wrong ENTRYPOINT or CMD, exec format error, "
        "application crashes on startup due to code/dependency issue, "
        "missing files that should have been COPY'd into the image.\n"
        "- **experiment** — The container image works as built but needs a slight "
        "variant for this deployment context. Examples: need a different CMD to run "
        "a specific subcommand, need an extra runtime package that isn't strictly "
        "required, need to bake in a config file, need a different port binding.\n\n"
        f"Error:\n{error_text[:3000]}\n\n"
        "Category:"
    )

    try:
        response = await triage_llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content
        if isinstance(raw, list):
            raw = "".join(
                part["text"] if isinstance(part, dict) and "text" in part else str(part)
                for part in raw
            )
        action = raw.strip().lower().strip("`\"' ")

        # Normalize common variations
        if "fix-dockerfile" in action or "fix_dockerfile" in action or "dockerfile" in action:
            action = "fix-dockerfile"
        elif "experiment" in action:
            action = "experiment"
        else:
            action = "fix-manifest"

        if action not in _VALID_TRIAGE_ACTIONS:
            action = "fix-manifest"

        logger.info("Triage classified error as: %s", action)
        return action

    except Exception as e:
        logger.warning("Triage LLM call failed (%s), defaulting to fix-manifest", e)
        return "fix-manifest"


async def apply_agent(
    state: PoCState,
    app_config: AutoPoCConfig | None = None,
    llm: Runnable | BaseChatModel | None = None,
) -> PoCStateUpdate:
    """Apply K8s manifests to the cluster and verify deployment.

    Args:
        state: Current pipeline state with manifests already generated by deploy agent
        app_config: Configuration (optional, loads from env if not provided)
        llm: Language model (optional, creates default if not provided)

    Returns:
        Updated state with deployed_resources and routes populated
    """
    logger.info("=== Apply Phase ===")

    if not app_config:
        app_config = load_config()

    if not llm:
        llm = create_llm()

    system_prompt = APPLY_PROMPT_PATH.read_text()

    # Check prerequisites
    project_name = state.get("project_name", "unknown")
    local_clone_path = state.get("local_clone_path") or ""
    components = state.get("components", [])
    built_images = state.get("built_images", [])
    previous_error = state.get("error")
    deploy_retries = state.get("deploy_retries", 0)
    poc_infrastructure = state.get("poc_infrastructure")

    if not components and not built_images:
        logger.error("No components or built images to apply — nothing to deploy")
        return {
            "current_phase": PoCPhase.APPLY,
            "deployed_resources": [],
            "routes": [],
            "error": (
                "No components or built images. "
                "Check earlier pipeline stages (intake, containerize, build)."
            ),
        }

    # ── Deterministic: ensure namespace exists before the LLM touches kubectl ──
    # The LLM *should* call kubectl_create_namespace first, but it often skips
    # straight to kubectl_apply, which fails with "namespaces not found".
    # Creating it here is idempotent and costs nothing.
    #
    # We use --save-config so kubectl writes the last-applied-configuration
    # annotation. Without it, a later `kubectl apply -f namespace.yaml` would
    # need to PATCH the namespace to add the annotation, requiring the patch
    # verb on namespaces (which may not be granted).
    try:
        # Check if namespace already exists
        result = _run_kubectl(["get", "namespace", project_name], check=False)
        if "NotFound" in result or "not found" in result.lower():
            _run_kubectl(["create", "namespace", project_name, "--save-config"], check=False)
            logger.info("Created namespace '%s' (with --save-config)", project_name)
        else:
            logger.info("Namespace '%s' already exists", project_name)
    except Exception as e:
        logger.debug("Namespace pre-creation returned: %s (continuing)", e)

    k8s_path = Path(local_clone_path) / "kubernetes"
    k8s_dir = str(k8s_path)

    # ── Deterministic: discover manifest files before the LLM runs ──
    # The LLM often skips list_files and guesses filenames, or uses relative
    # paths (CWD is /workspace, not the clone dir). Listing files here and
    # including absolute paths in the message eliminates both failure modes.
    manifest_files: list[str] = []
    if k8s_path.is_dir():
        manifest_files = sorted(str(f) for f in k8s_path.glob("*.yaml"))

    user_message = f"""Apply the Kubernetes manifests to the cluster.

Project: {project_name}
Namespace: {project_name}
Repository path: {local_clone_path}
Manifests directory: {k8s_dir}
"""

    if manifest_files:
        user_message += "\n**Manifest files to apply (use these EXACT absolute paths):**\n"
        for f in manifest_files:
            user_message += f"  {f}\n"
    else:
        user_message += (
            "\n**WARNING:** No manifest files found in kubernetes/ directory. "
            "Use list_files to verify the directory exists and check for manifests.\n"
        )

    user_message += "\nComponents:\n"

    for component in components:
        comp_name = component.get("name", "unknown")
        matching_image = next((img for img in built_images if comp_name in img), None)
        user_message += f"\n- {comp_name}: image={matching_image or 'NOT FOUND'}"
        port = component.get("port")
        if port:
            user_message += f", port={port}"

    # Include deployment model info
    if poc_infrastructure:
        deployment_model = poc_infrastructure.get("deployment_model", "deployment")
        listens_on_port = poc_infrastructure.get("listens_on_port", True)
        test_strategy = poc_infrastructure.get("test_strategy", "http")
        user_message += f"\n\n**Deployment model:** {deployment_model}"
        user_message += f"\n**Listens on port:** {listens_on_port}"
        user_message += f"\n**Test strategy:** {test_strategy}"

        if deployment_model in ("cli-only", "job"):
            user_message += (
                "\n\n**NOTE:** This is a Job-based workload. Apply the Job manifests, "
                "wait for completion (not rollout), and capture logs from the Job pods. "
                "Do NOT look for Deployments or Services."
            )

    # If this is a retry, include the previous error
    if previous_error and deploy_retries > 0:
        user_message += (
            f"\n\n**PREVIOUS APPLY ATTEMPT FAILED (retry {deploy_retries}):**\n"
            f"{previous_error}\n\n"
            f"Please re-apply and verify. If the manifests need fixing, return an error "
            f"and the pipeline will route back to the deploy agent."
        )

    user_message += (
        "\n\nApply the manifest files listed above in order. "
        "Use the EXACT absolute paths provided — do NOT use relative paths. "
        "Wait for rollouts, verify pods, and get service URLs."
    )

    # Create agent
    assert llm is not None
    agent = create_react_agent(
        model=llm,
        tools=APPLY_TOOLS,
        pre_model_hook=make_context_trimmer(),
    )

    logger.info("Invoking apply agent for %d components", len(components))

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

        messages = result.get("messages", [])
        raw_output = _extract_final_ai_content(messages)
        parsed = _parse_apply_output(raw_output, messages)

        deployed_resources = parsed["deployed_resources"]
        routes = parsed["routes"]
        error = parsed.get("error")

        # If we didn't extract resources and there's no error, infer from components
        if not deployed_resources and not error:
            for component in components:
                comp_name = component.get("name", "")
                deployed_resources.append(f"deployment/{comp_name}")
                if component.get("port"):
                    deployed_resources.append(f"service/{comp_name}")

        if error:
            logger.warning("Apply agent reported error: %s", error)
            current_retries = state.get("deploy_retries", 0)

            # Triage the error to decide routing (manifest fix vs container fix)
            triage_action = await _triage_apply_error(error)
            result_state = {
                "current_phase": PoCPhase.APPLY,
                "deployed_resources": deployed_resources,
                "routes": routes,
                "error": error,
                "deploy_retries": current_retries + 1,
                "container_fix_action": triage_action,
            }
            if triage_action in ("fix-dockerfile", "experiment"):
                result_state["container_fix_error"] = error
            return result_state

        logger.info(
            "Apply complete: %d resources, %d routes",
            len(deployed_resources),
            len(routes),
        )

        # ── Deterministic: verify pod health after apply reports success ──
        # kubectl rollout status can return success if the pod starts briefly
        # before crashing. Check pod status after a short delay to catch
        # CrashLoopBackOff, ImagePullBackOff, etc.
        health_error = _check_pod_health(project_name)
        if health_error:
            logger.warning("Post-apply health check failed: %s", health_error[:300])
            current_retries = state.get("deploy_retries", 0)
            triage_action = await _triage_apply_error(health_error)
            result_state = {
                "current_phase": PoCPhase.APPLY,
                "deployed_resources": deployed_resources,
                "routes": routes,
                "error": health_error,
                "deploy_retries": current_retries + 1,
                "container_fix_action": triage_action,
            }
            if triage_action in ("fix-dockerfile", "experiment"):
                result_state["container_fix_error"] = health_error
            return result_state

        return {
            "current_phase": PoCPhase.APPLY,
            "deployed_resources": deployed_resources,
            "routes": routes,
            "error": None,
            "container_fix_action": None,
            "container_fix_error": None,
        }

    except Exception as e:
        logger.error("Apply failed: %s", e, exc_info=True)
        current_retries = state.get("deploy_retries", 0)
        error_msg = f"Apply failed: {e}"

        # ── Enrich with pod health check ──
        # The exception often just says "rollout timed out" which is useless
        # for the containerize agent. Check pod health to get the ACTUAL
        # crash reason (e.g., "streamlit: command not found") with logs.
        health_error = _check_pod_health(project_name)
        if health_error:
            error_msg += f"\n\n{health_error}"

        # Triage even on exceptions — the error text may indicate a container issue
        triage_action = await _triage_apply_error(error_msg)
        result_state = {
            "current_phase": PoCPhase.APPLY,
            "deployed_resources": [],
            "routes": [],
            "error": error_msg,
            "deploy_retries": current_retries + 1,
            "container_fix_action": triage_action,
        }
        if triage_action in ("fix-dockerfile", "experiment"):
            result_state["container_fix_error"] = error_msg
        return result_state
