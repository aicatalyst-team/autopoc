"""Durable checkpoints precede uploads; recovery needs no original pod files."""

import hashlib
import json
import shutil

import pytest

from autopoc.executive_cluster import load_checkpoint, prepare_publication, recover_inputs
from autopoc.executive_inputs import seal_inputs
from tests.test_artifacts import repository as artifact_repository
from tests.test_executive_inputs import inputs


@pytest.fixture
def repository(tmp_path):
    return artifact_repository.__wrapped__(tmp_path)


class Drive:
    def __init__(self):
        self.counter = 0
        self.files = {}
        self.before_upload = None
        self.interrupt = False

    def allocate_file_id(self):
        self.counter += 1
        return f"file-{self.counter}"

    def upload_file_once(self, path, file_id, folder):
        if self.before_upload:
            self.before_upload()
        raw = __import__("pathlib").Path(path).read_bytes()
        if file_id in self.files and self.files[file_id] != raw:
            raise ValueError("immutable upload conflict")
        self.files[file_id] = raw
        if self.interrupt:
            self.interrupt = False
            raise TimeoutError()
        return {
            "file_id": file_id,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "web_view_link": f"https://drive.google.com/file/d/{file_id}/view",
        }

    def download_file(self, file_id, destination, expected_sha256, **kwargs):
        raw = self.files[file_id]
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("integrity mismatch")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        return destination

    def read_json(self, file_id):
        return json.loads(self.files[file_id]) if file_id in self.files else None


def package(root):
    evidence, narrative, review = inputs(root)
    return seal_inputs(
        evidence,
        narrative,
        review,
        root / "sealed",
        renderer_image="quay.io/org/image@sha256:" + "b" * 64,
    )


def test_upload_intent_is_durable_before_side_effect_and_survives_unknown_completion(
    repository, tmp_path
):
    source, _ = repository
    run = tmp_path / "run"
    run.mkdir()
    sealed = package(run)
    drive = Drive()
    drive.before_upload = lambda: load_checkpoint(source, "run-1")
    drive.interrupt = True
    with pytest.raises(TimeoutError):
        prepare_publication(source, sealed, "folder", drive)
    checkpoint = load_checkpoint(source, "run-1")
    reserved = checkpoint["input_id"]
    allocated = drive.counter
    retried = prepare_publication(source, sealed, "folder", drive)
    assert retried["status"] == "inputs_published"
    assert retried["input_id"] == reserved
    assert drive.counter == allocated


def test_recovery_uses_only_published_package_after_worker_files_deleted(repository, tmp_path):
    source, _ = repository
    original = tmp_path / "original"
    original.mkdir()
    sealed = package(original)
    drive = Drive()
    checkpoint = prepare_publication(source, sealed, "folder", drive)
    shutil.rmtree(original)
    recovered = recover_inputs(source, "run-1", tmp_path / "fresh", drive)
    assert hashlib.sha256(recovered.read_bytes()).hexdigest() == checkpoint["input_sha256"]


def test_recovery_rejects_changed_remote_inputs(repository, tmp_path):
    source, _ = repository
    run = tmp_path / "run"
    run.mkdir()
    drive = Drive()
    checkpoint = prepare_publication(source, package(run), "folder", drive)
    drive.files[checkpoint["input_id"]] = b"tampered"
    with pytest.raises(ValueError, match="integrity"):
        recover_inputs(source, "run-1", tmp_path / "fresh", drive)


def test_pending_input_upload_recovers_after_original_files_deleted(repository, tmp_path):
    source, _ = repository
    original = tmp_path / "original"
    original.mkdir()
    drive = Drive()
    drive.interrupt = True
    with pytest.raises(TimeoutError):
        prepare_publication(source, package(original), "folder", drive)
    shutil.rmtree(original)
    recovered = recover_inputs(source, "run-1", tmp_path / "fresh", drive)
    assert recovered.exists()
    assert load_checkpoint(source, "run-1")["status"] == "inputs_published"


def test_recovery_before_any_drive_upload_uses_sealed_git_backup(repository, tmp_path):
    source, _ = repository
    original = tmp_path / "original"
    original.mkdir()
    drive = Drive()
    drive.before_upload = lambda: (_ for _ in ()).throw(TimeoutError())
    with pytest.raises(TimeoutError):
        prepare_publication(source, package(original), "folder", drive)
    assert not drive.files
    shutil.rmtree(original)
    drive.before_upload = None
    recovered = recover_inputs(source, "run-1", tmp_path / "fresh", drive)
    assert recovered.exists()
    assert load_checkpoint(source, "run-1")["status"] == "inputs_published"


@pytest.mark.parametrize("symlink", [False, True])
def test_git_recovery_never_overwrites_an_existing_file_or_symlink(repository, tmp_path, symlink):
    source, _ = repository
    original = tmp_path / "original"
    original.mkdir()
    drive = Drive()
    drive.before_upload = lambda: (_ for _ in ()).throw(TimeoutError())
    with pytest.raises(TimeoutError):
        prepare_publication(source, package(original), "folder", drive)
    drive.before_upload = None
    destination = tmp_path / "fresh"
    destination.mkdir()
    protected = tmp_path / "protected"
    protected.write_bytes(b"keep me")
    target = destination / "render-inputs.zip"
    if symlink:
        target.symlink_to(protected)
    else:
        target.write_bytes(b"existing input")
    with pytest.raises(ValueError):
        recover_inputs(source, "run-1", destination, drive)
    assert protected.read_bytes() == b"keep me"
    if not symlink:
        assert target.read_bytes() == b"existing input"


def test_resume_dispatches_saved_launch_intent_even_without_uid(repository, tmp_path, monkeypatch):
    from autopoc.executive_cluster import reconcile_outputs

    source, _ = repository
    run = tmp_path / "run"
    run.mkdir()
    drive = Drive()
    jobs = {}
    creates = []

    def kubectl(arguments, payload=None):
        if arguments[0] == "create":
            manifest = json.loads(payload)
            manifest["metadata"]["uid"] = "recovered-uid"
            jobs[manifest["metadata"]["name"]] = manifest
            creates.append(manifest)
            return manifest
        return jobs.get(arguments[2], {})

    monkeypatch.setattr("autopoc.executive_cluster._kubectl", kubectl)
    prepare_publication(source, package(run), "folder", drive, launch_namespace="autopoc-test")
    first = reconcile_outputs(source, "run-1", None, drive)
    second = reconcile_outputs(source, "run-1", None, drive)
    assert first["job"]["uid"] == second["job"]["uid"] == "recovered-uid"
    assert len(creates) == 1


def test_renderer_publishes_partial_outputs_and_resume_updates_completed_blog(
    repository, tmp_path, monkeypatch
):
    import argparse

    from autopoc.executive_cluster import reconcile_outputs, render_remote

    source, _ = repository
    run = tmp_path / "run"
    run.mkdir()
    drive = Drive()
    checkpoint = prepare_publication(source, package(run), "folder", drive)

    def render(sealed, output, **kwargs):
        output.mkdir(parents=True)
        manifest = {
            "run_id": "run-1",
            "status": "partial",
            "artifacts": {"video": {"status": "failed"}},
        }
        for kind, name in {
            "source": "executable-source.zip",
            "deck": "static-site.zip",
            "pdf": "executive-summary.pdf",
            "summary": "executive-summary.md",
        }.items():
            (output / name).write_bytes(kind.encode())
            manifest["artifacts"][kind] = {
                "status": "generated_unpublished",
                "path": name,
                "sha256": hashlib.sha256(kind.encode()).hexdigest(),
                "size": len(kind),
            }
        (output / "presentation-manifest.json").write_text(json.dumps(manifest))
        return manifest

    monkeypatch.setattr("autopoc.executive_render.render_executive", render)
    upload = drive.upload_file_once
    receipt_interrupted = False

    def interrupted_upload(path, file_id, folder):
        nonlocal receipt_interrupted
        if file_id == checkpoint["slots"]["pdf"]["receipt_id"] and not receipt_interrupted:
            receipt_interrupted = True
            raise TimeoutError()
        return upload(path, file_id, folder)

    drive.upload_file_once = interrupted_upload
    args = argparse.Namespace(
        input_id=checkpoint["input_id"],
        input_sha256=checkpoint["input_sha256"],
        recovery_id=checkpoint["recovery_id"],
        recovery_sha256=checkpoint["recovery_sha256"],
        output_dir=tmp_path / "renderer" / "output",
    )
    result = render_remote(args, drive=drive)
    assert result["status"] == "partial"
    assert checkpoint["slots"]["pdf"]["file_id"] in drive.files
    assert checkpoint["slots"]["pdf"]["receipt_id"] not in drive.files
    state_path = tmp_path / "resumed-state.json"
    state_path.write_text(
        json.dumps(
            {
                "project": {"run_id": "run-1", "current_phase": "blog"},
                "blog_post": {"status": "completed"},
            }
        )
    )
    reconciled = reconcile_outputs(source, "run-1", state_path, drive)
    assert reconciled["status"] == "partial"
    assert "pdf" in reconciled["artifacts"]
    saved = json.loads(state_path.read_text())
    assert saved["blog_post"]["status"] == "completed"
    assert saved["project"]["current_phase"] == "blog"
    assert saved["executive_summary"]["artifacts"]["pdf"]["file_id"]


def test_unknown_job_creation_reconciles_existing_job_instead_of_duplicate(
    repository, tmp_path, monkeypatch
):
    from autopoc.executive_cluster import submit_renderer

    source, _ = repository
    run = tmp_path / "run"
    run.mkdir()
    drive = Drive()
    prepare_publication(source, package(run), "folder", drive)
    jobs = {}
    submissions = []

    def kubectl(arguments, payload=None):
        if arguments[0] == "create":
            manifest = json.loads(payload)
            assert load_checkpoint(source, "run-1")["job"]["name"] == manifest["metadata"]["name"]
            manifest["metadata"]["uid"] = "job-uid"
            jobs[manifest["metadata"]["name"]] = manifest
            submissions.append(manifest)
            raise TimeoutError()
        return jobs.get(arguments[2], {})

    monkeypatch.setattr("autopoc.executive_cluster._kubectl", kubectl)
    first = submit_renderer(source, "run-1", "autopoc-test", wait_seconds=0)
    second = submit_renderer(source, "run-1", "autopoc-test", wait_seconds=0)
    assert first["job"]["uid"] == second["job"]["uid"] == "job-uid"
    assert len(submissions) == 1


def test_dispatch_exits_nonzero_when_renderer_admission_fails(repository, tmp_path, monkeypatch):
    import argparse

    from autopoc import executive_cluster

    source, _ = repository
    run = tmp_path / "run"
    run.mkdir()
    drive = Drive()

    def kubectl(arguments, payload=None):
        raise RuntimeError("admission webhook denied the request")

    monkeypatch.setattr(executive_cluster, "_kubectl", kubectl)
    monkeypatch.setattr(executive_cluster, "_drive", lambda: drive)
    parser = argparse.ArgumentParser()
    executive_cluster.register_cluster_commands(parser.add_subparsers(dest="command"))
    args = parser.parse_args(
        [
            "executive-dispatch",
            "--repo",
            str(source),
            "--inputs",
            str(package(run)),
            "--namespace",
            "autopoc-test",
            "--folder-id",
            "folder",
            "--wait-seconds",
            "0",
        ]
    )
    with pytest.raises(SystemExit) as exit_info:
        args.func(args)
    assert exit_info.value.code == 1
