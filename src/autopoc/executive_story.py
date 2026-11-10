"""Structural evidence/story contracts shared by sealing and offline narration.

These checks establish references and bounds, not semantic truth. The configured
content reviewer must still assess whether sources actually support each claim.
"""

from __future__ import annotations

import re
from typing import cast
from urllib.parse import urlsplit

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
# Measured from the delivered OpenShell narration (410 words over 199.60s of
# speech): Heart at speed 0.95 averages 2.05 words per second, per-scene range
# 1.84-2.20. Estimating at 3.0 stays a lower bound - 63% faster than the slowest
# observed scene - so the guard still cannot reject a script that might fit,
# while catching scripts roughly 1.5x over budget instead of only 2x over.
# Re-measure from docs/validation/ receipts before changing this.
FASTEST_WORDS_PER_SECOND = 3.0
# misaki.en.LINK_REGEX: Misaki reads "[word](/ips/)" in ordinary text as a
# pronunciation or stress override, so reviewed scripts must never contain it.
MARKUP = re.compile(r"\[[^\]]+\]\([^)]*\)")


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
        if field == "edges":
            _need(
                all(
                    isinstance(row, list) and len(row) == 2 and all(isinstance(v, str) for v in row)
                    for row in graph[field]
                ),
                "Invalid storyboard graph edges",
            )
        else:
            _need(all(isinstance(row, dict) for row in graph[field]), "Invalid storyboard graph")


def validate_story(narrative: dict, evidence_index: dict, members: dict[str, bytes]) -> None:
    """Reject unsupported references, totals, classification and section order."""
    _need(
        isinstance(narrative, dict)
        and type(narrative.get("schema_version")) is int
        and narrative["schema_version"] in (2, 3)
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
            spoken = _text(sentence.get("text"), 2000)
            _need(not MARKUP.search(spoken), "Narration must not contain engine markup")
            words += len(spoken.split())
            _claim_refs(sentence.get("claim_ids"), claims)
        _need(words <= 180, "Narration exceeds per-slide word limit")
        graph = slide.get("graph")
        validate_graph(graph)
        _claim_refs(slide.get("graph_claim_ids"), claims, minimum=0 if graph is None else 1)
        if graph is None:
            _need(slide["graph_claim_ids"] == [])
    if narrative["schema_version"] == 3:
        _validate_generic_story(narrative, claims, evidence_index)
    _need(
        ranks == sorted(ranks) and set(REQUIRED_SECTIONS) <= chapters,
        "Required story chapters must appear in order",
    )


def derive_checks(evidence_index: dict) -> dict:
    """Copy original verified scenario identities and outcomes for offline display."""
    return {
        "schema_version": 1,
        "run_id": evidence_index["run_id"],
        "results": [
            {key: row[key] for key in ("scenario_id", "scenario_name", "status")}
            for row in evidence_index["final_results"]["results"]
        ],
    }


def _https_reference(value) -> None:
    reference = _text(value, 2048)
    try:
        parsed = urlsplit(reference)
        _need(
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not re.search(r"[\s\\\x00-\x1f\x7f]", reference),
            "Project references must be credential-free HTTPS URLs",
        )
        # Accessing port also rejects malformed authorities.
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid project reference") from exc


def _validate_generic_story(narrative: dict, claims: set[str], evidence_index: dict) -> None:
    context = narrative.get("project_context")
    _need(
        isinstance(context, dict)
        and set(context)
        == {
            "repository_url",
            "revision",
            "definition_claim_id",
            "homepage_url",
            "documentation_url",
        },
        "Missing project context",
    )
    context = cast(dict, context)
    _https_reference(context["repository_url"])
    for field in ("homepage_url", "documentation_url"):
        if context[field] is not None:
            _https_reference(context[field])
    if context["revision"] is not None:
        _text(context["revision"], 280)
    _claim_refs([context["definition_claim_id"]], claims)
    slides = narrative["slides"]
    _need(slides[0].get("layout") == "identity", "Opening must identify the project")
    _need(
        context["definition_claim_id"]
        in (slides[0]["title_claim_ids"] + slides[0]["bullet_claim_ids"]),
        "Project definition must be visible",
    )
    scenario_ids, check_slides = [], 0
    for slide in slides:
        layout = slide.get("layout")
        _need(isinstance(layout, str) and layout in {"summary", "identity", "checks", "topology"})
        _need("visual_id" in slide)
        visual = slide["visual_id"]
        if visual is not None:
            _id(visual)
            _need(layout == "identity", "Only identity layout supports imagery")
        if layout == "topology":
            _need(slide.get("graph") is not None, "Topology layout requires a graph")
        rows = slide.get("checks")
        _need(isinstance(rows, list))
        if layout != "checks":
            _need(rows == [], "Check rows require checks layout")
            continue
        check_slides += 1
        _need(
            slide["section"] == "testing" and len(rows) <= 5,
            "Paginate testing checks in five-row slides",
        )
        previous = -1
        for row in rows:
            _need(
                isinstance(row, dict)
                and set(row)
                == {
                    "scenario_id",
                    "label_claim_id",
                    "purpose_claim_id",
                    "narration_sentence_indices",
                }
            )
            scenario_ids.append(_id(row["scenario_id"]))
            _claim_refs([row["label_claim_id"]], claims)
            _claim_refs([row["purpose_claim_id"]], claims)
            indices = row["narration_sentence_indices"]
            _need(isinstance(indices, list) and bool(indices), "Check row needs spoken explanation")
            _need(all(type(i) is int and 0 <= i < len(slide["narration"]) for i in indices))
            _need(
                indices == list(range(indices[0], indices[-1] + 1)) and indices[0] > previous,
                "Check sentence mappings must be contiguous, ordered and nonoverlapping",
            )
            previous = indices[-1]
    original = [r["scenario_id"] for r in derive_checks(evidence_index)["results"]]
    _need(
        len(scenario_ids) == len(set(scenario_ids)) and set(scenario_ids) == set(original),
        "Every original scenario must appear exactly once",
    )
    _need(check_slides >= 1, "Explicit testing checks content is required even for no checks")


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
    # Optional: plans reviewed before the lexicon existed render without overrides.
    lexicon = narration.get("lexicon_sha256")
    _need(
        lexicon is None or (isinstance(lexicon, str) and re.fullmatch(r"[0-9a-f]{64}", lexicon)),
        "Invalid reviewed pronunciation identity",
    )
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
    estimate_total_seconds(narrative, policy)


def estimate_total_seconds(narrative: dict, policy: dict) -> float:
    """Reject only scripts no delivery speed can fit, and say by how much.

    This is a lower bound, not a prediction: it assumes speech far faster than
    Heart actually produces, so an accepted script may still exceed the guard
    once measured. Measured PCM in `executive_speech` stays authoritative, and
    nothing here clips, paces or shortens reviewed narration.
    """
    slides = narrative["slides"]
    total, spoken = 0.0, 0
    for slide in slides:
        sentences = slide.get("narration") or []
        words = sum(len(str(s.get("text", "")).split()) for s in sentences)
        spoken += words
        speech = (
            words / FASTEST_WORDS_PER_SECOND
            + max(len(sentences) - 1, 0) * policy["sentence_gap_seconds"]
        )
        total += max(
            policy["min_scene_seconds"],
            speech + policy["lead_seconds"] + policy["tail_seconds"],
        )
    _need(
        total <= policy["max_total_seconds"],
        f"Narration cannot fit the {policy['max_total_seconds']:g}s guard: {spoken} words"
        f" over {len(slides)} scenes need at least an estimated {total:.1f}s even at"
        " implausibly fast delivery. Shorten the script or seal a reviewed larger"
        " render policy; narration is never clipped or accelerated to fit.",
    )
    return total
