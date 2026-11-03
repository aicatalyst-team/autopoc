"""Seal reviewed narrative with verified original evidence for offline rendering."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from autopoc.evidence import verify_bundle

MAX_BYTES = 24 * 1024 * 1024
MEMBERS = {"evidence.zip", "narrative.json", "review.json", "scenes.json", "versions.json"}
TOPICS = ("purpose", "testing_strategy", "test_execution", "platform_suitability")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate input key")
            result[key] = value
        return result

    return json.loads(
        data,
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid number")),
    )


def _dump(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _validate(data: dict[str, bytes]) -> dict:
    # Reuse the collector's exact publication text policy.
    from autopoc.evidence import sanitize_text

    narrative, review = _json(data["narrative.json"]), _json(data["review.json"])
    scenes, versions = _json(data["scenes.json"]), _json(data["versions.json"])
    if versions.get("schema") != 1 or versions.get("policy") != 1 or versions.get("template") != 1:
        raise ValueError("Unsupported render-input version")
    if not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", versions.get("image", "")):
        raise ValueError("Renderer image must be pinned by digest")
    if (
        review.get("schema_version") != 1
        or review.get("approved") is not True
        or review.get("reviewer") != "configured-opencode"
        or review.get("findings") != []
        or review.get("narrative_sha256") != _hash(data["narrative.json"])
        or review.get("evidence_sha256") != _hash(data["evidence.zip"])
    ):
        raise ValueError("A matching automated content review is required")
    with tempfile.TemporaryDirectory(prefix="autopoc-verify-inputs-") as directory:
        evidence = Path(directory) / "evidence.zip"
        evidence.write_bytes(data["evidence.zip"])
        index = verify_bundle(evidence)
    if (
        not index["eligible_for_render"]
        or narrative.get("schema_version") != 1
        or narrative.get("run_id") != index["run_id"]
    ):
        raise ValueError("A usable report and matching run identity are required")
    if narrative.get("results") != index["final_results"]["totals"]:
        raise ValueError("Narrative totals disagree with original evidence")
    if (
        not isinstance(narrative.get("project_name"), str)
        or not 1 <= len(narrative["project_name"]) <= 100
    ):
        raise ValueError("Invalid project name")
    for name in ("narrative.json", "review.json", "scenes.json"):
        if sanitize_text(data[name].decode()) != data[name].decode():
            raise ValueError("Unsanitized render input")
    for topic in TOPICS:
        claims = narrative.get(topic)
        if not isinstance(claims, list) or not 1 <= len(claims) <= 4:
            raise ValueError("All four topics require concise evidence-based claims")
        for claim in claims:
            if not isinstance(claim.get("text"), str) or not 1 <= len(claim["text"]) <= 280:
                raise ValueError("Invalid executive claim")
            references = claim.get("sources")
            if (
                not isinstance(references, list)
                or not references
                or any(
                    not isinstance(ref, str) or ref.split("#", 1)[0] not in index["files"]
                    for ref in references
                )
            ):
                raise ValueError("Unknown claim evidence reference")
    limitations = narrative.get("limitations")
    if narrative.get("scenario_flow") and (
        len(narrative["test_execution"]) > 2
        or sum(len(c["text"]) for c in narrative["test_execution"]) > 300
    ):
        raise ValueError("Execution explanation must fit alongside the scenario animation")
    if (
        not isinstance(limitations, list)
        or not 1 <= len(limitations) <= 5
        or any(not isinstance(text, str) or not 1 <= len(text) <= 200 for text in limitations)
    ):
        raise ValueError("Explicit limitations are required")
    for graph in (narrative.get("topology"), narrative.get("scenario_flow")):
        # Require the arrays rather than defaulting them: renderer/render.mjs
        # rejects a graph with a missing nodes/edges/acts key, and a seal that
        # accepts one only defers the failure to an aborted render.
        if graph is not None and (
            not isinstance(graph, dict)
            or not all(isinstance(graph.get(key), list) for key in ("nodes", "edges", "acts"))
            or len(graph["nodes"]) > 12
            or len(graph["edges"]) > 20
            or len(graph["acts"]) > 5
        ):
            raise ValueError("Topology exceeds executive graph limits")
    durations = scenes.get("durations")
    if (
        not isinstance(durations, list)
        or len(durations) != 6
        or any(type(d) not in (int, float) or not 1 <= d <= 60 for d in durations)
        or sum(durations) > 180
    ):
        raise ValueError("Invalid scene timing")
    return {
        "run_id": index["run_id"],
        "evidence_index": index,
        "narrative": narrative,
        "scenes": scenes,
        "versions": versions,
    }


def seal_inputs(
    evidence_path: Path,
    narrative_path: Path,
    review_path: Path,
    output_dir: Path,
    *,
    renderer_image: str,
    scenes_path: Path | None = None,
) -> Path:
    """Write an immutable input ZIP after validating report, totals and review."""
    paths = {
        "evidence.zip": evidence_path,
        "narrative.json": narrative_path,
        "review.json": review_path,
    }
    if scenes_path:
        paths["scenes.json"] = scenes_path
    for path in paths.values():
        if path.is_symlink() or path.stat().st_size > MAX_BYTES:
            raise ValueError("Invalid render input file")
    if sum(path.stat().st_size for path in paths.values()) > MAX_BYTES - 1024 * 1024:
        raise ValueError("Render inputs exceed size limit")
    data = {name: path.read_bytes() for name, path in paths.items()}
    data.setdefault("scenes.json", _dump({"durations": [20] * 6}))
    data["versions.json"] = _dump(
        {"schema": 1, "policy": 1, "template": 1, "image": renderer_image}
    )
    validated = _validate(data)
    index = {
        "schema_version": 1,
        "run_id": validated["run_id"],
        "files": {
            name: {"sha256": _hash(content), "size": len(content)}
            for name, content in sorted(data.items())
        },
    }
    data["index.json"] = _dump(index)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(data.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)
    raw = buffer.getvalue()
    output_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    destination = output_dir / f"{_hash(raw)}.zip"
    with tempfile.NamedTemporaryFile(dir=output_dir, delete=False) as stream:
        stream.write(raw)
        temporary = Path(stream.name)
    try:
        verify_inputs(temporary)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise ValueError("Sealed input identity conflicts") from None
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def verify_inputs(path: Path) -> dict:
    """Verify exact members, bounds, hashes and review binding without extraction."""
    try:
        if path.is_symlink() or path.stat().st_size > MAX_BYTES:
            raise ValueError("Invalid sealed input size")
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if (
                len(entries) != 6
                or {i.filename for i in entries} != MEMBERS | {"index.json"}
                or sum(i.file_size for i in entries) > MAX_BYTES
                or any(
                    i.flag_bits & 1 or i.is_dir() or (i.external_attr >> 16) & 0o170000 == 0o120000
                    for i in entries
                )
            ):
                raise ValueError("Invalid sealed input archive")
            data = {i.filename: archive.read(i) for i in entries}
        index = _json(data.pop("index.json"))
        if index.get("schema_version") != 1 or index.get("files") != {
            name: {"sha256": _hash(content), "size": len(content)} for name, content in data.items()
        }:
            raise ValueError("Sealed input integrity mismatch")
        result = _validate(data)
        if result["run_id"] != index["run_id"]:
            raise ValueError("Sealed run identity mismatch")
        return result
    except (OSError, KeyError, TypeError, AttributeError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError("Cannot verify sealed inputs") from exc
