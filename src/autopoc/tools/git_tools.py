"""Git CLI tools for LangChain agents.

Provides clone, remote management, commit, push, and branch operations
by shelling out to the git CLI.
"""

import logging
import subprocess
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

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


# Public source code hosts that we must NEVER push to.
# Note: github.com is NOT in this list because when fork_target=github,
# we legitimately push to our GitHub fork. The fork agent ensures safety
# by removing the source remote entirely, so there is no path to push
# to the upstream repo.
_BLOCKED_PUSH_HOSTS = {"gitlab.com", "bitbucket.org", "codeberg.org"}


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

    Raises:
        RuntimeError: If the remote points to a public source code host
            (GitHub, GitLab.com, etc.) to prevent accidental pushes to
            upstream repos.
    """
    # Safety check: refuse to push to public source code hosts
    try:
        remote_url = _run_git(["remote", "get-url", remote], cwd=repo_path)
        for host in _BLOCKED_PUSH_HOSTS:
            if host in remote_url:
                raise RuntimeError(
                    f"BLOCKED: refusing to push to {remote} ({remote_url}). "
                    f"This points to a public host ({host}). "
                    f"Push to 'origin' (which should point to your fork) or "
                    f"reconfigure the remote to point to your target instance."
                )
    except RuntimeError as e:
        if "BLOCKED" in str(e):
            raise
        # If we can't resolve the remote URL, proceed cautiously
        pass

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


# ---------------------------------------------------------------------------
# Shared utility: commit files to a dedicated branch and push
# ---------------------------------------------------------------------------

ARTIFACTS_BRANCH = "autopoc-artifacts"


def commit_to_artifacts_branch(
    clone_path: str,
    files: list[str],
    message: str,
) -> None:
    """Commit files to the autopoc-artifacts branch and push to origin.

    Creates the branch from the current HEAD if it doesn't exist, switches to
    it, commits the specified files, pushes, then switches back to the original
    branch so downstream agents are unaffected.

    Stashes any uncommitted work before switching branches and restores it
    afterwards, so this is safe to call with a dirty working tree.

    This is a best-effort operation -- failures are logged as warnings and never
    propagate. The pipeline should not break because an artifact push failed.
    """
    original_ref = None
    stashed = False
    try:
        # Remember the current branch/ref so we can switch back
        original_ref = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=clone_path)

        # Read file contents before stashing so we can write them on the artifacts branch
        file_contents: dict[str, str] = {}
        clone = Path(clone_path)
        for f in files:
            fpath = clone / f
            if fpath.exists():
                file_contents[f] = fpath.read_text(encoding="utf-8")
            else:
                logger.warning("Artifact file %s does not exist, skipping", fpath)

        if not file_contents:
            logger.warning("No artifact files found to commit")
            return

        # Stash any dirty state so we can safely switch branches
        status = _run_git(["status", "--porcelain"], cwd=clone_path)
        if status.strip():
            _run_git(["stash", "push", "-u", "-m", "autopoc-artifacts-temp"], cwd=clone_path)
            stashed = True

        # Create or switch to the artifacts branch
        try:
            _run_git(["checkout", "-b", ARTIFACTS_BRANCH], cwd=clone_path)
        except RuntimeError:
            # Branch already exists -- switch to it
            _run_git(["checkout", ARTIFACTS_BRANCH], cwd=clone_path)

        # Write files to the artifacts branch and stage them
        for f, content in file_contents.items():
            fpath = clone / f
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
            _run_git(["add", f], cwd=clone_path)
        _run_git(["commit", "-m", message], cwd=clone_path)

        # Push to origin (which points to GitLab after fork agent runs)
        try:
            _run_git(["push", "origin", ARTIFACTS_BRANCH], cwd=clone_path)
            logger.info("Pushed %s to origin/%s", ", ".join(files), ARTIFACTS_BRANCH)
        except RuntimeError as push_err:
            logger.warning("Failed to push %s branch: %s", ARTIFACTS_BRANCH, push_err)

    except Exception as e:
        logger.warning("Failed to commit artifacts to %s: %s", ARTIFACTS_BRANCH, e)
    finally:
        # Always switch back to the original branch and restore stashed work
        if original_ref:
            try:
                _run_git(["checkout", original_ref], cwd=clone_path)
            except Exception:
                pass
        if stashed:
            try:
                _run_git(["stash", "pop"], cwd=clone_path)
                logger.debug("Restored stashed working tree state")
            except Exception as stash_err:
                logger.warning("Failed to pop stash: %s", stash_err)
