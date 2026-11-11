"""Rendering may consume only reviewed, bound and verifiable evidence."""

import hashlib
import json
import zipfile

import pytest

from autopoc.executive_inputs import seal_inputs, verify_inputs
from tests.test_evidence import collect, setup_run


def inputs(root):
    setup_run(root)
    evidence = collect(root)
    claim = {"text": "One HTTP smoke check passed.", "sources": ["report.md"]}
    narrative = {
        "schema_version": 1,
        "run_id": "run-1",
        "project_name": "Demo",
        "purpose": [claim],
        "testing_strategy": [claim],
        "test_execution": [claim],
        "platform_suitability": [claim],
        "limitations": ["Smoke checks only"],
        "results": {"pass": 1, "fail": 0, "error": 0, "skip": 0, "incomplete": 0},
        "topology": None,
    }
    path = root / "narrative.json"
    path.write_text(json.dumps(narrative))
    review = root / "review.json"
    review.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "approved": True,
                "reviewer": "configured-opencode",
                "findings": [],
                "narrative_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            }
        )
    )
    return evidence, path, review


def test_sealed_inputs_recover_after_original_workspace_is_deleted(tmp_path):
    import shutil

    run = tmp_path / "run"
    run.mkdir()
    evidence, narrative, review = inputs(run)
    package = seal_inputs(
        evidence,
        narrative,
        review,
        tmp_path / "durable",
        renderer_image="quay.io/org/image@sha256:" + "b" * 64,
    )
    shutil.rmtree(run)
    result = verify_inputs(package)
    assert result["run_id"] == "run-1"
    assert result["narrative"]["results"]["pass"] == 1
    assert result["versions"]["template"] == 2
    with zipfile.ZipFile(package) as archive:
        assert set(archive.namelist()) == {
            "index.json",
            "evidence.zip",
            "narrative.json",
            "review.json",
            "scenes.json",
            "versions.json",
        }


@pytest.mark.parametrize("version", [1, 2])
def test_explicit_template_revision_survives_verification(tmp_path, version):
    evidence, narrative, review = inputs(tmp_path)
    package = seal_inputs(
        evidence,
        narrative,
        review,
        tmp_path / "sealed",
        renderer_image="quay.io/org/image@sha256:" + "b" * 64,
        template_version=version,
    )
    assert verify_inputs(package)["versions"]["template"] == version


@pytest.mark.parametrize("version", [0, 3, True, "2"])
def test_unknown_template_revision_cannot_be_sealed(tmp_path, version):
    evidence, narrative, review = inputs(tmp_path)
    with pytest.raises(ValueError, match="version"):
        seal_inputs(
            evidence,
            narrative,
            review,
            tmp_path / "sealed",
            renderer_image="quay.io/org/image@sha256:" + "b" * 64,
            template_version=version,
        )


@pytest.mark.parametrize("change", ["review", "counts", "citation", "secret"])
def test_unreviewed_or_unsupported_claims_cannot_be_sealed(tmp_path, change):
    evidence, path, review = inputs(tmp_path)
    narrative = json.loads(path.read_text())
    if change == "counts":
        narrative["results"]["pass"] = 99
    elif change == "citation":
        narrative["purpose"][0]["sources"] = ["invented.md"]
    elif change == "secret":
        narrative["purpose"][0]["text"] = "Bearer this-is-a-secret-token"
    else:
        narrative["purpose"][0]["text"] = "Modified after review"
    path.write_text(json.dumps(narrative))
    if change != "review":
        receipt = json.loads(review.read_text())
        receipt["narrative_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        review.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        seal_inputs(
            evidence,
            path,
            review,
            tmp_path / "sealed",
            renderer_image="quay.io/org/image@sha256:" + "b" * 64,
        )


def test_seal_rejects_topology_the_renderer_would_refuse(tmp_path):
    """Seal-time graph checks must match renderer/render.mjs, which requires all three arrays."""
    run = tmp_path / "run"
    run.mkdir()
    evidence, narrative, review = inputs(run)
    document = json.loads(narrative.read_text())
    document["topology"] = {"nodes": [{"id": "a", "label": "A"}], "edges": []}
    narrative.write_text(json.dumps(document))
    review_document = json.loads(review.read_text())
    review_document["narrative_sha256"] = hashlib.sha256(narrative.read_bytes()).hexdigest()
    review.write_text(json.dumps(review_document))
    with pytest.raises(ValueError, match="graph"):
        seal_inputs(
            evidence,
            narrative,
            review,
            tmp_path / "durable",
            renderer_image="quay.io/org/image@sha256:" + "b" * 64,
        )


def generic_documents(root, count=0):
    from autopoc.evidence import verify_bundle
    from tests.executive_fixtures import v3_documents
    from tests.test_executive_visuals import prepare, staged

    evidence, narrative, scenes, review = v3_documents(root)
    doc = json.loads(narrative.read_text())
    doc["schema_version"] = 3
    doc["project_context"] = {
        "repository_url": "https://codeberg.org/org/demo",
        "revision": None,
        "definition_claim_id": "claim-0",
        "homepage_url": None,
        "documentation_url": None,
    }
    for slide in doc["slides"]:
        slide.update(layout="summary", visual_id=None, checks=[])
    doc["slides"][0]["layout"] = "identity"
    if count:
        doc["slides"][0]["visual_id"] = "image0"
    testing = doc["slides"][1]
    testing["layout"] = "checks"
    scenario = verify_bundle(evidence)["final_results"]["results"][0]["scenario_id"]
    testing["checks"] = [
        {
            "scenario_id": scenario,
            "label_claim_id": "claim-1",
            "purpose_claim_id": "claim-1",
            "narration_sentence_indices": [0],
        }
    ]
    narrative.write_text(json.dumps(doc))
    manifest = staged(root, count)
    visual = json.loads(manifest.read_text())
    for asset in visual["assets"]:
        asset["claim_ids"] = ["claim-0"]
    manifest.write_text(json.dumps(visual))
    visuals = prepare(manifest, root / "visuals.zip")
    receipt = json.loads(review.read_text())
    receipt.update(
        schema_version=3,
        narrative_sha256=hashlib.sha256(narrative.read_bytes()).hexdigest(),
        visuals_sha256=hashlib.sha256(visuals.read_bytes()).hexdigest(),
    )
    review.write_text(json.dumps(receipt))
    return evidence, narrative, scenes, review, visuals


def generic_seal(root, docs, **kwargs):
    evidence, narrative, scenes, review, visuals = docs
    return seal_inputs(
        evidence,
        narrative,
        review,
        root / "sealed",
        scenes_path=scenes,
        visuals_path=visuals,
        renderer_image="quay.io/org/image@sha256:" + "b" * 64,
        **kwargs,
    )


@pytest.mark.parametrize("count", [0, 4])
def test_schema3_binds_all_six_payloads_including_empty_visuals(tmp_path, count):
    package = generic_seal(tmp_path, generic_documents(tmp_path, count))
    result = verify_inputs(package)
    assert result["versions"] == {
        "schema": 3,
        "template": 4,
        "policy": 2,
        "image": "quay.io/org/image@sha256:" + "b" * 64,
    }
    assert len(result["visuals"]["assets"]) == count
    with zipfile.ZipFile(package) as archive:
        index = json.loads(archive.read("index.json"))
        assert len(index["files"]) == 6
        assert "visuals.zip" in index["files"]


@pytest.mark.parametrize(
    "change", ["missing", "stale", "unknown_visual", "unknown_claim", "downgrade", "unknown"]
)
def test_schema3_requires_reviewed_visuals_and_exact_versions(tmp_path, change):
    docs = list(generic_documents(tmp_path, 1))
    doc = json.loads(docs[1].read_text())
    receipt = json.loads(docs[3].read_text())
    if change == "missing":
        docs[4] = None
    elif change == "stale":
        receipt["visuals_sha256"] = "0" * 64
    elif change == "unknown_visual":
        doc["slides"][0]["visual_id"] = "missing"
    elif change == "unknown_claim":
        doc["claims"][0]["id"] = "changed"
    docs[1].write_text(json.dumps(doc))
    receipt["narrative_sha256"] = hashlib.sha256(docs[1].read_bytes()).hexdigest()
    docs[3].write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        generic_seal(
            tmp_path,
            docs,
            **(
                {"template_version": 3 if change == "downgrade" else 5}
                if change in ("downgrade", "unknown")
                else {}
            ),
        )


def test_current_template_does_not_retire_legacy_schema2(tmp_path, monkeypatch):
    import autopoc.executive_inputs as module
    from tests.executive_fixtures import make_v3_input

    monkeypatch.setattr(module, "CURRENT_TEMPLATE_VERSION", 4)
    result = verify_inputs(make_v3_input(tmp_path))
    assert result["versions"]["template"] == 3
    assert result["visuals"] is None


def rewrite_package(path, output, change):
    """Rehash an untrusted envelope so semantic guards are exercised independently."""
    with zipfile.ZipFile(path) as archive:
        data = {name: archive.read(name) for name in archive.namelist()}
    change(data)
    index = json.loads(data["index.json"])
    index["files"] = {
        name: {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
        for name, raw in data.items()
        if name != "index.json"
    }
    data["index.json"] = json.dumps(index).encode()
    with zipfile.ZipFile(output, "w") as archive:
        for name, raw in data.items():
            archive.writestr(name, raw)
    return output


@pytest.mark.parametrize("change", ["drop", "policy", "schema", "review", "visual_bytes"])
def test_rehashed_schema3_envelope_cannot_bypass_review_or_version_policy(tmp_path, change):
    package = generic_seal(tmp_path, generic_documents(tmp_path, 1))

    def mutate(data):
        if change == "drop":
            data.pop("visuals.zip")
        elif change == "visual_bytes":
            data["visuals.zip"] += b"changed after review"
        else:
            name = "review.json" if change == "review" else "versions.json"
            doc = json.loads(data[name])
            if change == "policy":
                doc["policy"] = 1
            elif change == "schema":
                doc["schema"] = 2
            else:
                doc.pop("visuals_sha256")
            data[name] = json.dumps(doc).encode()

    with pytest.raises(ValueError):
        verify_inputs(rewrite_package(package, tmp_path / "tampered.zip", mutate))


def test_legacy_envelope_rejects_new_visual_payload(tmp_path):
    evidence, narrative, review = inputs(tmp_path)
    package = seal_inputs(
        evidence,
        narrative,
        review,
        tmp_path / "sealed",
        renderer_image="quay.io/org/image@sha256:" + "b" * 64,
    )

    def mutate(data):
        data["visuals.zip"] = b"not a legacy payload"

    with pytest.raises(ValueError):
        verify_inputs(rewrite_package(package, tmp_path / "tampered.zip", mutate))


def test_seal_rejects_visual_fifo_without_blocking(tmp_path):
    import os
    import subprocess
    import sys

    evidence, narrative, scenes, review, visuals = generic_documents(tmp_path)
    visuals.unlink()
    os.mkfifo(visuals)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; from autopoc.executive_inputs import seal_inputs; import sys; "
            "e,n,s,r,v,o=map(Path,sys.argv[1:]); "
            'seal_inputs(e,n,r,o,scenes_path=s,visuals_path=v,renderer_image="quay.io/org/image@sha256:"+"b"*64)',
            str(evidence),
            str(narrative),
            str(scenes),
            str(review),
            str(visuals),
            str(tmp_path / "sealed"),
        ],
        capture_output=True,
        timeout=2,
        check=False,
    )
    assert result.returncode != 0
    assert b"ValueError" in result.stderr
    assert not (tmp_path / "sealed").exists()


def test_seal_rejects_visual_parent_symlink(tmp_path):
    docs = list(generic_documents(tmp_path))
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    docs[4] = alias / "visuals.zip"
    with pytest.raises(ValueError):
        generic_seal(tmp_path, docs)


def test_seal_bounds_visual_read_before_allocating_oversized_bytes(tmp_path, monkeypatch):
    from pathlib import Path
    from autopoc.executive_visuals import MAX_ARCHIVE

    docs = generic_documents(tmp_path)
    with docs[4].open("wb") as stream:
        stream.truncate(MAX_ARCHIVE + 1)
    original = Path.read_bytes

    def reject_unbounded_visual_read(path):
        if path == docs[4]:
            pytest.fail("sealing must bound visual reads before allocation")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", reject_unbounded_visual_read)
    with pytest.raises(ValueError):
        generic_seal(tmp_path, docs)


def test_seal_visual_replacement_race_rejects_symlink(tmp_path, monkeypatch):
    import os

    docs = generic_documents(tmp_path)
    original = os.open

    def replace_before_open(path, flags, *args, **kwargs):
        if path == docs[4]:
            target = tmp_path / "replacement.zip"
            docs[4].rename(target)
            docs[4].symlink_to(target)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_before_open)
    with pytest.raises(ValueError):
        generic_seal(tmp_path, docs)


def test_seal_freezes_visual_bytes_before_other_inputs_are_read(tmp_path, monkeypatch):
    from pathlib import Path

    docs = generic_documents(tmp_path)
    reviewed = docs[4].read_bytes()
    original = Path.read_bytes

    def replace_after_visual_freeze(path):
        if path == docs[0]:
            docs[4].write_bytes(b"changed after visual read")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", replace_after_visual_freeze)
    package = generic_seal(tmp_path, docs)
    with zipfile.ZipFile(package) as archive:
        assert archive.read("visuals.zip") == reviewed
    assert verify_inputs(package)["visuals"]["assets"] == []
