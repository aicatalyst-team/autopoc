"""GitHub API tools for repository forking.

Provides a client for forking repositories via the GitHub REST API.
These are NOT LangChain @tool-decorated — they are called procedurally
by the fork agent (same pattern as gitlab_tools.py).
"""

import logging
import re
import time

import httpx

from autopoc.config import AutoPoCConfig

logger = logging.getLogger(__name__)

# Timeout for GitHub API calls (seconds)
GITHUB_TIMEOUT = 30

# Default polling interval and max wait for async fork creation
FORK_POLL_INTERVAL = 2  # seconds between polls
FORK_MAX_WAIT = 300  # 5 minutes


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL.

    Supports formats:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - git@github.com:owner/repo.git
    - http://github.com/owner/repo

    Args:
        url: GitHub repository URL.

    Returns:
        Tuple of (owner, repo_name) without .git suffix.

    Raises:
        ValueError: If the URL cannot be parsed as a GitHub URL.
    """
    # HTTPS format: https://github.com/owner/repo[.git]
    https_match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url
    )
    if https_match:
        return https_match.group(1), https_match.group(2)

    # SSH format: git@github.com:owner/repo.git
    ssh_match = re.match(
        r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url
    )
    if ssh_match:
        return ssh_match.group(1), ssh_match.group(2)

    raise ValueError(
        f"Cannot parse GitHub URL: {url}. "
        f"Expected format: https://github.com/owner/repo"
    )


class GitHubClient:
    """Client for interacting with the GitHub REST API.

    Used by the fork agent to create forks of source repositories.

    Args:
        config: AutoPoC configuration with GitHub token (and optional org).
    """

    def __init__(self, config: AutoPoCConfig) -> None:
        self.token = config.github_token
        self.org = config.github_org
        self._client = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=GITHUB_TIMEOUT,
            follow_redirects=True,
        )

    def get_authenticated_user(self) -> dict:
        """Get the authenticated user's info.

        Used for credential validation and to determine the fork
        destination when no organization is configured.

        Returns:
            User dict with 'login', 'id', etc.

        Raises:
            httpx.HTTPStatusError: If authentication fails.
        """
        response = self._client.get("/user")
        response.raise_for_status()
        return response.json()

    def get_fork(self, owner: str, repo: str) -> dict | None:
        """Check if a fork of the given repo already exists under our org/user.

        Checks by directly looking up the repo under our namespace,
        then verifying it's actually a fork of the expected source.

        Args:
            owner: Source repo owner.
            repo: Source repo name.

        Returns:
            Fork repo dict if found, None otherwise.
        """
        # Determine where we'd expect the fork to be
        fork_owner = self.org or self.get_authenticated_user()["login"]

        response = self._client.get(f"/repos/{fork_owner}/{repo}")
        if response.status_code == 404:
            return None
        response.raise_for_status()

        repo_data = response.json()

        # Verify it's actually a fork (not just a repo with the same name)
        if not repo_data.get("fork"):
            return None

        # Verify the parent matches the expected source
        parent = repo_data.get("parent", {})
        if parent.get("full_name", "").lower() == f"{owner}/{repo}".lower():
            return repo_data

        # Also check "source" (the root of the fork network)
        source = repo_data.get("source", {})
        if source.get("full_name", "").lower() == f"{owner}/{repo}".lower():
            return repo_data

        return None

    def fork_repo(self, owner: str, repo: str) -> dict:
        """Fork a repository via the GitHub API.

        Creates a fork under the configured organization (if set) or
        the authenticated user's account.

        Note: Forking is asynchronous on GitHub. The returned repo dict
        may not be immediately usable. Use wait_for_fork() to poll until
        the fork is ready.

        Args:
            owner: Source repo owner.
            repo: Source repo name.

        Returns:
            Fork repo dict (from 202 Accepted response).

        Raises:
            httpx.HTTPStatusError: If the fork request fails.
        """
        body: dict = {}
        if self.org:
            body["organization"] = self.org

        response = self._client.post(
            f"/repos/{owner}/{repo}/forks",
            json=body,
        )

        if response.status_code not in (200, 202):
            response.raise_for_status()

        fork_data = response.json()
        logger.info(
            "Fork requested: %s -> %s (status %d)",
            f"{owner}/{repo}",
            fork_data.get("full_name"),
            response.status_code,
        )
        return fork_data

    def wait_for_fork(
        self,
        fork_owner: str,
        repo: str,
        timeout: int = FORK_MAX_WAIT,
        poll_interval: int = FORK_POLL_INTERVAL,
    ) -> dict:
        """Wait for an async fork to become ready.

        GitHub forks are created asynchronously. This method polls until
        the fork's git objects are available (i.e., the repo exists and
        has commits).

        Args:
            fork_owner: Owner of the fork (org or username).
            repo: Repository name.
            timeout: Maximum seconds to wait (default 300).
            poll_interval: Seconds between polls (default 2).

        Returns:
            The fork repo dict once ready.

        Raises:
            TimeoutError: If the fork isn't ready within the timeout.
        """
        start = time.monotonic()
        last_status = None

        while time.monotonic() - start < timeout:
            response = self._client.get(f"/repos/{fork_owner}/{repo}")

            if response.status_code == 200:
                repo_data = response.json()
                # A fork is "ready" when it has been pushed to (size > 0
                # or pushed_at is set). Some forks start with size=0 but
                # pushed_at is already set.
                if repo_data.get("pushed_at") or repo_data.get("size", 0) > 0:
                    logger.info(
                        "Fork %s/%s is ready (%.1fs)",
                        fork_owner,
                        repo,
                        time.monotonic() - start,
                    )
                    return repo_data

            if response.status_code != last_status:
                logger.debug(
                    "Waiting for fork %s/%s (status=%d, elapsed=%.0fs)",
                    fork_owner,
                    repo,
                    response.status_code,
                    time.monotonic() - start,
                )
                last_status = response.status_code

            time.sleep(poll_interval)

        elapsed = time.monotonic() - start
        raise TimeoutError(
            f"Fork {fork_owner}/{repo} not ready after {elapsed:.0f}s. "
            f"GitHub may be experiencing delays. Try again later."
        )

    def get_clone_url(self, repo_data: dict) -> str:
        """Extract the HTTPS clone URL with embedded token for push access.

        Args:
            repo_data: Repository dict from the GitHub API.

        Returns:
            Clone URL with token: https://{token}@github.com/owner/repo.git
        """
        clone_url = repo_data["clone_url"]
        # Embed token for push access: https://TOKEN@github.com/owner/repo.git
        if "://" in clone_url:
            scheme, rest = clone_url.split("://", 1)
            return f"{scheme}://{self.token}@{rest}"
        return clone_url

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
