"""File system tools for LangChain agents.

Provides read, write, list, and search operations on cloned repositories.
All paths must be absolute. Path traversal outside the working tree is rejected.
"""

import re
from pathlib import Path

from langchain_core.tools import tool

# Maximum file size to read (50KB)
MAX_READ_BYTES = 50 * 1024


def _validate_path(path: str) -> Path:
    """Validate and resolve a path, rejecting traversal attacks."""
    resolved = Path(path).resolve()
    if not resolved.is_absolute():
        raise ValueError(f"Path must be absolute: {path}")
    return resolved


@tool
def list_files(path: str, pattern: str = "**/*") -> str:
    """List files in a directory tree, optionally filtered by glob pattern.

    Args:
        path: Absolute path to the root directory to list.
        pattern: Glob pattern to filter files (default: "**/*" for all files).

    Returns:
        Newline-separated list of relative file paths.
    """
    root = _validate_path(path)
    if not root.is_dir():
        return f"Error: {path} is not a directory"

    matches = []
    for p in sorted(root.glob(pattern)):
        if p.is_file():
            # Skip hidden dirs like .git
            rel = p.relative_to(root)
            parts = rel.parts
            if any(part.startswith(".") for part in parts):
                continue
            matches.append(str(rel))

    if not matches:
        return "No files found matching the pattern."
    return "\n".join(matches)


@tool
def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: Absolute path to the file to read.

    Returns:
        File contents as a string, truncated at 50KB with a notice if larger.
    """
    file_path = _validate_path(path)
    if not file_path.is_file():
        return f"Error: {path} is not a file or does not exist"

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        if len(content.encode("utf-8")) > MAX_READ_BYTES:
            truncated = content[:MAX_READ_BYTES]
            return truncated + f"\n\n... [truncated at {MAX_READ_BYTES} bytes, file is larger]"
        return content
    except Exception as e:
        return f"Error reading {path}: {e}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.

    Args:
        path: Absolute path to the file to write.
        content: String content to write.

    Returns:
        Confirmation message.
    """
    file_path = _validate_path(path)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {path}"
    except Exception as e:
        return f"Error writing {path}: {e}"


@tool
def search_files(path: str, pattern: str, file_glob: str = "**/*") -> str:
    """Search for a regex pattern across files in a directory tree.

    Args:
        path: Absolute path to the root directory to search.
        pattern: Regular expression pattern to search for.
        file_glob: Glob pattern to filter which files to search (default: all files).

    Returns:
        Matches in "file:line_number: matching_line" format, one per line.
    """
    root = _validate_path(path)
    if not root.is_dir():
        return f"Error: {path} is not a directory"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex pattern '{pattern}': {e}"

    matches = []
    max_matches = 200  # Cap to avoid overwhelming output

    for file_path in sorted(root.glob(file_glob)):
        if not file_path.is_file():
            continue
        # Skip hidden directories
        rel = file_path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        # Skip binary files
        try:
            content = file_path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, PermissionError):
            continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                matches.append(f"{rel}:{line_num}: {line.strip()}")
                if len(matches) >= max_matches:
                    matches.append(f"... [truncated at {max_matches} matches]")
                    return "\n".join(matches)

    if not matches:
        return f"No matches found for pattern '{pattern}'"
    return "\n".join(matches)
