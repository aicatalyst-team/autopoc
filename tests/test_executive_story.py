"""Spoken claims require the same evidence and immutable review as visible claims."""

import json
import zipfile

import pytest

from autopoc.executive_inputs import seal_inputs, verify_inputs
from tests.executive_fixtures import make_v3_input, refresh_review, v3_documents


def seal(documents, root):
    evidence, narrative, scenes, review = documents
    return seal_inputs(
        evidence,
        narrative,
        review,
        root / "sealed",
        scenes_path=scenes,
        renderer_image="quay.io/org/image@sha256:" + "b" * 64,
    )


def test_v3_seal_preserves_identity(tmp_path):
    result = verify_inputs(make_v3_input(tmp_path, slides=8))
    assert result["versions"]["schema"] == 2
    assert result["versions"]["template"] == 3
    assert len(result["narrative"]["slides"]) == 8


@pytest.mark.parametrize(
    "change",
    [
        "counts",
        "unsupported_sentence",
        "unknown_claim",
        "missing_chapter",
        "reorder",
        "duplicate_slide",
        "selector",
        "missing_trace",
        "title",
        "graph",
        "words",
        "boolean_count",
        "empty_narration",
        "kind",
        "huge_title",
        "gaps",
    ],
)
def test_unsupported_or_misleading_story_structure_cannot_be_sealed(tmp_path, change):
    docs = v3_documents(tmp_path)
    doc = json.loads(docs[1].read_text())
    slide = doc["slides"][0]
    if change == "counts":
        doc["results"]["pass"] = 99
    elif change == "unsupported_sentence":
        slide["narration"][0]["claim_ids"] = []
    elif change == "unknown_claim":
        slide["bullet_claim_ids"] = ["unknown"]
    elif change == "missing_chapter":
        doc["slides"][4]["section"] = "results"
    elif change == "reorder":
        doc["slides"][1], doc["slides"][2] = doc["slides"][2], doc["slides"][1]
    elif change == "duplicate_slide":
        doc["slides"][1]["id"] = slide["id"]
    elif change == "selector":
        doc["claims"][0]["sources"] = ["report.md#L100-L101"]
    elif change == "missing_trace":
        doc["claims"][0]["sources"] = ["missing-trace.json#/spans/0"]
    elif change == "title":
        slide["title_claim_ids"] = []
    elif change == "graph":
        slide["graph"] = {"nodes": [], "edges": [], "acts": []}
    elif change == "words":
        slide["narration"][0]["text"] = "word " * 181
    elif change == "boolean_count":
        doc["results"]["pass"] = True
    elif change == "empty_narration":
        slide["narration"] = []
    elif change == "kind":
        doc["claims"][0]["kind"] = "proven"
    elif change == "huge_title":
        slide["title"] = "x" * 101
    elif change == "gaps":
        doc["coverage_gaps"] = "none"
    docs[1].write_text(json.dumps(doc))
    refresh_review(*docs)
    with pytest.raises(ValueError):
        seal(docs, tmp_path)


@pytest.mark.parametrize("file", ["narrative", "scenes"])
def test_exact_spoken_script_and_policy_are_review_bound(tmp_path, file):
    docs = v3_documents(tmp_path)
    path = docs[1] if file == "narrative" else docs[2]
    doc = json.loads(path.read_text())
    if file == "narrative":
        doc["slides"][0]["narration"][0]["text"] += " Changed."
    else:
        doc["narration"]["model_manifest_sha256"] = "d" * 64
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="review"):
        seal(docs, tmp_path)


@pytest.mark.parametrize(
    "source,valid",
    [
        ("state.json#/project/run_id", True),
        ("report.md#L2-L2", True),
        ("state.json#/project/missing", False),
        ("state.json#/project/~2", False),
        ("state.json#/project/run_id/child", False),
        ("report.md#L0-L2", False),
        ("https://example.com", False),
        ("/private/report.md", False),
    ],
)
def test_source_selectors_address_real_sanitized_data(tmp_path, source, valid):
    docs = v3_documents(tmp_path)
    doc = json.loads(docs[1].read_text())
    doc["claims"][0]["sources"] = [source]
    docs[1].write_text(json.dumps(doc))
    refresh_review(*docs)
    if valid:
        assert verify_inputs(seal(docs, tmp_path))["run_id"] == "run-1"
    else:
        with pytest.raises(ValueError):
            seal(docs, tmp_path)


def test_scene_order_must_match_reviewed_story(tmp_path):
    docs = v3_documents(tmp_path)
    scenes = json.loads(docs[2].read_text())
    scenes["slide_ids"].reverse()
    docs[2].write_text(json.dumps(scenes))
    refresh_review(*docs)
    with pytest.raises(ValueError):
        seal(docs, tmp_path)


def test_v3_uses_same_six_bounded_zip_members(tmp_path):
    with zipfile.ZipFile(make_v3_input(tmp_path)) as archive:
        assert set(archive.namelist()) == {
            "index.json",
            "evidence.zip",
            "narrative.json",
            "review.json",
            "scenes.json",
            "versions.json",
        }


def test_empty_json_selection_is_not_supporting_evidence(tmp_path):
    docs = v3_documents(tmp_path)
    doc = json.loads(docs[1].read_text())
    doc["claims"][0]["sources"] = ["state.json#/phases/poc_report"]
    docs[1].write_text(json.dumps(doc))
    refresh_review(*docs)
    with pytest.raises(ValueError):
        seal(docs, tmp_path)


@pytest.mark.parametrize(
    "case,totals",
    [
        ("simple", {"pass": 1, "fail": 0, "error": 0, "skip": 0, "incomplete": 0}),
        ("complex", {"pass": 3, "fail": 0, "error": 0, "skip": 0, "incomplete": 0}),
        ("failed", {"pass": 1, "fail": 1, "error": 0, "skip": 0, "incomplete": 1}),
    ],
)
def test_authoring_acceptance_examples_preserve_original_evidence(case, totals):
    from pathlib import Path
    from autopoc.evidence import verify_bundle
    from autopoc.executive_story import validate_scene_plan, validate_story

    root = Path(__file__).parent / "fixtures" / "executive-story" / case
    index = verify_bundle(root / "evidence.zip")
    with zipfile.ZipFile(root / "evidence.zip") as archive:
        members = {n: archive.read(n) for n in archive.namelist()}
    narrative = json.loads((root / "narrative.json").read_text())
    validate_story(narrative, index, members)
    validate_scene_plan(json.loads((root / "scenes.json").read_text()), narrative)
    assert narrative["results"] == totals
    if case == "failed":
        assert narrative["conflicts"]
        assert "incomplete_validation" in narrative["coverage_gaps"]
