"""Structural evidence/story contracts shared by sealing and offline narration.

These checks establish references and bounds, not semantic truth. The configured
content reviewer must still assess whether sources actually support each claim.
"""

from __future__ import annotations

import re
from typing import cast

from autopoc.evidence import _json

SECTIONS = (
    "objective",
    "testing",
    "setup",
    "execution",
    "results",
    "limitations",
    "recommendation",
)
REQUIRED_SECTIONS = tuple(s for s in SECTIONS if s != "execution")
DEFAULT_TIMING_POLICY = {
    "lead_seconds": 0.35,
    "tail_seconds": 0.65,
    "min_scene_seconds": 6,
    "sentence_gap_seconds": 0.20,
    "max_scene_seconds": 120,
    "max_total_seconds": 900,
    "max_scenes": 30,
}


def _need(condition, message="Invalid executive storyboard") -> None:
    if not condition:
        raise ValueError(message)


def _text(value, limit: int) -> str:
    _need(isinstance(value, str) and 1 <= len(value) <= limit and bool(value.strip()))
    return value


def _id(value) -> str:
    _need(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value))
    return value


def _claim_refs(value, claims: set[str], *, minimum=1, maximum=512) -> None:
    _need(isinstance(value, list) and minimum <= len(value) <= maximum)
    _need(all(isinstance(c, str) and c in claims for c in value))
    _need(len(value) == len(set(value)))


def validate_source(reference: str, members: dict[str, bytes]) -> None:
    """Resolve a whole member, inclusive line range, or RFC 6901 JSON Pointer."""
    _text(reference, 512)
    member, separator, selector = reference.partition("#")
    _need(member in members and bool(members[member].strip()), "Unknown evidence reference")
    if not separator:
        return
    lines = re.fullmatch(r"L([1-9][0-9]*)-L([1-9][0-9]*)", selector)
    if lines:
        first, last = map(int, lines.groups())
        _need(
            first <= last <= len(members[member].decode("utf-8").splitlines()),
            "Unknown evidence selector",
        )
        return
    _need(member.endswith(".json") and selector.startswith("/"), "Unknown evidence selector")
    try:
        value = _json(members[member])
        for component in selector[1:].split("/"):
            _need(not re.search(r"~(?![01])", component), "Invalid JSON Pointer")
            key = component.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                _need(re.fullmatch(r"0|[1-9][0-9]*", key), "Unknown evidence selector")
                value = value[int(key)]
            else:
                _need(isinstance(value, dict), "Unknown evidence selector")
                value = value[key]
        _need(
            value is not None and value != "" and value != [] and value != {},
            "Empty evidence selector",
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Unknown evidence selector") from exc


def validate_graph(graph) -> None:
    if graph is None:
        return
    _need(isinstance(graph, dict), "Invalid storyboard graph")
    for field, maximum in (("nodes", 12), ("edges", 20), ("acts", 5)):
        _need(
            isinstance(graph.get(field), list) and len(graph[field]) <= maximum,
            "Topology exceeds executive graph limits",
        )
        _need(all(isinstance(row, dict) for row in graph[field]), "Invalid storyboard graph")


def validate_story(narrative: dict, evidence_index: dict, members: dict[str, bytes]) -> None:
    """Reject unsupported references, totals, classification and section order."""
    _need(
        isinstance(narrative, dict)
        and type(narrative.get("schema_version")) is int
        and narrative["schema_version"] == 2
    )
    _need(narrative.get("run_id") == evidence_index["run_id"], "Story run identity mismatch")
    _text(narrative.get("project_name"), 100)
    totals = narrative.get("results")
    _need(
        isinstance(totals, dict) and set(totals) == {"pass", "fail", "error", "skip", "incomplete"}
    )
    totals = cast(dict, totals)
    _need(all(type(v) is int and v >= 0 for v in totals.values()), "Invalid scenario totals")
    _need(
        totals == evidence_index["final_results"]["totals"],
        "Narrative totals disagree with original evidence",
    )
    ledger = narrative.get("claims")
    _need(isinstance(ledger, list) and 1 <= len(ledger) <= 512)
    ledger = cast(list, ledger)
    claims = set()
    for claim in ledger:
        _need(isinstance(claim, dict))
        identity = _id(claim.get("id"))
        _need(identity not in claims, "Duplicate executive claim")
        claims.add(identity)
        _text(claim.get("text"), 280)
        _need(
            isinstance(claim.get("kind"), str)
            and claim["kind"] in {"planned", "observed", "inferred", "recommendation"}
        )
        sources = claim.get("sources")
        _need(isinstance(sources, list) and 1 <= len(sources) <= 16)
        for source in sources:
            validate_source(source, members)
    gaps = narrative.get("coverage_gaps")
    _need(isinstance(gaps, list) and len(gaps) <= 32)
    gaps = cast(list, gaps)
    for gap in gaps:
        _text(gap, 280)
    _need(
        set(evidence_index["coverage_gaps"]) <= set(gaps),
        "Original evidence gaps must remain explicit",
    )
    conflicts = narrative.get("conflicts")
    _need(isinstance(conflicts, list) and len(conflicts) <= 32)
    conflicts = cast(list, conflicts)
    for conflict in conflicts:
        _need(isinstance(conflict, dict))
        _text(conflict.get("text"), 280)
        _claim_refs(conflict.get("claim_ids"), claims, minimum=2)
    slides = narrative.get("slides")
    _need(isinstance(slides, list) and 6 <= len(slides) <= 30)
    slides = cast(list, slides)
    seen, chapters, ranks = set(), set(), []
    for slide in slides:
        _need(isinstance(slide, dict))
        identity = _id(slide.get("id"))
        _need(identity not in seen, "Duplicate storyboard slide")
        seen.add(identity)
        section = slide.get("section")
        _need(section in SECTIONS)
        chapters.add(section)
        ranks.append(SECTIONS.index(section))
        _text(slide.get("title"), 100)
        _claim_refs(slide.get("title_claim_ids"), claims)
        _claim_refs(slide.get("bullet_claim_ids"), claims, maximum=4)
        sentences = slide.get("narration")
        _need(isinstance(sentences, list) and 1 <= len(sentences) <= 12)
        words = 0
        for sentence in sentences:
            _need(isinstance(sentence, dict))
            words += len(_text(sentence.get("text"), 2000).split())
            _claim_refs(sentence.get("claim_ids"), claims)
        _need(words <= 180, "Narration exceeds per-slide word limit")
        graph = slide.get("graph")
        validate_graph(graph)
        _claim_refs(slide.get("graph_claim_ids"), claims, minimum=0 if graph is None else 1)
        if graph is None:
            _need(slide["graph_claim_ids"] == [])
    _need(
        ranks == sorted(ranks) and set(REQUIRED_SECTIONS) <= chapters,
        "Required story chapters must appear in order",
    )


def validate_scene_plan(plan: dict, narrative: dict) -> None:
    """The reviewed policy and script order are immutable before synthesis."""
    _need(
        isinstance(plan, dict)
        and type(plan.get("schema_version")) is int
        and plan["schema_version"] == 2
    )
    _need(
        plan.get("slide_ids") == [s["id"] for s in narrative["slides"]],
        "Scene order differs from storyboard",
    )
    _need("durations" not in plan, "Narrated durations must come from measured audio")
    narration = plan.get("narration")
    _need(isinstance(narration, dict))
    narration = cast(dict, narration)
    _need(narration.get("engine") == "kokoro" and narration.get("voice") == "af_heart")
    speed = narration.get("speed")
    _need(type(speed) in (int, float) and speed == 0.95)
    digest = narration.get("model_manifest_sha256")
    _need(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest))
    policy = plan.get("timing_policy")
    _need(isinstance(policy, dict) and set(policy) == set(DEFAULT_TIMING_POLICY))
    policy = cast(dict, policy)
    _need(
        all(
            type(policy[k]) in (int, float) and policy[k] == value
            for k, value in DEFAULT_TIMING_POLICY.items()
        ),
        "Unsupported narration timing policy",
    )
