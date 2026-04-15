"""Intake agent — analyzes a source repository to identify components and structure.

Uses an LLM with file-reading tools to examine a cloned repo and produce
a structured analysis of its components, languages, build systems, and
existing deployment artifacts.
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
from autopoc.tools.file_tools import list_files, read_file, search_files

# LangGraph emits this message when the agent exhausts its recursion budget.
STEPS_EXHAUSTED_MSG = "Sorry, need more steps to process this request."
from autopoc.tools.git_tools import git_clone

logger = logging.getLogger(__name__)


def _extract_final_ai_content(messages: list) -> str:
    """Extract the text content from the last AIMessage with non-empty content.

    The ReAct agent returns a list of messages including tool calls and tool
    results. The final analysis is in the last AIMessage that has actual text
    content (not just tool_calls with empty content).

    Args:
        messages: List of messages from the agent result.

    Returns:
        The text content of the last substantive AIMessage, or empty string.
    """
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue

        content = msg.content
        if isinstance(content, list):
            # Multi-part content (text blocks from Claude)
            content = "".join(
                part["text"] if isinstance(part, dict) and "text" in part else str(part)
                for part in content
            )

        if isinstance(content, str) and content.strip():
            logger.debug(
                "Found final AI content (%d chars) from message %d of %d",
                len(content),
                len(messages) - messages.index(msg),
                len(messages),
            )
            return content

    logger.warning("No AIMessage with non-empty content found in %d messages", len(messages))
    # Log message types for debugging
    msg_types = [type(m).__name__ for m in messages]
    logger.debug("Message types: %s", msg_types)
    return ""


# Tools available to the intake agent
INTAKE_TOOLS = [list_files, read_file, search_files]


def _load_system_prompt() -> str:
    """Load the intake system prompt from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "intake.md"
    return prompt_path.read_text(encoding="utf-8")


def _parse_intake_output(raw_output: str) -> dict:
    """Parse the LLM's JSON output into a structured dict.

    Handles common issues like markdown code fences around JSON.
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
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse intake output as JSON: %s", e)
        logger.debug("Raw output: %s", text[:500])
        # Return a minimal valid structure
        return {
            "repo_summary": f"Failed to parse analysis output: {e}",
            "components": [],
            "has_helm_chart": False,
            "has_kustomize": False,
            "has_compose": False,
            "existing_ci_cd": None,
        }


def _validate_component(comp: dict) -> ComponentInfo:
    """Validate and normalize a component dict from LLM output."""
    return ComponentInfo(
        name=comp.get("name", "unknown"),
        language=comp.get("language", "unknown"),
        build_system=comp.get("build_system", "unknown"),
        entry_point=comp.get("entry_point", ""),
        port=comp.get("port"),
        existing_dockerfile=comp.get("existing_dockerfile"),
        is_ml_workload=comp.get("is_ml_workload", False),
        source_dir=comp.get("source_dir", "."),
        dockerfile_ubi_path="",  # Set later by containerize agent
        image_name="",  # Set later by build agent
    )


async def intake_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Analyze a source repository and populate state with component information.

    This is a LangGraph node function. It receives the current state and returns
    a partial state update dict.

    Args:
        state: Current pipeline state with source_repo_url set.
        llm: Optional LLM override (for testing). Defaults to ChatAnthropic.

    Returns:
        Partial state update with repo analysis results.
    """
    source_url = state.get("source_repo_url", "")
    project_name = state.get("project_name", "unknown")

    logger.info("Starting intake analysis for %s (%s)", project_name, source_url)

    # Clone if not already done
    clone_path = state.get("local_clone_path")
    if not clone_path or not Path(clone_path).exists():
        from autopoc.config import load_config

        app_config = load_config()
        work_dir = Path(app_config.work_dir) / project_name
        clone_path = git_clone.invoke({"url": source_url, "dest": str(work_dir)})
        logger.info("Cloned repo to %s", clone_path)

    # Set up LLM
    # NOTE: Create a fresh LLM instance to avoid context overflow from previous agents.
    # Each agent should start with a clean slate.
    if llm is None:
        llm = create_llm()

    # Load system prompt
    system_prompt = _load_system_prompt()

    # Create the ReAct agent with context trimming to prevent overflow
    agent = create_react_agent(
        model=llm,
        tools=INTAKE_TOOLS,
        pre_model_hook=make_context_trimmer(),
    )

    # Build the user message
    user_message = (
        f"Analyze the repository cloned at: {clone_path}\n\n"
        f"Project name: {project_name}\n"
        f"Source URL: {source_url}\n\n"
        f"Use the tools to examine the repository and produce your analysis. "
        f"All tool calls should use absolute paths starting with {clone_path}."
    )

    # Invoke the agent.
    # Recursion limit of 60 allows ~30 tool calls. The pre_model_hook takes
    # a step each time, and the LLM needs headroom to produce output after
    # reading files. Previous limit of 30 was too tight.
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

    # Detect agent step exhaustion — LangGraph emits a canonical message
    # when remaining_steps < 2. If this happened, the agent never produced
    # its JSON output and we must fail explicitly.
    if STEPS_EXHAUSTED_MSG in raw_output:
        logger.error("Intake agent exhausted its step budget without producing output")
        return {
            "current_phase": PoCPhase.INTAKE,
            "local_clone_path": str(clone_path),
            "repo_summary": "",
            "components": [],
            "has_helm_chart": False,
            "has_kustomize": False,
            "has_compose": False,
            "existing_ci_cd": None,
            "error": (
                "Intake agent exhausted its step budget before producing analysis. "
                "The repository may be too large or complex. "
                "Try running with a simpler repo or increasing the recursion limit."
            ),
        }

    # Parse the structured output
    parsed = _parse_intake_output(raw_output)

    # Validate and build components list
    components = [_validate_component(comp) for comp in parsed.get("components", [])]

    # If we parsed but got 0 components, that's also a failure — intake must
    # find at least one component for the pipeline to do anything useful.
    if not components:
        logger.error("Intake found 0 components — pipeline cannot proceed")
        return {
            "current_phase": PoCPhase.INTAKE,
            "local_clone_path": str(clone_path),
            "repo_summary": parsed.get("repo_summary", ""),
            "components": [],
            "has_helm_chart": parsed.get("has_helm_chart", False),
            "has_kustomize": parsed.get("has_kustomize", False),
            "has_compose": parsed.get("has_compose", False),
            "existing_ci_cd": parsed.get("existing_ci_cd"),
            "error": (
                "Intake analysis found 0 components. The repository may use an "
                "unsupported build system, or the LLM failed to parse the output correctly."
            ),
        }

    logger.info(
        "Intake complete: found %d component(s): %s",
        len(components),
        [c.get("name", "unknown") for c in components],
    )

    # Return partial state update
    return {
        "current_phase": PoCPhase.INTAKE,
        "local_clone_path": str(clone_path),
        "repo_summary": parsed.get("repo_summary", ""),
        "components": components,
        "has_helm_chart": parsed.get("has_helm_chart", False),
        "has_kustomize": parsed.get("has_kustomize", False),
        "has_compose": parsed.get("has_compose", False),
        "existing_ci_cd": parsed.get("existing_ci_cd"),
    }
