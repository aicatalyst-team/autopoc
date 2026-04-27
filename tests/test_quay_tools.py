from unittest.mock import MagicMock, patch

import pytest

from autopoc.config import AutoPoCConfig
from autopoc.tools.quay_tools import QuayClient


@pytest.fixture
def mock_config():
    config = MagicMock(spec=AutoPoCConfig)
    config.quay_registry = "quay.io"
    config.quay_token = "secret"
    return config


@pytest.fixture
def mock_httpx_client():
    with patch("autopoc.tools.quay_tools.httpx.Client") as mock:
        yield mock.return_value


def test_quay_repo_exists(mock_config, mock_httpx_client):
    client = QuayClient(mock_config)

    # Exists
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_httpx_client.get.return_value = mock_response

    assert client.repo_exists("my-org", "my-repo") is True
    mock_httpx_client.get.assert_called_with("/repository/my-org/my-repo")

    # Missing
    mock_response.status_code = 404
    assert client.repo_exists("my-org", "missing-repo") is False


def test_quay_ensure_repo_exists(mock_config, mock_httpx_client):
    client = QuayClient(mock_config)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_httpx_client.get.return_value = mock_response

    result = client.ensure_repo("my-org", "my-repo")

    assert result == "quay.io/my-org/my-repo"
    mock_httpx_client.post.assert_not_called()


def test_quay_ensure_repo_creates(mock_config, mock_httpx_client):
    client = QuayClient(mock_config)

    # Get returns 404
    mock_get_response = MagicMock()
    mock_get_response.status_code = 404
    mock_httpx_client.get.return_value = mock_get_response

    # Post succeeds
    mock_post_response = MagicMock()
    mock_post_response.status_code = 201
    mock_httpx_client.post.return_value = mock_post_response

    result = client.ensure_repo("my-org", "new-repo")

    assert result == "quay.io/my-org/new-repo"
    mock_httpx_client.post.assert_called_once_with(
        "/repository",
        json={
            "namespace": "my-org",
            "repository": "new-repo",
            "visibility": "private",
            "description": "AutoPoC created repository",
        },
    )


def test_quay_client_context_manager(mock_config, mock_httpx_client):
    with QuayClient(mock_config) as client:
        assert client.token == "secret"

    mock_httpx_client.close.assert_called_once()
