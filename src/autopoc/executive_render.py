"""Offline execution and publication packaging for sealed executive inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from autopoc.executive_inputs import MAX_BYTES, TOPICS, verify_inputs

TOPIC_TITLES = dict(
    zip(
        TOPICS,
        (
            "Repository purpose",
            "Testing strategy",
            "Test execution",
            "OpenShift and Kubernetes suitability",
        ),
    )
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_path(path: Path) -> None:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Symbolic links are forbidden")


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _zip(destination: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)


def _tree(root: Path) -> dict[str, bytes]:
    files = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            _safe_path(path)
            if path.is_file():
                files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def _reuse(output: Path, identity: str) -> dict:
    path = output / "presentation-manifest.json"
    _safe_path(path)
    try:
        manifest = json.loads(path.read_text())
        if manifest["status"] != "generated_unpublished" or manifest["input_sha256"] != identity:
            raise ValueError("Output directory conflicts with this render")
        if set(manifest["artifacts"]) != {"source", "deck", "pdf", "video", "summary"}:
            raise ValueError("Output integrity conflict")
        for member in output.rglob("*"):
            _safe_path(member)
        for metadata in manifest["artifacts"].values():
            if metadata["status"] != "generated_unpublished":
                raise ValueError("Output integrity conflict")
            name = metadata["path"]
            if Path(name).name != name:
                raise ValueError("Invalid artifact path")
            artifact = output / name
            _safe_path(artifact)
            raw = artifact.read_bytes()
            if metadata["sha256"] != _sha(raw) or metadata["size"] != len(raw):
                raise ValueError("Output integrity conflict")
        return manifest
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Output directory conflicts with this render") from exc


def _run_renderer(command: list[str], *, timeout: int, log_path: Path | None = None) -> None:
    """Bound the entire renderer process tree, including Chromium and FFmpeg."""
    descriptor = (
        os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        if log_path is not None
        else os.open(os.devnull, os.O_WRONLY)
    )
    with (
        os.fdopen(descriptor, "wb") as log,
        subprocess.Popen(
            command,
            start_new_session=True,
            stdout=log,
            stderr=log,
        ) as process,
    ):
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def _runtime_metrics(
    started: float, roots: list[Path], peak_path: Path = Path("/sys/fs/cgroup/memory.peak")
) -> dict:
    """Measure logical scratch bytes and the container's cgroup peak when available."""
    try:
        peak = int(peak_path.read_text().strip())
        peak = peak if peak > 0 else None
    except (OSError, ValueError):
        peak = None
    size = 0
    selected: list[Path] = []

    def fail_walk(error: OSError) -> None:
        raise error

    try:
        for root in sorted({p.absolute() for p in roots}, key=lambda p: len(p.parts)):
            if any(root.is_relative_to(parent) for parent in selected):
                continue
            _safe_path(root)
            if not root.is_dir():
                raise OSError("Scratch directory unavailable")
            selected.append(root)
            for directory, _, filenames in os.walk(root, followlinks=False, onerror=fail_walk):
                for name in filenames:
                    path = Path(directory) / name
                    if not path.is_symlink():
                        size += path.stat().st_size
    except (OSError, ValueError):
        size = None
    return {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "peak_memory_bytes": peak,
        "scratch_usage_bytes": size,
    }


def render_executive(inputs_path: Path, output_dir: Path, *, timeout: int = 600) -> dict:
    """Verify inputs, render within a deadline, and preserve independently usable outputs.

    Only a complete output with matching input identity and artifact hashes is reused.
    Partial output is retained for inspection; retry in a new empty directory.
    """
    started = time.monotonic()
    if not 1 <= timeout <= 600:
        raise ValueError("Renderer timeout must be between 1 and 600 seconds")
    _safe_path(inputs_path)
    if inputs_path.stat().st_size > MAX_BYTES:
        raise ValueError("Invalid sealed input size")
    # Freeze first so validation and execution always consume the same bytes.
    raw = inputs_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="autopoc-render-") as directory:
        private = Path(directory)
        sealed = private / "render-inputs.zip"
        sealed.write_bytes(raw)
        validated = verify_inputs(sealed)
        identity = _sha(raw)
        _safe_path(output_dir)
        if output_dir.exists() and any(output_dir.iterdir()):
            return _reuse(output_dir, identity)
        output_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(output_dir, 0o700)
        data = private / "inputs"
        data.mkdir(mode=0o700)
        with zipfile.ZipFile(sealed) as archive:
            for name in ("narrative.json", "scenes.json"):
                (data / name).write_bytes(archive.read(name))
            evidence_hash = _sha(archive.read("evidence.zip"))
        renderer = Path(os.environ.get("AUTOPOC_RENDERER_ROOT", "/opt/autopoc/renderer"))
        engine_output = private / "rendered"
        engine_output.mkdir(mode=0o700)
        try:
            _run_renderer(
                ["node", str(renderer / "render.mjs"), str(data), str(engine_output)],
                timeout=timeout,
                log_path=output_dir / "renderer.log",
            )
        except (OSError, subprocess.TimeoutExpired):
            pass  # Independently completed deck/PDF remain useful after video failure or timeout.
        engine_manifest = engine_output / "presentation-manifest.json"
        state = json.loads(engine_manifest.read_text()) if engine_manifest.is_file() else {}
        recovery = {
            "schema_version": 1,
            "run_id": validated["run_id"],
            "input_sha256": identity,
            "evidence_sha256": evidence_hash,
            "renderer_image": validated["versions"]["image"],
            "command": "autopoc-tools executive-render --inputs render-inputs.zip --output-dir output",
        }
        manifest = {
            "schema_version": 1,
            "run_id": validated["run_id"],
            "input_sha256": identity,
            "evidence_sha256": evidence_hash,
            "source_hashes": validated["evidence_index"]["files"],
            "versions": validated["versions"],
            "scenes": state.get("scenes", []),
            "status": "partial",
            "artifacts": {},
        }

        def artifact(key: str, name: str, content: bytes) -> None:
            (output_dir / name).write_bytes(content)
            manifest["artifacts"][key] = {
                "status": "generated_unpublished",
                "path": name,
                "sha256": _sha(content),
                "size": len(content),
            }

        source = engine_output / "source"
        source_files = {
            "render-inputs.zip": raw,
            "recovery.json": json.dumps(recovery, indent=2).encode(),
        }
        # ponytail: fixed trusted template allowlist; extend only with reviewed renderer assets.
        for name in ("slides.md", "package.json", "package-lock.json", "style.css"):
            path = source / name
            _safe_path(path)
            if path.is_file():
                source_files[name] = path.read_bytes()
        for name in ("components", "vendor"):
            source_files.update({f"{name}/{k}": v for k, v in _tree(source / name).items()})
        source_files.update(
            {name: (data / name).read_bytes() for name in ("narrative.json", "scenes.json")}
        )
        for name in ("render.mjs", "README.md"):
            path = renderer / name
            if path.is_file():
                source_files[name] = path.read_bytes()
        (output_dir / "render-inputs.zip").write_bytes(raw)
        _json(output_dir / "recovery.json", recovery)
        _zip(output_dir / "executable-source.zip", source_files)
        artifact(
            "source", "executable-source.zip", (output_dir / "executable-source.zip").read_bytes()
        )
        static = _tree(source / "dist")
        if "index.html" in static:
            _zip(output_dir / "static-site.zip", static)
            artifact("deck", "static-site.zip", (output_dir / "static-site.zip").read_bytes())
        else:
            manifest["artifacts"]["deck"] = {"status": "failed"}
        for key, suffix in (("pdf", "pdf"), ("video", "mp4")):
            path = engine_output / f"executive-summary.{suffix}"
            _safe_path(path)
            if (
                path.is_file()
                and state.get("artifacts", {}).get(key, {}).get("status") == "validated"
            ):
                artifact(key, path.name, path.read_bytes())
            else:
                manifest["artifacts"][key] = {"status": "failed"}
        narrative = validated["narrative"]
        summary = [
            f"# {narrative['project_name']} executive summary",
            f"Run: {validated['run_id']}",
            "Report: archived report.md in render-inputs.zip → evidence.zip.",
        ]
        for topic, title in TOPIC_TITLES.items():
            summary.append(f"\n## {title}\n")
            summary.extend(
                f"- {claim['text']} (Evidence: {', '.join(claim['sources'])})"
                for claim in narrative[topic]
            )
        summary.append("\n## Limitations\n")
        summary.extend(f"- {text}" for text in narrative["limitations"])
        for key, metadata in manifest["artifacts"].items():
            if metadata["status"] == "failed":
                summary.append(
                    f"- {key.title()} generation failed; available outputs are retained."
                )
            else:
                summary.append(f"- [{key.title()}]({metadata['path']}) — generated, unpublished.")
        summary.append(
            "- Silent video; animation timing is illustrative. No live tests were replayed."
        )
        artifact("summary", "executive-summary.md", ("\n\n".join(summary) + "\n").encode())
        if all(a["status"] == "generated_unpublished" for a in manifest["artifacts"].values()):
            manifest["status"] = "generated_unpublished"
        roots = [private, output_dir]
        roots.extend(
            Path(os.environ[name]) for name in ("TMPDIR", "XDG_CACHE_HOME") if name in os.environ
        )
        manifest["runtime"] = _runtime_metrics(started, roots)
        _json(output_dir / "presentation-manifest.json", manifest)
        return manifest


def cmd_executive_render(args: argparse.Namespace) -> None:
    """Run the standalone offline renderer; publication is managed separately."""
    if args.inputs:
        if not args.output_dir:
            raise ValueError("Local rendering requires --output-dir")
        result = render_executive(Path(args.inputs), Path(args.output_dir))
    else:
        from autopoc.executive_cluster import render_remote

        result = render_remote(args)
    print(json.dumps(result, indent=2))
    if result.get("status") in {"partial", "failed"}:
        raise SystemExit(1)


def register_cli(subparsers) -> None:
    """Register with the existing argparse tool dispatcher."""
    parser = subparsers.add_parser("executive-render", help="Render a verified sealed input ZIP")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inputs")
    mode.add_argument("--input-id")
    parser.add_argument("--output-dir")
    parser.add_argument("--input-sha256")
    parser.add_argument("--recovery-id")
    parser.add_argument("--recovery-sha256")
    parser.set_defaults(func=cmd_executive_render)
