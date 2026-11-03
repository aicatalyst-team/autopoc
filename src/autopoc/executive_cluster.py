"""Durable executive extension journal, independent of the eleven PoC phases.

The Git checkpoint discovers immutable Drive inputs and preallocated output
journal slots. The renderer writes each intent before its binary upload, then
a receipt, without cluster API permissions or Git credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from autopoc.artifacts import _git, _identifier, publish_artifacts
from autopoc.executive_inputs import MAX_BYTES, verify_inputs

ARTIFACTS = {
    "source": "executable-source.zip",
    "deck": "static-site.zip",
    "pdf": "executive-summary.pdf",
    "video": "executive-summary.mp4",
    "summary": "executive-summary.md",
    "manifest": "presentation-manifest.json",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    path.chmod(0o600)


def _immutable_file(path: Path, raw: bytes) -> None:
    path = path.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symbolic links are forbidden in recovery paths")
    if path.exists():
        if not path.is_file() or path.stat().st_size != len(raw) or path.read_bytes() != raw:
            raise ValueError("Recovery destination contains different content")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != raw:
                raise ValueError("Recovery destination conflicts") from None
    finally:
        temporary.unlink(missing_ok=True)


def load_checkpoint(repo: Path, run_id: str) -> dict | None:
    """Read a remote run checkpoint without changing the source checkout."""
    _identifier(run_id)
    url = _git(repo, "remote", "get-url", "origin").stdout.strip()
    with tempfile.TemporaryDirectory(prefix="autopoc-read-checkpoint-") as directory:
        checkout = Path(directory)
        _git(checkout, "init", "--quiet")
        _git(checkout, "remote", "add", "origin", url)
        exists = _git(
            checkout,
            "ls-remote",
            "--exit-code",
            "origin",
            "refs/heads/autopoc-artifacts",
            allowed=(0, 2),
        )
        if exists.returncode == 2:
            return None
        _git(checkout, "fetch", "--quiet", "--depth=1", "origin", "refs/heads/autopoc-artifacts")
        pointer = _git(
            checkout, "show", f"FETCH_HEAD:runs/{run_id}/heads/recovery.json", allowed=(0, 128)
        )
        if pointer.returncode == 128:
            return None
        head = json.loads(pointer.stdout)
        path = head.get("path", "")
        if not re.fullmatch(rf"runs/{re.escape(run_id)}/recovery/[0-9a-f]{{64}}", path):
            raise ValueError("Invalid recovery checkpoint pointer")
        raw = _git(checkout, "show", f"FETCH_HEAD:{path}/recovery.json").stdout
        if len(raw) > 1024 * 1024:
            raise ValueError("Oversized recovery checkpoint")
        checkpoint = json.loads(raw)
        if checkpoint.get("schema_version") != 1 or checkpoint.get("run_id") != run_id:
            raise ValueError("Unsupported recovery checkpoint")
        if not checkpoint.get("git_inputs"):
            backup = _git(
                checkout, "cat-file", "-e", f"FETCH_HEAD:{path}/render-inputs.zip", allowed=(0, 128)
            )
            if backup.returncode == 0:
                checkpoint["git_inputs"] = {
                    "commit": _git(checkout, "rev-parse", "FETCH_HEAD").stdout.strip(),
                    "path": f"{path}/render-inputs.zip",
                }
        return checkpoint


def _persist(repo: Path, checkpoint: dict, *, inputs: Path | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="autopoc-checkpoint-") as directory:
        path = Path(directory) / "recovery.json"
        _json(path, checkpoint)
        files = {"recovery.json": path}
        if inputs is not None:
            files["render-inputs.zip"] = inputs
        publication = publish_artifacts(repo, checkpoint["run_id"], "recovery", files)
        if inputs is not None:
            checkpoint["git_inputs"] = {
                "commit": publication["commit"],
                "path": f"{publication['path']}/render-inputs.zip",
            }


def _descriptor(checkpoint: dict) -> dict:
    return {
        key: checkpoint[key]
        for key in (
            "schema_version",
            "run_id",
            "revision",
            "input_sha256",
            "input_id",
            "folder_id",
            "image",
            "slots",
        )
    }


def prepare_publication(
    repo: Path,
    inputs: Path,
    folder_id: str,
    drive,
    *,
    new_attempt: bool = False,
    launch_namespace: str | None = None,
    credentials_secret: str = "autopoc-google-sa",
) -> dict:
    """Persist upload identities before side effects, then verify durable inputs."""
    validated = verify_inputs(inputs)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", folder_id):
        raise ValueError("Explicit Drive destination required")
    raw = inputs.read_bytes()
    identity = _sha(raw)
    run_id = validated["run_id"]
    checkpoint = load_checkpoint(repo, run_id)
    previous_attempt = checkpoint.get("attempt", 1) if checkpoint else 0
    if new_attempt and previous_attempt >= 3:
        raise ValueError("Renderer retry limit reached")
    if checkpoint and checkpoint["input_sha256"] == identity and not new_attempt:
        if checkpoint["folder_id"] != folder_id:
            raise ValueError("Recovery destination differs from existing intent")
    else:
        checkpoint = {
            "schema_version": 1,
            "run_id": run_id,
            "revision": _sha(f"{identity}/{uuid.uuid4().hex}".encode())
            if new_attempt
            else identity,
            "attempt": previous_attempt + 1 if new_attempt else 1,
            "input_sha256": identity,
            "input_size": len(raw),
            "input_id": drive.allocate_file_id(),
            "recovery_id": drive.allocate_file_id(),
            "folder_id": folder_id,
            "image": validated["versions"]["image"],
            "status": "input_upload_pending",
            "slots": {
                kind: {
                    name: drive.allocate_file_id()
                    for name in ("file_id", "intent_id", "receipt_id")
                }
                for kind in ARTIFACTS
            },
        }
        # The checkpoint is the durable upload intent, including content hash.
        if launch_namespace:
            checkpoint["launch"] = {
                "namespace": launch_namespace,
                "credentials_secret": credentials_secret,
            }
        _persist(repo, checkpoint, inputs=inputs)
    if launch_namespace:
        launch = {"namespace": launch_namespace, "credentials_secret": credentials_secret}
        if checkpoint.get("launch", launch) != launch:
            raise ValueError("Launch configuration differs from durable intent")
        checkpoint["launch"] = launch
    with tempfile.TemporaryDirectory(prefix="autopoc-publish-inputs-") as directory:
        temporary = Path(directory)
        descriptor = temporary / "recovery.json"
        _json(descriptor, _descriptor(checkpoint))
        descriptor_hash = _sha(descriptor.read_bytes())
        if checkpoint.get("recovery_sha256") not in (None, descriptor_hash):
            raise ValueError("Recovery descriptor conflicts with saved intent")
        checkpoint["recovery_sha256"] = descriptor_hash
        _persist(repo, checkpoint)
        drive.upload_file_once(str(inputs), checkpoint["input_id"], folder_id)
        drive.download_file(
            checkpoint["input_id"], temporary / "verified-inputs.zip", identity, max_bytes=MAX_BYTES
        )
        drive.upload_file_once(str(descriptor), checkpoint["recovery_id"], folder_id)
        drive.download_file(
            checkpoint["recovery_id"],
            temporary / "verified-recovery.json",
            descriptor_hash,
            max_bytes=1024 * 1024,
        )
    if checkpoint["status"] == "input_upload_pending":
        checkpoint["status"] = "inputs_published"
    _persist(repo, checkpoint)
    return checkpoint


def _kubectl(arguments: list[str], payload: str | None = None) -> dict:
    result = subprocess.run(
        ["kubectl", *arguments],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise RuntimeError("Renderer cluster operation failed")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def submit_renderer(
    repo: Path,
    run_id: str,
    namespace: str,
    *,
    wait_seconds: int = 300,
    credentials_secret: str = "autopoc-google-sa",
) -> dict:
    """Reconcile deterministic Job identity and wait only within the worker budget."""
    from autopoc.executive_job import build_renderer_job

    if not 0 <= wait_seconds <= 600:
        raise ValueError("Worker wait must be between 0 and 600 seconds")
    checkpoint = load_checkpoint(repo, run_id)
    if not checkpoint or checkpoint["status"] == "input_upload_pending":
        raise ValueError("Durable render inputs are required before dispatch")
    manifest = build_renderer_job(
        run_id,
        checkpoint["revision"],
        checkpoint["image"],
        checkpoint["input_id"],
        checkpoint["input_sha256"],
        checkpoint["recovery_id"],
        namespace,
        recovery_sha256=checkpoint["recovery_sha256"],
        credentials_secret=credentials_secret,
    )
    name = manifest["metadata"]["name"]
    old_job = checkpoint.get("job", {})
    if old_job.get("namespace", namespace) != namespace:
        raise ValueError("Resume namespace differs from saved Job identity")
    checkpoint["job"] = {
        **old_job,
        "name": name,
        "namespace": namespace,
        "status": "submission_pending",
    }
    _persist(repo, checkpoint)
    get = ["get", "job", name, "-n", namespace, "--ignore-not-found=true", "-o", "json"]
    try:
        existing = _kubectl(get)
        if not existing:
            if old_job.get("uid") or checkpoint.get("artifacts"):
                raise ValueError("Prior Job disappeared; reconcile outputs or start a new attempt")
            attempts = checkpoint.get("submission_attempts", 0)
            if attempts >= 3:
                raise ValueError("Job submission retry limit reached")
            checkpoint["submission_attempts"] = attempts + 1
            _persist(repo, checkpoint)
            try:
                existing = _kubectl(["create", "-f", "-", "-o", "json"], json.dumps(manifest))
            except (OSError, RuntimeError, subprocess.SubprocessError):
                existing = _kubectl(get)
                if not existing:
                    raise RuntimeError("Renderer Job was not admitted") from None
        actual_container = existing["spec"]["template"]["spec"]["containers"][0]
        expected_container = manifest["spec"]["template"]["spec"]["containers"][0]
        if any(actual_container.get(key) != expected_container[key] for key in ("image", "args")):
            raise ValueError("Existing Job differs from the saved render intent")
        uid = existing["metadata"]["uid"]
        if old_job.get("uid", uid) != uid:
            raise ValueError("Existing Job UID differs from the saved render intent")
        checkpoint["job"].update({"uid": uid, "status": "running"})
        checkpoint["status"] = "render_submitted"
        _persist(repo, checkpoint)
        deadline = time.monotonic() + wait_seconds
        while True:
            status = existing.get("status", {})
            if status.get("succeeded"):
                checkpoint["job"]["status"] = "completed"
                break
            if status.get("failed"):
                checkpoint["job"]["status"] = "failed"
                checkpoint["status"] = "failed"
                break
            if time.monotonic() >= deadline:
                checkpoint["job"]["status"] = "wait_expired"
                break
            time.sleep(min(5, max(0, deadline - time.monotonic())))
            existing = _kubectl(get)
        _persist(repo, checkpoint)
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError):
        checkpoint["job"]["status"] = "failed"
        checkpoint["status"] = "failed"
        checkpoint["error"] = "Renderer admission or reconciliation failed"
        _persist(repo, checkpoint)
    return checkpoint


def recover_inputs(repo: Path, run_id: str, destination: Path, drive) -> Path:
    """Recover a sealed render revision without the original worker workspace."""
    checkpoint = load_checkpoint(repo, run_id)
    if not checkpoint:
        raise ValueError("Render inputs are not durably published")
    destination = destination.absolute()
    if any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError("Symbolic links are forbidden in recovery paths")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = destination / "render-inputs.zip"
    if checkpoint["status"] == "input_upload_pending" and checkpoint.get("git_inputs"):
        backup = checkpoint["git_inputs"]
        if not re.fullmatch(r"[0-9a-f]{40,64}", backup.get("commit", "")) or not re.fullmatch(
            rf"runs/{re.escape(run_id)}/recovery/[0-9a-f]{{64}}/render-inputs.zip",
            backup.get("path", ""),
        ):
            raise ValueError("Invalid sealed Git backup reference")
        with tempfile.TemporaryDirectory(prefix="autopoc-git-inputs-") as directory:
            checkout = Path(directory)
            _git(checkout, "init", "--quiet")
            url = _git(repo, "remote", "get-url", "origin").stdout.strip()
            _git(checkout, "remote", "add", "origin", url)
            _git(checkout, "fetch", "--quiet", "--depth=1", "origin", backup["commit"])
            ref = f"FETCH_HEAD:{backup['path']}"
            size = int(_git(checkout, "cat-file", "-s", ref).stdout)
            if not 0 < size <= MAX_BYTES:
                raise ValueError("Sealed Git backup exceeds size limit")
            raw = subprocess.run(
                ["git", "-C", str(checkout), "show", ref],
                capture_output=True,
                timeout=60,
                check=False,
            )
            if (
                raw.returncode
                or len(raw.stdout) != size
                or _sha(raw.stdout) != checkpoint["input_sha256"]
            ):
                raise ValueError("Sealed Git backup integrity mismatch")
            _immutable_file(path, raw.stdout)
    else:
        drive.download_file(
            checkpoint["input_id"], path, checkpoint["input_sha256"], max_bytes=MAX_BYTES
        )
    validated = verify_inputs(path)
    if validated["run_id"] != run_id:
        raise ValueError("Recovered run identity differs")
    if checkpoint["status"] == "input_upload_pending":
        descriptor = destination / "recovery.json"
        _immutable_file(
            descriptor,
            (json.dumps(_descriptor(checkpoint), sort_keys=True, indent=2) + "\n").encode(),
        )
        digest = _sha(descriptor.read_bytes())
        if checkpoint.get("recovery_sha256") not in (None, digest):
            raise ValueError("Recovered descriptor integrity mismatch")
        checkpoint["recovery_sha256"] = digest
        _persist(repo, checkpoint)
        drive.upload_file_once(str(path), checkpoint["input_id"], checkpoint["folder_id"])
        drive.download_file(
            checkpoint["input_id"],
            destination / "verified-inputs.zip",
            checkpoint["input_sha256"],
            max_bytes=MAX_BYTES,
        )
        drive.upload_file_once(str(descriptor), checkpoint["recovery_id"], checkpoint["folder_id"])
        drive.download_file(
            checkpoint["recovery_id"],
            destination / "verified-recovery.json",
            digest,
            max_bytes=1024 * 1024,
        )
        checkpoint["status"] = "inputs_published"
        _persist(repo, checkpoint)
    return path


def _drive():
    from autopoc.tools.google_drive_tools import GoogleDriveService

    credentials = os.environ.get("AUTOPOC_SHEET_CREDENTIALS")
    if not credentials:
        raise ValueError("Configured Drive credentials are required")
    return GoogleDriveService(credentials)


def _receipt(checkpoint: dict, kind: str, value: dict) -> dict:
    expected = {
        "run_id": checkpoint["run_id"],
        "revision": checkpoint["revision"],
        "input_sha256": checkpoint["input_sha256"],
        "kind": kind,
        "file_id": checkpoint["slots"][kind]["file_id"],
    }
    if (
        any(value.get(key) != expected_value for key, expected_value in expected.items())
        or not re.fullmatch(r"[0-9a-f]{64}", value.get("sha256", ""))
        or type(value.get("size")) is not int
        or not 0 < value["size"] <= 256 * 1024 * 1024
    ):
        raise ValueError("Output receipt differs from durable render identity")
    file_id = value["file_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", file_id):
        raise ValueError("Invalid output identity")
    return {
        **expected,
        "sha256": value["sha256"],
        "size": value["size"],
        "web_view_link": f"https://drive.google.com/file/d/{file_id}/view",
        "status": "published",
    }


def render_remote(args, *, drive=None) -> dict:
    """Renderer pod entry point: verify durable inputs and publish journaled outputs."""
    from autopoc.executive_render import render_executive

    drive = drive or _drive()
    output = Path(args.output_dir or "/scratch/output")
    output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix="executive-inputs-") as directory:
        temporary = Path(directory)
        descriptor = temporary / "recovery.json"
        drive.download_file(
            args.recovery_id, descriptor, args.recovery_sha256, max_bytes=1024 * 1024
        )
        checkpoint = json.loads(descriptor.read_text())
        if (
            checkpoint.get("schema_version") != 1
            or checkpoint.get("input_id") != args.input_id
            or checkpoint.get("input_sha256") != args.input_sha256
        ):
            raise ValueError("Renderer arguments differ from durable input identity")
        inputs = temporary / "render-inputs.zip"
        drive.download_file(args.input_id, inputs, args.input_sha256, max_bytes=MAX_BYTES)
        verified = verify_inputs(inputs)
        if (
            verified["run_id"] != checkpoint["run_id"]
            or verified["versions"]["image"] != checkpoint["image"]
        ):
            raise ValueError("Renderer identity differs from sealed inputs")
        manifest = render_executive(inputs, output)
        if manifest.get("run_id") != checkpoint["run_id"]:
            raise ValueError("Rendered run identity differs")
        published = {}

        def publish(kind: str, path: Path) -> dict:
            raw = path.read_bytes()
            intent = {
                "schema_version": 1,
                "run_id": checkpoint["run_id"],
                "revision": checkpoint["revision"],
                "input_sha256": args.input_sha256,
                "kind": kind,
                "file_id": checkpoint["slots"][kind]["file_id"],
                "sha256": _sha(raw),
                "size": len(raw),
            }
            slot = checkpoint["slots"][kind]
            intent_path = temporary / f"{kind}-intent.json"
            _json(intent_path, intent)
            drive.upload_file_once(str(intent_path), slot["intent_id"], checkpoint["folder_id"])
            # No binary upload occurs until its hash/ID intent is durable.
            drive.upload_file_once(str(path), slot["file_id"], checkpoint["folder_id"])
            drive.download_file(
                slot["file_id"], temporary / f"verified-{path.name}", intent["sha256"]
            )
            receipt = _receipt(checkpoint, kind, intent)
            receipt_path = temporary / f"{kind}-receipt.json"
            _json(receipt_path, receipt)
            drive.upload_file_once(str(receipt_path), slot["receipt_id"], checkpoint["folder_id"])
            return receipt

        for kind, name in ARTIFACTS.items():
            if kind == "manifest":
                continue
            metadata = manifest["artifacts"].get(kind, {})
            if metadata.get("status") != "generated_unpublished":
                continue
            path = output / name
            if metadata.get("path") != name or _sha(path.read_bytes()) != metadata.get("sha256"):
                raise ValueError("Rendered artifact integrity differs")
            if kind == "summary":
                with path.open("a") as stream:
                    stream.write("\n\n## Published outputs\n\n")
                    for label, receipt in published.items():
                        stream.write(f"- [{label.title()}]({receipt['web_view_link']})\n")
            try:
                published[kind] = publish(kind, path)
                manifest["artifacts"][kind] = published[kind]
            except (OSError, ValueError, RuntimeError):
                manifest["artifacts"][kind] = {"status": "publication_failed"}
        manifest["status"] = "outputs_published" if len(published) == 5 else "partial"
        _json(output / ARTIFACTS["manifest"], manifest)
        publish("manifest", output / ARTIFACTS["manifest"])
        return manifest


def _linked_report(canonical: str, artifacts: dict, status: str) -> str:
    start, end = "<!-- autopoc-executive:start -->", "<!-- autopoc-executive:end -->"
    links = [start, "### Executive presentation and video", "", f"Generation status: **{status}**."]
    titles = {
        "deck": "Browser presentation ZIP (download and serve locally)",
        "source": "Editable Slidev source",
        "pdf": "Executive PDF",
        "video": "Silent executive video",
        "summary": "Executive summary",
        "manifest": "Artifact manifest",
    }
    for kind, receipt in artifacts.items():
        links.append(f"- [{titles[kind]}]({receipt['web_view_link']})")
    if "video" not in artifacts:
        links.append("- Video unavailable; available presentation outputs are retained.")
    links.extend(["", end])
    block = "\n".join(links)
    if start in canonical or end in canonical:
        if canonical.count(start) != 1 or canonical.count(end) != 1:
            raise ValueError("Ambiguous generated report links")
        return re.sub(
            re.escape(start) + r".*?" + re.escape(end), lambda _: block, canonical, flags=re.DOTALL
        )
    heading = re.search(r"(?im)^#{1,6}[^\n]*executive summary[^\n]*$", canonical)
    if heading:
        return canonical[: heading.end()] + "\n\n" + block + canonical[heading.end() :]
    return canonical + "\n\n" + block + "\n"


def reconcile_outputs(repo: Path, run_id: str, state_path: Path | None, drive) -> dict:
    """Discover renderer receipts even after blog completion or worker deletion."""
    import zipfile

    import yaml

    from autopoc.capture import _write

    checkpoint = load_checkpoint(repo, run_id)
    if not checkpoint:
        return {"status": "pending", "run_id": run_id}
    artifacts = {}
    with tempfile.TemporaryDirectory(prefix="autopoc-reconcile-") as directory:
        temporary = Path(directory)
        if checkpoint["status"] == "input_upload_pending":
            recover_inputs(repo, run_id, temporary / "pending-inputs", drive)
            recovered_checkpoint = load_checkpoint(repo, run_id)
            if recovered_checkpoint is None:
                raise ValueError("Recovery checkpoint disappeared")
            checkpoint = recovered_checkpoint
        for kind, filename in ARTIFACTS.items():
            value = drive.read_json(checkpoint["slots"][kind]["receipt_id"])
            if value is None:
                intent = drive.read_json(checkpoint["slots"][kind]["intent_id"])
                if intent is None:
                    continue
                from googleapiclient.errors import HttpError

                receipt = _receipt(checkpoint, kind, intent)
                try:
                    drive.download_file(receipt["file_id"], temporary / filename, receipt["sha256"])
                except HttpError as exc:
                    if exc.resp.status == 404:
                        continue
                    raise
                except KeyError:
                    continue
                receipt_path = temporary / f"{kind}-recovered-receipt.json"
                _json(receipt_path, receipt)
                drive.upload_file_once(
                    str(receipt_path),
                    checkpoint["slots"][kind]["receipt_id"],
                    checkpoint["folder_id"],
                )
                value = receipt
            receipt = _receipt(checkpoint, kind, value)
            drive.download_file(receipt["file_id"], temporary / filename, receipt["sha256"])
            artifacts[kind] = receipt
        if checkpoint.get("launch") and len(artifacts) != len(ARTIFACTS):
            checkpoint["artifacts"] = artifacts
            _persist(repo, checkpoint)
            launch = checkpoint["launch"]
            checkpoint = submit_renderer(
                repo,
                run_id,
                launch["namespace"],
                wait_seconds=0,
                credentials_secret=launch["credentials_secret"],
            )
        job = checkpoint.get("job")
        if job and job.get("uid") and job.get("status") not in ("completed", "failed"):
            observed = _kubectl(
                [
                    "get",
                    "job",
                    job["name"],
                    "-n",
                    job["namespace"],
                    "--ignore-not-found=true",
                    "-o",
                    "json",
                ]
            )
            if not observed or observed.get("status", {}).get("failed"):
                job["status"] = "failed"
            elif observed.get("status", {}).get("succeeded"):
                job["status"] = "completed"
        checkpoint["artifacts"] = artifacts
        final_status = "complete" if len(artifacts) == len(ARTIFACTS) else "partial"
        if artifacts:
            checkpoint["status"] = "outputs_published" if final_status == "complete" else "partial"
        elif job and job.get("status") in ("completed", "failed"):
            checkpoint["status"] = "failed"
            checkpoint["error"] = "Renderer finished without published validated outputs"
        checkpoint["report_links"] = "pending" if artifacts else "not_available"
        _persist(repo, checkpoint)

        def update_state() -> None:
            if state_path is not None:
                state = yaml.safe_load(state_path.read_text()) if state_path.exists() else {}
                project = state.get("project", {})
                if project.get("run_id", run_id) != run_id:
                    raise ValueError("Recovery state belongs to another run")
                state["executive_summary"] = checkpoint
                state.setdefault("project", {}).setdefault("run_id", run_id)
                _write(state_path, state)

        update_state()
        if artifacts:
            sealed = recover_inputs(repo, run_id, temporary / "inputs", drive)
            with zipfile.ZipFile(sealed) as outer:
                evidence = temporary / "evidence.zip"
                evidence.write_bytes(outer.read("evidence.zip"))
            with zipfile.ZipFile(evidence) as archive:
                canonical = archive.read("report.md").decode()
            report = temporary / "poc-report.md"
            report.write_text(_linked_report(canonical, artifacts, final_status))
            publication = publish_artifacts(
                repo,
                run_id,
                "report",
                {"poc-report.md": report},
                head_names=["report", "executive"],
            )
            checkpoint.update(
                {
                    "report_links": "persisted",
                    "report_artifact": publication,
                    "status": final_status,
                }
            )
            _persist(repo, checkpoint)
            update_state()
    return checkpoint


def register_cluster_commands(subparsers) -> None:
    """Expose preparation, dispatch and independent recovery to the OpenCode skill."""

    def command(args: argparse.Namespace) -> None:
        from autopoc.executive_inputs import seal_inputs

        if args.command == "executive-seal":
            path = seal_inputs(
                args.evidence,
                args.narrative,
                args.review,
                args.output_dir,
                renderer_image=args.renderer_image,
                scenes_path=args.scenes,
            )
            result = {
                "inputs_path": str(path),
                "input_sha256": _sha(path.read_bytes()),
                "run_id": verify_inputs(path)["run_id"],
                "status": "sealed_local",
            }
        elif args.command == "executive-status":
            result = load_checkpoint(args.repo, args.run_id) or {"status": "pending"}
        elif args.command == "executive-recover":
            path = recover_inputs(args.repo, args.run_id, args.output_dir, _drive())
            result = {"inputs_path": str(path), "input_sha256": _sha(path.read_bytes())}
        elif args.command == "executive-reconcile":
            result = reconcile_outputs(args.repo, args.run_id, args.state, _drive())
        else:
            folder = (
                args.folder_id
                or os.environ.get("AUTOPOC_EXECUTIVE_FOLDER_ID")
                or os.environ.get("GOOGLE_DOCS_FOLDER_ID")
            )
            if not folder:
                raise ValueError(
                    "Durable Drive destination is not configured; cluster dispatch blocked"
                )
            drive = _drive()
            checkpoint = prepare_publication(
                args.repo,
                args.inputs,
                folder,
                drive,
                new_attempt=args.retry,
                launch_namespace=args.namespace,
                credentials_secret=args.credentials_secret,
            )
            prior = reconcile_outputs(args.repo, checkpoint["run_id"], args.state, drive)
            if prior.get("status") == "complete":
                result = prior
            else:
                submit_renderer(
                    args.repo,
                    checkpoint["run_id"],
                    args.namespace,
                    wait_seconds=args.wait_seconds,
                    credentials_secret=args.credentials_secret,
                )
                result = reconcile_outputs(args.repo, checkpoint["run_id"], args.state, drive)
        print(json.dumps(result, indent=2))
        if args.command == "executive-dispatch" and result.get("status") in {"partial", "failed"}:
            raise SystemExit(1)

    seal = subparsers.add_parser(
        "executive-seal", help="Seal reviewed narrative and original evidence"
    )
    for name in ("evidence", "narrative", "review", "output-dir"):
        seal.add_argument(f"--{name}", type=Path, required=True)
    seal.add_argument("--renderer-image", required=True)
    seal.add_argument("--scenes", type=Path)
    seal.set_defaults(func=command)
    for name in ("executive-status", "executive-recover", "executive-reconcile"):
        parser = subparsers.add_parser(
            name, help="Reconcile executive artifacts without rerunning PoC tests"
        )
        parser.add_argument("--repo", type=Path, required=True)
        parser.add_argument("--run-id", required=True)
        if name == "executive-recover":
            parser.add_argument("--output-dir", type=Path, required=True)
        if name == "executive-reconcile":
            parser.add_argument("--state", type=Path)
        parser.set_defaults(func=command)
    dispatch = subparsers.add_parser(
        "executive-dispatch", help="Publish inputs and reconcile an isolated renderer Job"
    )
    dispatch.add_argument("--repo", type=Path, required=True)
    dispatch.add_argument("--inputs", type=Path, required=True)
    dispatch.add_argument("--namespace", required=True)
    dispatch.add_argument("--folder-id")
    dispatch.add_argument("--state", type=Path)
    dispatch.add_argument("--credentials-secret", default="autopoc-google-sa")
    dispatch.add_argument("--wait-seconds", type=int, default=300)
    dispatch.add_argument(
        "--retry", action="store_true", help="New bounded render attempt; retain prior revisions"
    )
    dispatch.set_defaults(func=command)
