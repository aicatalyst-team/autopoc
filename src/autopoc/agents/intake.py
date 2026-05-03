"""Intake agent — analyzes a source repository to identify components and structure.

Uses a procedural repo digest + one-shot LLM call (no ReAct agent).
The repo is first summarized deterministically by repo_digest.py, then
the LLM analyzes the summary and produces structured JSON. This is
simpler, faster, cheaper, and more reliable than giving the LLM file
tools and letting it explore.
"""

import json
import logging
import re
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from autopoc.llm import create_llm
from autopoc.state import ComponentInfo, PoCPhase, PoCState
from autopoc.tools.git_tools import git_clone
from autopoc.tools.repo_digest import build_repo_digest

logger = logging.getLogger(__name__)

INTAKE_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "intake.md"


def _parse_intake_output(raw_output: str) -> dict:
    """Parse the JSON output from the intake LLM response.

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
        from autopoc.debug import dump_llm_response

        dump_llm_response("intake", f"JSON parse failure: {e}", raw_output)
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


async def _fix_component_paths(
    components: list[ComponentInfo],
    clone_path: Path,
    llm: BaseChatModel,
) -> list[ComponentInfo]:
    """Validate component source_dir paths and fix any that don't exist.

    For each component whose source_dir doesn't exist on disk, asks the LLM
    to identify the correct path from the actual directory listing.
    Components that can't be resolved are dropped with a warning.
    """
    valid = []
    for comp in components:
        source_dir = comp.get("source_dir", ".")
        comp_path = clone_path / source_dir if source_dir != "." else clone_path

        if comp_path.exists():
            valid.append(comp)
            continue

        comp_name = comp.get("name", "unknown")
        logger.warning(
            "Component '%s' has source_dir='%s' which does not exist on disk. "
            "Asking LLM to correct the path.",
            comp_name,
            source_dir,
        )

        # List actual directories (max 2 levels deep) for the LLM to pick from
        actual_dirs = sorted(
            str(p.relative_to(clone_path))
            for p in clone_path.rglob("*")
            if p.is_dir()
            and ".git" not in p.parts
            and "node_modules" not in p.parts
            and "__pycache__" not in p.parts
            and len(p.relative_to(clone_path).parts) <= 3
        )
        # Truncate to keep the prompt manageable
        if len(actual_dirs) > 100:
            actual_dirs = actual_dirs[:100]

        prompt = (
            f"The component '{comp_name}' (language: {comp.get('language', 'unknown')}) "
            f"was identified with source directory '{source_dir}', but that directory "
            f"does not exist in the repository.\n\n"
            f"Here are the actual directories in the repository:\n"
            f"{chr(10).join(actual_dirs)}\n\n"
            f"Which directory contains the source code for '{comp_name}'?\n"
            f"Reply with ONLY the directory path, nothing else. "
            f"If the component does not exist in this repository, reply with NONE."
        )

        try:
            response = await llm.ainvoke([
                SystemMessage(content="You are identifying source code directories in a repository. Reply with only the directory path."),
                HumanMessage(content=prompt),
            ])
            answer = response.content.strip()
            # Strip Qwen3 thinking tags (<think>...</think>)
            answer = re.sub(r"<think>.*?</think>\s*", "", answer, flags=re.DOTALL)
            answer = answer.strip().strip("`\"'")

            if answer.upper() == "NONE" or not answer:
                logger.warning(
                    "Component '%s' does not exist in the repository — dropping it",
                    comp_name,
                )
                continue

            # Verify the suggested path exists
            suggested_path = clone_path / answer
            if suggested_path.exists():
                logger.info(
                    "Corrected source_dir for '%s': '%s' → '%s'",
                    comp_name,
                    source_dir,
                    answer,
                )
                comp["source_dir"] = answer
                valid.append(comp)
            else:
                logger.warning(
                    "LLM suggested '%s' for component '%s' but it doesn't exist either — dropping",
                    answer,
                    comp_name,
                )
        except Exception as e:
            logger.warning(
                "Failed to correct path for component '%s': %s — dropping",
                comp_name,
                e,
            )

    if len(valid) < len(components):
        dropped = len(components) - len(valid)
        logger.info(
            "Dropped %d component(s) with invalid source paths, %d remaining",
            dropped,
            len(valid),
        )

    return valid


async def intake_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Analyze a source repository and populate state with component information.

    This is a LangGraph node function. It:
    1. Clones the repo (if not already cloned)
    2. Builds a procedural digest of the repo (no LLM)
    3. Sends the digest to the LLM for one-shot analysis
    4. Parses the JSON response

    No ReAct agent, no file tools, no compaction needed.

    Args:
        state: Current pipeline state with source_repo_url set.
        llm: Optional LLM override (for testing).

    Returns:
        Partial state update dict.
    """
    source_url = state.get("source_repo_url", "")
    project_name = state.get("project_name", "unknown")

    logger.info("Starting intake analysis for %s (%s)", project_name, source_url)

    # Clone the repository
    from autopoc.config import load_config

    config = load_config()
    clone_path = Path(config.work_dir) / project_name

    if not clone_path.exists() or not (clone_path / ".git").exists():
        clone_result = git_clone.invoke({"url": source_url, "dest": str(clone_path)})
        if clone_result.startswith("Error"):
            logger.error("Clone failed: %s", clone_result)
            return {
                "current_phase": PoCPhase.INTAKE,
                "error": f"Failed to clone repository: {clone_result}",
            }
        logger.info("Cloned repo to %s", clone_path)
    else:
        logger.info("Using existing clone at %s", clone_path)

    # Build repo digest (procedural — no LLM, no tools, fast)
    digest = build_repo_digest(str(clone_path))
    logger.info("Built repo digest: %d chars", len(digest))

    # Load system prompt
    system_prompt = INTAKE_PROMPT_PATH.read_text()

    # Set up LLM
    if llm is None:
        llm = create_llm()

    # One-shot LLM call — no ReAct agent, no tools
    user_message = (
        f"Project name: {project_name}\n"
        f"Source URL: {source_url}\n\n"
        f"Here is a pre-generated summary of the repository:\n\n"
        f"{digest}\n\n"
        f"Analyze this summary and produce your JSON output."
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
    )

    # Extract content from response
    raw_output = response.content
    if isinstance(raw_output, list):
        raw_output = "".join(
            part["text"] if isinstance(part, dict) and "text" in part else str(part)
            for part in raw_output
        )

    # Parse the structured output
    parsed = _parse_intake_output(raw_output)

    # Validate and build components list
    components = [_validate_component(comp) for comp in parsed.get("components", [])]

    # Verify each component's source_dir exists on disk.
    # If the LLM hallucinated a path, ask it to correct it.
    components = await _fix_component_paths(components, clone_path, llm)

    if not components:
        logger.error("Intake found 0 components — pipeline cannot proceed")
        return {
            "current_phase": PoCPhase.INTAKE,
            "local_clone_path": str(clone_path),
            "repo_digest": digest,
            "repo_summary": parsed.get("repo_summary", ""),
            "components": [],
            "has_helm_chart": parsed.get("has_helm_chart", False),
            "has_kustomize": parsed.get("has_kustomize", False),
            "has_compose": parsed.get("has_compose", False),
            "existing_ci_cd": parsed.get("existing_ci_cd"),
            "error": (
                "Intake analysis found 0 components. The repository may use an "
                "unsupported build system, or the LLM failed to parse the repo digest."
            ),
        }

    logger.info(
        "Intake complete: found %d component(s): %s",
        len(components),
        [c.get("name", "unknown") for c in components],
    )

    return {
        "current_phase": PoCPhase.INTAKE,
        "local_clone_path": str(clone_path),
        "repo_digest": digest,
        "repo_summary": parsed.get("repo_summary", ""),
        "components": components,
        "has_helm_chart": parsed.get("has_helm_chart", False),
        "has_kustomize": parsed.get("has_kustomize", False),
        "has_compose": parsed.get("has_compose", False),
        "existing_ci_cd": parsed.get("existing_ci_cd"),
    }
