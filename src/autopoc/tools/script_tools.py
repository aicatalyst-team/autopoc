"""Script execution tools for the PoC Execute agent.

Provides a safe way to execute Python test scripts with timeout and
output capture, for use by the LLM-powered PoC Execute agent.
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Raw output capture — records full subprocess output before truncation
# ---------------------------------------------------------------------------

MAX_SCENARIO_OUTPUT_BYTES = 102_400  # 100KB per stdout/stderr block


@dataclass
class RawRunRecord:
    """Raw output from a single run_script invocation."""

    script_path: str
    timestamp: str  # ISO 8601
    stdout_raw: str  # Full stdout (no truncation)
    stderr_raw: str  # Full stderr (no truncation)
    exit_code: int  # -1 for timeout
    duration_seconds: float
    timed_out: bool = False


# Module-level buffer — populated by run_script, consumed by poc_execute_agent
_raw_run_log: list[RawRunRecord] = []


def get_raw_run_log() -> list[RawRunRecord]:
    """Return and clear the raw run log buffer."""
    log = list(_raw_run_log)
    _raw_run_log.clear()
    return log


def clear_raw_run_log() -> None:
    """Clear the raw run log buffer (for test isolation)."""
    _raw_run_log.clear()


def truncate_output(text: str, max_bytes: int = MAX_SCENARIO_OUTPUT_BYTES) -> str:
    """Tail-truncate text to fit within *max_bytes* (UTF-8).

    If the text exceeds *max_bytes*, keep the **last** *max_bytes* bytes and
    prepend a truncation marker.  This preserves error messages which are
    typically at the end of output.

    Returns the text unchanged if it fits within the limit.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    total_size = len(encoded)
    # Take the tail, then decode safely (errors="ignore" drops split chars)
    tail = encoded[-max_bytes:].decode("utf-8", errors="ignore")

    marker = (
        f"... [truncated — showing last {max_bytes // 1024}KB "
        f"of {total_size // 1024}KB total] ...\n"
    )
    return marker + tail


@tool
def run_script(
    script_path: str,
    timeout: int = 300,
    script_args: str = "",
    **kwargs,
) -> str:
    """Execute a Python script and capture its output.

    Runs the script as a subprocess with timeout enforcement.
    Returns the combined stdout, stderr, and exit code.

    Args:
        script_path: Absolute path to the Python script to execute.
        timeout: Maximum execution time in seconds (default 300 = 5 minutes).
        script_args: Optional command-line arguments to pass to the script (space-separated).

    Returns:
        A structured string with exit code, stdout, and stderr.
    """
    path = Path(script_path)

    # Validate script exists
    if not path.exists():
        return f"ERROR: Script not found: {script_path}"

    if not path.is_file():
        return f"ERROR: Path is not a file: {script_path}"

    if not path.suffix == ".py":
        return f"ERROR: Not a Python script (expected .py extension): {script_path}"

    # Build command
    cmd = ["python3", str(path)]
    if script_args:
        cmd.extend(script_args.split())

    logger.info("Executing script: %s (timeout=%ds)", script_path, timeout)

    start_time = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(path.parent),
        )

        elapsed = round(time.monotonic() - start_time, 2)

        # Capture raw output BEFORE truncation
        _raw_run_log.append(
            RawRunRecord(
                script_path=str(path),
                timestamp=datetime.now(timezone.utc).isoformat(),
                stdout_raw=result.stdout or "",
                stderr_raw=result.stderr or "",
                exit_code=result.returncode,
                duration_seconds=elapsed,
            )
        )

        output_parts = [
            f"EXIT_CODE: {result.returncode}",
        ]

        if result.stdout:
            output_parts.append(f"STDOUT:\n{result.stdout}")
        else:
            output_parts.append("STDOUT: (empty)")

        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")
        else:
            output_parts.append("STDERR: (empty)")

        output = "\n\n".join(output_parts)

        # Truncate if too large (keep first 20k chars)
        if len(output) > 20000:
            output = output[:20000] + "\n\n... (output truncated at 20000 chars)"

        logger.info(
            "Script finished with exit code %d (%d chars output)",
            result.returncode,
            len(output),
        )

        return output

    except subprocess.TimeoutExpired:
        elapsed = round(time.monotonic() - start_time, 2)
        logger.warning("Script timed out after %ds: %s", timeout, script_path)

        # Capture timeout in raw log
        _raw_run_log.append(
            RawRunRecord(
                script_path=str(path),
                timestamp=datetime.now(timezone.utc).isoformat(),
                stdout_raw="",
                stderr_raw="",
                exit_code=-1,
                duration_seconds=elapsed,
                timed_out=True,
            )
        )

        return (
            f"EXIT_CODE: -1\n\n"
            f"ERROR: Script timed out after {timeout} seconds.\n"
            f"The script at {script_path} did not complete within the allowed time.\n"
            f"Consider increasing the timeout or checking if the script is hanging."
        )

    except PermissionError:
        logger.error("Permission denied executing script: %s", script_path)
        return f"ERROR: Permission denied executing script: {script_path}"

    except Exception as e:
        logger.error("Error executing script %s: %s", script_path, e)
        return f"ERROR: Failed to execute script: {e}"
