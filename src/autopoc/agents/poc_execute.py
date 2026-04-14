"""PoC Execute agent — generates and runs test scripts for the deployed PoC.

After deployment, this agent creates a Python test script based on the PoC plan
scenarios, executes it against the deployed service, and captures the results.
"""

import json
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from autopoc.llm import create_llm
from autopoc.state import PoCPhase, PoCResult, PoCState
from autopoc.tools.file_tools import read_file, write_file
from autopoc.tools.k8s_tools import kubectl_get, kubectl_logs
from autopoc.tools.script_tools import run_script

logger = logging.getLogger(__name__)


# Tools available to the PoC execute agent
POC_EXECUTE_TOOLS = [write_file, read_file, run_script, kubectl_get, kubectl_logs]


def _load_system_prompt() -> str:
    """Load the PoC execute system prompt from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "poc_execute.md"
    return prompt_path.read_text(encoding="utf-8")


def _extract_final_ai_content(messages: list) -> str:
    """Extract the text content from the last AIMessage with non-empty content."""
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

    logger.warning("No AIMessage with non-empty content found in %d messages", len(messages))
    return ""


def _parse_poc_results(raw_output: str) -> list[PoCResult]:
    """Parse test results from script output or agent message.

    The test script outputs JSON to stdout with the format:
    {"results": [{"scenario_name": "...", "status": "pass", ...}, ...]}

    The agent may also include results in its final message.
    """
    # Try to find JSON in the output
    results = []

    # Look for JSON blocks in the output
    try:
        # Try parsing the entire output as JSON first
        data = json.loads(raw_output.strip())
        if isinstance(data, dict) and "results" in data:
            for r in data["results"]:
                results.append(_validate_result(r))
            return results
    except json.JSONDecodeError:
        pass

    # Try to find embedded JSON
    import re

    json_match = re.search(r'\{[^{}]*"results"\s*:\s*\[.*?\]\s*\}', raw_output, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if isinstance(data, dict) and "results" in data:
                for r in data["results"]:
                    results.append(_validate_result(r))
                return results
        except json.JSONDecodeError:
            pass

    # Try to find individual result objects
    for match in re.finditer(r'\{[^{}]*"scenario_name"[^{}]*\}', raw_output):
        try:
            r = json.loads(match.group(0))
            results.append(_validate_result(r))
        except json.JSONDecodeError:
            continue

    if not results:
        logger.warning("Could not parse any test results from output (%d chars)", len(raw_output))

    return results


def _validate_result(r: dict) -> PoCResult:
    """Validate and normalize a result dict."""
    return PoCResult(
        scenario_name=r.get("scenario_name", "unknown"),
        status=r.get("status", "error"),
        output=str(r.get("output", ""))[:2000],  # Cap output length
        error_message=r.get("error_message"),
        duration_seconds=float(r.get("duration_seconds", 0)),
    )


def _build_user_message(state: PoCState) -> str:
    """Build the user message for the PoC execute agent."""
    parts = []

    clone_path = state.get("local_clone_path", "")
    project_name = state.get("project_name", "unknown")

    parts.append(f"Execute the PoC test plan for project: {project_name}")
    parts.append(f"Repository location: {clone_path}")
    parts.append("")

    # Include PoC plan
    poc_plan = state.get("poc_plan", "")
    if poc_plan:
        parts.append("## PoC Plan")
        parts.append(poc_plan[:5000])  # Cap to avoid context overflow
        parts.append("")

    # Include structured scenarios
    scenarios = state.get("poc_scenarios", [])
    if scenarios:
        parts.append("## Test Scenarios (structured)")
        for s in scenarios:
            parts.append(f"### {s.get('name', '?')}")
            parts.append(f"- Description: {s.get('description', '')}")
            parts.append(f"- Type: {s.get('type', 'http')}")
            if s.get("endpoint"):
                parts.append(f"- Endpoint: {s['endpoint']}")
            if s.get("input_data"):
                parts.append(f"- Input: {s['input_data']}")
            parts.append(f"- Expected: {s.get('expected_behavior', '')}")
            parts.append(f"- Timeout: {s.get('timeout_seconds', 30)}s")
            parts.append("")

    # Include deployment info
    routes = state.get("routes", [])
    if routes:
        parts.append("## Service Routes / URLs")
        for route in routes:
            parts.append(f"- {route}")
        parts.append("")

    deployed = state.get("deployed_resources", [])
    if deployed:
        parts.append("## Deployed Resources")
        for resource in deployed:
            parts.append(f"- {resource}")
        parts.append("")

    # Namespace info
    namespace = f"poc-{project_name}"
    parts.append(f"## Kubernetes Namespace: {namespace}")
    parts.append("")

    parts.append("## Instructions")
    parts.append(
        f"1. Write the test script to {clone_path}/poc_test.py\n"
        f"2. Execute it using the run_script tool, passing the service URL as an argument\n"
        f"3. If the service URL is from routes above, use the first HTTP URL\n"
        f"4. If tests fail, use kubectl_get and kubectl_logs to debug\n"
        f"5. Report the results as structured JSON\n"
    )
    parts.append(f"All file paths should be absolute, starting with {clone_path}.")

    return "\n".join(parts)


async def poc_execute_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Generate and execute PoC test scripts.

    This is a LangGraph node function. It runs after successful deployment
    and exercises the deployed service according to the PoC plan.

    Args:
        state: Current pipeline state with deployment results populated.
        llm: Optional LLM override (for testing).

    Returns:
        Partial state update with PoC execution results.
    """
    project_name = state.get("project_name", "unknown")
    clone_path = state.get("local_clone_path", "")

    logger.info("Starting PoC execution for %s", project_name)

    # Set up LLM
    if llm is None:
        llm = create_llm()

    # Load system prompt
    system_prompt = _load_system_prompt()

    # Create the ReAct agent
    agent = create_react_agent(
        model=llm,
        tools=POC_EXECUTE_TOOLS,
    )

    # Build user message
    user_message = _build_user_message(state)

    try:
        # Invoke the agent
        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ],
            }
        )

        # Extract the final AI message
        raw_output = _extract_final_ai_content(result["messages"])

        # Try to parse results from the agent output
        poc_results = _parse_poc_results(raw_output)

        # Also try to find results from tool call outputs (run_script output)
        if not poc_results:
            for msg in result["messages"]:
                if hasattr(msg, "content") and isinstance(msg.content, str):
                    if "EXIT_CODE:" in msg.content and "STDOUT:" in msg.content:
                        # This is a run_script output — extract stdout part
                        stdout_match = msg.content.split("STDOUT:\n", 1)
                        if len(stdout_match) > 1:
                            stdout = stdout_match[1].split("\n\nSTDERR:")[0]
                            poc_results = _parse_poc_results(stdout)
                            if poc_results:
                                break

        # Determine script path
        poc_script_path = str(Path(clone_path or ".") / "poc_test.py")

        logger.info(
            "PoC execution complete: %d results (%d pass, %d fail, %d error)",
            len(poc_results),
            sum(1 for r in poc_results if r.get("status") == "pass"),
            sum(1 for r in poc_results if r.get("status") == "fail"),
            sum(1 for r in poc_results if r.get("status") == "error"),
        )

        return {
            "current_phase": PoCPhase.POC_EXECUTE,
            "poc_results": poc_results,
            "poc_script_path": poc_script_path,
        }

    except Exception as e:
        logger.error("PoC execution failed: %s", e)
        return {
            "current_phase": PoCPhase.POC_EXECUTE,
            "poc_results": [
                PoCResult(
                    scenario_name="execution-error",
                    status="error",
                    output="",
                    error_message=f"PoC execution agent failed: {e}",
                    duration_seconds=0,
                )
            ],
            "poc_script_path": "",
            "error": f"PoC execution failed: {e}",
        }
