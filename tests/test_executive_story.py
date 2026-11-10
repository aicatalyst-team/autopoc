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
        ("long", {"pass": 3, "fail": 0, "error": 0, "skip": 0, "incomplete": 0}),
        ("omnigent", {"pass": 5, "fail": 0, "error": 0, "skip": 0, "incomplete": 0}),
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


def test_reviewed_story_cannot_carry_engine_markup_or_a_malformed_lexicon(tmp_path):
    """Pronunciation identity and script text are review-bound, so check at seal."""
    documents = v3_documents(tmp_path)
    narrative = documents[1]
    doc = json.loads(narrative.read_text())
    doc["slides"][0]["narration"][0]["text"] = "Deployed to [Quay](/kˈi/) today."
    narrative.write_text(json.dumps(doc))
    refresh_review(*documents)
    with pytest.raises(ValueError, match="markup"):
        seal(documents, tmp_path / "markup")

    documents = v3_documents(tmp_path / "second")
    plan = json.loads(documents[2].read_text())
    plan["narration"]["lexicon_sha256"] = "not-a-digest"
    documents[2].write_text(json.dumps(plan))
    refresh_review(*documents)
    with pytest.raises(ValueError):
        seal(documents, tmp_path / "digest")


def test_unrenderable_script_length_is_diagnosed_before_synthesis(tmp_path):
    """Structural maxima permit scripts no delivery speed can fit in 900s.

    The estimate rejects only the impossible: it assumes speech far faster than
    Heart, so a rejected script cannot fit even at that bound. Measured PCM
    remains authoritative for everything the estimate accepts.
    """
    from autopoc.executive_story import validate_scene_plan

    documents = v3_documents(tmp_path, slides=30)
    narrative = json.loads(documents[1].read_text())
    plan = json.loads(documents[2].read_text())
    for slide in narrative["slides"]:
        slide["narration"] = [
            {"text": " ".join(["word"] * 15), "claim_ids": slide["title_claim_ids"]}
            for _ in range(12)
        ]
    with pytest.raises(ValueError, match="estimated"):
        validate_scene_plan(plan, narrative)
    documents[1].write_text(json.dumps(narrative))
    refresh_review(documents[0], documents[1], documents[2], documents[3])
    with pytest.raises(ValueError, match="estimated"):
        seal(documents, tmp_path)


def test_plausible_long_script_is_left_to_measured_audio(tmp_path):
    """A script that could fit must not be rejected by the estimate."""
    from autopoc.executive_story import validate_scene_plan

    documents = v3_documents(tmp_path, slides=30)
    narrative = json.loads(documents[1].read_text())
    plan = json.loads(documents[2].read_text())
    for slide in narrative["slides"]:
        slide["narration"] = [
            {"text": " ".join(["word"] * 10), "claim_ids": slide["title_claim_ids"]}
            for _ in range(4)
        ]
    validate_scene_plan(plan, narrative)


def test_estimate_stays_below_the_slowest_measured_delivery(tmp_path):
    """Delivered narration measured 1.84 words/second in its slowest scene.

    The guard must assume speech faster than anything observed, or it would
    reject scripts that do fit; it must not be so loose that a script well over
    budget still reaches synthesis before failing.
    """
    from autopoc.executive_story import DEFAULT_TIMING_POLICY, FASTEST_WORDS_PER_SECOND

    assert FASTEST_WORDS_PER_SECOND > 2.20
    budget = DEFAULT_TIMING_POLICY["max_total_seconds"]
    measured_capacity = budget * 2.05
    rejects_above = budget * FASTEST_WORDS_PER_SECOND
    assert rejects_above / measured_capacity <= 1.5


def test_story_accepts_real_topoloop_edge_pairs(tmp_path):
    from pathlib import Path

    docs = v3_documents(tmp_path)
    doc = json.loads(docs[1].read_text())
    doc["slides"][2]["graph"] = json.loads(
        (Path(__file__).parent / "fixtures/executive-story/graph.json").read_text()
    )
    doc["slides"][2]["graph_claim_ids"] = ["claim-2"]
    docs[1].write_text(json.dumps(doc))
    refresh_review(*docs)
    assert verify_inputs(seal(docs, tmp_path))["run_id"] == "run-1"


# Shared JSON exercises the same schema-3 contract in Python and JavaScript.
def generic_cases():
    from pathlib import Path

    return json.loads(
        (Path(__file__).parent / "fixtures/executive-story/schema3-cases.json").read_text()
    )


def validate_generic(case):
    from autopoc.executive_story import validate_scene_plan, validate_story

    validate_story(
        case["narrative"],
        case["evidence_index"],
        {k: v.encode() for k, v in case["members"].items()},
    )
    validate_scene_plan(case["plan"], case["narrative"])


@pytest.mark.parametrize("case", generic_cases(), ids=lambda c: c["name"])
def test_schema3_generic_hosts_graphs_and_paginated_inventory(case):
    validate_generic(case)


@pytest.mark.parametrize(
    "change",
    [
        "missing_context",
        "missing_optional",
        "credentials",
        "http",
        "bad_revision",
        "unknown_definition",
        "invisible_definition",
        "opening_layout",
        "missing_layout",
        "unknown_layout",
        "missing_visual",
        "summary_visual",
        "checks_visual",
        "topology_without_graph",
        "duplicate_check",
        "missing_check",
        "unknown_check",
        "too_many_rows",
        "wrong_section",
        "missing_checks",
        "unknown_label",
        "unknown_purpose",
        "empty_mapping",
        "duplicate_mapping",
        "reverse_mapping",
        "noncontiguous_mapping",
        "overlapping_mapping",
        "outside_mapping",
        "boolean_mapping",
        "nonchecks_rows",
        "unknown_version",
    ],
)
def test_schema3_rejects_invalid_identity_layout_and_check_mappings(change):
    case = generic_cases()[4]
    n = case["narrative"]
    first = n["slides"][0]
    slide = n["slides"][1]
    row = slide["checks"][0]
    if change == "missing_context":
        del n["project_context"]
    elif change == "missing_optional":
        del n["project_context"]["homepage_url"]
    elif change == "credentials":
        n["project_context"]["repository_url"] = "https://user:secret@git.example/repo"
    elif change == "http":
        n["project_context"]["documentation_url"] = "http://example.org/docs"
    elif change == "bad_revision":
        n["project_context"]["revision"] = ""
    elif change == "unknown_definition":
        n["project_context"]["definition_claim_id"] = "missing"
    elif change == "invisible_definition":
        first["bullet_claim_ids"] = ["claim-1"]
        first["title_claim_ids"] = ["claim-1"]
    elif change == "opening_layout":
        first["layout"] = "summary"
    elif change == "missing_layout":
        del first["layout"]
    elif change == "unknown_layout":
        slide["layout"] = "gallery"
    elif change == "missing_visual":
        del first["visual_id"]
    elif change == "summary_visual":
        n["slides"][-1]["visual_id"] = "image-1"
    elif change == "checks_visual":
        slide["visual_id"] = "image-1"
    elif change == "topology_without_graph":
        n["slides"][-1]["layout"] = "topology"
    elif change == "duplicate_check":
        slide["checks"][1]["scenario_id"] = row["scenario_id"]
    elif change == "missing_check":
        slide["checks"].pop()
    elif change == "unknown_check":
        row["scenario_id"] = "not-original"
    elif change == "too_many_rows":
        slide["checks"].append(n["slides"][2]["checks"].pop())
    elif change == "wrong_section":
        first["checks"] = slide["checks"]
        slide["checks"] = []
        first["layout"] = "checks"
    elif change == "missing_checks":
        del slide["checks"]
    elif change == "unknown_label":
        row["label_claim_id"] = "missing"
    elif change == "unknown_purpose":
        row["purpose_claim_id"] = "missing"
    elif change == "empty_mapping":
        row["narration_sentence_indices"] = []
    elif change == "duplicate_mapping":
        row["narration_sentence_indices"] = [0, 0]
    elif change == "reverse_mapping":
        row["narration_sentence_indices"] = [1, 0]
    elif change == "noncontiguous_mapping":
        row["narration_sentence_indices"] = [0, 2]
    elif change == "overlapping_mapping":
        slide["checks"][1]["narration_sentence_indices"] = [0]
    elif change == "outside_mapping":
        row["narration_sentence_indices"] = [12]
    elif change == "boolean_mapping":
        row["narration_sentence_indices"] = [True]
    elif change == "nonchecks_rows":
        n["slides"][-1]["checks"] = [row]
    elif change == "unknown_version":
        n["schema_version"] = 4
    with pytest.raises(ValueError):
        validate_generic(case)


def test_schema3_empty_inventory_requires_testing_checks_layout():
    case = generic_cases()[0]
    case["narrative"]["slides"][1]["layout"] = "summary"
    with pytest.raises(ValueError):
        validate_generic(case)


def test_derive_checks_preserves_verified_names_statuses_and_order():
    from autopoc.executive_story import derive_checks

    case = generic_cases()[2]
    actual = derive_checks(case["evidence_index"])
    assert actual == {
        "schema_version": 1,
        "run_id": "run-1",
        "results": [
            {"scenario_id": "check-0", "scenario_name": "Original scenario 0", "status": "pass"},
            {"scenario_id": "check-1", "scenario_name": "Original scenario 1", "status": "fail"},
            {"scenario_id": "check-2", "scenario_name": "Original scenario 2", "status": "error"},
            {"scenario_id": "check-3", "scenario_name": "Original scenario 3", "status": "skip"},
            {
                "scenario_id": "check-4",
                "scenario_name": "Original scenario 4",
                "status": "incomplete",
            },
        ],
    }
    actual["results"][0]["scenario_name"] = "Changed"
    assert (
        case["evidence_index"]["final_results"]["results"][0]["scenario_name"]
        == "Original scenario 0"
    )


def test_schema3_reviewed_metadata_and_multi_sentence_check_ranges():
    case = generic_cases()[1]
    n = case["narrative"]
    n["project_context"].update(
        revision="abc123",
        homepage_url="https://example.org/",
        documentation_url="https://docs.example.org/guide",
    )
    n["slides"][0]["visual_id"] = "project-image"
    slide = n["slides"][1]
    slide["narration"].append(
        {"text": "The check also covers invalid input.", "claim_ids": ["claim-1"]}
    )
    slide["checks"][0]["narration_sentence_indices"] = [0, 1]
    validate_generic(case)


def test_schema3_long_inventory_fails_lower_bound_before_synthesis():
    import copy

    case = generic_cases()[4]
    n = case["narrative"]
    while len(n["slides"]) < 30:
        extra = copy.deepcopy(n["slides"][-1])
        extra["id"] = f"extra-{len(n['slides'])}"
        n["slides"].append(extra)
    for slide in n["slides"]:
        slide["narration"] = [
            {"text": " ".join(["word"] * 15), "claim_ids": ["claim-0"]} for _ in range(12)
        ]
    case["plan"]["slide_ids"] = [s["id"] for s in n["slides"]]
    with pytest.raises(ValueError, match="estimated"):
        validate_generic(case)


@pytest.mark.parametrize(
    "url",
    [
        "https://exa%mple.org/repo",
        "https://exa%25mple.org/repo",
        "https://exa%2Fmple.org/repo",
        "https:///example.org",
        "https://@example.org",
        "https://example.org:bad",
        "https://example.org/\nsecret",
    ],
)
def test_schema3_rejects_malformed_https_authorities(url):
    case = generic_cases()[0]
    case["narrative"]["project_context"]["repository_url"] = url
    with pytest.raises(ValueError):
        validate_generic(case)


@pytest.mark.parametrize("url", ["https://ex%61mple.org/repo", "https://[2001:db8::1]/repo"])
def test_schema3_preserves_valid_encoded_and_ipv6_hosts(url):
    case = generic_cases()[0]
    case["narrative"]["project_context"]["repository_url"] = url
    validate_generic(case)
