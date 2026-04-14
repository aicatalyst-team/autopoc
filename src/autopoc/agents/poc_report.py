"""PoC Report agent — generates a comprehensive PoC report.

Synthesizes all pipeline results into a structured markdown report
covering project analysis, infrastructure deployed, test results,
and recommendations for production readiness.
"""

import json
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from autopoc.llm import create_llm
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.file_tools import read_file, write_file

logger = logging.getLogger(__name__)


# Tools available to the PoC report agent
POC_REPORT_TOOLS = [write_file, read_file]


def _load_system_prompt() -> str:
    """Load the PoC report system prompt from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "poc_report.md"
    return prompt_path.read_text(encoding="utf-8")


def _build_user_message(state: PoCState) -> str:
    """Build the user message for the PoC report agent with all pipeline data."""
    parts = []

    clone_path = state.get("local_clone_path", "")
    project_name = state.get("project_name", "unknown")

    parts.append(f"Generate a comprehensive PoC report for project: {project_name}")
    parts.append(f"Repository location: {clone_path}")
    parts.append(f"Source URL: {state.get('source_repo_url', '')}")
    parts.append("")

    # --- Project Analysis ---
    parts.append("## Project Analysis Data")
    repo_summary = state.get("repo_summary", "")
    if repo_summary:
        parts.append(f"**Repository Summary:** {repo_summary}")
        parts.append("")

    poc_type = state.get("poc_type", "unknown")
    parts.append(f"**PoC Type:** {poc_type}")
    parts.append("")

    components = state.get("components", [])
    if components:
        parts.append("**Components:**")
        parts.append("| Name | Language | Build System | ML Workload | Port |")
        parts.append("|------|----------|-------------|-------------|------|")
        for comp in components:
            parts.append(
                f"| {comp.get('name', '?')} | {comp.get('language', '?')} "
                f"| {comp.get('build_system', '?')} "
                f"| {'Yes' if comp.get('is_ml_workload') else 'No'} "
                f"| {comp.get('port', '-')} |"
            )
        parts.append("")

    # --- PoC Plan ---
    parts.append("## PoC Plan Data")
    poc_plan = state.get("poc_plan", "")
    if poc_plan:
        # Include first 3000 chars to avoid context overflow
        parts.append(poc_plan[:3000])
        if len(poc_plan) > 3000:
            parts.append("... (truncated)")
        parts.append("")

    poc_infrastructure = state.get("poc_infrastructure", {})
    if poc_infrastructure:
        parts.append("**Infrastructure Requirements:**")
        parts.append(f"```json\n{json.dumps(poc_infrastructure, indent=2)}\n```")
        parts.append("")

    scenarios = state.get("poc_scenarios", [])
    if scenarios:
        parts.append(f"**Planned Scenarios:** {len(scenarios)}")
        for s in scenarios:
            parts.append(f"- {s.get('name', '?')}: {s.get('description', '')}")
        parts.append("")

    # --- Build Data ---
    parts.append("## Build Data")
    built_images = state.get("built_images", [])
    if built_images:
        parts.append("**Built Images:**")
        for img in built_images:
            parts.append(f"- `{img}`")
    else:
        parts.append("No images were built.")
    build_retries = state.get("build_retries", 0)
    parts.append(f"**Build Retries:** {build_retries}")
    parts.append("")

    # --- Deploy Data ---
    parts.append("## Deploy Data")
    deployed_resources = state.get("deployed_resources", [])
    if deployed_resources:
        parts.append("**Deployed Resources:**")
        for resource in deployed_resources:
            parts.append(f"- `{resource}`")
    else:
        parts.append("No resources were deployed.")

    routes = state.get("routes", [])
    if routes:
        parts.append("**Routes / URLs:**")
        for route in routes:
            parts.append(f"- `{route}`")
    else:
        parts.append("No routes were created.")

    deploy_retries = state.get("deploy_retries", 0)
    parts.append(f"**Deploy Retries:** {deploy_retries}")
    parts.append("")

    # --- PoC Execution Results ---
    parts.append("## PoC Execution Results")
    poc_results = state.get("poc_results", [])
    if poc_results:
        parts.append("| Scenario | Status | Duration | Details |")
        parts.append("|----------|--------|----------|---------|")
        for r in poc_results:
            status = r.get("status", "unknown")
            status_emoji = {"pass": "PASS", "fail": "FAIL", "error": "ERROR", "skip": "SKIP"}.get(
                status, status.upper()
            )
            error_msg = r.get("error_message", "")
            detail = error_msg if error_msg else r.get("output", "")[:100]
            parts.append(
                f"| {r.get('scenario_name', '?')} | {status_emoji} "
                f"| {r.get('duration_seconds', 0):.1f}s | {detail} |"
            )
        parts.append("")

        total = len(poc_results)
        passed = sum(1 for r in poc_results if r.get("status") == "pass")
        failed = sum(1 for r in poc_results if r.get("status") in ("fail", "error"))
        parts.append(f"**Summary:** {passed}/{total} passed, {failed}/{total} failed")
    else:
        parts.append("No test results available.")
    parts.append("")

    poc_script_path = state.get("poc_script_path", "")
    if poc_script_path:
        parts.append(f"**Test Script:** `{poc_script_path}`")
        parts.append("")

    # --- Errors ---
    error = state.get("error")
    if error:
        parts.append("## Errors Encountered")
        parts.append(f"```\n{error[:2000]}\n```")
        parts.append("")

    # --- GitLab ---
    gitlab_url = state.get("gitlab_repo_url", "")
    if gitlab_url:
        parts.append(f"## GitLab Repository")
        parts.append(f"`{gitlab_url}`")
        parts.append("")

    # --- Existing artifacts ---
    artifacts = []
    if state.get("has_helm_chart"):
        artifacts.append("Helm chart")
    if state.get("has_kustomize"):
        artifacts.append("Kustomize")
    if state.get("has_compose"):
        artifacts.append("Docker Compose")
    if state.get("existing_ci_cd"):
        artifacts.append(f"CI/CD ({state.get('existing_ci_cd')})")
    if artifacts:
        parts.append(f"**Existing Deployment Artifacts:** {', '.join(artifacts)}")
        parts.append("")

    # --- Instructions ---
    parts.append("## Instructions")
    parts.append(
        f"Write the PoC report to {clone_path}/poc-report.md using the write_file tool. "
        f"Include ALL the data above in the appropriate sections of the report. "
        f"Follow the structure defined in your system prompt."
    )

    return "\n".join(parts)


async def poc_report_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Generate a comprehensive PoC report.

    This is a LangGraph node function. It runs after PoC execution
    and synthesizes all pipeline results into a markdown report.

    Args:
        state: Current pipeline state with all results populated.
        llm: Optional LLM override (for testing).

    Returns:
        Partial state update with PoC report path.
    """
    project_name = state.get("project_name", "unknown")
    clone_path = state.get("local_clone_path", "")

    logger.info("Starting PoC report generation for %s", project_name)

    # Set up LLM
    if llm is None:
        llm = create_llm()

    # Load system prompt
    system_prompt = _load_system_prompt()

    # Create the ReAct agent
    agent = create_react_agent(
        model=llm,
        tools=POC_REPORT_TOOLS,
    )

    # Build user message
    user_message = _build_user_message(state)

    try:
        # Invoke the agent
        await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ],
            }
        )

        poc_report_path = str(Path(clone_path or ".") / "poc-report.md")

        # Verify the report was written
        report_file = Path(poc_report_path)
        if report_file.exists():
            report_size = report_file.stat().st_size
            logger.info("PoC report written to %s (%d bytes)", poc_report_path, report_size)
        else:
            logger.warning("PoC report was not written at %s", poc_report_path)

        return {
            "current_phase": PoCPhase.POC_REPORT,
            "poc_report_path": poc_report_path,
        }

    except Exception as e:
        logger.error("PoC report generation failed: %s", e)
        poc_report_path = str(Path(clone_path or ".") / "poc-report.md")
        return {
            "current_phase": PoCPhase.POC_REPORT,
            "poc_report_path": poc_report_path,
            "error": f"PoC report generation failed: {e}",
        }
