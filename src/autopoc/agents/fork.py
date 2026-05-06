"""Fork agent — forks a GitHub repo to the configured target platform.

Supports two targets:
- **GitLab** (default): Creates a project on a self-hosted GitLab instance,
  clones from GitHub, and pushes all branches and tags.
- **GitHub**: Uses the GitHub API to create a true fork (preserving the
  parent-child relationship), waits for the async fork to complete, and
  configures remotes to point at the fork.

This is a procedural node (no LLM calls).
"""

import logging
from pathlib import Path

from autopoc.config import AutoPoCConfig
from autopoc.state import PoCState
from autopoc.tools.git_tools import git_add_remote, git_clone, git_push
from autopoc.tools.github_tools import GitHubClient, parse_github_url
from autopoc.tools.gitlab_tools import GitLabClient

logger = logging.getLogger(__name__)


async def fork_agent(
    state: PoCState,
    *,
    app_config: AutoPoCConfig | None = None,
    gitlab_client: GitLabClient | None = None,
    github_client: GitHubClient | None = None,
) -> dict:
    """Fork the source repo to the configured target platform.

    This is a LangGraph node function. It receives the current state and returns
    a partial state update dict.

    Args:
        state: Current pipeline state with source_repo_url and project_name set.
        app_config: Optional config override (for testing).
        gitlab_client: Optional GitLab client override (for testing).
        github_client: Optional GitHub client override (for testing).

    Returns:
        Partial state update with fork_repo_url, fork_target, and local_clone_path.
    """
    # Load config if not provided
    if app_config is None:
        from autopoc.config import load_config

        app_config = load_config()

    fork_target = app_config.fork_target

    if fork_target == "github":
        return await _fork_to_github(state, app_config, github_client)
    else:
        return await _fork_to_gitlab(state, app_config, gitlab_client)


async def _fork_to_gitlab(
    state: PoCState,
    config: AutoPoCConfig,
    gitlab_client: GitLabClient | None = None,
) -> dict:
    """Fork the source repo to the internal GitLab instance.

    This is the original fork logic, extracted into a helper.
    """
    project_name = state["project_name"]
    source_url = state["source_repo_url"]

    logger.info("Starting GitLab fork for %s (%s)", project_name, source_url)

    owns_client = gitlab_client is None
    if gitlab_client is None:
        gitlab_client = GitLabClient(config)

    try:
        # Check if project already exists on GitLab
        existing = gitlab_client.get_project(project_name)
        if existing:
            gitlab_url = gitlab_client.get_project_clone_url(existing)
            logger.info("Project already exists on GitLab: %s", existing["path_with_namespace"])
        else:
            # Create project on GitLab
            project = gitlab_client.create_project(project_name)
            gitlab_url = gitlab_client.get_project_clone_url(project)
            logger.info("Created GitLab project: %s", project["path_with_namespace"])

        # Clone from GitHub if not already done
        clone_path = state.get("local_clone_path")
        if not clone_path or not Path(clone_path).exists():
            work_dir = Path(config.work_dir) / project_name
            clone_path = git_clone.invoke({"url": source_url, "dest": str(work_dir)})
            logger.info("Cloned repo to %s", clone_path)

        # Rename origin (GitHub) to "github" so it's never the default push target,
        # then set origin to GitLab.
        clone_str = str(clone_path)
        try:
            from autopoc.tools.git_tools import _run_git

            # Check if origin exists and rename it to github
            try:
                _run_git(["remote", "get-url", "origin"], cwd=clone_str)
                try:
                    _run_git(["remote", "rename", "origin", "github"], cwd=clone_str)
                    logger.info("Renamed remote 'origin' -> 'github' (source repo)")
                except RuntimeError:
                    pass  # May already be renamed
            except RuntimeError:
                pass  # No origin remote

            # Set origin to GitLab
            try:
                _run_git(["remote", "get-url", "origin"], cwd=clone_str)
                _run_git(["remote", "set-url", "origin", gitlab_url], cwd=clone_str)
            except RuntimeError:
                _run_git(["remote", "add", "origin", gitlab_url], cwd=clone_str)

            logger.info("Set remote 'origin' -> GitLab (%s)", gitlab_url)

            # Also add a 'gitlab' alias
            try:
                _run_git(["remote", "get-url", "gitlab"], cwd=clone_str)
                _run_git(["remote", "set-url", "gitlab", gitlab_url], cwd=clone_str)
            except RuntimeError:
                _run_git(["remote", "add", "gitlab", gitlab_url], cwd=clone_str)
            logger.info("Added remote 'gitlab' alias -> GitLab (%s)", gitlab_url)
        except Exception as e:
            logger.warning("Failed to reconfigure remotes, falling back to 'gitlab' remote: %s", e)
            git_add_remote.invoke({"repo_path": clone_str, "name": "gitlab", "url": gitlab_url})

        # Force-push all branches and tags so re-runs overwrite previous results
        git_push.invoke({"repo_path": clone_str, "remote": "origin", "ref": "--all", "force": True})
        git_push.invoke({"repo_path": clone_str, "remote": "origin", "ref": "--tags", "force": True})

        logger.info("Pushed all branches and tags to GitLab")

        # NOTE: Do not set current_phase here — fork runs in parallel with
        # poc_plan, and both writing to current_phase causes a conflict.
        return {
            "gitlab_repo_url": gitlab_url,
            "fork_repo_url": gitlab_url,
            "fork_target": "gitlab",
            "local_clone_path": str(clone_path),
        }

    finally:
        if owns_client:
            gitlab_client.close()


async def _fork_to_github(
    state: PoCState,
    config: AutoPoCConfig,
    github_client: GitHubClient | None = None,
) -> dict:
    """Fork the source repo on GitHub using the GitHub API.

    Creates a true GitHub fork (preserving the parent-child relationship),
    waits for the async fork to be ready, then configures local remotes.
    No explicit push is needed since GitHub forks copy all branches/tags.
    """
    project_name = state["project_name"]
    source_url = state["source_repo_url"]

    logger.info("Starting GitHub fork for %s (%s)", project_name, source_url)

    # Parse the source URL to get owner/repo
    source_owner, source_repo = parse_github_url(source_url)

    owns_client = github_client is None
    if github_client is None:
        github_client = GitHubClient(config)

    try:
        # Determine the fork destination owner (org or user)
        if config.github_org:
            fork_owner = config.github_org
        else:
            user = github_client.get_authenticated_user()
            fork_owner = user["login"]

        # Check if fork already exists
        existing_fork = github_client.get_fork(source_owner, source_repo)
        if existing_fork:
            fork_data = existing_fork
            logger.info(
                "Fork already exists: %s",
                fork_data.get("full_name"),
            )
        else:
            # Create the fork via GitHub API
            fork_data = github_client.fork_repo(source_owner, source_repo)
            logger.info(
                "Fork requested: %s -> %s",
                f"{source_owner}/{source_repo}",
                fork_data.get("full_name"),
            )

            # Wait for the async fork to be ready
            fork_data = github_client.wait_for_fork(fork_owner, source_repo)
            logger.info("Fork is ready: %s", fork_data.get("full_name"))

        # Get clone URL with embedded token for push access
        fork_clone_url = github_client.get_clone_url(fork_data)

        # Clone or reconfigure remotes
        clone_path = state.get("local_clone_path")
        from autopoc.tools.git_tools import _run_git

        if clone_path and Path(clone_path).exists():
            # Already cloned from source by intake — reconfigure remotes
            clone_str = str(clone_path)

            # Remove the source remote entirely (safety: no path to push upstream)
            for remote_name in ("origin", "github"):
                try:
                    _run_git(["remote", "get-url", remote_name], cwd=clone_str)
                    _run_git(["remote", "remove", remote_name], cwd=clone_str)
                    logger.info("Removed remote '%s' (source repo)", remote_name)
                except RuntimeError:
                    pass  # Remote doesn't exist

            # Set origin to the fork
            try:
                _run_git(["remote", "get-url", "origin"], cwd=clone_str)
                _run_git(["remote", "set-url", "origin", fork_clone_url], cwd=clone_str)
            except RuntimeError:
                _run_git(["remote", "add", "origin", fork_clone_url], cwd=clone_str)

            logger.info("Set remote 'origin' -> GitHub fork (%s)", fork_data.get("full_name"))
        else:
            # Clone from the fork
            work_dir = Path(config.work_dir) / project_name
            clone_path = git_clone.invoke({"url": fork_clone_url, "dest": str(work_dir)})
            logger.info("Cloned fork to %s", clone_path)

        # No explicit push needed — GitHub fork automatically copies all branches/tags

        return {
            "fork_repo_url": fork_clone_url,
            "fork_target": "github",
            "local_clone_path": str(clone_path),
        }

    finally:
        if owns_client:
            github_client.close()
