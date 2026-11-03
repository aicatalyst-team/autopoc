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
    with zipfile.ZipFile(package) as archive:
        assert set(archive.namelist()) == {
            "index.json",
            "evidence.zip",
            "narrative.json",
            "review.json",
            "scenes.json",
            "versions.json",
        }


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
