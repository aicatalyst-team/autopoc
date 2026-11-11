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


@pytest.mark.parametrize("narrated", [False, True])
def test_renderer_publishes_partial_outputs_and_resume_updates_completed_blog(
    repository, tmp_path, monkeypatch, narrated
):
    import argparse

    from autopoc.executive_cluster import reconcile_outputs, render_remote

    source, _ = repository
    run = tmp_path / "run"
    run.mkdir()
    drive = Drive()
    from tests.executive_fixtures import make_v3_input

    checkpoint = prepare_publication(
        source, make_v3_input(run) if narrated else package(run), "folder", drive
    )

    def render(sealed, output, **kwargs):
        assert kwargs.get("timeout") == (3000 if narrated else 600)
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


@pytest.mark.parametrize("template", [3, 4])
def test_narrated_policy_is_durable_before_upload_and_survives_late_completion(
    repository, tmp_path, monkeypatch, template
):
    from autopoc import executive_cluster as cluster
    from tests.executive_fixtures import make_v3_input

    source, _ = repository
    from tests.test_executive_inputs import generic_documents, generic_seal

    run = tmp_path / "run"
    package = (
        generic_seal(run, generic_documents(run, 1))
        if template == 4
        else make_v3_input(run, slides=8)
    )
    drive = Drive()

    def before():
        saved = load_checkpoint(source, "run-1")
        assert saved["render_policy"]["profile"] == "kokoro-v3"
        assert saved["render_policy"]["render_timeout_seconds"] == 3000

    drive.before_upload = before
    cp = prepare_publication(source, package, "folder", drive)
    descriptor = json.loads(drive.files[cp["recovery_id"]])
    assert descriptor["render_policy"] == cp["render_policy"]
    assert cp["render_policy"]["narration"] == "kokoro"
    count = drive.counter
    jobs = {}
    created = []

    def kubectl(args, payload=None):
        if args[0] == "create":
            item = json.loads(payload)
            item["metadata"]["uid"] = "narrated-uid"
            jobs[item["metadata"]["name"]] = item
            created.append(item)
            return item
        return jobs.get(args[2], {})

    monkeypatch.setattr(cluster, "_kubectl", kubectl)
    first = cluster.submit_renderer(source, "run-1", "autopoc-test", wait_seconds=0)
    assert first["job"]["status"] == "wait_expired"
    monkeypatch.setenv("AUTOPOC_EXECUTIVE_NARRATION", "none")
    monkeypatch.setenv("AUTOPOC_EXECUTIVE_IMAGE", "quay.io/changed@sha256:" + "f" * 64)
    again = prepare_publication(source, package, "folder", drive)
    second = cluster.submit_renderer(source, "run-1", "autopoc-test", wait_seconds=0)
    assert again["render_policy"] == cp["render_policy"]
    assert first["job"]["uid"] == second["job"]["uid"]
    assert len(created) == 1 and drive.counter == count
    assert (
        created[0]["spec"]["activeDeadlineSeconds"] == cp["render_policy"]["job_deadline_seconds"]
    )
    assert cp["render_policy"]["job_deadline_seconds"] == 3600
    assert created[0]["spec"]["template"]["spec"]["containers"][0]["args"][-2:] == [
        "--timeout-seconds",
        "3000",
    ]
    shutil.rmtree(tmp_path / "run")
    recovered = recover_inputs(source, "run-1", tmp_path / "fresh", drive)
    assert recovered.exists()
    jobs[first["job"]["name"]]["status"] = {"succeeded": 1}
    assert (
        cluster.submit_renderer(source, "run-1", "autopoc-test", wait_seconds=0)["job"]["status"]
        == "completed"
    )

    if template == 4:
        import argparse
        import io
        import zipfile

        from autopoc.executive_inputs import verify_inputs
        from autopoc.executive_render import _zip
        from autopoc.executive_story import derive_checks

        expected = verify_inputs(recovered)
        expected_checks = derive_checks(expected["evidence_index"])
        render_calls = []

        def render(sealed, output, **kwargs):
            render_calls.append(1)
            assert kwargs == {"timeout": 3000}
            verified = verify_inputs(sealed)
            assert verified["visuals"] == expected["visuals"]
            assert derive_checks(verified["evidence_index"]) == expected_checks
            output.mkdir(parents=True)
            with zipfile.ZipFile(sealed) as outer:
                with zipfile.ZipFile(io.BytesIO(outer.read("visuals.zip"))) as visuals:
                    image = visuals.read("assets/image0.png")
            metadata = {
                "checks.json": json.dumps(expected_checks).encode(),
                "visuals.json": json.dumps(verified["visuals"]).encode(),
            }
            _zip(
                output / "executable-source.zip",
                {
                    **metadata,
                    "render-inputs.zip": sealed.read_bytes(),
                    "public/visuals/image0.png": image,
                },
            )
            _zip(
                output / "static-site.zip",
                {**metadata, "index.html": b"deck", "visuals/image0.png": image},
            )
            (output / "executive-summary.pdf").write_bytes(b"PDF")
            (output / "executive-summary.mp4").write_bytes(b"video")
            (output / "executive-summary.md").write_text("Reviewed executive summary")
            manifest = {"run_id": "run-1", "status": "generated_unpublished", "artifacts": {}}
            for kind, name in cluster.ARTIFACTS.items():
                if kind != "manifest":
                    raw = (output / name).read_bytes()
                    manifest["artifacts"][kind] = {
                        "status": "generated_unpublished",
                        "path": name,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "size": len(raw),
                    }
            return manifest

        monkeypatch.setattr("autopoc.executive_render.render_executive", render)
        args = argparse.Namespace(
            input_id=cp["input_id"],
            input_sha256=cp["input_sha256"],
            recovery_id=cp["recovery_id"],
            recovery_sha256=cp["recovery_sha256"],
            output_dir=tmp_path / "late-output",
        )
        published = cluster.render_remote(args, drive=drive)
        assert published["status"] == "outputs_published"
        receipts = dict(published["artifacts"])
        for receipt in receipts.values():
            assert hashlib.sha256(drive.files[receipt["file_id"]]).hexdigest() == receipt["sha256"]
        before_reconcile = dict(drive.files)
        reconciled = cluster.reconcile_outputs(source, "run-1", None, drive)
        assert reconciled["status"] == "complete"
        assert (
            cluster.reconcile_outputs(source, "run-1", None, drive)["artifacts"]
            == reconciled["artifacts"]
        )
        assert drive.files == before_reconcile
        assert render_calls == [1]
        receipt = receipts["source"]
        with zipfile.ZipFile(io.BytesIO(drive.files[receipt["file_id"]])) as archive:
            assert json.loads(archive.read("checks.json")) == expected_checks
            assert (
                hashlib.sha256(archive.read("public/visuals/image0.png")).hexdigest()
                == expected["visuals"]["assets"][0]["sha256"]
            )
        drive.files[receipt["file_id"]] += b"altered output"
        with pytest.raises(ValueError, match="integrity"):
            cluster.reconcile_outputs(source, "run-1", None, drive)
        drive.files[cp["input_id"]] += b"altered input"
        with pytest.raises(ValueError, match="integrity"):
            recover_inputs(source, "run-1", tmp_path / "altered-recovery", drive)
        assert render_calls == [1]


@pytest.mark.parametrize(
    "kind,amount,ok",
    [
        ("video", 1024**3, True),
        ("video", 1024**3 + 1, False),
        ("source", 512 * 1024**2, True),
        ("source", 512 * 1024**2 + 1, False),
        ("pdf", 512 * 1024**2, False),
    ],
)
def test_narrated_receipt_caps_are_selected_by_kind(kind, amount, ok):
    from autopoc.executive_cluster import _receipt

    cp = {
        "run_id": "run-1",
        "revision": "a" * 64,
        "input_sha256": "b" * 64,
        "render_policy": {
            "profile": "kokoro-v3",
            "narration": "kokoro",
            "render_timeout_seconds": 3000,
            "job_deadline_seconds": 3120,
            "scene_policy_sha256": "c" * 64,
        },
        "slots": {kind: {"file_id": "file-id"}},
    }
    value = {
        "run_id": "run-1",
        "revision": "a" * 64,
        "input_sha256": "b" * 64,
        "kind": kind,
        "file_id": "file-id",
        "sha256": "d" * 64,
        "size": amount,
    }
    if ok:
        assert _receipt(cp, kind, value)["status"] == "published"
    else:
        with pytest.raises(ValueError):
            _receipt(cp, kind, value)


def test_legacy_and_current_narrated_deadlines_are_both_durable(repository, tmp_path):
    """New policy keeps startup headroom; 3120s descriptors stay dispatchable."""
    from autopoc.executive_inputs import verify_inputs
    from autopoc.executive_policy import render_policy, saved_policy
    from tests.executive_fixtures import make_v3_input

    verified = verify_inputs(make_v3_input(tmp_path / "run"))
    current = render_policy(verified)
    assert current["job_deadline_seconds"] == 3600
    assert current["render_timeout_seconds"] == 3000
    legacy = {**current, "job_deadline_seconds": 3120}
    assert saved_policy({"render_policy": legacy}, verified) == legacy
    assert saved_policy({"render_policy": current}, verified) == current
    with pytest.raises(ValueError):
        saved_policy({"render_policy": {**current, "job_deadline_seconds": 3300}}, verified)


@pytest.mark.parametrize("change", ["timeout", "profile", "image"])
def test_remote_rejects_cli_or_saved_policy_conflicts_before_render(
    repository, tmp_path, monkeypatch, change
):
    import argparse

    from autopoc import executive_cluster as cluster
    from tests.executive_fixtures import make_v3_input

    source, _ = repository
    drive = Drive()
    cp = prepare_publication(source, make_v3_input(tmp_path / "run"), "folder", drive)
    descriptor = json.loads(drive.files[cp["recovery_id"]])
    if change == "profile":
        descriptor["render_policy"] = {"profile": "silent-v2"}
    if change == "image":
        descriptor["image"] = "quay.io/old@sha256:" + "e" * 64
    raw = json.dumps(descriptor).encode()
    drive.files[cp["recovery_id"]] = raw
    args = argparse.Namespace(
        input_id=cp["input_id"],
        input_sha256=cp["input_sha256"],
        recovery_id=cp["recovery_id"],
        recovery_sha256=hashlib.sha256(raw).hexdigest(),
        output_dir=tmp_path / "out",
        timeout_seconds=600 if change == "timeout" else 3000,
    )
    monkeypatch.setattr(
        "autopoc.executive_render.render_executive",
        lambda *a, **kw: pytest.fail("conflicting render launched"),
    )
    with pytest.raises(ValueError):
        cluster.render_remote(args, drive=drive)


def test_narrated_retry_is_bounded_and_preserves_input_identity(repository, tmp_path):
    from tests.executive_fixtures import make_v3_input

    source, _ = repository
    drive = Drive()
    package = make_v3_input(tmp_path / "run")
    first = prepare_publication(source, package, "folder", drive)
    second = prepare_publication(source, package, "folder", drive, new_attempt=True)
    third = prepare_publication(source, package, "folder", drive, new_attempt=True)
    assert first["input_sha256"] == second["input_sha256"] == third["input_sha256"]
    assert len({cp["revision"] for cp in (first, second, third)}) == 3
    with pytest.raises(ValueError, match="retry limit"):
        prepare_publication(source, package, "folder", drive, new_attempt=True)


def test_legacy_descriptor_bytes_do_not_gain_a_policy():
    from autopoc.executive_cluster import _descriptor

    cp = {
        key: "value"
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
    assert _descriptor(cp) == cp


def test_reconcile_rejects_forged_size_even_with_valid_hash(repository, tmp_path):
    from autopoc.executive_cluster import reconcile_outputs

    source, _ = repository
    drive = Drive()
    run = tmp_path / "run"
    run.mkdir()
    cp = prepare_publication(source, package(run), "folder", drive)
    raw = b"published artifact bytes"
    slot = cp["slots"]["pdf"]
    drive.files[slot["file_id"]] = raw
    drive.files[slot["receipt_id"]] = json.dumps(
        {
            "run_id": "run-1",
            "revision": cp["revision"],
            "input_sha256": cp["input_sha256"],
            "kind": "pdf",
            "file_id": slot["file_id"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": 1,
        }
    ).encode()
    with pytest.raises(ValueError, match="size"):
        reconcile_outputs(source, "run-1", None, drive)


def test_worker_templates_forward_narration_opt_in():
    from pathlib import Path

    import yaml

    root = Path(__file__).parents[1]
    for name in ("job", "cronjob"):
        manifest = yaml.safe_load((root / f"deploy/base/{name}.yaml").read_text())
        spec = manifest["spec"] if name == "job" else manifest["spec"]["jobTemplate"]["spec"]
        env = spec["template"]["spec"]["containers"][0]["env"]
        narration = next((row for row in env if row["name"] == "AUTOPOC_EXECUTIVE_NARRATION"), None)
        assert narration and narration["valueFrom"]["secretKeyRef"] == {
            "name": "autopoc-credentials",
            "key": "AUTOPOC_EXECUTIVE_NARRATION",
            "optional": True,
        }


def test_resume_rejects_changed_saved_launch_credentials(repository, tmp_path):
    from autopoc.executive_cluster import submit_renderer

    source, _ = repository
    run = tmp_path / "run"
    run.mkdir()
    prepare_publication(
        source,
        package(run),
        "folder",
        Drive(),
        launch_namespace="autopoc-test",
        credentials_secret="saved-secret",
    )
    with pytest.raises(ValueError, match="Launch configuration"):
        submit_renderer(
            source, "run-1", "autopoc-test", credentials_secret="changed-secret", wait_seconds=0
        )


def test_visuals_cli_packages_and_seals_schema3(tmp_path, capsys):
    import argparse

    from autopoc.executive_cluster import register_cluster_commands
    from autopoc.executive_inputs import verify_inputs
    from tests.test_executive_inputs import generic_documents

    docs = generic_documents(tmp_path)
    parser = argparse.ArgumentParser()
    register_cluster_commands(parser.add_subparsers(dest="command"))
    args = parser.parse_args(
        [
            "executive-visuals",
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output",
            str(tmp_path / "cli.zip"),
        ]
    )
    args.func(args)
    assert json.loads(capsys.readouterr().out)["visuals_path"] == str(tmp_path / "cli.zip")
    evidence, narrative, scenes, review, _ = docs
    args = parser.parse_args(
        [
            "executive-seal",
            "--evidence",
            str(evidence),
            "--narrative",
            str(narrative),
            "--scenes",
            str(scenes),
            "--review",
            str(review),
            "--visuals",
            str(tmp_path / "cli.zip"),
            "--output-dir",
            str(tmp_path / "sealed"),
            "--template-version",
            "4",
            "--renderer-image",
            "quay.io/org/image@sha256:" + "b" * 64,
        ]
    )
    args.func(args)
    result = json.loads(capsys.readouterr().out)
    assert (
        verify_inputs(__import__("pathlib").Path(result["inputs_path"]))["visuals"]["assets"] == []
    )
