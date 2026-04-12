"""Tests for autopoc.tools.git_tools module."""

import subprocess
from pathlib import Path

import pytest

from autopoc.tools.git_tools import (
    git_add_remote,
    git_checkout_branch,
    git_clone,
    git_commit,
    git_push,
)


@pytest.fixture
def bare_repo(tmp_path: Path) -> Path:
    """Create a bare git repo to use as a remote."""
    bare = tmp_path / "remote.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


@pytest.fixture
def local_repo(tmp_path: Path, bare_repo: Path) -> Path:
    """Create a local repo cloned from the bare repo with an initial commit."""
    local = tmp_path / "local"
    subprocess.run(["git", "clone", str(bare_repo), str(local)], check=True, capture_output=True)
    # Configure user for commits
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(local),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(local), check=True, capture_output=True
    )
    # Create initial commit
    (local / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "-A"], cwd=str(local), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(local),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", "HEAD"],
        cwd=str(local),
        check=True,
        capture_output=True,
    )
    return local


class TestGitClone:
    def test_clone_local_bare_repo(self, bare_repo: Path, tmp_path: Path) -> None:
        dest = str(tmp_path / "cloned")
        result = git_clone.invoke({"url": str(bare_repo), "dest": dest})
        assert dest in result
        assert Path(dest).is_dir()
        assert (Path(dest) / ".git").is_dir()

    def test_clone_dest_already_exists(self, bare_repo: Path, tmp_path: Path) -> None:
        dest = tmp_path / "existing"
        dest.mkdir()
        result = git_clone.invoke({"url": str(bare_repo), "dest": str(dest)})
        assert result == str(dest.resolve())


class TestGitAddRemote:
    def test_add_new_remote(self, local_repo: Path, tmp_path: Path) -> None:
        other_bare = tmp_path / "other.git"
        other_bare.mkdir()
        subprocess.run(["git", "init", "--bare", str(other_bare)], check=True, capture_output=True)
        result = git_add_remote.invoke(
            {"repo_path": str(local_repo), "name": "gitlab", "url": str(other_bare)}
        )
        assert "Added remote" in result
        assert "gitlab" in result

        # Verify remote exists
        remotes = subprocess.run(
            ["git", "remote", "-v"],
            cwd=str(local_repo),
            capture_output=True,
            text=True,
        )
        assert "gitlab" in remotes.stdout

    def test_remote_already_exists_updates_url(self, local_repo: Path) -> None:
        result = git_add_remote.invoke(
            {"repo_path": str(local_repo), "name": "origin", "url": "https://other.com"}
        )
        assert "Updated remote" in result

        # Verify it actually updated
        actual = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(local_repo),
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert actual == "https://other.com"


class TestGitCommit:
    def test_commit_all_changes(self, local_repo: Path) -> None:
        (local_repo / "new_file.txt").write_text("hello")
        result = git_commit.invoke({"repo_path": str(local_repo), "message": "add new file"})
        assert "add new file" in result

        # Verify commit exists in log
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(local_repo),
            capture_output=True,
            text=True,
        )
        assert "add new file" in log.stdout

    def test_commit_specific_files(self, local_repo: Path) -> None:
        (local_repo / "a.txt").write_text("aaa")
        (local_repo / "b.txt").write_text("bbb")
        result = git_commit.invoke(
            {
                "repo_path": str(local_repo),
                "message": "add only a",
                "files": ["a.txt"],
            }
        )
        assert "add only a" in result

        # b.txt should still be untracked
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(local_repo),
            capture_output=True,
            text=True,
        )
        assert "b.txt" in status.stdout


class TestGitPush:
    def test_push_to_origin(self, local_repo: Path) -> None:
        # Make a new commit to push
        (local_repo / "pushed.txt").write_text("push me")
        subprocess.run(["git", "add", "-A"], cwd=str(local_repo), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "to push"],
            cwd=str(local_repo),
            check=True,
            capture_output=True,
        )

        # Detect default branch name
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(local_repo),
            capture_output=True,
            text=True,
        ).stdout.strip()

        result = git_push.invoke({"repo_path": str(local_repo), "remote": "origin", "ref": branch})
        assert "Pushed" in result or result == ""  # git push may produce empty stdout


class TestGitCheckoutBranch:
    def test_create_and_checkout_branch(self, local_repo: Path) -> None:
        result = git_checkout_branch.invoke(
            {"repo_path": str(local_repo), "branch": "feature-x", "create": True}
        )
        assert "feature-x" in result

        # Verify we're on the new branch
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(local_repo),
            capture_output=True,
            text=True,
        )
        assert branch.stdout.strip() == "feature-x"

    def test_checkout_existing_branch(self, local_repo: Path) -> None:
        # Create a branch first
        subprocess.run(
            ["git", "checkout", "-b", "existing"],
            cwd=str(local_repo),
            check=True,
            capture_output=True,
        )
        # Go back to default branch
        default_branch = (
            subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
                cwd=str(local_repo),
                capture_output=True,
                text=True,
            )
            .stdout.strip()
            .replace("origin/", "")
        )
        subprocess.run(
            ["git", "checkout", default_branch],
            cwd=str(local_repo),
            check=True,
            capture_output=True,
        )

        result = git_checkout_branch.invoke({"repo_path": str(local_repo), "branch": "existing"})
        assert "existing" in result
