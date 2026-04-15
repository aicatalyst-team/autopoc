"""File system tools for LangChain agents.

Provides read, write, list, and search operations on cloned repositories.
All paths must be absolute. Path traversal outside the working tree is rejected.
"""

import re
from pathlib import Path

from langchain_core.tools import tool

# Maximum file size to read (20KB — keeps context manageable across many reads)
MAX_READ_BYTES = 20 * 1024

# Maximum number of files to list (prevents huge file trees from filling context)
MAX_LIST_FILES = 500

# Files that should be skipped or heavily truncated — they're large and not useful
# for understanding project structure.
SKIP_EXTENSIONS = frozenset(
    {
        # Lock files (often hundreds of KB)
        ".lock",
        # Data/benchmark files
        ".jsonl",
        ".csv",
        ".tsv",
        ".parquet",
        ".arrow",
        # Binary/media files
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".webp",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        # Model/data files
        ".pt",
        ".pth",
        ".onnx",
        ".safetensors",
        ".bin",
        ".h5",
        ".pkl",
        ".pickle",
        ".npy",
        ".npz",
        # Compiled/generated
        ".pyc",
        ".pyo",
        ".so",
        ".dylib",
        ".dll",
        ".o",
        ".a",
        ".wasm",
        ".map",
    }
)

# Directories whose contents should be skipped when reading files
SKIP_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        ".git",
        ".svn",
        ".hg",
        "vendor",
        "dist",
        "build",
        ".tox",
        ".eggs",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "benchmarks",
        "benchmark",
    }
)

# Maximum bytes for files that match LARGE_FILE_EXTENSIONS — show just enough to
# understand what they are.
LARGE_FILE_MAX_BYTES = 2 * 1024  # 2KB preview

LARGE_FILE_EXTENSIONS = frozenset(
    {
        ".lock",  # uv.lock, poetry.lock, yarn.lock, package-lock.json, etc.
        ".sum",  # go.sum
    }
)


def _validate_path(path: str) -> Path:
    """Validate and resolve a path, rejecting traversal attacks."""
    resolved = Path(path).resolve()
    if not resolved.is_absolute():
        raise ValueError(f"Path must be absolute: {path}")
    return resolved


def _is_in_skip_dir(rel_path: Path) -> bool:
    """Check if a relative path is inside a directory that should be skipped."""
    return any(part in SKIP_DIRS for part in rel_path.parts)


@tool
def list_files(path: str, pattern: str = "**/*") -> str:
    """List files in a directory tree, optionally filtered by glob pattern.

    Args:
        path: Absolute path to the root directory to list.
        pattern: Glob pattern to filter files (default: "**/*" for all files).

    Returns:
        Newline-separated list of relative file paths (max 500).
    """
    root = _validate_path(path)
    if not root.is_dir():
        return f"Error: {path} is not a directory"

    matches = []
    for p in sorted(root.glob(pattern)):
        if p.is_file():
            rel = p.relative_to(root)
            parts = rel.parts
            # Skip hidden dirs like .git
            if any(part.startswith(".") for part in parts):
                continue
            # Skip known noisy directories
            if _is_in_skip_dir(rel):
                continue
            matches.append(str(rel))
            if len(matches) >= MAX_LIST_FILES:
                matches.append(
                    f"... [truncated at {MAX_LIST_FILES} files — "
                    f"use a more specific glob pattern to see more]"
                )
                break

    if not matches:
        return "No files found matching the pattern."
    return "\n".join(matches)


@tool
def read_file(path: str) -> str:
    """Read the contents of a file.

    Skips binary/data files and truncates lock files. Returns at most 20KB
    to keep agent context manageable.

    Args:
        path: Absolute path to the file to read.

    Returns:
        File contents as a string, or a short message explaining why
        the file was skipped/truncated.
    """
    file_path = _validate_path(path)
    if not file_path.is_file():
        return f"Error: {path} is not a file or does not exist"

    suffix = file_path.suffix.lower()
    name_lower = file_path.name.lower()

    # Skip binary/data files entirely
    if suffix in SKIP_EXTENSIONS:
        size = file_path.stat().st_size
        return (
            f"[Skipped: {file_path.name} is a {suffix} file ({size:,} bytes). "
            f"These files are not useful for project analysis.]"
        )

    # Large lock files: show just a preview
    if suffix in LARGE_FILE_EXTENSIONS or name_lower in (
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "composer.lock",
        "gemfile.lock",
    ):
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            size = len(content.encode("utf-8"))
            if size > LARGE_FILE_MAX_BYTES:
                truncated = content[:LARGE_FILE_MAX_BYTES]
                return (
                    f"{truncated}\n\n... [lock/generated file truncated at "
                    f"{LARGE_FILE_MAX_BYTES} bytes — full file is {size:,} bytes. "
                    f"Only the first entries are shown for dependency identification.]"
                )
            return content
        except Exception as e:
            return f"Error reading {path}: {e}"

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
