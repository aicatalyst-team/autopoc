"""Supplemental evidence cannot bypass run identity, sanitization or archive bounds."""

import hashlib
import json
import zipfile

import pytest

from autopoc.evidence import EvidenceError, create_bundle, verify_bundle
from tests.test_evidence import setup_run


def stage(root, *, kind="log", payload=None):
    setup_run(root)
    if payload is None:
        payload = "Build failed, then passed.\npassword=private-value\n"
    raw = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
    source = root / ("build.txt" if isinstance(payload, str) else "capture.json")
    source.write_bytes(raw)
    descriptor = {
        "schema_version": 1,
        "run_id": "run-1",
        "records": [
            {
                "id": "build-1",
                "kind": kind,
                "path": source.name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "provenance": {"run_id": "run-1", "capture": "original"},
                "execution_id": "exec-1",
                "scenario_id": "health",
            }
        ],
    }
    path = root / "supplemental.json"
    path.write_text(json.dumps(descriptor))
    return path, descriptor, source


def collect(root, descriptor):
    return create_bundle(
        root / "state.json",
        root / "attempt-index.json",
        root / "out",
        supplemental_index=descriptor,
    )


def test_supplemental_roundtrip_preserves_totals(tmp_path):
    path, _, _ = stage(tmp_path)
    bundle = collect(tmp_path, path)
    index = verify_bundle(bundle)
    assert index["schema_version"] == 2
    assert index["final_results"]["totals"] == {
        "pass": 1,
        "fail": 0,
        "error": 0,
        "skip": 0,
        "incomplete": 0,
    }
    assert "missing_trace" in index["coverage_gaps"]
    with zipfile.ZipFile(bundle) as archive:
        assert archive.read("supplemental/build-1.txt") == (
            b"Build failed, then passed.\npassword=[REDACTED]\n"
        )
        public = json.loads(archive.read("supplemental-index.json"))
        assert "path" not in public["records"][0]
        assert "private-value" not in archive.read("supplemental/build-1.txt").decode()
    assert collect(tmp_path, path) == bundle


@pytest.mark.parametrize(
    "change",
    [
        "run",
        "provenance",
        "execution",
        "scenario",
        "traversal",
        "symlink",
        "hash",
        "duplicate",
        "unsafe",
        "many",
        "large",
        "unknown_kind",
        "missing",
        "descriptor_symlink",
    ],
)
def test_rejects_untrusted_supplemental_inputs(tmp_path, change):
    path, doc, source = stage(tmp_path)
    row = doc["records"][0]
    if change == "run":
        doc["run_id"] = "other-run"
    elif change == "provenance":
        row["provenance"]["run_id"] = "other-run"
    elif change == "execution":
        row["execution_id"] = "other-execution"
    elif change == "scenario":
        row["scenario_id"] = "other-scenario"
    elif change == "traversal":
        row["path"] = "../outside.txt"
    elif change == "symlink":
        (tmp_path / "linked.txt").symlink_to(source)
        row["path"] = "linked.txt"
    elif change == "hash":
        row["sha256"] = "0" * 64
    elif change == "duplicate":
        doc["records"].append(dict(row))
    elif change == "unsafe":
        source.write_text("Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==")
        row["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    elif change == "many":
        doc["records"] = [{**row, "id": f"log-{i}"} for i in range(33)]
    elif change == "large":
        source.write_bytes(b"x" * (512 * 1024 + 1))
        row["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    elif change == "unknown_kind":
        row["kind"] = "arbitrary"
    elif change == "missing":
        source.unlink()
    path.write_text(json.dumps(doc))
    if change == "descriptor_symlink":
        linked = tmp_path / "descriptor-link.json"
        linked.symlink_to(path)
        path = linked
    with pytest.raises(EvidenceError):
        collect(tmp_path, path)


def test_deployment_export_removes_secrets_environment_and_annotations(tmp_path):
    payload = {
        "run_id": "run-1",
        "observed": True,
        "resources": [
            {"kind": "Secret", "metadata": {"name": "private"}, "data": {"x": "opaque"}},
            {
                "kind": "Deployment",
                "metadata": {"name": "app", "annotations": {"x": "opaque"}},
                "spec": {
                    "replicas": 1,
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "app",
                                    "image": "example/app:v1",
                                    "env": [{"name": "X", "value": "opaque"}],
                                    "resources": {"limits": {"memory": "1Gi"}},
                                }
                            ]
                        }
                    },
                },
                "status": {"readyReplicas": 1},
            },
        ],
    }
    path, _, _ = stage(tmp_path, kind="deployment", payload=payload)
    with zipfile.ZipFile(collect(tmp_path, path)) as archive:
        raw = archive.read("supplemental/build-1.json")
        assert b"opaque" not in raw
        doc = json.loads(raw)
        assert len(doc["resources"]) == 1
        assert doc["resources"][0]["status"]["readyReplicas"] == 1
        assert doc["observed"] is True


def test_trace_preserves_observed_relations_without_request_bodies(tmp_path):
    payload = {
        "run_id": "run-1",
        "spans": [
            {
                "trace_id": "trace1",
                "span_id": "parent",
                "parent_span_id": None,
                "service": "frontend",
                "operation": "GET",
                "start_time": 10,
                "duration_seconds": 1,
                "status": "ok",
                "body": "opaque",
            },
            {
                "trace_id": "trace1",
                "span_id": "child",
                "parent_span_id": "parent",
                "service": "backend",
                "operation": "query",
                "start_time": 10.2,
                "duration_seconds": 0.4,
                "status": "ok",
                "attributes": {"authorization": "opaque"},
            },
        ],
    }
    path, _, _ = stage(tmp_path, kind="trace", payload=payload)
    bundle = collect(tmp_path, path)
    assert "missing_trace" not in verify_bundle(bundle)["coverage_gaps"]
    with zipfile.ZipFile(bundle) as archive:
        raw = archive.read("supplemental/build-1.json")
        assert b"opaque" not in raw
        assert json.loads(raw)["spans"][1]["parent_span_id"] == "parent"


def test_mixed_run_trace_is_rejected(tmp_path):
    path, _, _ = stage(tmp_path, kind="trace", payload={"run_id": "other", "spans": []})
    with pytest.raises(EvidenceError):
        collect(tmp_path, path)


def test_cli_accepts_supplemental_descriptor(tmp_path, capsys):
    from tests.test_evidence_cli import invoke

    path, _, _ = stage(tmp_path)
    invoke(
        [
            "evidence-create",
            "--state",
            str(tmp_path / "state.json"),
            "--attempt-index",
            str(tmp_path / "attempt-index.json"),
            "--output-dir",
            str(tmp_path / "out"),
            "--supplemental-index",
            str(path),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == 2


def test_public_provenance_does_not_publish_private_paths_or_original_hashes(tmp_path):
    path, doc, _ = stage(tmp_path)
    doc["records"][0]["provenance"].update(path="/private/staging/input", original_sha256="a" * 64)
    path.write_text(json.dumps(doc))
    with zipfile.ZipFile(collect(tmp_path, path)) as archive:
        public = json.loads(archive.read("supplemental-index.json"))
        assert public["records"][0]["provenance"] == {"run_id": "run-1", "capture": "original"}


def test_route_export_does_not_publish_inline_tls_key(tmp_path):
    path, _, _ = stage(
        tmp_path,
        kind="deployment",
        payload={
            "run_id": "run-1",
            "observed": False,
            "resources": [
                {
                    "kind": "Route",
                    "metadata": {"name": "app"},
                    "spec": {"tls": {"termination": "edge", "key": "opaque-private-material"}},
                }
            ],
        },
    )
    with zipfile.ZipFile(collect(tmp_path, path)) as archive:
        raw = archive.read("supplemental/build-1.json")
        assert b"opaque-private-material" not in raw
        assert json.loads(raw)["resources"][0]["spec"]["tls"] == {"termination": "edge"}


def test_rehashed_archive_cannot_smuggle_extra_evidence(tmp_path):
    path, _, _ = stage(tmp_path)
    bundle = collect(tmp_path, path)
    with zipfile.ZipFile(bundle) as archive:
        members = {n: archive.read(n) for n in archive.namelist()}
    members["supplemental/undeclared.txt"] = b"Invented evidence"
    index = json.loads(members["index.json"])
    index["files"]["supplemental/undeclared.txt"] = {
        "sha256": hashlib.sha256(members["supplemental/undeclared.txt"]).hexdigest(),
        "size": len(members["supplemental/undeclared.txt"]),
    }
    members["index.json"] = json.dumps(index).encode()
    altered = tmp_path / "altered.zip"
    with zipfile.ZipFile(altered, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    with pytest.raises(EvidenceError):
        verify_bundle(altered)
