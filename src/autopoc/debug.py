"""Debug utilities for capturing LLM responses that failed to parse.

When verbose/debug mode is enabled, failed LLM response parses are written
to a debug directory. At the end of the run, the CLI prints their contents
so operators can diagnose model output issues (e.g. when switching from
Claude to a self-hosted model like Qwen).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level state: debug dump directory (set by CLI at startup)
_debug_dir: Path | None = None
_dump_files: list[Path] = []


def init_debug_dir(work_dir: str) -> Path:
    """Initialize the debug dump directory for this run.

    Args:
        work_dir: Base working directory (e.g. /workspace or /tmp/autopoc).

    Returns:
        Path to the debug directory.
    """
    global _debug_dir, _dump_files
    _debug_dir = Path(work_dir) / "debug" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    _debug_dir.mkdir(parents=True, exist_ok=True)
    _dump_files = []
    return _debug_dir


def is_debug_enabled() -> bool:
    """Check if debug mode is active (debug dir was initialized)."""
    return _debug_dir is not None


def dump_llm_response(
    agent_name: str,
    context: str,
    raw_response: str,
    *,
    component: str | None = None,
) -> Path | None:
    """Write a failed-to-parse LLM response to the debug directory.

    Args:
        agent_name: Name of the agent (e.g. "containerize", "intake").
        context: What was being parsed (e.g. "JSON output", "PoC plan").
        raw_response: The full raw LLM response text.
        component: Optional component name for per-component dumps.

    Returns:
        Path to the dump file, or None if debug is not enabled.
    """
    if _debug_dir is None:
        return None

    # Build filename: agent_component_timestamp.txt
    parts = [agent_name]
    if component:
        parts.append(component)
    timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
    parts.append(timestamp)
    filename = "_".join(parts) + ".txt"

    dump_path = _debug_dir / filename
    try:
        header = (
            f"Agent: {agent_name}\n"
            f"Context: {context}\n"
            f"Component: {component or 'n/a'}\n"
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
            f"Response length: {len(raw_response)} chars\n"
            f"{'=' * 72}\n\n"
        )
        dump_path.write_text(header + raw_response, encoding="utf-8")
        _dump_files.append(dump_path)
        logger.debug("Dumped LLM response to %s", dump_path)
        return dump_path
    except Exception as e:
        logger.warning("Failed to write debug dump: %s", e)
        return None


def get_dump_files() -> list[Path]:
    """Return list of all debug dump files from this run."""
    return list(_dump_files)


def get_debug_dir() -> Path | None:
    """Return the debug directory path, or None if not initialized."""
    return _debug_dir
