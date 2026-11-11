"""Append-only artifact Git persistence, isolated from the source checkout.

Callers must sanitize/validate publication payloads first. Git diagnostics are
never returned because remote URLs may contain credentials. Content revisions
hash a sorted JSON manifest of filenames, byte sizes and SHA-256 digests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

BRANCH = "autopoc-artifacts"


class ArtifactError(ValueError):
    """A safe-to-display artifact persistence failure."""


def _identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ArtifactError("Invalid artifact identifier")


def _git(
    repo: Path, *args: str, allowed: tuple[int, ...] = (0,)
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        raise ArtifactError("Artifact Git operation failed") from None
    if result.returncode not in allowed:
        raise ArtifactError("Artifact Git operation failed")
    return result


def _safe_target(root: Path, relative: str) -> Path:
    target = root
    for part in PurePosixPath(relative).parts:
        target = target / part
        if target.is_symlink():
            raise ArtifactError("Artifact tree contains a symbolic link")
    return target


def publish_artifacts(
    repo_path: Path,
    run_id: str,
    kind: str,
    files: Mapping[str, Path],
    *,
    remote: str = "origin",
    max_attempts: int = 3,
    head_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Persist immutable payloads and per-kind heads with bounded push retries.

    Every attempt fetches the current remote artifact head into a fresh private
    repository. Concurrent pushes are reconciled by replaying this append on the
    new head. Source branches, index and untracked files are never touched.
    """
    _identifier(run_id)
    _identifier(kind)
    _identifier(remote)
    heads = list(head_names) if head_names is not None else [kind]
    if not heads or len(heads) > 16 or len(set(heads)) != len(heads):
        raise ArtifactError("Invalid artifact head names")
    for name in heads:
        _identifier(name)
    if not 1 <= max_attempts <= 20 or not files:
        raise ArtifactError("Invalid artifact publication request")
    payloads = {}
    try:
        for name, source in files.items():
            path = PurePosixPath(name)
            if (
                not name
                or path.is_absolute()
                or str(path) != name
                or any(part in (".", "..", ".git") for part in path.parts)
                or "\\" in name
            ):
                raise ArtifactError("Invalid artifact filename")
            if source.is_symlink() or not source.is_file():
                raise ArtifactError("Invalid artifact source file")
            payloads[name] = source.read_bytes()
    except OSError:
        raise ArtifactError("Cannot read artifact source") from None
    manifest = {
        name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(payloads.items())
    }
    revision = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    relative = f"runs/{run_id}/{kind}/{revision}"
    pointer = {"run_id": run_id, "kind": kind, "revision": revision, "path": relative}
    pointer_bytes = (json.dumps(pointer, sort_keys=True) + "\n").encode()
    url = _git(repo_path, "remote", "get-url", remote).stdout.strip()
    if not url or url.startswith("-"):
        raise ArtifactError("Invalid artifact remote")
    try:
        with tempfile.TemporaryDirectory(prefix="autopoc-artifacts-") as temporary:
            for attempt in range(max_attempts):
                checkout = Path(temporary) / str(attempt)
                checkout.mkdir(mode=0o700)
                _git(checkout, "init", "--quiet")
                _git(checkout, "remote", "add", "origin", url)
                exists = _git(
                    checkout,
                    "ls-remote",
                    "--exit-code",
                    "origin",
                    f"refs/heads/{BRANCH}",
                    allowed=(0, 2),
                )
                if exists.returncode == 0:
                    _git(checkout, "fetch", "--quiet", "origin", f"refs/heads/{BRANCH}")
                    _git(checkout, "checkout", "--quiet", "-b", BRANCH, "FETCH_HEAD")
                else:
                    _git(checkout, "checkout", "--quiet", "--orphan", BRANCH)
                destination = _safe_target(checkout, relative)
                if destination.exists():
                    actual = {}
                    for path in destination.rglob("*"):
                        if path.is_symlink():
                            raise ArtifactError("Immutable artifact revision conflicts")
                        if path.is_file():
                            actual[path.relative_to(destination).as_posix()] = path.read_bytes()
                    if actual != payloads:
                        raise ArtifactError("Immutable artifact revision conflicts")
                else:
                    destination.mkdir(parents=True)
                    for name, data in payloads.items():
                        target = _safe_target(destination, name)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                for head in heads:
                    target = _safe_target(checkout, f"runs/{run_id}/heads/{head}.json")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(pointer_bytes)
                _git(checkout, "add", "--", "runs")
                changed = _git(checkout, "diff", "--cached", "--quiet", allowed=(0, 1)).returncode
                if changed:
                    _git(
                        checkout,
                        "-c",
                        "user.name=AutoPoC",
                        "-c",
                        "user.email=autopoc@localhost",
                        "-c",
                        "commit.gpgsign=false",
                        "commit",
                        "--quiet",
                        "-m",
                        f"Persist {kind} artifact revision",
                    )
                commit = _git(checkout, "rev-parse", "HEAD").stdout.strip()
                pushed = _git(
                    checkout,
                    "push",
                    "--quiet",
                    "origin",
                    f"HEAD:refs/heads/{BRANCH}",
                    allowed=(0, 1, 128),
                )
                if pushed.returncode == 0:
                    return {
                        **pointer,
                        "commit": commit,
                        "head_paths": [f"runs/{run_id}/heads/{head}.json" for head in heads],
                    }
    except OSError:
        raise ArtifactError("Cannot persist artifact files") from None
    raise ArtifactError("Artifact push failed after bounded retries")


def _command(args: argparse.Namespace) -> None:
    try:
        files = {}
        for item in args.file:
            name, separator, source = item.partition("=")
            if not separator or name in files:
                raise ArtifactError("Use unique NAME=PATH artifact files")
            files[name] = Path(source)
        result = publish_artifacts(args.repo, args.run_id, args.kind, files, head_names=args.head)
    except ArtifactError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))


def register_artifact_commands(subparsers: Any) -> None:
    """Register the publication CLI without importing the main dispatcher."""
    parser = subparsers.add_parser("artifact-publish", help="Append sanitized artifacts to Git")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--file", action="append", required=True, metavar="NAME=PATH")
    parser.add_argument("--head", action="append", help="Head name (repeat for atomic pointers)")
    parser.set_defaults(func=_command)
