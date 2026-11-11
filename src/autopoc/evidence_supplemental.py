"""Selected, run-bound supplemental evidence; never discover files recursively."""

from __future__ import annotations

import math
import re
from pathlib import Path

from autopoc.evidence import (
    _dump,
    _hash,
    _identifier,
    _json,
    _path,
    _require,
    sanitize_text,
)

KINDS = {"log", "trace", "deployment", "analysis", "test_definition"}
MAX_RECORDS = 32
MAX_RECORD_BYTES = 512 * 1024


def _select(data: dict, names: tuple[str, ...]) -> dict:
    return {key: data[key] for key in names if key in data}


def _deployment(doc: dict, run_id: str) -> dict:
    _require(doc.get("run_id") == run_id and type(doc.get("observed")) is bool)
    _require(isinstance(doc.get("resources"), list) and len(doc["resources"]) <= 256)
    result = []
    for resource in doc["resources"]:
        _require(isinstance(resource, dict) and isinstance(resource.get("kind"), str))
        if resource["kind"] == "Secret":
            continue
        metadata = resource.get("metadata", {})
        _require(isinstance(metadata, dict) and isinstance(metadata.get("name"), str))
        clean = {
            "kind": resource["kind"],
            "metadata": _select(metadata, ("name", "namespace", "labels")),
        }
        spec = resource.get("spec", {})
        _require(isinstance(spec, dict))
        clean["spec"] = _select(
            spec,
            (
                "replicas",
                "selector",
                "ports",
                "type",
                "host",
                "to",
                "accessModes",
                "storageClassName",
                "resources",
                "volumeMode",
            ),
        )
        if "tls" in spec:
            _require(isinstance(spec["tls"], dict))
            clean["spec"]["tls"] = _select(
                spec["tls"], ("termination", "insecureEdgeTerminationPolicy")
            )
        pod = spec.get("template", {}).get("spec", {}) if "template" in spec else spec
        _require(isinstance(pod, dict))
        if "containers" in pod:
            _require(isinstance(pod["containers"], list))
            selected_pod = _select(pod, ("securityContext", "serviceAccountName"))
            selected_pod["containers"] = [
                _select(
                    c, ("name", "image", "ports", "resources", "securityContext", "volumeMounts")
                )
                for c in pod["containers"]
                if isinstance(c, dict)
            ]
            selected_pod["volumes"] = [
                _select(v, ("name", "emptyDir", "persistentVolumeClaim"))
                for v in pod.get("volumes", [])
                if isinstance(v, dict)
            ]
            if "template" in spec:
                clean["spec"]["template"] = {"spec": selected_pod}
            else:
                clean["spec"].update(selected_pod)
        status = resource.get("status", {})
        _require(isinstance(status, dict))
        clean["status"] = _select(
            status, ("phase", "replicas", "readyReplicas", "availableReplicas", "conditions")
        )
        result.append(clean)
    return {"run_id": run_id, "observed": doc["observed"], "resources": result}


def _trace(doc: dict, run_id: str) -> dict:
    _require(doc.get("run_id") == run_id)
    spans = doc["spans"]
    _require(isinstance(spans, list) and 1 <= len(spans) <= 2048)
    clean, seen = [], set()
    for span in spans:
        _require(isinstance(span, dict) and span.get("run_id", run_id) == run_id)
        for name in ("trace_id", "span_id", "service", "operation", "status"):
            _require(isinstance(span.get(name), str) and 1 <= len(span[name]) <= 240)
        identity = (span["trace_id"], span["span_id"])
        _require(identity not in seen)
        seen.add(identity)
        _require(span.get("parent_span_id") is None or isinstance(span["parent_span_id"], str))
        for name in ("start_time", "duration_seconds"):
            value = span[name]
            _require(type(value) in (int, float) and math.isfinite(value) and value >= 0)
        clean.append(
            _select(
                span,
                (
                    "trace_id",
                    "span_id",
                    "parent_span_id",
                    "service",
                    "operation",
                    "start_time",
                    "duration_seconds",
                    "status",
                ),
            )
        )
    return {"run_id": run_id, "spans": clean}


def _normalize(raw: bytes, kind: str, run_id: str) -> bytes:
    if kind in {"trace", "deployment"}:
        doc = _json(raw)
        _require(isinstance(doc, dict))
        normalized = _trace(doc, run_id) if kind == "trace" else _deployment(doc, run_id)
        return sanitize_text(_dump(normalized).decode()).encode()
    return sanitize_text(raw.decode("utf-8")).encode()


def _records(descriptor: dict, run_id: str) -> list[dict]:
    _require(
        isinstance(descriptor, dict)
        and type(descriptor.get("schema_version")) is int
        and descriptor["schema_version"] == 1
        and descriptor.get("run_id") == run_id
    )
    records = descriptor["records"]
    _require(isinstance(records, list) and len(records) <= MAX_RECORDS)
    seen = set()
    for row in records:
        _require(isinstance(row, dict))
        identity = _identifier(row.get("id"))
        _require(identity not in seen and row.get("kind") in KINDS)
        seen.add(identity)
        _require(
            isinstance(row.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
        )
        provenance = row.get("provenance")
        _require(isinstance(provenance, dict) and provenance.get("run_id") == run_id)
        for key in ("execution_id", "scenario_id"):
            if key in row:
                _identifier(row[key])
    return records


def _provenance(value: dict) -> dict:
    """Keep capture identity and optional excerpt coordinates, not private paths/hashes."""
    clean = _select(value, ("run_id", "capture", "captured_at", "source_revision"))
    _require(clean.get("capture") in {"original", "later_observation", "synthetic"})
    if "excerpt" in value:
        excerpt = value["excerpt"]
        _require(isinstance(excerpt, dict))
        _require(
            type(excerpt.get("start_line")) is int
            and type(excerpt.get("end_line")) is int
            and 1 <= excerpt["start_line"] <= excerpt["end_line"]
        )
        clean["excerpt"] = _select(excerpt, ("start_line", "end_line"))
    return clean


def collect_supplemental(
    index_path: Path, *, root: Path, run_id: str
) -> tuple[dict[str, bytes], dict]:
    """Verify originals, then expose only bounded, sanitized and normalized bytes."""
    path = _path(index_path, root)
    _require(path.is_file() and path.stat().st_size <= MAX_RECORD_BYTES)
    descriptor = _json(path.read_bytes())
    members, records = {}, []
    for row in _records(descriptor, run_id):
        _require(isinstance(row.get("path"), str) and ".." not in Path(row["path"]).parts)
        source = Path(row["path"])
        source = _path(source if source.is_absolute() else root / source, root)
        _require(source.is_file() and source.stat().st_size <= MAX_RECORD_BYTES)
        with source.open("rb") as stream:
            raw = stream.read(MAX_RECORD_BYTES + 1)
        _require(len(raw) <= MAX_RECORD_BYTES and _hash(raw) == row["sha256"])
        data = _normalize(raw, row["kind"], run_id)
        _require(len(data) <= MAX_RECORD_BYTES)
        suffix = "json" if row["kind"] in {"trace", "deployment"} else "txt"
        member = f"supplemental/{row['id']}.{suffix}"
        members[member] = data
        public = _select(row, ("id", "kind", "provenance", "execution_id", "scenario_id"))
        public["provenance"] = _provenance(row["provenance"])
        public.update(member=member, sha256=_hash(data))
        records.append(public)
    public_descriptor = {"schema_version": 1, "run_id": run_id, "records": records}
    public_descriptor = _json(sanitize_text(_dump(public_descriptor).decode()).encode())
    members["supplemental-index.json"] = _dump(public_descriptor)
    return members, public_descriptor


def verify_supplemental(data: dict[str, bytes], run_id: str, attempts: dict) -> set[str]:
    """Validate exact declared members and cross-check attempt/run provenance."""
    descriptor = _json(data["supplemental-index.json"])
    expected = {"supplemental-index.json"}
    executions = {r["execution_id"] for r in attempts["executions"]}
    scenarios = {r["scenario_id"] for r in attempts["scenarios"]}
    pairs = {(r["execution_id"], r["scenario_id"]) for r in attempts["attempts"]}
    for row in _records(descriptor, run_id):
        _require(
            set(row)
            <= {"id", "kind", "member", "sha256", "provenance", "execution_id", "scenario_id"}
        )
        _require(_provenance(row["provenance"]) == row["provenance"])
        suffix = "json" if row["kind"] in {"trace", "deployment"} else "txt"
        member = f"supplemental/{row['id']}.{suffix}"
        _require(row.get("member") == member and member in data and "path" not in row)
        raw = data[member]
        _require(len(raw) <= MAX_RECORD_BYTES and _hash(raw) == row["sha256"])
        _require(_normalize(raw, row["kind"], run_id) == raw, "Unnormalized supplemental evidence")
        if "execution_id" in row:
            _require(row["execution_id"] in executions)
        if "scenario_id" in row:
            _require(row["scenario_id"] in scenarios)
        if "execution_id" in row and "scenario_id" in row:
            _require((row["execution_id"], row["scenario_id"]) in pairs)
        expected.add(member)
    return expected
