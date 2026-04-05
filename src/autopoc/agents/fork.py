"""Fork agent — forks a GitHub repo to the internal GitLab instance.

This is a procedural node (no LLM calls). It creates a project on GitLab,
clones from GitHub if needed, and pushes all branches and tags to GitLab.
"""

import logging
from pathlib import Path

from autopoc.config import AutoPoCConfig
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.git_tools import git_add_remote, git_clone, git_push
from autopoc.tools.gitlab_tools import GitLabClient

logger = logging.getLogger(__name__)


async def fork_agent(
    state: PoCState,
    *,
    app_config: AutoPoCConfig | None = None,
    gitlab_client: GitLabClient | None = None,
) -> dict:
    """Fork the source repo to the internal GitLab instance.

    This is a LangGraph node function. It receives the current state and returns
    a partial state update dict.

    Args:
        state: Current pipeline state with source_repo_url and project_name set.
        app_config: Optional config override (for testing).
        gitlab_client: Optional GitLab client override (for testing).

    Returns:
        Partial state update with gitlab_repo_url and local_clone_path.
    """
    project_name = state["project_name"]
    source_url = state["source_repo_url"]

    logger.info("Starting fork for %s (%s)", project_name, source_url)

    # Load config if not provided
    if app_config is None:
        from autopoc.config import load_config

        app_config = load_config()

    # Set up GitLab client
    owns_client = gitlab_client is None
    if gitlab_client is None:
        gitlab_client = GitLabClient(app_config)

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
            work_dir = Path(app_config.work_dir) / project_name
            clone_path = git_clone.invoke({"url": source_url, "dest": str(work_dir)})
            logger.info("Cloned repo to %s", clone_path)

        # Add GitLab as a remote (idempotent — git_add_remote handles existing remotes)
        git_add_remote.invoke(
            {
                "repo_path": str(clone_path),
                "name": "gitlab",
                "url": gitlab_url,
            }
        )

        # Push all branches and tags to GitLab
        git_push.invoke(
            {
                "repo_path": str(clone_path),
                "remote": "gitlab",
                "ref": "--all",
            }
        )
        git_push.invoke(
            {
                "repo_path": str(clone_path),
                "remote": "gitlab",
                "ref": "--tags",
            }
        )

        logger.info("Pushed all branches and tags to GitLab")

        return {
            "current_phase": PoCPhase.FORK,
            "gitlab_repo_url": gitlab_url,
            "local_clone_path": str(clone_path),
        }

    finally:
        if owns_client:
            gitlab_client.close()
