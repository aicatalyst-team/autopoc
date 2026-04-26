"""PoC Report agent — generates a comprehensive PoC report.

Synthesizes all pipeline results into a structured markdown report
covering project analysis, infrastructure deployed, test results,
and recommendations for production readiness.

Non-agentic: uses a one-shot LLM call (no ReAct, no tools). All data
comes from the pipeline state. The LLM produces markdown which is
written to disk procedurally.
"""

import json
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from autopoc.llm import create_llm
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.git_tools import commit_to_artifacts_branch

logger = logging.getLogger(__name__)


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
            status_display = {
                "pass": "PASS",
                "fail": "FAIL",
                "error": "ERROR",
                "skip": "SKIP",
            }.get(status, status.upper())
            error_msg = r.get("error_message", "")
            detail = error_msg if error_msg else r.get("output", "")[:100]
            parts.append(
                f"| {r.get('scenario_name', '?')} | {status_display} "
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
        parts.append("## GitLab Repository")
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
        "Produce the PoC report as a complete markdown document. "
        "Include ALL the data above in the appropriate sections of the report. "
        "Follow the structure defined in your system prompt."
    )

    return "\n".join(parts)


def _strip_preamble(content: str) -> str:
    """Strip LLM preamble text that appears before the actual markdown report.

    LLMs sometimes prepend conversational text like "I'll generate a report..."
    before the actual markdown content. This function finds the first markdown
    heading (# ...) and discards everything before it.

    Also strips any trailing commentary after the report ends.
    """
    # Find the first markdown heading (line starting with #)
    lines = content.split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("#"):
            start_idx = i
            break

    if start_idx > 0:
        stripped = lines[:start_idx]
        logger.debug(
            "Stripped %d lines of LLM preamble from report: %s",
            start_idx,
            stripped[0][:80] if stripped else "",
        )

    return "\n".join(lines[start_idx:]).strip() + "\n"


async def poc_report_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Generate a comprehensive PoC report.

    Non-agentic: one-shot LLM call (no ReAct, no tools). All data comes from
    the pipeline state. The LLM produces markdown which is written to disk.

    Args:
        state: Current pipeline state with all results populated.
        llm: Optional LLM override (for testing).

    Returns:
        Partial state update with PoC report path.
    """
    project_name = state.get("project_name", "unknown")
    clone_path = state.get("local_clone_path", "")

    logger.info("Starting PoC report generation for %s", project_name)

    if llm is None:
        llm = create_llm()

    system_prompt = _load_system_prompt()
    user_message = _build_user_message(state)

    poc_report_path = str(Path(clone_path or ".") / "poc-report.md")

    try:
        # One-shot LLM call — no ReAct, no tools
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
        )

        report_content = response.content
        if isinstance(report_content, list):
            report_content = "".join(
                part["text"] if isinstance(part, dict) and "text" in part else str(part)
                for part in report_content
            )

        # Strip any LLM preamble before the actual markdown report.
        # The report should start with a markdown heading (# ...).
        report_content = _strip_preamble(report_content)

        # Write report to disk
        report_file = Path(poc_report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report_content, encoding="utf-8")
        logger.info("PoC report written to %s (%d chars)", poc_report_path, len(report_content))

        # Commit poc-report.md to the artifacts branch and push to GitLab
        if clone_path:
            commit_to_artifacts_branch(
                clone_path,
                files=["poc-report.md"],
                message="Add PoC report (poc-report.md)",
            )

        return {
            "current_phase": PoCPhase.POC_REPORT,
            "poc_report_path": poc_report_path,
        }

    except Exception as e:
        logger.error("PoC report generation failed: %s", e)
        return {
            "current_phase": PoCPhase.POC_REPORT,
            "poc_report_path": poc_report_path,
            "error": f"PoC report generation failed: {e}",
        }
