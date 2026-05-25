"""Vale prose linting utility with LLM revision loop.

Provides a shared ``vale_lint_and_revise`` function that any markdown-producing
agent can call after writing an artifact.  The function:

1. Runs ``vale --output=JSON`` on the file.
2. If findings exist, feeds them to the LLM with the original content and a
   system prompt instructing conservative, selective revision.
3. Re-runs Vale on the revised text.
4. Repeats up to ``max_vale_revisions`` times (configurable, default 3).

Vale availability is treated as optional: if the binary is not installed or
styles are not synced, linting is silently skipped with a warning log.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from autopoc.config import load_config

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


# ---------------------------------------------------------------------------
# Vale runner
# ---------------------------------------------------------------------------


def _vale_available() -> bool:
    """Check whether the ``vale`` binary is on PATH."""
    return shutil.which("vale") is not None


def run_vale(file_path: str | Path) -> list[dict]:
    """Run Vale on a single file and return structured findings.

    Each finding is a dict with keys: ``line``, ``severity``, ``message``,
    ``check``, and ``link``.

    Returns an empty list when:
    - Vale is not installed
    - The file does not exist
    - Vale exits with a non-parse error (e.g. missing styles)
    """
    file_path = Path(file_path)
    if not file_path.exists():
        logger.warning("Vale target does not exist: %s", file_path)
        return []

    if not _vale_available():
        logger.warning("vale binary not found on PATH — skipping prose lint")
        return []

    try:
        result = subprocess.run(
            ["vale", "--output=JSON", str(file_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        logger.warning("vale binary not found — skipping prose lint")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("vale timed out on %s — skipping", file_path)
        return []

    # Vale exits 0 for no findings, 1 for findings, 2 for errors.
    # Both 0 and 1 produce valid JSON on stdout.
    if result.returncode > 1:
        stderr = result.stderr.strip()
        logger.warning("vale exited with code %d: %s", result.returncode, stderr[:200])
        return []

    stdout = result.stdout.strip()
    if not stdout:
        return []

    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError:
        logger.warning("Failed to parse vale JSON output: %s", stdout[:200])
        return []

    # Vale JSON output is ``{ "file_path": [ {finding}, ... ] }``
    findings: list[dict] = []
    for _path, file_findings in raw.items():
        if not isinstance(file_findings, list):
            continue
        for f in file_findings:
            findings.append(
                {
                    "line": f.get("Line", 0),
                    "severity": f.get("Severity", "suggestion"),
                    "message": f.get("Message", ""),
                    "check": f.get("Check", ""),
                    "link": f.get("Link", ""),
                }
            )

    return findings


def _format_findings_for_llm(findings: list[dict]) -> str:
    """Format Vale findings into a concise text block for the LLM."""
    lines: list[str] = []
    for f in findings:
        severity = f["severity"].upper()
        line_num = f["line"]
        check = f["check"]
        message = f["message"]
        lines.append(f"  Line {line_num} [{severity}] ({check}): {message}")
    return "\n".join(lines)


def _load_revision_prompt() -> str:
    """Load the Vale revision system prompt."""
    prompt_path = _PROMPTS_DIR / "vale_revision.md"
    return prompt_path.read_text(encoding="utf-8")


def _extract_llm_text(response: object) -> str:
    """Extract plain text from an LLM response, handling multi-part content."""
    content = getattr(response, "content", "")
    if isinstance(content, list):
        return "".join(
            part["text"] if isinstance(part, dict) and "text" in part else str(part)
            for part in content
        )
    return str(content)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def vale_lint_and_revise(
    file_path: str | Path,
    llm: Runnable | BaseChatModel,
    *,
    max_revisions: int | None = None,
) -> tuple[str, list[dict]]:
    """Lint a markdown file with Vale and revise it using the LLM.

    Args:
        file_path: Path to the markdown file to lint.
        llm: LLM instance for generating revisions.
        max_revisions: Max revision passes. If None, reads from config.

    Returns:
        Tuple of (final_content, all_findings) where *all_findings* is the
        list of Vale findings from the **first** run (before any revision).
        This is stored in state for observability.
    """
    file_path = Path(file_path)

    if max_revisions is None:
        config = load_config()
        max_revisions = config.max_vale_revisions

    # Read the current file content
    if not file_path.exists():
        logger.warning("Cannot lint %s: file does not exist", file_path)
        return "", []

    content = file_path.read_text(encoding="utf-8")

    # First Vale run
    findings = run_vale(file_path)
    initial_findings = list(findings)  # snapshot for state

    if not findings:
        logger.info("Vale found no issues in %s", file_path)
        return content, []

    logger.info("Vale found %d issues in %s — starting revision loop", len(findings), file_path)

    system_prompt = _load_revision_prompt()

    for iteration in range(1, max_revisions + 1):
        findings_text = _format_findings_for_llm(findings)

        user_message = (
            f"## Original Markdown\n\n"
            f"```markdown\n{content}\n```\n\n"
            f"## Vale Findings ({len(findings)} issues)\n\n"
            f"{findings_text}\n\n"
            f"Produce the complete revised markdown. Output ONLY the revised "
            f"markdown content — no commentary, no code fences wrapping the "
            f"whole document."
        )

        try:
            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ]
            )
            revised = _extract_llm_text(response).strip()
        except Exception as e:
            logger.warning(
                "Vale revision LLM call failed (iteration %d/%d): %s",
                iteration,
                max_revisions,
                e,
            )
            break

        # Strip accidental wrapping fences
        if revised.startswith("```markdown"):
            revised = revised[len("```markdown") :].strip()
        if revised.startswith("```"):
            revised = revised[3:].strip()
        if revised.endswith("```"):
            revised = revised[:-3].strip()

        if not revised:
            logger.warning("LLM returned empty revision — keeping previous content")
            break

        # Basic validation: revised content should be at least 50% of original
        # to catch cases where the LLM truncates the document.
        if len(revised) < len(content) * 0.5:
            logger.warning(
                "Revised content suspiciously short (%d vs %d chars) — keeping previous",
                len(revised),
                len(content),
            )
            break

        # Accept the revision
        content = revised
        file_path.write_text(content, encoding="utf-8")

        # Re-run Vale on the revised content
        findings = run_vale(file_path)
        if not findings:
            logger.info(
                "All Vale issues resolved after %d revision(s) of %s",
                iteration,
                file_path,
            )
            break

        logger.info(
            "Vale still has %d issues after revision %d/%d of %s",
            len(findings),
            iteration,
            max_revisions,
            file_path,
        )

    return content, initial_findings
