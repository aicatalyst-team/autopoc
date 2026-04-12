"""Git CLI tools for LangChain agents.

Provides clone, remote management, commit, push, and branch operations
by shelling out to the git CLI.
"""

import subprocess
from pathlib import Path

from langchain_core.tools import tool

# Timeout for git operations (seconds)
GIT_TIMEOUT = 120


def _run_git(
    args: list[str],
    cwd: str | None = None,
    timeout: int = GIT_TIMEOUT,
) -> str:
    """Run a git command and return its output.

    Args:
        args: Git command arguments (without 'git' prefix).
        cwd: Working directory for the command.
        timeout: Command timeout in seconds.

    Returns:
        Combined stdout on success.

    Raises:
        RuntimeError: If the git command fails.
    """
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            error_msg = stderr or stdout or f"git command failed with exit code {result.returncode}"
            raise RuntimeError(f"git {' '.join(args)}: {error_msg}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git {' '.join(args)}: timed out after {timeout}s")


@tool
def git_clone(url: str, dest: str) -> str:
    """Clone a git repository.

    Args:
        url: Repository URL to clone from.
        dest: Destination directory path.

    Returns:
        Path to the cloned repository.
    """
    dest_path = Path(dest).resolve()
    if dest_path.exists():
        return str(dest_path)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", url, str(dest_path)], timeout=300)
    return str(dest_path)


@tool
def git_add_remote(repo_path: str, name: str, url: str) -> str:
    """Add a remote to a git repository.

    Args:
        repo_path: Path to the local git repository.
        name: Name for the remote (e.g. "gitlab").
        url: Remote URL.

    Returns:
        Confirmation message.
    """
    # Check if remote already exists
    try:
        existing = _run_git(["remote", "get-url", name], cwd=repo_path)
        if existing != url:
            # If the remote URL has changed (e.g. new token generated for E2E tests), update it
            _run_git(["remote", "set-url", name, url], cwd=repo_path)
            return f"Updated remote '{name}' to new URL"
        return f"Remote '{name}' already exists with URL: {existing}"
    except RuntimeError:
        pass  # Remote doesn't exist, create it

    _run_git(["remote", "add", name, url], cwd=repo_path)
    return f"Added remote '{name}' -> {url}"


@tool
def git_push(repo_path: str, remote: str = "origin", ref: str = "main") -> str:
    """Push to a remote repository.

    Args:
        repo_path: Path to the local git repository.
        remote: Remote name to push to (default: "origin").
        ref: Branch name or ref to push, or "--all" for all branches,
             or "--tags" for all tags.

    Returns:
        Git push output.
    """
    args = ["push", remote]
    if ref in ("--all", "--tags"):
        args.append(ref)
    else:
        args.append(ref)

    output = _run_git(args, cwd=repo_path)
    return output or f"Pushed {ref} to {remote}"


@tool
def git_commit(
    repo_path: str,
    message: str,
    files: list[str] | None = None,
) -> str:
    """Stage files and create a commit.

    Args:
        repo_path: Path to the local git repository.
        message: Commit message.
        files: Specific files to stage. If None, stages all changes.

    Returns:
        Git commit output.
    """
    if files:
        for f in files:
            _run_git(["add", f], cwd=repo_path)
    else:
        _run_git(["add", "-A"], cwd=repo_path)

    output = _run_git(["commit", "-m", message], cwd=repo_path)
    return output


@tool
def git_checkout_branch(
    repo_path: str,
    branch: str,
    create: bool = False,
) -> str:
    """Checkout a branch, optionally creating it.

    Args:
        repo_path: Path to the local git repository.
        branch: Branch name.
        create: If True, create the branch if it doesn't exist.

    Returns:
        Git checkout output.
    """
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(branch)

    output = _run_git(args, cwd=repo_path)
    return output or f"Checked out branch '{branch}'"
