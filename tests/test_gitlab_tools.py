"""Tests for autopoc.tools.gitlab_tools module."""

from unittest.mock import patch

import httpx
import pytest

from autopoc.config import AutoPoCConfig
from autopoc.tools.gitlab_tools import GitLabClient


@pytest.fixture
def gitlab_config() -> AutoPoCConfig:
    """Create a config with GitLab settings for testing."""
    return AutoPoCConfig(
        anthropic_api_key="sk-test",
        gitlab_url="https://gitlab.example.com",
        gitlab_token="glpat-test-token",
        gitlab_group="poc-demos",
        quay_org="org",
        quay_token="tok",
        openshift_api_url="https://api.example.com:6443",
        openshift_token="tok",
    )


def _mock_response(status_code: int = 200, json_data: object = None) -> httpx.Response:
    """Create a mock httpx Response."""
    response = httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://fake"),
    )
    return response


class TestGitLabClient:
    def test_auth_header_set(self, gitlab_config: AutoPoCConfig) -> None:
        """Client sets the PRIVATE-TOKEN header correctly."""
        client = GitLabClient(gitlab_config)
        assert client._client.headers["PRIVATE-TOKEN"] == "glpat-test-token"
        client.close()

    def test_base_url_constructed(self, gitlab_config: AutoPoCConfig) -> None:
        """Client constructs the correct base URL."""
        client = GitLabClient(gitlab_config)
        assert str(client._client.base_url).rstrip("/") == "https://gitlab.example.com/api/v4"
        client.close()

    def test_base_url_strips_trailing_slash(self) -> None:
        """Client strips trailing slash from GitLab URL."""
        config = AutoPoCConfig(
            anthropic_api_key="sk-test",
            gitlab_url="https://gitlab.example.com/",
            gitlab_token="tok",
            gitlab_group="poc",
            quay_org="org",
            quay_token="tok",
            openshift_api_url="https://api.example.com:6443",
            openshift_token="tok",
        )
        client = GitLabClient(config)
        assert client.base_url == "https://gitlab.example.com"
        client.close()


class TestGetProject:
    def test_project_found(self, gitlab_config: AutoPoCConfig) -> None:
        """get_project returns project dict when found."""
        project_data = {
            "id": 42,
            "name": "my-repo",
            "path_with_namespace": "poc-demos/my-repo",
            "http_url_to_repo": "https://gitlab.example.com/poc-demos/my-repo.git",
        }

        with patch.object(httpx.Client, "get", return_value=_mock_response(200, project_data)):
            client = GitLabClient(gitlab_config)
            result = client.get_project("my-repo")
            client.close()

        assert result is not None
        assert result["id"] == 42
        assert result["name"] == "my-repo"

    def test_project_not_found(self, gitlab_config: AutoPoCConfig) -> None:
        """get_project returns None when project doesn't exist."""
        with patch.object(
            httpx.Client,
            "get",
            return_value=_mock_response(404, {"message": "404 Project Not Found"}),
        ):
            client = GitLabClient(gitlab_config)
            result = client.get_project("nonexistent")
            client.close()

        assert result is None

    def test_project_exists_true(self, gitlab_config: AutoPoCConfig) -> None:
        """project_exists returns True when project is found."""
        project_data = {"id": 1, "name": "repo"}

        with patch.object(httpx.Client, "get", return_value=_mock_response(200, project_data)):
            client = GitLabClient(gitlab_config)
            assert client.project_exists("repo") is True
            client.close()

    def test_project_exists_false(self, gitlab_config: AutoPoCConfig) -> None:
        """project_exists returns False when project is not found."""
        with patch.object(httpx.Client, "get", return_value=_mock_response(404, {})):
            client = GitLabClient(gitlab_config)
            assert client.project_exists("nope") is False
            client.close()


class TestCreateProject:
    def test_create_project_success(self, gitlab_config: AutoPoCConfig) -> None:
        """create_project creates a project and returns its data."""
        group_data = [{"id": 10, "path": "poc-demos", "full_path": "poc-demos"}]
        project_data = {
            "id": 99,
            "name": "new-repo",
            "path_with_namespace": "poc-demos/new-repo",
            "http_url_to_repo": "https://gitlab.example.com/poc-demos/new-repo.git",
        }

        def mock_get(url, **kwargs):
            return _mock_response(200, group_data)

        def mock_post(url, **kwargs):
            return _mock_response(201, project_data)

        with (
            patch.object(httpx.Client, "get", side_effect=mock_get),
            patch.object(httpx.Client, "post", side_effect=mock_post),
        ):
            client = GitLabClient(gitlab_config)
            result = client.create_project("new-repo")
            client.close()

        assert result["id"] == 99
        assert result["name"] == "new-repo"

    def test_create_project_group_not_found(self, gitlab_config: AutoPoCConfig) -> None:
        """create_project raises RuntimeError if group not found."""
        empty_groups: list = []

        with patch.object(httpx.Client, "get", return_value=_mock_response(200, empty_groups)):
            client = GitLabClient(gitlab_config)
            with pytest.raises(RuntimeError, match="not found"):
                client.create_project("repo")
            client.close()


class TestGetProjectCloneUrl:
    def test_clone_url_with_token(self, gitlab_config: AutoPoCConfig) -> None:
        """get_project_clone_url embeds token in the URL."""
        project = {"http_url_to_repo": "https://gitlab.example.com/poc-demos/repo.git"}
        client = GitLabClient(gitlab_config)
        url = client.get_project_clone_url(project)
        client.close()

        assert url == "https://oauth2:glpat-test-token@gitlab.example.com/poc-demos/repo.git"

    def test_context_manager(self, gitlab_config: AutoPoCConfig) -> None:
        """GitLabClient works as a context manager."""
        with GitLabClient(gitlab_config) as client:
            assert client.base_url == "https://gitlab.example.com"
