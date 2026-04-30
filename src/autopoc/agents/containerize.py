"""Containerize agent — generates Dockerfile.ubi files for each component.

Uses an LLM with file and template tools to create UBI-based Dockerfiles
that are compatible with OpenShift (arbitrary UID support).
"""

import json
import logging
import re
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from autopoc.context import make_context_trimmer
from autopoc.llm import create_llm
from autopoc.state import ComponentInfo, PoCPhase, PoCState
from autopoc.tools.file_tools import list_files, read_file, search_files, write_file
from autopoc.tools.git_tools import git_commit, git_push
from autopoc.tools.template_tools import render_template

logger = logging.getLogger(__name__)


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


# Tools available to the containerize agent
CONTAINERIZE_TOOLS = [list_files, read_file, write_file, search_files, render_template]


def _load_system_prompt() -> str:
    """Load the containerize system prompt from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "containerize.md"
    return prompt_path.read_text(encoding="utf-8")


def _build_user_message(
    component: ComponentInfo,
    clone_path: str,
    build_error: str | None = None,
    poc_infrastructure: dict | None = None,  # PoCInfrastructure TypedDict
    poc_type: str | None = None,
    poc_plan_text: str | None = None,
) -> str:
    """Build the user message for the containerize agent.

    Args:
        component: Component info from the intake phase.
        clone_path: Absolute path to the cloned repository.
        build_error: Previous build error message (for retry loop).
        poc_infrastructure: PoC infrastructure requirements (from poc_plan agent).
        poc_type: PoC project type classification (from poc_plan agent).

    Returns:
        User message string.
    """
    source_dir = component.get("source_dir", ".")
    if source_dir == ".":
        component_path = clone_path
    else:
        component_path = str(Path(clone_path) / source_dir)

    parts = [
        "Create a Dockerfile.ubi for the following component:\n",
        f"- **Name:** {component.get('name', 'unknown')}",
        f"- **Language:** {component.get('language', 'unknown')}",
        f"- **Build system:** {component.get('build_system', 'unknown')}",
        f"- **Entry point:** {component.get('entry_point', 'unknown')}",
        f"- **Port:** {component.get('port', 'not specified')}",
        f"- **Is ML workload:** {component.get('is_ml_workload', False)}",
        f"- **Source directory:** {source_dir}",
        f"- **Full path on disk:** {component_path}",
        f"- **Build context (repo root):** {clone_path}",
    ]

    existing = component.get("existing_dockerfile")
    if existing:
        parts.append(f"\n**Existing Dockerfile:** `{existing}` (read it and adapt to UBI)")
    else:
        parts.append("\n**No existing Dockerfile.** Create one from scratch.")

    parts.append(f"\nWrite the Dockerfile.ubi to: `{component_path}/Dockerfile.ubi`")

    # Add explicit reminder about COPY paths for subdirectory components
    if source_dir != ".":
        parts.append(
            f"\n**CRITICAL:** This component is in a subdirectory (`{source_dir}/`). "
            f"The build context will be the repo root (`{clone_path}`), NOT the component directory. "
            f"ALL COPY commands must use paths relative to the repo root. "
            f"Example: `COPY {source_dir}/package.json ./` (not `COPY package.json ./`)"
        )
    parts.append(f"All tool calls should use absolute paths starting with `{clone_path}`.")

    # Include PoC infrastructure requirements if available
    if poc_infrastructure:
        parts.append("\n## PoC Infrastructure Requirements")
        if poc_type:
            parts.append(f"**Project type:** {poc_type}")

        if poc_infrastructure.get("needs_inference_server"):
            server_type = poc_infrastructure.get("inference_server_type", "custom")
            parts.append(
                f"\n**Inference server needed:** {server_type}. "
                f"If the project doesn't include its own serving code, consider bundling "
                f"or configuring the inference server in the Dockerfile."
            )

        if poc_infrastructure.get("needs_vector_db"):
            db_type = poc_infrastructure.get("vector_db_type", "in-memory")
            if db_type == "in-memory":
                parts.append(
                    "\n**In-memory vector DB needed:** Include the vector DB library "
                    "(e.g., ChromaDB, FAISS) in the Python dependencies."
                )

        if poc_infrastructure.get("needs_embedding_model"):
            model = poc_infrastructure.get("embedding_model", "")
            parts.append(
                f"\n**Embedding model needed:** {model}. Consider whether to download "
                f"at build time or at runtime. For small models, baking into the image "
                f"is acceptable for PoC."
            )

        if poc_infrastructure.get("needs_gpu"):
            parts.append(
                "\n**GPU support needed:** Consider using a CUDA-capable base image "
                "such as `nvcr.io/nvidia/cuda:12.x-runtime-ubi9`."
            )

        extra_env = poc_infrastructure.get("extra_env_vars", {})
        if extra_env:
            parts.append("\n**Environment variables to set in Dockerfile:**")
            for key, value in extra_env.items():
                if value == "required":
                    parts.append(
                        f"  - `{key}` (must be provided at runtime via K8s secret/configmap)"
                    )
                else:
                    parts.append(f"  - `{key}={value}`")

        resource_profile = poc_infrastructure.get("resource_profile", "small")
        parts.append(f"\n**Resource profile:** {resource_profile}")

        # Deployment model — critical for deciding ENTRYPOINT/CMD and EXPOSE
        deployment_model = poc_infrastructure.get("deployment_model", "deployment")
        listens_on_port = poc_infrastructure.get("listens_on_port", True)
        long_running = poc_infrastructure.get("long_running", True)
        parts.append(f"\n**Deployment model:** {deployment_model}")
        parts.append(f"**Listens on port:** {listens_on_port}")
        parts.append(f"**Long-running process:** {long_running}")

        if not listens_on_port:
            parts.append(
                "\n**IMPORTANT:** This component does NOT listen on a network port. "
                "Do NOT add EXPOSE to the Dockerfile."
            )

        if deployment_model == "cli-only":
            parts.append(
                "\n**IMPORTANT:** This is a CLI tool / library. The ENTRYPOINT should be "
                "the CLI binary. CMD should default to --help or --version. "
                "Do NOT add EXPOSE. The container will be invoked with explicit commands, "
                "not run as a long-lived daemon."
            )

        entrypoint = poc_infrastructure.get("entrypoint_suggestion")
        if entrypoint:
            parts.append(f"\n**Suggested entrypoint:** `{entrypoint}`")

    # Include full PoC plan for additional context
    if poc_plan_text:
        parts.append("\n## Full PoC Plan (for context)")
        parts.append(poc_plan_text)

    if build_error:
        parts.append(
            f"\n**PREVIOUS BUILD FAILED.** Fix the Dockerfile.ubi based on this error:\n"
            f"```\n{build_error}\n```"
        )

    return "\n".join(parts)


def _extract_dockerfile_from_response(raw_output: str) -> str | None:
    """Extract Dockerfile content from the LLM's text response.

    Looks for a Dockerfile in a markdown code block (```dockerfile or ```).
    This is a fallback for when the LLM doesn't use the write_file tool
    but includes the Dockerfile content in its response text.

    Returns:
        Dockerfile content string, or None if not found.
    """
    # Try ```dockerfile ... ``` first
    match = re.search(
        r"```[Dd]ockerfile\s*\n(.*?)```",
        raw_output,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip() + "\n"

    # Try any code block that starts with FROM
    match = re.search(
        r"```\s*\n(FROM\s+.*?)```",
        raw_output,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip() + "\n"

    # Try bare FROM ... at start of a line (no code block)
    match = re.search(
        r"^(FROM\s+.+(?:\n(?!```).+)*)",
        raw_output,
        re.MULTILINE,
    )
    if match:
        return match.group(1).strip() + "\n"

    return None


def _parse_containerize_output(raw_output: str, component_path: str) -> dict:
    """Parse the containerize agent's JSON output.

    Args:
        raw_output: Raw LLM output string.
        component_path: Expected path prefix for the Dockerfile.

    Returns:
        Dict with dockerfile_ubi_path and other metadata.
    """
    text = raw_output.strip()

    # Try to find a markdown code block containing JSON
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Fallback: extract from first { to last }
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)

    try:
        parsed = json.loads(text)
        return parsed
    except json.JSONDecodeError:
        logger.warning("Failed to parse containerize output as JSON, using defaults")
        from autopoc.debug import dump_llm_response

        dump_llm_response(
            "containerize",
            "JSON output parse failure",
            raw_output,
            component=component_path.rsplit("/", 1)[-1],
        )
        return {
            "dockerfile_ubi_path": f"{component_path}/Dockerfile.ubi",
            "strategy": "unknown",
            "notes": "Output parsing failed",
        }


async def containerize_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Generate Dockerfile.ubi files for each component in the repository.

    This is a LangGraph node function. It receives the current state and returns
    a partial state update dict.

    Args:
        state: Current pipeline state with components populated by intake.
        llm: Optional LLM override (for testing).

    Returns:
        Partial state update with updated components (dockerfile_ubi_path set).
    """
    clone_path = state.get("local_clone_path")
    if not clone_path:
        logger.error("Cannot containerize: local_clone_path is missing from state")
        return {"current_phase": PoCPhase.CONTAINERIZE, "error": "Missing local_clone_path"}

    components = list(state.get("components", []))
    build_error = state.get("error")

    # -------------------------------------------------------------------------
    # Detect outer-loop entry: apply escalated to containerize due to a
    # container-level runtime failure (CrashLoopBackOff, missing dep, etc.)
    # -------------------------------------------------------------------------
    container_fix_error = state.get("container_fix_error")
    container_fix_action = state.get("container_fix_action")  # "fix-dockerfile" | "experiment"

    # Detect outer-loop entry. This happens in two ways:
    # 1. Explicit: apply triage classified as "fix-dockerfile" / "experiment"
    #    and container_fix_error was set.
    # 2. Last-resort: deploy retries exhausted with a "fix-manifest" triage,
    #    the router escalated to containerize as a hail-mary. In this case,
    #    container_fix_error is NOT set, but state has an error and
    #    deploy_retries is at the max. We must still increment the counter
    #    and reset deploy_retries, otherwise we loop forever.
    is_container_fix = container_fix_error is not None
    if not is_container_fix and state.get("error") and state.get("deploy_retries", 0) > 0:
        # Last-resort escalation: deploy retries were exhausted and the router
        # sent us here even though triage said "fix-manifest".
        is_container_fix = True
        container_fix_error = state.get("error")
        logger.info(
            "Detected last-resort escalation from apply (deploy_retries=%d, action=%s)",
            state.get("deploy_retries", 0),
            container_fix_action,
        )

    # Extra state to return when we're in the outer loop
    outer_loop_state: dict = {}

    if is_container_fix:
        # Increment the outer-loop counter and reset inner counters so the
        # rebuilt image gets a fresh deploy→apply cycle.
        prev_fix_retries = state.get("container_fix_retries", 0)
        outer_loop_state = {
            "container_fix_retries": prev_fix_retries + 1,
            "deploy_retries": 0,
            "build_retries": 0,
            # Carry the action through so build_agent knows the tagging strategy
            "container_fix_action": container_fix_action,
            # Clear the error that triggered the escalation (we're handling it)
            "container_fix_error": None,
        }
        logger.info(
            "Outer loop: containerize re-entered from apply (action=%s, container_fix_retry=%d)",
            container_fix_action,
            prev_fix_retries + 1,
        )

    # Check if poc_plan failed — if so, stop early. Proceeding with fallback
    # defaults would produce wrong Dockerfiles and waste LLM calls.
    poc_plan_error = state.get("poc_plan_error")
    if poc_plan_error:
        logger.error("PoC plan failed, cannot containerize: %s", poc_plan_error)
        return {
            "current_phase": PoCPhase.CONTAINERIZE,
            "components": components,
            "error": f"PoC plan failed: {poc_plan_error}",
            **outer_loop_state,
        }

    if not components:
        logger.warning("No components to containerize")
        return {
            "current_phase": PoCPhase.CONTAINERIZE,
            "components": components,
            **outer_loop_state,
        }

    # Filter to only PoC-relevant components (if poc_plan specified which ones)
    poc_components = state.get("poc_components", [])
    if poc_components:
        original_count = len(components)
        components = [c for c in components if c.get("name", "") in poc_components]
        skipped = original_count - len(components)
        if skipped > 0:
            logger.info(
                "Filtered to %d PoC-relevant component(s), skipping %d (poc_components=%s)",
                len(components),
                skipped,
                poc_components,
            )
        if not components:
            logger.warning("No PoC-relevant components after filtering")
            return {
                "current_phase": PoCPhase.CONTAINERIZE,
                "components": components,
                **outer_loop_state,
            }

    # Get PoC infrastructure requirements (may be absent for older flows)
    poc_infrastructure = state.get("poc_infrastructure")
    poc_type = state.get("poc_type")

    logger.info("Containerizing %d component(s) (poc_type=%s)", len(components), poc_type or "none")

    # Set up LLM
    # NOTE: Always create a fresh LLM instance per component to avoid context overflow.
    # Even if an LLM is passed in for testing, ReAct agents manage their own message
    # state, so we don't accumulate context across components.
    if llm is None:
        llm = create_llm()

    # Load system prompt
    system_prompt = _load_system_prompt()

    # Process each component
    updated_components = []
    retries = state.get("build_retries", 0)

    for component in components:
        comp_name = component.get("name", "unknown")

        # In a build-retry loop, skip components that already built successfully
        if retries > 0 and not is_container_fix:
            if component.get("image_name") in state.get("built_images", []):
                logger.info("Skipping containerize for %s: already built successfully", comp_name)
                updated_components.append(component)
                continue

        # In a build-retry loop, skip components that haven't failed
        component_build_error = None
        if retries > 0 and not is_container_fix:
            if not build_error or f"Build failed for component '{comp_name}'" not in build_error:
                logger.info(
                    "Skipping containerize for %s: no build error for this component", comp_name
                )
                updated_components.append(component)
                continue
            component_build_error = build_error

        logger.info("Containerizing component: %s", comp_name)

        # Create the ReAct agent with context trimming to prevent overflow
        agent = create_react_agent(
            model=llm,
            tools=CONTAINERIZE_TOOLS,
            pre_model_hook=make_context_trimmer(),
        )

        # Build user message (with PoC context if available)
        user_message = _build_user_message(
            component,
            clone_path,
            component_build_error,
            poc_infrastructure=dict(poc_infrastructure) if poc_infrastructure else None,
            poc_type=poc_type,
            poc_plan_text=state.get("poc_plan"),
        )

        # If this is a container-fix from the outer loop, append the runtime
        # error so the LLM knows what went wrong at deploy time.
        if is_container_fix and container_fix_error:
            action_label = (
                "Create an experimental variant"
                if container_fix_action == "experiment"
                else "Fix the Dockerfile"
            )
            user_message += (
                f"\n\n**RUNTIME FAILURE — CONTAINER FIX REQUESTED**\n"
                f"Action: **{action_label}**\n\n"
                f"The container was deployed to Kubernetes but failed at runtime. "
                f"The error below is from the running pod (logs, events, or status).\n"
                f"```\n{container_fix_error}\n```\n\n"
            )
            if container_fix_action == "experiment":
                user_message += (
                    "The existing Dockerfile.ubi is considered correct for the base image. "
                    "Create a **modified variant** that addresses the runtime issue — for "
                    "example, a different CMD/ENTRYPOINT, an extra runtime dependency, or "
                    "a baked-in config file. The build system will tag this as an experiment "
                    "image so the original `:latest` stays clean.\n"
                )
            else:
                user_message += (
                    "The Dockerfile.ubi has a bug that causes the container to fail at "
                    "runtime. Fix it so the container starts and runs correctly. Common "
                    "causes: missing dependency in requirements/package install, wrong "
                    "ENTRYPOINT/CMD, missing COPY for required files, wrong working "
                    "directory.\n"
                )

        # Invoke the agent
        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ],
            },
            config={"recursion_limit": 60},
        )

        # Extract the final AI message with actual content
        raw_output = _extract_final_ai_content(result["messages"])

        # Parse output
        source_dir = component.get("source_dir", ".")
        component_path = clone_path if source_dir == "." else str(Path(clone_path) / source_dir)
        parsed = _parse_containerize_output(raw_output, component_path)

        # Update component with dockerfile path
        updated = dict(component)
        dockerfile_path = parsed.get("dockerfile_ubi_path", f"{component_path}/Dockerfile.ubi")
        # Ensure path is relative to repo root for state storage
        if dockerfile_path.startswith(clone_path):
            dockerfile_path = dockerfile_path[len(clone_path) :].lstrip("/")

        # Verify the Dockerfile was actually written to disk.
        # If the LLM didn't use the write_file tool (common with weaker models),
        # try to extract the Dockerfile content from the response and write it ourselves.
        abs_dockerfile = Path(clone_path) / dockerfile_path
        if not abs_dockerfile.exists():
            logger.warning(
                "Dockerfile not found at %s after agent run — "
                "attempting to extract from LLM response",
                abs_dockerfile,
            )
            dockerfile_content = _extract_dockerfile_from_response(raw_output)
            if dockerfile_content:
                abs_dockerfile.parent.mkdir(parents=True, exist_ok=True)
                abs_dockerfile.write_text(dockerfile_content, encoding="utf-8")
                logger.info(
                    "Wrote Dockerfile.ubi from LLM response (%d chars) to %s",
                    len(dockerfile_content),
                    abs_dockerfile,
                )
            else:
                logger.error(
                    "Could not extract Dockerfile content from LLM response for %s",
                    comp_name,
                )

        updated["dockerfile_ubi_path"] = dockerfile_path
        updated_components.append(updated)

        logger.info(
            "Component %s: Dockerfile.ubi at %s (strategy: %s, exists: %s)",
            comp_name,
            dockerfile_path,
            parsed.get("strategy", "unknown"),
            abs_dockerfile.exists(),
        )

    # Commit and push the new Dockerfiles
    commit_msg = (
        "Fix Dockerfile.ubi (runtime container fix)"
        if is_container_fix
        else "Add Dockerfile.ubi files for OpenShift deployment"
    )
    try:
        dockerfile_files = [
            c["dockerfile_ubi_path"] for c in updated_components if c.get("dockerfile_ubi_path")
        ]
        if dockerfile_files:
            git_commit.invoke(
                {
                    "repo_path": clone_path,
                    "message": commit_msg,
                    "files": dockerfile_files,
                }
            )

            # Push to fork if remote exists
            fork_url = state.get("fork_repo_url") or state.get("gitlab_repo_url")
            if fork_url:
                git_push.invoke(
                    {
                        "repo_path": clone_path,
                        "remote": "origin",
                        "ref": "HEAD",
                    }
                )
                logger.info("Pushed Dockerfile.ubi files to fork")
    except Exception as e:
        logger.warning("Failed to commit/push Dockerfiles: %s", e)

    return {
        "current_phase": PoCPhase.CONTAINERIZE,
        "components": updated_components,
        "error": None,  # Clear any previous build/apply error
        **outer_loop_state,
    }
