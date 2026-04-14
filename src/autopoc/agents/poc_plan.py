"""PoC Plan agent — generates a proof-of-concept plan for the repository.

Analyzes the repo and intake results to determine what constitutes a meaningful
PoC in the context of Open Data Hub / OpenShift AI. Produces a poc-plan.md file
and structured state fields that influence downstream containerization and deployment.
"""

import json
import logging
import re
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from autopoc.llm import create_llm
from autopoc.state import PoCInfrastructure, PoCPhase, PoCScenario, PoCState
from autopoc.tools.file_tools import list_files, read_file, search_files, write_file

logger = logging.getLogger(__name__)


# Tools available to the PoC plan agent
POC_PLAN_TOOLS = [list_files, read_file, search_files, write_file]


def _load_system_prompt() -> str:
    """Load the PoC plan system prompt from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "poc_plan.md"
    return prompt_path.read_text(encoding="utf-8")


def _extract_final_ai_content(messages: list) -> str:
    """Extract the text content from the last AIMessage with non-empty content.

    The ReAct agent returns a list of messages including tool calls and tool
    results. The final analysis is in the last AIMessage that has actual text
    content (not just tool_calls with empty content).
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
            return content

    logger.warning("No AIMessage with non-empty content found in %d messages", len(messages))
    return ""


def _parse_poc_plan_output(raw_output: str) -> dict:
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
        logger.warning("Failed to parse PoC plan output as JSON: %s", e)
        logger.debug("Raw output: %s", text[:500])
        # Return a minimal valid structure
        return {
            "poc_type": "web-app",
            "poc_plan_summary": f"Failed to parse PoC plan output: {e}",
            "infrastructure": {},
            "scenarios": [],
        }


def _validate_scenario(scenario: dict) -> PoCScenario:
    """Validate and normalize a scenario dict from LLM output."""
    return PoCScenario(
        name=scenario.get("name", "unnamed"),
        description=scenario.get("description", ""),
        type=scenario.get("type", "http"),
        endpoint=scenario.get("endpoint"),
        input_data=scenario.get("input_data"),
        expected_behavior=scenario.get("expected_behavior", ""),
        timeout_seconds=scenario.get("timeout_seconds", 30),
    )


def _validate_infrastructure(infra: dict) -> PoCInfrastructure:
    """Validate and normalize an infrastructure dict from LLM output."""
    return PoCInfrastructure(
        needs_inference_server=infra.get("needs_inference_server", False),
        inference_server_type=infra.get("inference_server_type"),
        needs_vector_db=infra.get("needs_vector_db", False),
        vector_db_type=infra.get("vector_db_type"),
        needs_embedding_model=infra.get("needs_embedding_model", False),
        embedding_model=infra.get("embedding_model"),
        needs_gpu=infra.get("needs_gpu", False),
        gpu_type=infra.get("gpu_type"),
        needs_pvc=infra.get("needs_pvc", False),
        pvc_size=infra.get("pvc_size"),
        sidecar_containers=infra.get("sidecar_containers", []),
        extra_env_vars=infra.get("extra_env_vars", {}),
        odh_components=infra.get("odh_components", []),
        resource_profile=infra.get("resource_profile", "small"),
    )


def _build_user_message(state: PoCState) -> str:
    """Build the user message for the PoC plan agent."""
    parts = []

    project_name = state.get("project_name", "unknown")
    clone_path = state.get("local_clone_path", "")

    parts.append(f"Analyze this project and create a PoC plan.\n")
    parts.append(f"Project name: {project_name}")
    parts.append(f"Source URL: {state.get('source_repo_url', '')}")
    parts.append(f"Repository cloned at: {clone_path}")
    parts.append("")

    # Include intake results
    repo_summary = state.get("repo_summary", "")
    if repo_summary:
        parts.append(f"## Repository Summary (from intake analysis)")
        parts.append(repo_summary)
        parts.append("")

    components = state.get("components", [])
    if components:
        parts.append("## Detected Components")
        for comp in components:
            parts.append(
                f"- **{comp.get('name', '?')}**: {comp.get('language', '?')} "
                f"({comp.get('build_system', '?')})"
            )
            if comp.get("port"):
                parts.append(f"  - Port: {comp['port']}")
            if comp.get("entry_point"):
                parts.append(f"  - Entry point: {comp['entry_point']}")
            if comp.get("is_ml_workload"):
                parts.append(f"  - **ML workload: yes**")
            if comp.get("existing_dockerfile"):
                parts.append(f"  - Has Dockerfile: {comp['existing_dockerfile']}")
            if comp.get("source_dir") and comp["source_dir"] != ".":
                parts.append(f"  - Source directory: {comp['source_dir']}")
        parts.append("")

    # Existing deployment artifacts
    existing = []
    if state.get("has_helm_chart"):
        existing.append("Helm chart")
    if state.get("has_kustomize"):
        existing.append("Kustomize")
    if state.get("has_compose"):
        existing.append("Docker Compose")
    if state.get("existing_ci_cd"):
        existing.append(f"CI/CD ({state['existing_ci_cd']})")

    if existing:
        parts.append(f"## Existing Deployment Artifacts")
        parts.append(", ".join(existing))
        parts.append("")

    parts.append("## Instructions")
    parts.append(
        f"Use the tools to examine the repository at {clone_path}. "
        f"Read key files (README, dependency files, main source files) to understand "
        f"the project deeply. Then write a poc-plan.md file to {clone_path}/poc-plan.md "
        f"and respond with the structured JSON output as described in your system prompt."
    )
    parts.append("")
    parts.append(f"All tool calls should use absolute paths starting with {clone_path}.")

    return "\n".join(parts)


async def poc_plan_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Generate a PoC plan for the repository.

    This is a LangGraph node function. It receives the current state and returns
    a partial state update dict. It runs in parallel with the fork agent.

    Args:
        state: Current pipeline state with intake results populated.
        llm: Optional LLM override (for testing). Defaults to ChatAnthropic.

    Returns:
        Partial state update with PoC plan results.
    """
    project_name = state.get("project_name", "unknown")
    clone_path = state.get("local_clone_path", "")

    logger.info("Starting PoC plan generation for %s", project_name)

    # Set up LLM — fresh instance to avoid context overflow
    if llm is None:
        llm = create_llm()

    # Load system prompt
    system_prompt = _load_system_prompt()

    # Create the ReAct agent
    agent = create_react_agent(
        model=llm,
        tools=POC_PLAN_TOOLS,
    )

    # Build the user message
    user_message = _build_user_message(state)

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

    # Parse the structured output
    parsed = _parse_poc_plan_output(raw_output)

    # Validate scenarios
    scenarios = [_validate_scenario(s) for s in parsed.get("scenarios", [])]

    # Validate infrastructure
    infrastructure = _validate_infrastructure(parsed.get("infrastructure", {}))

    # Read the poc-plan.md content (agent should have written it)
    poc_plan_path = str(Path(clone_path or ".") / "poc-plan.md")
    poc_plan_content = ""
    try:
        poc_plan_file = Path(poc_plan_path)
        if poc_plan_file.exists():
            poc_plan_content = poc_plan_file.read_text(encoding="utf-8")
            logger.info("PoC plan written to %s (%d chars)", poc_plan_path, len(poc_plan_content))
        else:
            logger.warning("poc-plan.md was not written by the agent at %s", poc_plan_path)
            # Use the summary as fallback content
            poc_plan_content = parsed.get("poc_plan_summary", "")
    except Exception as e:
        logger.warning("Failed to read poc-plan.md: %s", e)
        poc_plan_content = parsed.get("poc_plan_summary", "")

    poc_type = parsed.get("poc_type", "web-app")

    logger.info(
        "PoC plan complete: type=%s, %d scenarios, profile=%s",
        poc_type,
        len(scenarios),
        infrastructure.get("resource_profile", "unknown"),
    )

    # Return partial state update
    return {
        "current_phase": PoCPhase.POC_PLAN,
        "poc_plan": poc_plan_content,
        "poc_plan_path": poc_plan_path,
        "poc_scenarios": scenarios,
        "poc_infrastructure": infrastructure,
        "poc_type": poc_type,
    }
