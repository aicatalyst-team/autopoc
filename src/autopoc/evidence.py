"""Version 1 sanitized, content-addressed PoC evidence archives.

Only selected structured fields and staged Markdown are retained. Text policy v1
redacts credential assignments, bearer/recognized tokens, private keys and secret
environment values; residual suspicious material fails closed. This policy does
not certify the absence of every possible secret. Source hashes are checked before
sanitizing; archived attempt hashes describe the sanitized payloads.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import stat
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

MAX_BYTES = 20 * 1024 * 1024
MAX_MEMBERS = 4096
STATUSES = ("pass", "fail", "error", "skip")
REDACTED = "[REDACTED]"
SECRET_KEY = re.compile(
    r"password|passwd|secret|token|api[_-]?key|authorization|credential|private[_-]?key",
    re.IGNORECASE,
)


class EvidenceError(ValueError):
    """A diagnostic that never contains input data or filesystem paths."""


def _require(condition: Any, message: str = "Invalid evidence structure") -> None:
    if not condition:
        raise EvidenceError(message)


def _identifier(value: Any) -> str:
    _require(
        isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value),
        "Invalid evidence identifier",
    )
    return value


def _path(path: Path, root: Path | None = None) -> Path:
    for component in [path, *path.parents]:
        _require(not component.is_symlink(), "Symbolic links are forbidden")
    path = Path(os.path.abspath(path))
    for parent in [path, *path.parents]:
        _require(not parent.is_symlink(), "Symbolic links are forbidden")
    if root is not None:
        _require(path.is_relative_to(root), "Evidence path escapes workspace")
    return path


def _member(name: str) -> None:
    p = PurePosixPath(name)
    _require(
        bool(name)
        and not p.is_absolute()
        and str(p) == name
        and "\\" not in name
        and all(x not in (".", "..") for x in p.parts),
        "Invalid archive member",
    )


def _read(path: Path, root: Path, budget: list[int]) -> bytes:
    path = _path(path, root)
    _require(path.is_file(), "Missing evidence input")
    size = path.stat().st_size
    _require(size <= MAX_BYTES - budget[0], "Evidence size limit exceeded")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES - budget[0] + 1)
    budget[0] += len(data)
    _require(budget[0] <= MAX_BYTES, "Evidence size limit exceeded")
    return data


def _json(data: bytes) -> Any:
    def pairs(items):
        out = {}
        for key, value in items:
            _require(key not in out, "Duplicate JSON key")
            out[key] = value
        return out

    return json.loads(
        data,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(EvidenceError("Nonfinite JSON number")),
    )


def _dump(value: Any) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode()


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_text(value: str) -> str:
    """Apply evidence text policy v1; raise a safe error on residual suspicious data."""
    # Decode structured text before scanning string values, so JSON escaping
    # cannot hide assignments and redaction cannot break its quoting.
    if value.lstrip().startswith(("{", "[")):
        try:
            document = _json(value.encode())
        except (ValueError, TypeError):
            pass
        else:
            sanitized = _sanitize(document)
            return value if sanitized == document else _dump(sanitized).decode()
    for key, secret in os.environ.items():
        if SECRET_KEY.search(key) and len(secret) >= 6:
            value = value.replace(secret, REDACTED)
    value = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        REDACTED,
        value,
        flags=re.DOTALL,
    )
    value = re.sub(r"(?i)\bBearer\s+[^\s\"\'<>]+", "Bearer " + REDACTED, value)
    # Never consume a bare auth scheme as if it were the credential: doing so
    # leaves the payload behind and strips the anchor the residual guard needs.
    value = re.sub(
        r"""(?i)((?:password|passwd|secret|token|api[_-]?key|authorization|credential)[A-Za-z0-9_-]*["']?\s*[=:]\s*)("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|(?!(?:basic|bearer|digest|negotiate)\b)[^\s,;"'<>]+)""",
        lambda match: (
            match[1] + (match[2][0] + REDACTED + match[2][-1] if match[2][0] in "\"'" else REDACTED)
        ),
        value,
    )
    value = re.sub(
        r"\b(?:sha256~[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b",
        REDACTED,
        value,
    )
    _require(
        not re.search(
            r"-----BEGIN .*KEY-----|(?i:basic)\s+[A-Za-z0-9+/=]{12,}|https?://[^\s/@]+:[^\s/@]+@|(?i:token|secret|password)\s+(?=[A-Za-z0-9_+/=-]*[0-9])[A-Za-z0-9_+/=-]{24,}",
            value,
        ),
        "Suspicious evidence text",
    )
    return value


def _capture_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    _require(
        isinstance(value, str)
        and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
        ),
        "Invalid capture timestamp",
    )
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise EvidenceError("Invalid capture timestamp") from None
    return value


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): REDACTED if SECRET_KEY.search(str(k)) else _sanitize(v)
            for k, v in value.items()
            if str(k).lower()
            not in {
                "output",
                "body",
                "response_body",
                "request_body",
                "stdout",
                "stderr",
                "env",
                "configuration",
            }
        }
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, str):
        return sanitize_text(value)
    _require(value is None or isinstance(value, (int, float, bool)))
    if isinstance(value, float):
        _require(math.isfinite(value))
    return value


def _select(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    _require(isinstance(value, dict))
    return {k: _sanitize(v) for k, v in value.items() if k in fields}


def _validate_attempts(index: Any, run_id: str) -> dict[str, Any]:
    _require(
        isinstance(index, dict)
        and index.get("schema_version") == 1
        and index.get("run_id") == run_id
    )
    scenarios: Any = index.get("scenarios")
    executions: Any = index.get("executions")
    attempts: Any = index.get("attempts")
    _require(
        isinstance(scenarios, list) and isinstance(executions, list) and isinstance(attempts, list)
    )
    scenario_ids, execution_ids, attempt_ids, orders, sequences = set(), set(), set(), set(), set()
    for row in scenarios:
        sid = _identifier(row["scenario_id"])
        _require(sid not in scenario_ids)
        scenario_ids.add(sid)
    for row in executions:
        eid = _identifier(row["execution_id"])
        order = row["order"]
        _require(
            row["run_id"] == run_id
            and eid not in execution_ids
            and type(order) is int
            and order >= 0
            and order not in orders
            and isinstance(row.get("plan_revision"), (str, type(None)))
        )
        execution_ids.add(eid)
        orders.add(order)
    for row in attempts:
        aid = _identifier(row["attempt_id"])
        sequence = row["sequence"]
        key = (row["execution_id"], row["scenario_id"], sequence)
        _require(
            row["run_id"] == run_id
            and aid not in attempt_ids
            and row["scenario_id"] in scenario_ids
            and row["execution_id"] in execution_ids
            and type(sequence) is int
            and sequence >= 1
            and key not in sequences
        )
        _require(
            row.get("outcome") in (*STATUSES, None)
            and isinstance(row.get("mechanism"), str)
            and bool(row["mechanism"])
        )
        duration = row.get("duration_seconds")
        _require(
            duration is None
            or (type(duration) in (int, float) and math.isfinite(duration) and duration >= 0)
        )
        for field in ("started_at", "finished_at"):
            _require(row.get(field) is None or isinstance(row[field], str))
        _require(
            isinstance(row["payload_path"], str)
            and re.fullmatch(r"[0-9a-f]{64}", row["payload_sha256"])
        )
        attempt_ids.add(aid)
        sequences.add(key)
    final = index.get("final_execution_id")
    _require(final is None or final in execution_ids)
    gaps = index.get("coverage_gaps", [])
    _require(isinstance(gaps, list) and all(isinstance(x, str) for x in gaps))
    return index


def _results(index: dict[str, Any]) -> dict[str, Any]:
    results = []
    totals = dict.fromkeys((*STATUSES, "incomplete"), 0)
    for scenario in index["scenarios"]:
        rows = [
            a
            for a in index["attempts"]
            if a["execution_id"] == index["final_execution_id"]
            and a["scenario_id"] == scenario["scenario_id"]
        ]
        last = max(rows, key=lambda a: a["sequence"]) if rows else None
        outcome = last["outcome"] if last and last.get("outcome") is not None else "incomplete"
        totals[outcome] += 1
        results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "scenario_name": scenario.get("name", scenario["scenario_id"]),
                "status": outcome,
                "attempt_id": last["attempt_id"] if last else None,
            }
        )
    return {
        "results": results,
        "totals": totals,
        "complete": bool(results)
        and totals["incomplete"] == 0
        and index["final_execution_id"] is not None,
    }


def _create(state_path: Path, attempt_index_path: Path, output_dir: Path) -> Path:
    state_path = _path(state_path)
    root = state_path.parent
    budget = [0]
    state = yaml.safe_load(_read(state_path, root, budget))
    _require(isinstance(state, dict) and isinstance(state.get("project"), dict))
    run_id = _identifier(state["project"].get("run_id"))
    capture_timestamp = _capture_timestamp(state["project"].get("capture_timestamp"))
    attempts = _validate_attempts(_json(_read(attempt_index_path, root, budget)), run_id)
    clean = _select(
        attempts,
        (
            "schema_version",
            "run_id",
            "scenarios",
            "executions",
            "attempts",
            "final_execution_id",
            "coverage_gaps",
            "provenance",
        ),
    )
    clean["scenarios"] = [
        _select(r, ("scenario_id", "name", "description")) for r in attempts["scenarios"]
    ]
    clean["executions"] = [
        _select(r, ("run_id", "execution_id", "order", "plan_revision", "provenance"))
        for r in attempts["executions"]
    ]
    clean["attempts"] = []
    members = {}
    for row in attempts["attempts"]:
        source = Path(row["payload_path"])
        _require(".." not in source.parts and "\\" not in str(source), "Invalid attempt path")
        raw = _read(source if source.is_absolute() else root / source, root, budget)
        _require(_hash(raw) == row["payload_sha256"], "Attempt payload hash mismatch")
        payload = _select(
            _json(raw),
            (
                "scenario_id",
                "status",
                "error",
                "error_message",
                "duration_seconds",
                "description",
                "provenance",
            ),
        )
        _require(
            payload.get("scenario_id") == row["scenario_id"]
            and payload.get("status") == row["outcome"],
            "Attempt outcome mismatch",
        )
        member = f"attempts/{row['attempt_id']}.json"
        data = _dump(payload)
        members[member] = data
        item = _select(
            row,
            (
                "run_id",
                "scenario_id",
                "execution_id",
                "attempt_id",
                "sequence",
                "mechanism",
                "started_at",
                "finished_at",
                "outcome",
                "duration_seconds",
                "provenance",
            ),
        )
        item.update(payload_path=member, payload_sha256=_hash(data))
        clean["attempts"].append(item)
    snapshot = {
        "project": _select(
            state["project"],
            (
                "run_id",
                "name",
                "project_name",
                "source_repo_url",
                "source_revision",
                "artifact_revision",
                "current_phase",
                "capture_timestamp",
            ),
        ),
        "phases": {},
        "omitted_fields": sorted(k for k in state if k not in ("project", "provenance")),
        "provenance": _sanitize(state.get("provenance", {})),
    }
    for phase in (
        "intake",
        "evaluate",
        "fork",
        "poc_plan",
        "containerize",
        "build",
        "deploy",
        "apply",
        "poc_execute",
        "poc_report",
        "blog_post",
    ):
        if isinstance(state.get(phase), dict):
            snapshot["phases"][phase] = _select(
                state[phase],
                (
                    "status",
                    "namespace",
                    "deployed_resources",
                    "repo_summary",
                    "scenarios",
                    "score",
                    "recommendation",
                    "built_images",
                    "images",
                    "resources",
                    "retries",
                    "build_retries",
                    "deploy_retries",
                ),
            )
    gaps = list(clean.get("coverage_gaps", []))
    for member, section, fields in [
        ("report.md", "poc_report", ("canonical_report_path", "canonical_path", "report_path")),
        ("plan.md", "poc_plan", ("poc_plan_path",)),
        ("evaluation.md", "evaluate", ("evaluation_path",)),
    ]:
        value = next(
            (state.get(section, {}).get(k) for k in fields if state.get(section, {}).get(k)), None
        )
        if value:
            source = Path(value)
            source = source if source.is_absolute() else root / source
            _path(source, root)
            if source.exists():
                members[member] = sanitize_text(
                    _read(source, root, budget).decode("utf-8")
                ).encode()
            elif member == "report.md":
                gaps.append("missing_report")
        elif member == "report.md":
            gaps.append("missing_report")
    results = _results(clean)
    if not results["complete"]:
        gaps.append("incomplete_validation")
    if clean["final_execution_id"] is None:
        gaps.append("no_final_execution")
    members.update(
        {
            "state.json": _dump(snapshot),
            "attempt-index.json": _dump(clean),
            "test-results.json": _dump(results),
        }
    )
    manifest = {
        name: {"sha256": _hash(data), "size": len(data)} for name, data in sorted(members.items())
    }
    index = {
        "schema_version": 1,
        "sanitizer_policy": 1,
        "run_id": run_id,
        "project": snapshot["project"],
        "provenance": snapshot["provenance"],
        "capture_timestamp": capture_timestamp,
        "files": manifest,
        "coverage_gaps": sorted(set(gaps)),
        "eligible_for_render": bool(members.get("report.md", b"").strip()),
        "final_results": results,
    }
    members["index.json"] = _dump(_sanitize(index))
    _require(
        sum(map(len, members.values())) <= MAX_BYTES and len(members) <= MAX_MEMBERS,
        "Evidence size limit exceeded",
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(members.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(entry, data)
    data = buffer.getvalue()
    destination = _path(output_dir) / run_id
    _path(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = destination / f"{_hash(data)}.zip"
    with tempfile.NamedTemporaryFile(
        dir=destination, prefix=".evidence-", delete=False
    ) as temporary:
        temporary.write(data)
        temp_path = Path(temporary.name)
    try:
        verify_bundle(temp_path)
        try:
            os.link(temp_path, target)
        except FileExistsError:
            _require(
                _path(target).is_file() and target.read_bytes() == data,
                "Evidence archive conflicts",
            )
    finally:
        temp_path.unlink(missing_ok=True)
    return target


def create_bundle(state_path: Path, attempt_index_path: Path, output_dir: Path) -> Path:
    """Collect allowlisted inputs inside the state directory, without replaying tests."""
    try:
        return _create(state_path, attempt_index_path, output_dir)
    except EvidenceError:
        raise
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        yaml.YAMLError,
    ):
        raise EvidenceError("Cannot collect evidence inputs") from None


def verify_bundle(bundle_path: Path) -> dict[str, Any]:
    """Validate bounded archive contents in memory; never extract input paths."""
    try:
        path = _path(bundle_path)
        _require(path.stat().st_size <= MAX_BYTES, "Evidence size limit exceeded")
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            _require(
                len(infos) <= MAX_MEMBERS and sum(i.file_size for i in infos) <= MAX_BYTES,
                "Evidence size limit exceeded",
            )
            names = [i.filename for i in infos]
            _require(len(set(names)) == len(names), "Duplicate archive members")
            for info in infos:
                _member(info.filename)
                _require(
                    not info.is_dir()
                    and not stat.S_ISLNK(info.external_attr >> 16)
                    and not info.flag_bits & 1,
                    "Invalid archive member",
                )
            _require("index.json" in names)
            data = {}
            for info in infos:
                with archive.open(info) as stream:
                    data[info.filename] = stream.read(info.file_size + 1)
                _require(len(data[info.filename]) == info.file_size)
        index = _json(data["index.json"])
        _require(
            sanitize_text(data["index.json"].decode("utf-8")) == data["index.json"].decode("utf-8"),
            "Unsanitized evidence metadata",
        )
        _capture_timestamp(index.get("capture_timestamp"))
        _require(index["schema_version"] == 1 and index["sanitizer_policy"] == 1)
        run_id = _identifier(index["run_id"])
        files = index["files"]
        _require(isinstance(files, dict) and set(files) == set(names) - {"index.json"})
        _require({"state.json", "attempt-index.json", "test-results.json"} <= set(files))
        for name, metadata in files.items():
            _require(
                name
                in (
                    "state.json",
                    "attempt-index.json",
                    "test-results.json",
                    "report.md",
                    "plan.md",
                    "evaluation.md",
                )
                or re.fullmatch(r"attempts/[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.json", name)
            )
            _require(
                metadata == {"sha256": _hash(data[name]), "size": len(data[name])},
                "Evidence member hash or size mismatch",
            )
            _require(
                sanitize_text(data[name].decode("utf-8")) == data[name].decode("utf-8"),
                "Unsanitized evidence member",
            )
        attempts = _validate_attempts(_json(data["attempt-index.json"]), run_id)
        expected = {"state.json", "attempt-index.json", "test-results.json"}
        for row in attempts["attempts"]:
            name = row["payload_path"]
            _require(
                name == f"attempts/{row['attempt_id']}.json"
                and name in files
                and _hash(data[name]) == row["payload_sha256"]
            )
            payload = _json(data[name])
            _require(
                payload.get("scenario_id") == row["scenario_id"]
                and payload.get("status") == row["outcome"]
            )
            expected.add(name)
        _require(set(files) - {"report.md", "plan.md", "evaluation.md"} == expected)
        results = _results(attempts)
        _require(
            results == _json(data["test-results.json"]) == index["final_results"],
            "Inconsistent final results",
        )
        _require(_json(data["state.json"])["project"]["run_id"] == run_id)
        _require(index["eligible_for_render"] == (bool(data.get("report.md", b"").strip())))
        _require("report.md" in files or "missing_report" in index["coverage_gaps"])
        return index
    except EvidenceError:
        raise
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        zipfile.BadZipFile,
        RuntimeError,
        NotImplementedError,
    ):
        raise EvidenceError("Cannot verify evidence archive") from None


def _command(args: argparse.Namespace) -> None:
    try:
        if args.evidence_action == "create":
            path = create_bundle(args.state, args.attempt_index, args.output_dir)
            result = {"bundle_path": str(path), "archive_sha256": path.stem, **verify_bundle(path)}
        else:
            result = verify_bundle(args.bundle)
        print(json.dumps(result, sort_keys=True))
    except EvidenceError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        raise SystemExit(1) from None


def register_evidence_commands(subparsers: Any) -> None:
    """Register create/verify without importing the main CLI dispatcher."""
    create = subparsers.add_parser("evidence-create", help="Collect sanitized evidence")
    for name in ("state", "attempt-index", "output-dir"):
        create.add_argument("--" + name, type=Path, required=True)
    create.set_defaults(func=_command, evidence_action="create")
    verify = subparsers.add_parser("evidence-verify", help="Verify evidence archive")
    verify.add_argument("bundle", type=Path)
    verify.set_defaults(func=_command, evidence_action="verify")
