import subprocess
from unittest.mock import patch

import pytest

from autopoc.tools.podman_tools import (
    podman_build,
    podman_inspect,
    podman_push,
    podman_tag,
)


@pytest.fixture
def mock_run():
    with patch("autopoc.tools.podman_tools.subprocess.run") as mock:
        yield mock


def test_podman_build_success(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "Build successful"
    mock_run.return_value.stderr = ""

    result = podman_build.invoke(
        {
            "context_path": ".",
            "dockerfile": "Dockerfile",
            "tag": "my-image:latest",
            "build_args": {"VERSION": "1.0"},
        }
    )

    mock_run.assert_called_once_with(
        [
            "podman",
            "build",
            "-f",
            "Dockerfile",
            "-t",
            "my-image:latest",
            "--build-arg",
            "VERSION=1.0",
            ".",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert "Build successful" in result


def test_podman_build_failure(mock_run):
    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = "Error: build failed"

    with pytest.raises(RuntimeError) as exc:
        podman_build.invoke(
            {
                "context_path": ".",
                "dockerfile": "Dockerfile",
                "tag": "my-image:latest",
            }
        )

    assert "build failed" in str(exc.value)


def test_podman_push(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "Pushed successfully"
    mock_run.return_value.stderr = ""

    result = podman_push.invoke({"image": "my-image:latest"})

    mock_run.assert_called_once_with(
        ["podman", "push", "my-image:latest"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "Pushed successfully" in result


def test_podman_inspect(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = '[{"Id": "123"}]'
    mock_run.return_value.stderr = ""

    result = podman_inspect.invoke({"image": "my-image:latest"})

    mock_run.assert_called_once_with(
        ["podman", "inspect", "my-image:latest"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "123" in result


def test_podman_tag(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = ""

    podman_tag.invoke({"image": "my-image:latest", "new_tag": "my-image:v1"})

    mock_run.assert_called_once_with(
        ["podman", "tag", "my-image:latest", "my-image:v1"],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_podman_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="podman push", timeout=120)

    with pytest.raises(RuntimeError) as exc:
        podman_push.invoke({"image": "my-image:latest"})

    assert "timed out after 120s" in str(exc.value)
