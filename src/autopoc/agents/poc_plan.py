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
from autopoc.state import PoCInfrastructure, PoCScenario, PoCState
from autopoc.tools.file_tools import list_files, read_file, search_files, write_file
from autopoc.tools.git_tools import commit_to_artifacts_branch

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

    The expected response format is: JSON first, then markdown plan.
    But we also handle the reverse order (markdown first, then JSON) for
    backward compatibility.
    """
    # Look for a markdown heading that indicates the plan start.
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

    # If the JSON came before the markdown (expected order), plan_text is
    # already clean — just the markdown from the heading onward.
    # If the JSON came after the markdown (legacy order), cut it off.
    cutoff_patterns = [
        '\n{"poc_type"',
        "\n```json",
        '\n```\n{"poc_type"',
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


def _normalize_sidecar(entry: dict | str) -> dict:
    """Normalize a sidecar entry from LLM output.

    The LLM sometimes returns bare image strings (e.g. ``"postgres:18-alpine"``)
    instead of ``{"name": "postgres", "image": "postgres:18-alpine"}``.
    """
    if isinstance(entry, str):
        # Derive a name from the image string (strip tag and registry prefix)
        name = entry.split("/")[-1].split(":")[0]
        return {"name": name, "image": entry}
    return entry


def _validate_infrastructure(infra: dict) -> PoCInfrastructure:
    """Validate and normalize an infrastructure dict from LLM output."""
    raw_sidecars = infra.get("sidecar_containers", [])
    sidecars = [_normalize_sidecar(s) for s in raw_sidecars]

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
        sidecar_containers=sidecars,
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


def _build_user_message(state: PoCState, *, include_tool_instructions: bool = True) -> str:
    """Build the user message for the PoC plan agent.

    Args:
        state: Current pipeline state.
        include_tool_instructions: If True, include instructions about using tools.
            Set to False for the one-shot (no-tools) phase.
    """
    parts = []

    project_name = state.get("project_name", "unknown")
    clone_path = state.get("local_clone_path", "")

    parts.append("Analyze this project and create a PoC plan.\n")
    parts.append(f"Project name: {project_name}")
    parts.append(f"Source URL: {state.get('source_repo_url', '')}")
    parts.append(f"Repository cloned at: {clone_path}")
    parts.append("")

    # Include repo digest (pre-generated summary of the repo)
    repo_digest = state.get("repo_digest", "")
    if repo_digest:
        parts.append("## Repository Digest (pre-generated)")
        parts.append(repo_digest)
        parts.append("")

    # Include intake results
    repo_summary = state.get("repo_summary", "")
    if repo_summary:
        parts.append("## Repository Summary (from intake analysis)")
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
                parts.append("  - **ML workload: yes**")
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
        parts.append("## Existing Deployment Artifacts")
        parts.append(", ".join(existing))
        parts.append("")

    if include_tool_instructions:
        parts.append("## Instructions")
        parts.append(
            f"Use the tools to examine the repository at {clone_path}. "
            f"Read key files (README, dependency files, main source files) to understand "
            f"the project deeply. Then write a poc-plan.md file to {clone_path}/poc-plan.md "
            f"and respond with the structured JSON output as described in your system prompt."
        )
        parts.append("")
        parts.append(f"All tool calls should use absolute paths starting with {clone_path}.")
    else:
        parts.append("## Instructions")
        parts.append(
            "Based on the repository digest and intake results above, produce:\n"
            "1. A poc-plan.md in markdown format (include it in your response)\n"
            "2. The structured JSON output as described in your system prompt\n\n"
            "You have all the information you need. Produce your output directly."
        )

    return "\n".join(parts)


def _process_poc_plan_output(
    raw_output: str,
    clone_path: str,
    messages: list | None = None,
) -> tuple[dict, list, PoCInfrastructure, list[str], str, str | None]:
    """Process LLM output into validated poc_plan results.

    Returns (parsed, scenarios, infrastructure, poc_components, poc_plan_content, plan_error).
    Shared between one-shot and fallback phases.
    """
    # Also try all AI content if messages provided (ReAct fallback)
    all_ai_content = ""
    if messages:
        all_ai_content = _collect_all_ai_content(messages)

    # Parse the structured JSON output
    parsed = _parse_poc_plan_output(raw_output)
    if not parsed.get("scenarios") and all_ai_content and all_ai_content != raw_output:
        parsed_alt = _parse_poc_plan_output(all_ai_content)
        if parsed_alt.get("scenarios"):
            parsed = parsed_alt

    scenarios = [_validate_scenario(s) for s in parsed.get("scenarios", [])]
    infrastructure = _validate_infrastructure(parsed.get("infrastructure", {}))
    poc_components = parsed.get("poc_components", [])

    # Extract/write poc-plan.md
    poc_plan_path = str(Path(clone_path or ".") / "poc-plan.md")
    poc_plan_content = ""
    text_to_search = all_ai_content if all_ai_content else raw_output

    try:
        poc_plan_file = Path(poc_plan_path)
        if poc_plan_file.exists():
            poc_plan_content = poc_plan_file.read_text(encoding="utf-8")
            logger.info("PoC plan read from %s (%d chars)", poc_plan_path, len(poc_plan_content))
        else:
            # Try to extract from tool calls (ReAct fallback)
            if messages:
                poc_plan_content = _extract_poc_plan_from_tool_calls(messages, poc_plan_path)

            # Try to extract from response text
            if not poc_plan_content:
                poc_plan_content = _extract_markdown_plan_from_response(text_to_search)

            # Write if we found content
            if poc_plan_content:
                try:
                    poc_plan_file.parent.mkdir(parents=True, exist_ok=True)
                    poc_plan_file.write_text(poc_plan_content, encoding="utf-8")
                    logger.info("Wrote poc-plan.md (%d chars)", len(poc_plan_content))
                except Exception as e:
                    logger.warning("Failed to write poc-plan.md: %s", e)
            else:
                logger.warning("Could not extract poc-plan.md content")
                poc_plan_content = parsed.get("poc_plan_summary", "")
    except Exception as e:
        logger.warning("Error processing poc-plan.md: %s", e)
        poc_plan_content = parsed.get("poc_plan_summary", "")

    # Detect failure
    parse_failed = parsed.get("_parse_failed", False)
    plan_error = None
    if parse_failed:
        plan_error = (
            "PoC plan agent failed to produce valid JSON output. "
            "The pipeline cannot proceed with default/fallback values."
        )
        logger.error("PoC plan failed: %s", plan_error)
    elif not scenarios:
        logger.warning("PoC plan produced 0 test scenarios — downstream testing will be limited")

    return parsed, scenarios, infrastructure, poc_components, poc_plan_content, plan_error


def _extract_llm_text(response) -> str:
    """Extract plain text from an LLM response, handling multi-part content."""
    raw = response.content
    if isinstance(raw, list):
        return "".join(
            part["text"] if isinstance(part, dict) and "text" in part else str(part) for part in raw
        )
    return raw


async def _generate_markdown_plan(
    llm: BaseChatModel,
    state: PoCState,
    parsed_json: dict,
    clone_path: str,
) -> str:
    """Generate the poc-plan.md markdown via a dedicated LLM call.

    This is a separate call from the JSON-generation step so that each call
    gets the full output-token budget.  The JSON (already parsed) is fed back
    as context so the markdown is consistent.
    """
    project_name = state.get("project_name", "unknown")
    json_block = json.dumps(parsed_json, indent=2)

    user_parts = [
        f"Generate a detailed poc-plan.md for the project **{project_name}**.\n",
        "The structured JSON analysis has already been completed. "
        "Use it as the authoritative source for your markdown plan:\n",
        f"```json\n{json_block}\n```\n",
    ]

    # Include repo summary for extra context
    repo_summary = state.get("repo_summary", "")
    if repo_summary:
        user_parts.append("## Repository Summary")
        user_parts.append(repo_summary)
        user_parts.append("")

    user_parts.append(
        "Produce ONLY the full poc-plan.md markdown content (starting with "
        f"`# PoC Plan: {project_name}`). Follow the poc-plan.md template from "
        "your system prompt. Do NOT repeat the JSON."
    )

    system_msg = (
        "You are a technical writer producing a PoC plan document. "
        "You will be given a completed JSON analysis of a project. "
        "Your job is to produce the full poc-plan.md markdown document based on "
        "that JSON. Follow the template structure: Project Classification, "
        "PoC Objectives, Infrastructure Requirements, Test Scenarios, "
        "Dockerfile Considerations, and Deployment Considerations. "
        "Output ONLY the markdown — no JSON, no commentary."
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=system_msg),
            HumanMessage(content="\n".join(user_parts)),
        ]
    )

    md_text = _extract_llm_text(response).strip()

    # Strip any accidental markdown fences wrapping the whole response
    if md_text.startswith("```markdown"):
        md_text = md_text[len("```markdown") :].strip()
    if md_text.startswith("```"):
        md_text = md_text[3:].strip()
    if md_text.endswith("```"):
        md_text = md_text[:-3].strip()

    logger.info("Generated poc-plan.md via dedicated LLM call (%d chars)", len(md_text))
    return md_text


async def poc_plan_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Generate a PoC plan for the repository.

    Three-phase approach:
    - Phase 1a: One-shot LLM call to produce the structured JSON (no tools).
    - Phase 1b: One-shot LLM call to produce the poc-plan.md markdown, fed
      with the JSON from phase 1a.
    - Phase 2 (fallback): ReAct agent with file tools, only if phase 1a
      fails to produce scenarios.

    Splitting JSON and markdown into separate calls avoids output-token
    truncation that previously caused both outputs to be cut short.

    This is a LangGraph node function. It runs in parallel with the fork agent.

    Args:
        state: Current pipeline state with intake results populated.
        llm: Optional LLM override (for testing). Defaults to ChatAnthropic.

    Returns:
        Partial state update with PoC plan results.
    """
    project_name = state.get("project_name", "unknown")
    clone_path = state.get("local_clone_path", "")

    logger.info("Starting PoC plan generation for %s", project_name)

    if llm is None:
        llm = create_llm()

    system_prompt = _load_system_prompt()

    # -------------------------------------------------------------------------
    # Phase 1a: One-shot LLM call for structured JSON (no tools)
    # -------------------------------------------------------------------------
    user_message = _build_user_message(state, include_tool_instructions=False)

    logger.info("Phase 1a: one-shot PoC plan — JSON only (no tools)")
    response = await llm.ainvoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
    )

    raw_output = _extract_llm_text(response)

    parsed, scenarios, infrastructure, poc_components, poc_plan_content, plan_error = (
        _process_poc_plan_output(raw_output, clone_path or ".")
    )

    poc_type = parsed.get("poc_type", "web-app")

    # If phase 1a produced valid JSON with scenarios, generate the markdown
    if scenarios and not plan_error:
        logger.info(
            "Phase 1a succeeded: type=%s, %d scenarios, poc_components=%s, profile=%s",
            poc_type,
            len(scenarios),
            poc_components,
            infrastructure.get("resource_profile", "unknown"),
        )

        # -----------------------------------------------------------------
        # Phase 1b: Dedicated LLM call for poc-plan.md markdown
        # -----------------------------------------------------------------
        # If phase 1a already yielded usable markdown (>200 chars with a
        # heading), keep it. Otherwise generate it in a separate call.
        if len(poc_plan_content) < 200 or "## " not in poc_plan_content:
            logger.info("Phase 1b: generating poc-plan.md via dedicated LLM call")
            try:
                markdown_llm = create_llm()
                poc_plan_content = await _generate_markdown_plan(
                    markdown_llm, state, parsed, clone_path
                )
            except Exception as e:
                logger.warning("Phase 1b markdown generation failed: %s", e)
                # Fall back to whatever we got from phase 1a (may be partial)
                if not poc_plan_content:
                    poc_plan_content = parsed.get("poc_plan_summary", "")
        else:
            logger.info(
                "Phase 1a already produced adequate markdown (%d chars), skipping phase 1b",
                len(poc_plan_content),
            )

        # Write poc-plan.md to disk
        poc_plan_path = Path(clone_path or ".") / "poc-plan.md"
        if poc_plan_content:
            try:
                poc_plan_path.parent.mkdir(parents=True, exist_ok=True)
                poc_plan_path.write_text(poc_plan_content, encoding="utf-8")
                logger.info("Wrote poc-plan.md (%d chars)", len(poc_plan_content))
            except Exception as e:
                logger.warning("Failed to write poc-plan.md: %s", e)

        # Commit poc-plan.md to a dedicated branch and push to GitLab
        if clone_path and poc_plan_content:
            commit_to_artifacts_branch(
                clone_path,
                files=["poc-plan.md"],
                message="Add PoC plan (poc-plan.md)",
            )

        return {
            "poc_plan": poc_plan_content,
            "poc_plan_path": str(poc_plan_path),
            "poc_plan_error": None,
            "poc_components": poc_components,
            "poc_scenarios": scenarios,
            "poc_infrastructure": infrastructure,
            "poc_type": poc_type,
        }

    # -------------------------------------------------------------------------
    # Phase 2: ReAct fallback with file tools
    # Only triggered when phase 1a didn't produce scenarios.
    # -------------------------------------------------------------------------
    logger.warning(
        "Phase 1a produced %d scenarios (parse_failed=%s). Falling back to ReAct agent.",
        len(scenarios),
        bool(plan_error),
    )

    # Fresh LLM instance to avoid context carryover from phase 1a
    fallback_llm = create_llm()

    agent = create_react_agent(
        model=fallback_llm,
        tools=POC_PLAN_TOOLS,
        pre_model_hook=make_context_trimmer(),
    )

    # Build user message with tool instructions + phase 1a context
    fallback_message = _build_user_message(state, include_tool_instructions=True)

    # Include phase 1a's partial result to avoid re-doing work
    if not plan_error and parsed.get("poc_type"):
        fallback_message += (
            f"\n\n## Previous Analysis Attempt\n"
            f"A previous analysis produced this partial result (missing test scenarios):\n"
            f"```json\n{json.dumps(parsed, indent=2)}\n```\n\n"
            f"Please complete this by adding concrete test scenarios. "
            f"Read specific source files if needed to determine how to test the application."
        )

    try:
        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=fallback_message),
                ],
            },
            config={"recursion_limit": 60},
        )

        raw_output_2 = _extract_final_ai_content(result["messages"])

        (
            parsed_2,
            scenarios_2,
            infrastructure_2,
            poc_components_2,
            poc_plan_content_2,
            plan_error_2,
        ) = _process_poc_plan_output(raw_output_2, clone_path or ".", result["messages"])

        # Use phase 2 results if better, otherwise keep phase 1a
        if scenarios_2 or (not scenarios and not plan_error_2):
            scenarios = scenarios_2
            infrastructure = infrastructure_2
            poc_components = poc_components_2 or poc_components
            poc_plan_content = poc_plan_content_2 or poc_plan_content
            plan_error = plan_error_2
            poc_type = parsed_2.get("poc_type", poc_type)

    except Exception as e:
        logger.error("Phase 2 (ReAct fallback) failed: %s", e)
        # Keep phase 1a results (possibly partial) rather than failing completely
        if not plan_error:
            plan_error = f"ReAct fallback failed: {e}"

    # If phase 2 produced JSON but markdown is still inadequate, try phase 1b
    if (
        not plan_error
        and scenarios
        and (len(poc_plan_content) < 200 or "## " not in poc_plan_content)
    ):
        logger.info("Phase 2 JSON ok but markdown inadequate; generating markdown separately")
        try:
            md_llm = create_llm()
            final_parsed = parsed_2 if scenarios_2 else parsed
            poc_plan_content = await _generate_markdown_plan(
                md_llm, state, final_parsed, clone_path
            )
        except Exception as e:
            logger.warning("Post-phase-2 markdown generation failed: %s", e)

    # Write poc-plan.md to disk (if we have content and it wasn't already written)
    poc_plan_path = Path(clone_path or ".") / "poc-plan.md"
    if poc_plan_content and not poc_plan_path.exists():
        try:
            poc_plan_path.parent.mkdir(parents=True, exist_ok=True)
            poc_plan_path.write_text(poc_plan_content, encoding="utf-8")
            logger.info("Wrote poc-plan.md (%d chars)", len(poc_plan_content))
        except Exception as e:
            logger.warning("Failed to write poc-plan.md: %s", e)

    # Commit poc-plan.md to a dedicated branch and push to GitLab
    if clone_path and poc_plan_content:
        commit_to_artifacts_branch(
            clone_path,
            files=["poc-plan.md"],
            message="Add PoC plan (poc-plan.md)",
        )

    logger.info(
        "PoC plan complete: type=%s, %d scenarios, profile=%s, error=%s",
        poc_type,
        len(scenarios),
        infrastructure.get("resource_profile", "unknown"),
        "yes" if plan_error else "no",
    )

    return {
        "poc_plan": poc_plan_content,
        "poc_plan_path": str(poc_plan_path),
        "poc_plan_error": plan_error,
        "poc_components": poc_components,
        "poc_scenarios": scenarios,
        "poc_infrastructure": infrastructure,
        "poc_type": poc_type,
    }
