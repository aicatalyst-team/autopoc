"""Tests for the GitHub API client."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from autopoc.config import AutoPoCConfig
from autopoc.tools.github_tools import GitHubClient, parse_github_url


@pytest.fixture
def github_config() -> AutoPoCConfig:
    """Config for GitHub target."""
    return AutoPoCConfig(
        anthropic_api_key="sk-ant-test",
        fork_target="github",
        github_token="ghp_test-token-12345",
        github_org="test-org",
        quay_org="org",
        quay_token="tok",
        openshift_api_url="https://api.example.com:6443",
        openshift_token="tok",
        _env_file=None,
    )


@pytest.fixture
def github_config_no_org() -> AutoPoCConfig:
    """Config for GitHub target without org (forks to user account)."""
    return AutoPoCConfig(
        anthropic_api_key="sk-ant-test",
        fork_target="github",
        github_token="ghp_test-token-12345",
        quay_org="org",
        quay_token="tok",
        openshift_api_url="https://api.example.com:6443",
        openshift_token="tok",
        _env_file=None,
    )


class TestParseGitHubUrl:
    """Tests for parse_github_url."""

    def test_https_url(self) -> None:
        owner, repo = parse_github_url("https://github.com/octocat/Hello-World")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_https_url_with_git_suffix(self) -> None:
        owner, repo = parse_github_url("https://github.com/octocat/Hello-World.git")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_https_url_with_trailing_slash(self) -> None:
        owner, repo = parse_github_url("https://github.com/octocat/Hello-World/")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_http_url(self) -> None:
        owner, repo = parse_github_url("http://github.com/octocat/Hello-World")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_ssh_url(self) -> None:
        owner, repo = parse_github_url("git@github.com:octocat/Hello-World.git")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_ssh_url_without_git_suffix(self) -> None:
        owner, repo = parse_github_url("git@github.com:octocat/Hello-World")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse GitHub URL"):
            parse_github_url("https://gitlab.com/octocat/Hello-World")

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse GitHub URL"):
            parse_github_url("not-a-url")


class TestGitHubClient:
    """Tests for GitHubClient using mocked HTTP."""

    def test_get_authenticated_user(self, github_config: AutoPoCConfig) -> None:
        """get_authenticated_user returns user info."""
        mock_response = httpx.Response(
            200,
            json={"login": "testuser", "id": 12345},
            request=httpx.Request("GET", "https://api.github.com/user"),
        )

        with GitHubClient(github_config) as client:
            client._client = MagicMock()
            client._client.get = MagicMock(return_value=mock_response)

            user = client.get_authenticated_user()
            assert user["login"] == "testuser"
            client._client.get.assert_called_once_with("/user")

    def test_fork_repo_returns_202(self, github_config: AutoPoCConfig) -> None:
        """fork_repo creates a fork and returns fork data."""
        mock_response = httpx.Response(
            202,
            json={
                "id": 999,
                "full_name": "test-org/Hello-World",
                "clone_url": "https://github.com/test-org/Hello-World.git",
                "fork": True,
            },
            request=httpx.Request(
                "POST", "https://api.github.com/repos/octocat/Hello-World/forks"
            ),
        )

        with GitHubClient(github_config) as client:
            client._client = MagicMock()
            client._client.post = MagicMock(return_value=mock_response)

            fork = client.fork_repo("octocat", "Hello-World")
            assert fork["full_name"] == "test-org/Hello-World"
            client._client.post.assert_called_once_with(
                "/repos/octocat/Hello-World/forks",
                json={"organization": "test-org"},
            )

    def test_fork_repo_without_org(self, github_config_no_org: AutoPoCConfig) -> None:
        """fork_repo without org sends empty body."""
        mock_response = httpx.Response(
            202,
            json={
                "id": 999,
                "full_name": "testuser/Hello-World",
                "clone_url": "https://github.com/testuser/Hello-World.git",
            },
            request=httpx.Request(
                "POST", "https://api.github.com/repos/octocat/Hello-World/forks"
            ),
        )

        with GitHubClient(github_config_no_org) as client:
            client._client = MagicMock()
            client._client.post = MagicMock(return_value=mock_response)

            fork = client.fork_repo("octocat", "Hello-World")
            assert fork["full_name"] == "testuser/Hello-World"
            # No org in body
            client._client.post.assert_called_once_with(
                "/repos/octocat/Hello-World/forks",
                json={},
            )

    def test_get_fork_found(self, github_config: AutoPoCConfig) -> None:
        """get_fork returns fork data when it exists."""
        mock_response = httpx.Response(
            200,
            json={
                "full_name": "test-org/Hello-World",
                "fork": True,
                "parent": {"full_name": "octocat/Hello-World"},
            },
            request=httpx.Request(
                "GET", "https://api.github.com/repos/test-org/Hello-World"
            ),
        )

        with GitHubClient(github_config) as client:
            client._client = MagicMock()
            client._client.get = MagicMock(return_value=mock_response)

            fork = client.get_fork("octocat", "Hello-World")
            assert fork is not None
            assert fork["full_name"] == "test-org/Hello-World"

    def test_get_fork_not_found(self, github_config: AutoPoCConfig) -> None:
        """get_fork returns None when no fork exists."""
        mock_response = httpx.Response(
            404,
            json={"message": "Not Found"},
            request=httpx.Request(
                "GET", "https://api.github.com/repos/test-org/Hello-World"
            ),
        )

        with GitHubClient(github_config) as client:
            client._client = MagicMock()
            client._client.get = MagicMock(return_value=mock_response)

            fork = client.get_fork("octocat", "Hello-World")
            assert fork is None

    def test_get_fork_exists_but_not_a_fork(self, github_config: AutoPoCConfig) -> None:
        """get_fork returns None when repo exists but is not a fork."""
        mock_response = httpx.Response(
            200,
            json={
                "full_name": "test-org/Hello-World",
                "fork": False,  # Not a fork
            },
            request=httpx.Request(
                "GET", "https://api.github.com/repos/test-org/Hello-World"
            ),
        )

        with GitHubClient(github_config) as client:
            client._client = MagicMock()
            client._client.get = MagicMock(return_value=mock_response)

            fork = client.get_fork("octocat", "Hello-World")
            assert fork is None

    def test_get_fork_wrong_parent(self, github_config: AutoPoCConfig) -> None:
        """get_fork returns None when fork has different parent."""
        mock_response = httpx.Response(
            200,
            json={
                "full_name": "test-org/Hello-World",
                "fork": True,
                "parent": {"full_name": "other-owner/Hello-World"},
            },
            request=httpx.Request(
                "GET", "https://api.github.com/repos/test-org/Hello-World"
            ),
        )

        with GitHubClient(github_config) as client:
            client._client = MagicMock()
            client._client.get = MagicMock(return_value=mock_response)

            fork = client.get_fork("octocat", "Hello-World")
            assert fork is None

    def test_wait_for_fork_immediate(self, github_config: AutoPoCConfig) -> None:
        """wait_for_fork returns immediately when fork is ready."""
        mock_response = httpx.Response(
            200,
            json={
                "full_name": "test-org/Hello-World",
                "pushed_at": "2024-01-01T00:00:00Z",
                "size": 100,
            },
            request=httpx.Request(
                "GET", "https://api.github.com/repos/test-org/Hello-World"
            ),
        )

        with GitHubClient(github_config) as client:
            client._client = MagicMock()
            client._client.get = MagicMock(return_value=mock_response)

            result = client.wait_for_fork("test-org", "Hello-World", timeout=5)
            assert result["full_name"] == "test-org/Hello-World"

    def test_wait_for_fork_polls(self, github_config: AutoPoCConfig) -> None:
        """wait_for_fork polls until fork is ready."""
        not_ready = httpx.Response(
            404,
            json={"message": "Not Found"},
            request=httpx.Request(
                "GET", "https://api.github.com/repos/test-org/Hello-World"
            ),
        )
        ready = httpx.Response(
            200,
            json={
                "full_name": "test-org/Hello-World",
                "pushed_at": "2024-01-01T00:00:00Z",
                "size": 100,
            },
            request=httpx.Request(
                "GET", "https://api.github.com/repos/test-org/Hello-World"
            ),
        )

        with GitHubClient(github_config) as client:
            client._client = MagicMock()
            client._client.get = MagicMock(side_effect=[not_ready, not_ready, ready])

            with patch("autopoc.tools.github_tools.time.sleep"):
                result = client.wait_for_fork(
                    "test-org", "Hello-World", timeout=30, poll_interval=0
                )
                assert result["full_name"] == "test-org/Hello-World"
                assert client._client.get.call_count == 3

    def test_wait_for_fork_timeout(self, github_config: AutoPoCConfig) -> None:
        """wait_for_fork raises TimeoutError when fork never becomes ready."""
        not_ready = httpx.Response(
            404,
            json={"message": "Not Found"},
            request=httpx.Request(
                "GET", "https://api.github.com/repos/test-org/Hello-World"
            ),
        )

        with GitHubClient(github_config) as client:
            client._client = MagicMock()
            client._client.get = MagicMock(return_value=not_ready)

            with patch("autopoc.tools.github_tools.time.sleep"):
                with patch("autopoc.tools.github_tools.time.monotonic") as mock_time:
                    # Simulate time passing beyond timeout
                    mock_time.side_effect = [0, 0, 100, 100, 400]
                    with pytest.raises(TimeoutError, match="not ready"):
                        client.wait_for_fork(
                            "test-org", "Hello-World", timeout=10
                        )

    def test_get_clone_url_embeds_token(self, github_config: AutoPoCConfig) -> None:
        """get_clone_url embeds token in the URL."""
        repo_data = {
            "clone_url": "https://github.com/test-org/Hello-World.git"
        }

        with GitHubClient(github_config) as client:
            url = client.get_clone_url(repo_data)
            assert url == "https://ghp_test-token-12345@github.com/test-org/Hello-World.git"

    def test_context_manager(self, github_config: AutoPoCConfig) -> None:
        """GitHubClient works as a context manager."""
        with GitHubClient(github_config) as client:
            assert client.token == "ghp_test-token-12345"
            assert client.org == "test-org"
        # After exiting, the client should be closed (no exception)
