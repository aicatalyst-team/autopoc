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

from autopoc.context import make_context_trimmer
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

    The LLM output often contains markdown prose followed by (or mixed with)
    a JSON block. We need to find the JSON that contains our expected keys
    (poc_type, scenarios, infrastructure).

    Handles common issues like:
    - Markdown code fences around JSON
    - JSON embedded in narrative text
    - Multiple JSON-like blocks (from markdown examples in the poc-plan)
    """
    text = raw_output.strip()

    # Strategy 1: Find a ```json ... ``` code block containing our expected keys
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        candidate = match.group(1)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and ("poc_type" in parsed or "scenarios" in parsed):
                return parsed
        except json.JSONDecodeError:
            continue

    # Strategy 2: Find JSON objects containing our expected keys
    # Search backwards (the structured output is usually at the end)
    # Use a balanced brace matcher instead of greedy regex
    candidates = _find_json_objects(text)
    for candidate in reversed(candidates):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and ("poc_type" in parsed or "scenarios" in parsed):
                return parsed
        except json.JSONDecodeError:
            continue

    # Strategy 3: Last resort — try the whole text
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    logger.warning("Failed to parse PoC plan output as JSON from %d chars of output", len(text))
    logger.debug("Raw output (last 500 chars): %s", text[-500:])
    # Return a minimal structure with a parse failure flag
    return {
        "poc_type": "web-app",
        "poc_plan_summary": "Failed to parse PoC plan output from LLM response",
        "_parse_failed": True,
        "infrastructure": {},
        "scenarios": [],
    }


def _find_json_objects(text: str) -> list[str]:
    """Find potential JSON object strings in text using balanced brace matching.

    Returns a list of substrings that start with { and end with the matching }.
    Only returns candidates that are at least 20 chars (to skip trivial matches
    like `{}` or `{"key": "val"}`).
    """
    candidates = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            depth = 0
            start = i
            in_string = False
            escape_next = False
            for j in range(i, len(text)):
                ch = text[j]
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\":
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : j + 1]
                        if len(candidate) >= 20:
                            candidates.append(candidate)
                        i = j + 1
                        break
            else:
                # Unbalanced — skip this opening brace
                i += 1
        else:
            i += 1
    return candidates


def _collect_all_ai_content(messages: list) -> str:
    """Collect text content from all AIMessages, concatenated.

    Useful when the structured JSON output is in a different message
    than the final one (e.g., when the agent makes tool calls after
    outputting the JSON).
    """
    parts = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, list):
            content = "".join(
                part["text"] if isinstance(part, dict) and "text" in part else str(part)
                for part in content
            )
        if isinstance(content, str) and content.strip():
            parts.append(content)
    return "\n\n".join(parts)


def _extract_poc_plan_from_tool_calls(messages: list, expected_path: str) -> str:
    """Extract poc-plan.md content from write_file tool calls in the message history.

    The agent should have called write_file to create poc-plan.md. If the file
    wasn't written to disk (path mismatch, etc.), we can extract the content
    from the tool call arguments.
    """
    for msg in messages:
        if not hasattr(msg, "tool_calls"):
            continue
        for tool_call in getattr(msg, "tool_calls", []):
            name = tool_call.get("name", "")
            if name != "write_file":
                continue
            args = tool_call.get("args", {})
            # LLM might use "path" or "file_path" as the arg name
            path = args.get("path", "") or args.get("file_path", "")
            content = args.get("content", "")
            if not content:
                continue
            # Check if this is the poc-plan.md file
            if (
                "poc-plan" in path.lower()
                or "poc_plan" in path.lower()
                or "PoC Plan" in content[:500]
                or "Project Classification" in content[:500]
            ):
                logger.info(
                    "Found poc-plan.md content in write_file tool call (%d chars, path=%s)",
                    len(content),
                    path,
                )
                return content
    return ""


def _extract_markdown_plan_from_response(text: str) -> str:
    """Extract a markdown PoC plan from LLM response text.

    If the LLM included the poc-plan.md content directly in its response
    (instead of using write_file), try to extract the full markdown plan.
    Looks for the plan start marker and extracts until the JSON output block.
    """
    # Look for a markdown heading that indicates the plan start.
    # Try most specific first.
    plan_markers = [
        "# PoC Plan",
        "# Proof of Concept Plan",
        "## Project Classification",
    ]

    best_start = -1
    for marker in plan_markers:
        idx = text.find(marker)
        if idx != -1:
            if best_start == -1 or idx < best_start:
                best_start = idx

    if best_start == -1:
        return ""

    plan_text = text[best_start:]

    # Cut off at the structured JSON output block.
    # The JSON block starts with {"poc_type" at the beginning of a line,
    # or inside a ```json fence. We need to be careful not to cut on
    # random { characters inside markdown prose.
    cutoff_patterns = [
        '\n{"poc_type"',  # JSON at start of line
        "\n```json",  # Fenced JSON block
        '\n```\n{"poc_type"',  # Fenced then JSON
    ]
    earliest_cut = len(plan_text)
    for pattern in cutoff_patterns:
        idx = plan_text.find(pattern)
        if idx != -1 and idx < earliest_cut:
            earliest_cut = idx

    plan_text = plan_text[:earliest_cut].rstrip()

    if len(plan_text) > 50:
        logger.info("Extracted PoC plan from LLM response text (%d chars)", len(plan_text))
        return plan_text.strip()

    return ""


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
        # Deployment model fields — default to "deployment" / True for backward compat
        deployment_model=infra.get("deployment_model", "deployment"),
        listens_on_port=infra.get("listens_on_port", True),
        long_running=infra.get("long_running", True),
        entrypoint_suggestion=infra.get("entrypoint_suggestion"),
        test_strategy=infra.get("test_strategy", "http"),
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

    # Create the ReAct agent with context trimming to prevent overflow
    agent = create_react_agent(
        model=llm,
        tools=POC_PLAN_TOOLS,
        pre_model_hook=make_context_trimmer(),
    )

    # Build the user message
    user_message = _build_user_message(state)

    # Invoke the agent with a recursion limit.
    # Each tool call round-trip is ~2 recursions. Limit of 50 allows ~25 tool calls,
    # which gives the agent enough room to read files AND produce the plan + JSON.
    # (30 was too tight — the agent would exhaust steps reading files and never
    # get to write poc-plan.md or output the JSON.)
    result = await agent.ainvoke(
        {
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ],
        },
        config={"recursion_limit": 50},
    )

    # Extract the final AI message with actual content
    raw_output = _extract_final_ai_content(result["messages"])

    # Also try to extract JSON from all messages (the structured output
    # may be in a different message than the final one)
    all_ai_content = _collect_all_ai_content(result["messages"])

    # Parse the structured output — try the final message first, then all content
    parsed = _parse_poc_plan_output(raw_output)
    if not parsed.get("scenarios") and all_ai_content != raw_output:
        parsed_alt = _parse_poc_plan_output(all_ai_content)
        if parsed_alt.get("scenarios"):
            parsed = parsed_alt

    # Validate scenarios
    scenarios = [_validate_scenario(s) for s in parsed.get("scenarios", [])]

    # Validate infrastructure
    infrastructure = _validate_infrastructure(parsed.get("infrastructure", {}))

    # Read the poc-plan.md content (agent should have written it via write_file tool)
    poc_plan_path = str(Path(clone_path or ".") / "poc-plan.md")
    poc_plan_content = ""
    try:
        poc_plan_file = Path(poc_plan_path)
        if poc_plan_file.exists():
            poc_plan_content = poc_plan_file.read_text(encoding="utf-8")
            logger.info("PoC plan written to %s (%d chars)", poc_plan_path, len(poc_plan_content))
        else:
            # Fallback 1: Try to extract poc-plan.md content from write_file tool calls
            poc_plan_content = _extract_poc_plan_from_tool_calls(result["messages"], poc_plan_path)
            if poc_plan_content:
                # The tool call was made but the file wasn't written (path issue?)
                # Write it ourselves
                try:
                    poc_plan_file.parent.mkdir(parents=True, exist_ok=True)
                    poc_plan_file.write_text(poc_plan_content, encoding="utf-8")
                    logger.info(
                        "Wrote poc-plan.md from tool call content (%d chars)", len(poc_plan_content)
                    )
                except Exception as write_err:
                    logger.warning("Failed to write poc-plan.md: %s", write_err)
            else:
                # Fallback 2: Extract markdown content from the LLM response
                # Try all AI content (not just the last message), since the plan
                # may be in an earlier message before tool calls
                poc_plan_content = _extract_markdown_plan_from_response(all_ai_content)
                if poc_plan_content:
                    try:
                        poc_plan_file.parent.mkdir(parents=True, exist_ok=True)
                        poc_plan_file.write_text(poc_plan_content, encoding="utf-8")
                        logger.info(
                            "Wrote poc-plan.md from LLM response (%d chars)", len(poc_plan_content)
                        )
                    except Exception as write_err:
                        logger.warning("Failed to write poc-plan.md: %s", write_err)
                else:
                    logger.warning("poc-plan.md was not written and could not be extracted")
                    poc_plan_content = parsed.get("poc_plan_summary", "")
    except Exception as e:
        logger.warning("Failed to read poc-plan.md: %s", e)
        poc_plan_content = parsed.get("poc_plan_summary", "")

    poc_type = parsed.get("poc_type", "web-app")

    # Detect if the plan agent failed to produce valid output
    parse_failed = parsed.get("_parse_failed", False)
    plan_error = None
    if parse_failed:
        plan_error = (
            "PoC plan agent failed to produce valid JSON output. "
            "The LLM may have exhausted its tool call budget before writing "
            "the plan. The pipeline cannot proceed with default/fallback values."
        )
        logger.error("PoC plan failed: %s", plan_error)
    elif not scenarios:
        # No scenarios but JSON parsed OK — this is a soft warning, not a failure.
        # The agent may have produced a plan with no test scenarios.
        logger.warning("PoC plan produced 0 test scenarios — downstream testing will be limited")

    logger.info(
        "PoC plan complete: type=%s, %d scenarios, profile=%s, error=%s",
        poc_type,
        len(scenarios),
        infrastructure.get("resource_profile", "unknown"),
        "yes" if plan_error else "no",
    )

    # Return partial state update
    # NOTE: Do not set current_phase or error here — poc_plan runs in parallel
    # with fork, and both writing to those fields would cause a LangGraph conflict.
    # Use poc_plan_error (dedicated field) to signal failure to downstream agents.
    return {
        "poc_plan": poc_plan_content,
        "poc_plan_path": poc_plan_path,
        "poc_plan_error": plan_error,
        "poc_scenarios": scenarios,
        "poc_infrastructure": infrastructure,
        "poc_type": poc_type,
    }
