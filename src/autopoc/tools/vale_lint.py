"""Vale prose linting utility.

Provides ``run_vale`` for running Vale on a single file and returning
structured findings, plus ``_format_findings_for_llm`` for presenting
those findings as text suitable for an LLM prompt.

Vale availability is treated as optional: if the binary is not installed or
styles are not synced, linting is silently skipped with a warning log.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


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
