"""Quay.io API tools for project management.

Provides functions for creating and querying repositories on a Quay
registry. These are NOT LangChain @tool-decorated — they are called procedurally
by the build agent.
"""

import logging

import httpx

from autopoc.config import AutoPoCConfig

logger = logging.getLogger(__name__)

# Timeout for Quay API calls (seconds)
QUAY_TIMEOUT = 30


class QuayClient:
    """Client for interacting with the Quay API.

    Supports two authentication modes:
    - Robot account: config.quay_username is set (e.g. 'myuser+robotname'), uses Basic auth.
    - OAuth token: config.quay_username is unset, uses Bearer auth.

    Args:
        config: AutoPoC configuration with Quay token and registry.
    """

    def __init__(self, config: AutoPoCConfig) -> None:
        raw_registry = config.quay_registry
        if raw_registry.startswith(("http://", "https://")):
            self.base_url = raw_registry.rstrip("/")
            self.registry = raw_registry.split("://", 1)[1].rstrip("/")
        else:
            self.base_url = f"https://{raw_registry}".rstrip("/")
            self.registry = raw_registry.rstrip("/")

        self.token = config.quay_token
        self.username = config.quay_username

        # Use Basic auth for robot accounts, Bearer for OAuth tokens
        if self.username:
            auth = (self.username, self.token)
            headers = {}
        else:
            auth = None
            headers = {"Authorization": f"Bearer {self.token}"}

        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v1",
            auth=auth,
            headers=headers,
            timeout=QUAY_TIMEOUT,
            follow_redirects=True,
        )

    def repo_exists(self, org: str, name: str) -> bool:
        """Check if a repository exists in Quay.

        Args:
            org: Organization namespace.
            name: Repository name.

        Returns:
            True if the repository exists.
        """
        response = self._client.get(f"/repository/{org}/{name}")
        if response.status_code == 404:
            return False
        if response.status_code == 401:
            # Robot accounts can't query the REST API — assume the repo
            # may or may not exist and let the push create it on first use.
            logger.debug(
                "Cannot check if %s/%s exists (401 — likely robot account). "
                "Assuming it will be created on first push.",
                org,
                name,
            )
            return False

        response.raise_for_status()
        return True

    def ensure_repo(self, org: str, name: str) -> str:
        """Check if a Quay repo exists. If not, create it.

        For robot accounts (which cannot use the Quay REST API), this
        method skips the API check and returns the image reference
        directly. Quay.io auto-creates repositories on first push if
        the account has permission.

        Args:
            org: Organization namespace.
            name: Repository name.

        Returns:
            The image reference string for the repository (e.g. quay.io/org/name).

        Raises:
            httpx.HTTPStatusError: If creation fails (OAuth tokens only).
        """
        repo_ref = f"{self.registry}/{org}/{name}"

        # Robot accounts can't use the REST API — skip the check and rely
        # on Quay's auto-create-on-push behavior.
        if self.username:
            logger.info(
                "Robot account detected — skipping REST API repo check for %s. "
                "Repository will be created on first push if it doesn't exist.",
                repo_ref,
            )
            return repo_ref

        if self.repo_exists(org, name):
            logger.info("Quay repository %s already exists.", repo_ref)
            return repo_ref

        response = self._client.post(
            "/repository",
            json={
                "namespace": org,
                "repository": name,
                "visibility": "public",
                "description": "AutoPoC created repository",
            },
        )
        response.raise_for_status()
        logger.info("Created Quay repository %s.", repo_ref)

        return repo_ref

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> "QuayClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
