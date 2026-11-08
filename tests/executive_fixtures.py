"""Small real sealed-input fixtures for narrated rendering, without model downloads."""

import hashlib
import json
from pathlib import Path

from autopoc.evidence import create_bundle
from autopoc.executive_inputs import seal_inputs
from tests.test_evidence import setup_run

SECTIONS = ["objective", "testing", "setup", "results", "limitations", "recommendation"]


def refresh_review(evidence: Path, narrative: Path, scenes: Path, review: Path) -> None:
    review.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "reviewer": "configured-opencode",
                "approved": True,
                "findings": [],
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "narrative_sha256": hashlib.sha256(narrative.read_bytes()).hexdigest(),
                "scenes_sha256": hashlib.sha256(scenes.read_bytes()).hexdigest(),
            }
        )
    )


def v3_documents(root: Path, *, slides: int = 6) -> tuple[Path, Path, Path, Path]:
    setup_run(root)
    (root / "report.md").write_text(
        "# Demo PoC\nDeploy the server on OpenShift.\nUse one HTTP smoke check.\n"
        "One server was deployed.\nOne health check passed.\n"
        "Authenticated operations were not tested.\nValidate authentication next.\n"
    )
    evidence = create_bundle(root / "state.json", root / "attempt-index.json", root / "bundles")
    texts = [
        "Evaluate server deployment on OpenShift.",
        "Use an HTTP smoke check.",
        "One server was deployed.",
        "One health check passed.",
        "Authenticated operations were not tested.",
        "Validate authentication next.",
    ]
    claims = [
        {
            "id": f"claim-{i}",
            "text": text,
            "kind": "planned" if i < 2 else "recommendation" if i == 5 else "observed",
            "sources": [f"report.md#L{i + 2}-L{i + 2}"],
        }
        for i, text in enumerate(texts)
    ]
    order = list(range(6))
    order[3:3] = [2] * (slides - 6)
    deck = [
        {
            "id": f"slide-{i}",
            "section": SECTIONS[k],
            "title": texts[k],
            "title_claim_ids": [f"claim-{k}"],
            "bullet_claim_ids": [f"claim-{k}"],
            "narration": [{"text": texts[k], "claim_ids": [f"claim-{k}"]}],
            "graph": None,
            "graph_claim_ids": [],
        }
        for i, k in enumerate(order)
    ]
    narrative = root / "narrative.json"
    narrative.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "run-1",
                "project_name": "Demo",
                "claims": claims,
                "slides": deck,
                "conflicts": [],
                "coverage_gaps": [],
                "results": {"pass": 1, "fail": 0, "error": 0, "skip": 0, "incomplete": 0},
            }
        )
    )
    scenes = root / "scenes.json"
    scenes.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "slide_ids": [s["id"] for s in deck],
                "narration": {
                    "engine": "kokoro",
                    "voice": "af_heart",
                    "speed": 0.95,
                    "model_manifest_sha256": "c" * 64,
                },
                "timing_policy": {
                    "lead_seconds": 0.35,
                    "tail_seconds": 0.65,
                    "min_scene_seconds": 6,
                    "sentence_gap_seconds": 0.20,
                    "max_scene_seconds": 120,
                    "max_total_seconds": 900,
                    "max_scenes": 30,
                },
            }
        )
    )
    review = root / "review.json"
    refresh_review(evidence, narrative, scenes, review)
    return evidence, narrative, scenes, review


def make_v3_input(root: Path, *, slides: int = 6) -> Path:
    evidence, narrative, scenes, review = v3_documents(root, slides=slides)
    return seal_inputs(
        evidence,
        narrative,
        review,
        root / "sealed",
        scenes_path=scenes,
        renderer_image="quay.io/org/renderer@sha256:" + "b" * 64,
    )
