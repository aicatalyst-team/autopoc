"""Containerize agent — generates Dockerfile.ubi files for each component.

Uses an LLM with file and template tools to create UBI-based Dockerfiles
that are compatible with OpenShift (arbitrary UID support).
"""

import json
import logging
import re
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from autopoc.agents.intake import _extract_final_ai_content
from autopoc.llm import create_llm
from autopoc.state import ComponentInfo, PoCPhase, PoCState
from autopoc.tools.file_tools import list_files, read_file, search_files, write_file
from autopoc.tools.git_tools import git_commit, git_push
from autopoc.tools.template_tools import render_template

logger = logging.getLogger(__name__)

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
) -> str:
    """Build the user message for the containerize agent.

    Args:
        component: Component info from the intake phase.
        clone_path: Absolute path to the cloned repository.
        build_error: Previous build error message (for retry loop).

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
        f"- **Repository root:** {clone_path}",
    ]

    existing = component.get("existing_dockerfile")
    if existing:
        parts.append(f"\n**Existing Dockerfile:** `{existing}` (read it and adapt to UBI)")
    else:
        parts.append("\n**No existing Dockerfile.** Create one from scratch.")

    parts.append(f"\nWrite the Dockerfile.ubi to: `{component_path}/Dockerfile.ubi`")
    parts.append(f"All tool calls should use absolute paths starting with `{clone_path}`.")

    if build_error:
        parts.append(
            f"\n**PREVIOUS BUILD FAILED.** Fix the Dockerfile.ubi based on this error:\n"
            f"```\n{build_error}\n```"
        )

    return "\n".join(parts)


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
    clone_path = state.get("local_clone_path", "")
    components = list(state.get("components", []))
    build_error = state.get("error")

    if not components:
        logger.warning("No components to containerize")
        return {"current_phase": PoCPhase.CONTAINERIZE, "components": components}

    logger.info("Containerizing %d component(s)", len(components))

    # Set up LLM
    if llm is None:
        llm = create_llm()

    # Load system prompt
    system_prompt = _load_system_prompt()

    # Process each component
    updated_components = []
    for component in components:
        comp_name = component.get("name", "unknown")
        logger.info("Containerizing component: %s", comp_name)

        # Create the ReAct agent
        agent = create_react_agent(
            model=llm,
            tools=CONTAINERIZE_TOOLS,
        )

        # Build user message
        user_message = _build_user_message(component, clone_path, build_error)

        # Invoke the agent
        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ],
            }
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
        updated["dockerfile_ubi_path"] = dockerfile_path
        updated_components.append(updated)

        logger.info(
            "Component %s: Dockerfile.ubi at %s (strategy: %s)",
            comp_name,
            dockerfile_path,
            parsed.get("strategy", "unknown"),
        )

    # Commit and push the new Dockerfiles
    try:
        dockerfile_files = [
            c["dockerfile_ubi_path"] for c in updated_components if c.get("dockerfile_ubi_path")
        ]
        if dockerfile_files:
            git_commit.invoke(
                {
                    "repo_path": clone_path,
                    "message": "Add Dockerfile.ubi files for OpenShift deployment",
                    "files": dockerfile_files,
                }
            )

            # Push to GitLab if remote exists
            gitlab_url = state.get("gitlab_repo_url")
            if gitlab_url:
                git_push.invoke(
                    {
                        "repo_path": clone_path,
                        "remote": "gitlab",
                        "ref": "HEAD",
                    }
                )
                logger.info("Pushed Dockerfile.ubi files to GitLab")
    except Exception as e:
        logger.warning("Failed to commit/push Dockerfiles: %s", e)

    return {
        "current_phase": PoCPhase.CONTAINERIZE,
        "components": updated_components,
        "error": None,  # Clear any previous build error
    }
