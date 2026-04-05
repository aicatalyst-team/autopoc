"""GitLab API tools for project management.

Provides functions for creating and querying projects on a self-hosted GitLab
instance. These are NOT LangChain @tool-decorated — they are called procedurally
by the fork agent.
"""

import logging

import httpx

from autopoc.config import AutoPoCConfig

logger = logging.getLogger(__name__)

# Timeout for GitLab API calls (seconds)
GITLAB_TIMEOUT = 30


class GitLabClient:
    """Client for interacting with the GitLab API.

    Args:
        config: AutoPoC configuration with GitLab URL and token.
    """

    def __init__(self, config: AutoPoCConfig) -> None:
        self.base_url = config.gitlab_url.rstrip("/")
        self.token = config.gitlab_token
        self.group = config.gitlab_group
        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v4",
            headers={"PRIVATE-TOKEN": self.token},
            timeout=GITLAB_TIMEOUT,
            follow_redirects=True,
        )

    def _get_group_id(self) -> int:
        """Look up the numeric ID for the configured group/namespace.

        Returns:
            The group ID.

        Raises:
            RuntimeError: If the group is not found.
        """
        response = self._client.get(
            "/groups",
            params={"search": self.group},
        )
        response.raise_for_status()
        groups = response.json()

        for group in groups:
            if group["full_path"] == self.group or group["path"] == self.group:
                return group["id"]

        raise RuntimeError(
            f"GitLab group '{self.group}' not found. "
            f"Available groups matching search: {[g['full_path'] for g in groups]}"
        )

    def get_project(self, name: str) -> dict | None:
        """Get a project by name within the configured group.

        Args:
            name: Project name (not the full path).

        Returns:
            Project dict if found, None otherwise.
        """
        project_path = f"{self.group}/{name}"
        encoded_path = project_path.replace("/", "%2F")
        response = self._client.get(f"/projects/{encoded_path}")

        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def project_exists(self, name: str) -> bool:
        """Check if a project exists in the configured group.

        Args:
            name: Project name.

        Returns:
            True if the project exists.
        """
        return self.get_project(name) is not None

    def create_project(self, name: str) -> dict:
        """Create a new project in the configured group.

        Args:
            name: Project name.

        Returns:
            The created project dict (includes id, http_url_to_repo, etc.)

        Raises:
            httpx.HTTPStatusError: If creation fails.
        """
        group_id = self._get_group_id()

        response = self._client.post(
            "/projects",
            json={
                "name": name,
                "namespace_id": group_id,
                "visibility": "internal",
                "initialize_with_readme": False,
            },
        )
        response.raise_for_status()
        project = response.json()

        logger.info(
            "Created GitLab project: %s (id=%s)",
            project.get("path_with_namespace"),
            project.get("id"),
        )
        return project

    def get_project_clone_url(self, project: dict) -> str:
        """Extract the HTTP clone URL from a project dict.

        Args:
            project: Project dict from GitLab API.

        Returns:
            The HTTP clone URL with token embedded for push access.
        """
        http_url = project["http_url_to_repo"]
        # Embed token for push access: https://oauth2:TOKEN@gitlab.example.com/group/project.git
        if "://" in http_url:
            scheme, rest = http_url.split("://", 1)
            return f"{scheme}://oauth2:{self.token}@{rest}"
        return http_url

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> "GitLabClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
