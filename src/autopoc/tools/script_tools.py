"""Script execution tools for the PoC Execute agent.

Provides a safe way to execute Python test scripts with timeout and
output capture, for use by the LLM-powered PoC Execute agent.
"""

import logging
import subprocess
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


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

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(path.parent),
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
        logger.warning("Script timed out after %ds: %s", timeout, script_path)
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
