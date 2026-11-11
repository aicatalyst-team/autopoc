"""Real Git integration coverage for append-only artifact publication."""

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    source = tmp_path / "source"
    subprocess.run(["git", "clone", str(remote), str(source)], check=True, capture_output=True)
    git(source, "config", "user.name", "Test")
    git(source, "config", "user.email", "test@example.test")
    (source / "README.md").write_text("source")
    git(source, "add", ".")
    git(source, "commit", "-m", "source")
    git(source, "push", "origin", "HEAD:main")
    return source, remote


def test_pipeline_preserves_all_revisions_and_source_checkout(repository, tmp_path):
    from autopoc.artifacts import publish_artifacts

    source, remote = repository
    (source / "README.md").write_text("uncommitted source")
    (source / "private-untracked").write_text("keep me")
    original = git(source, "status", "--porcelain")
    canonical = tmp_path / "canonical.md"
    canonical.write_text("# Report\nFive passed\n")
    canonical_hash = hashlib.sha256(canonical.read_bytes()).hexdigest()
    publications = []
    for kind in ["plan", "tests", "report", "executive", "blog"]:
        payload = canonical if kind == "report" else tmp_path / f"{kind}.md"
        if kind != "report":
            payload.write_text(kind)
        publications.append(publish_artifacts(source, "run-123", kind, {payload.name: payload}))
    linked = tmp_path / "linked.md"
    linked.write_text(
        canonical.read_text() + "\n<!-- executive-links -->deck<!-- /executive-links -->"
    )
    revised = publish_artifacts(source, "run-123", "report", {"canonical.md": linked})
    for entry in publications + [revised]:
        assert git(
            remote,
            "show",
            f"autopoc-artifacts:{entry['path']}/"
            + ("canonical.md" if entry["kind"] == "report" else entry["kind"] + ".md"),
        )
    assert hashlib.sha256(canonical.read_bytes()).hexdigest() == canonical_hash
    assert git(source, "status", "--porcelain") == original
    assert (source / "private-untracked").read_text() == "keep me"
    assert git(remote, "show", "main:README.md") == "source"
    assert (
        json.loads(git(remote, "show", "autopoc-artifacts:runs/run-123/heads/report.json"))[
            "revision"
        ]
        == revised["revision"]
    )
    assert (
        publish_artifacts(source, "run-123", "report", {"canonical.md": linked})["commit"]
        == revised["commit"]
    )


def test_competing_writers_preserve_every_payload(repository, tmp_path):
    from autopoc.artifacts import publish_artifacts

    source, remote = repository
    payloads = []
    for index in range(4):
        path = tmp_path / f"{index}.md"
        path.write_text(f"writer {index}")
        payloads.append(path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        entries = list(
            pool.map(
                lambda path: publish_artifacts(
                    source, "concurrent", "report", {"report.md": path}, max_attempts=10
                ),
                payloads,
            )
        )
    for index, entry in enumerate(entries):
        assert (
            git(remote, "show", f"autopoc-artifacts:{entry['path']}/report.md") == f"writer {index}"
        )


def test_remote_errors_never_expose_credentials(repository, tmp_path):
    from autopoc.artifacts import ArtifactError, publish_artifacts

    source, _ = repository
    git(source, "remote", "set-url", "origin", str(tmp_path / "token-super-secret.git"))
    payload = tmp_path / "report.md"
    payload.write_text("safe")
    with pytest.raises(ArtifactError) as error:
        publish_artifacts(source, "run", "report", {"report.md": payload})
    assert "secret" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


@pytest.mark.parametrize(
    "run_id,kind,name",
    [
        ("../escape", "report", "a"),
        ("run", "main", "../a"),
        ("run", "../x", "a"),
        ("run", "report", ".git/config"),
    ],
)
def test_unsafe_paths_fail_before_publication(repository, tmp_path, run_id, kind, name):
    from autopoc.artifacts import ArtifactError, publish_artifacts

    payload = tmp_path / "input"
    payload.write_text("safe")
    with pytest.raises(ArtifactError):
        publish_artifacts(repository[0], run_id, kind, {name: payload})


def test_atomic_heads_and_existing_revision_corruption_fail(repository, tmp_path):
    from autopoc.artifacts import ArtifactError, publish_artifacts

    source, remote = repository
    payload = tmp_path / "canonical.md"
    payload.write_text("original report")
    entry = publish_artifacts(
        source, "run", "report", {"report.md": payload}, head_names=["report", "executive"]
    )
    assert git(remote, "show", "autopoc-artifacts:runs/run/heads/report.json") == git(
        remote, "show", "autopoc-artifacts:runs/run/heads/executive.json"
    )
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", "--branch", "autopoc-artifacts", str(remote), str(other)],
        check=True,
        capture_output=True,
    )
    (other / entry["path"] / "report.md").write_text("tampered")
    git(other, "add", ".")
    git(
        other,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.test",
        "commit",
        "-m",
        "corrupt",
    )
    git(other, "push")
    with pytest.raises(ArtifactError, match="conflicts"):
        publish_artifacts(source, "run", "report", {"report.md": payload})
    assert git(remote, "show", f"autopoc-artifacts:{entry['path']}/report.md") == "tampered"


def test_push_rejection_fails_boundedly_without_changing_remote(repository, tmp_path):
    from autopoc.artifacts import ArtifactError, publish_artifacts

    source, remote = repository
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho token-super-secret >&2\nexit 1\n")
    hook.chmod(0o700)
    payload = tmp_path / "payload"
    payload.write_text("report")
    with pytest.raises(ArtifactError, match="bounded retries") as error:
        publish_artifacts(source, "run", "report", {"report.md": payload}, max_attempts=2)
    assert "secret" not in str(error.value)
    assert git(remote, "branch", "--list", "autopoc-artifacts") == ""


def test_cli_registration_publishes_json_and_sanitizes_failure(repository, tmp_path, capsys):
    import argparse

    from autopoc.artifacts import register_artifact_commands

    parser = argparse.ArgumentParser()
    register_artifact_commands(parser.add_subparsers(required=True))
    payload = tmp_path / "report.md"
    payload.write_text("report")
    args = parser.parse_args(
        [
            "artifact-publish",
            "--repo",
            str(repository[0]),
            "--run-id",
            "run",
            "--kind",
            "report",
            "--file",
            f"report.md={payload}",
        ]
    )
    args.func(args)
    assert json.loads(capsys.readouterr().out)["path"].startswith("runs/run/report/")
    args.file = ["report.md=/nonexistent/token-secret"]
    with pytest.raises(SystemExit) as error:
        args.func(args)
    assert error.value.code == 1
    assert "secret" not in capsys.readouterr().err


def test_legacy_branch_reset_loses_report_and_links(repository, tmp_path):
    """Characterize the old failure: the blog resets history to source HEAD."""
    source, remote = repository
    (source / "poc-report.md").write_text("report with executive link")
    git(source, "checkout", "-B", "autopoc-artifacts")
    git(source, "add", "poc-report.md")
    git(source, "commit", "-m", "report")
    git(source, "push", "origin", "autopoc-artifacts")
    git(source, "checkout", "-")
    assert not (source / "poc-report.md").exists()
    git(source, "checkout", "-B", "autopoc-artifacts")
    (source / "blog.md").write_text("blog")
    git(source, "add", "blog.md")
    git(source, "commit", "-m", "blog")
    git(source, "push", "--force", "origin", "autopoc-artifacts")
    assert "poc-report.md" not in git(remote, "ls-tree", "--name-only", "autopoc-artifacts")
