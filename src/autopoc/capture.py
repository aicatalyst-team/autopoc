"""Stdlib-only attempt recorder used by generated PoC scripts.

Only metadata is captured. HTTP bodies, headers, URLs and exception text are
never evidence payloads. The collector performs the publication sanitization.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(data, stream, sort_keys=True, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def begin_execution(index_path: Path, run_id: str, scenarios: list[dict]) -> str:
    """Create a script-invocation identity, retaining all earlier invocations."""
    from autopoc.artifacts import _identifier

    _identifier(run_id)
    names = [s["name"] for s in scenarios]
    if not names or len(set(names)) != len(names) or any(not n for n in names):
        raise ValueError("Expected unique planned scenario names")
    planned = [
        {"scenario_id": hashlib.sha256(n.encode()).hexdigest()[:24], "name": n} for n in names
    ]
    with _locked(index_path):
        index = (
            json.loads(index_path.read_text())
            if index_path.exists()
            else {
                "schema_version": 1,
                "run_id": run_id,
                "scenarios": planned,
                "executions": [],
                "attempts": [],
                "final_execution_id": None,
                "coverage_gaps": [],
            }
        )
        if index["run_id"] != run_id or index["scenarios"] != planned:
            raise ValueError("Attempt index identity or scenario plan differs")
        for previous in index["executions"]:
            if not previous.get("finished_at"):
                gap = f"Execution {previous['execution_id']} interrupted before finalization"
                if gap not in index["coverage_gaps"]:
                    index["coverage_gaps"].append(gap)
        execution = uuid.uuid4().hex
        index["executions"].append(
            {
                "execution_id": execution,
                "run_id": run_id,
                "order": len(index["executions"]),
                "plan_revision": hashlib.sha256(
                    json.dumps(planned, sort_keys=True).encode()
                ).hexdigest(),
                "started_at": _timestamp(),
            }
        )
        index["final_execution_id"] = None
        _write(index_path, index)
    return execution


class AttemptRecorder:
    """Persist each actual HTTP/CLI/exec attempt before retrying it."""

    def __init__(self, index_path: Path, execution_id: str):
        self.index_path = Path(index_path)
        self.execution_id = execution_id

    @classmethod
    def from_environment(cls) -> AttemptRecorder:
        return cls(Path(os.environ["AUTOPOC_ATTEMPT_INDEX"]), os.environ["AUTOPOC_EXECUTION_ID"])

    def record(
        self,
        name: str,
        mechanism: str,
        outcome: str | None,
        duration: float,
        *,
        started_at: str | None = None,
        error: str | None = None,
    ) -> dict:
        import math

        if (
            mechanism not in ("http", "cli", "exec")
            or outcome
            not in (
                "pass",
                "fail",
                "error",
                "skip",
                None,
            )
            or not math.isfinite(duration)
            or duration < 0
        ):
            raise ValueError("Invalid attempt metadata")
        with _locked(self.index_path):
            index = json.loads(self.index_path.read_text())
            scenario = next((s for s in index["scenarios"] if s["name"] == name), None)
            if scenario is None or not any(
                e["execution_id"] == self.execution_id for e in index["executions"]
            ):
                raise ValueError("Attempt must reference a planned scenario and execution")
            attempt_id = uuid.uuid4().hex
            payload = {
                "scenario_id": scenario["scenario_id"],
                "status": outcome,
                "duration_seconds": duration,
                "error": error,
            }
            payload_path = Path("attempts") / self.execution_id / f"{attempt_id}.json"
            _write(self.index_path.parent / payload_path, payload)
            prior = [
                a
                for a in index["attempts"]
                if a["execution_id"] == self.execution_id
                and a["scenario_id"] == scenario["scenario_id"]
            ]
            finished = _timestamp()
            index["attempts"].append(
                {
                    "attempt_id": attempt_id,
                    "run_id": index["run_id"],
                    "execution_id": self.execution_id,
                    "scenario_id": scenario["scenario_id"],
                    "sequence": len(prior) + 1,
                    "mechanism": mechanism,
                    "started_at": started_at or finished,
                    "finished_at": finished,
                    "outcome": outcome,
                    "duration_seconds": duration,
                    "payload_path": str(payload_path),
                    "payload_sha256": hashlib.sha256(
                        (self.index_path.parent / payload_path).read_bytes()
                    ).hexdigest(),
                }
            )
            _write(self.index_path, index)
        return {
            "scenario_name": name,
            "status": outcome,
            "duration_seconds": duration,
            "error_message": error,
        }

    def http(
        self,
        name: str,
        url: str,
        *,
        method: str = "GET",
        body=None,
        expected_status: int = 200,
        expected_content: str | None = None,
        timeout: float = 30,
        retries: int = 5,
        delay: float = 10,
    ) -> dict:
        if not 1 <= retries <= 10 or timeout <= 0 or delay < 0:
            raise ValueError("Invalid HTTP retry limits")
        for attempt in range(retries):
            start, started = time.monotonic(), _timestamp()
            try:
                data = (
                    json.dumps(body).encode()
                    if isinstance(body, dict)
                    else (body.encode() if isinstance(body, str) else body)
                )
                request = urllib.request.Request(url, data=data, method=method)
                if data is not None:
                    request.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    content = response.read(4 * 1024 * 1024 + 1)
                    passed = response.status == expected_status and len(content) <= 4 * 1024 * 1024
                    if expected_content:
                        passed = passed and expected_content.encode() in content
                outcome, error = ("pass", None) if passed else ("fail", "HTTP assertion failed")
            except urllib.error.HTTPError as exc:
                with exc:
                    content = exc.read(4 * 1024 * 1024 + 1)
                passed = exc.code == expected_status and len(content) <= 4 * 1024 * 1024
                if expected_content:
                    passed = passed and expected_content.encode() in content
                outcome, error = ("pass", None) if passed else ("fail", f"HTTP status {exc.code}")
            except (urllib.error.URLError, OSError):
                outcome, error = "error", "HTTP request failed"
            result = self.record(
                name, "http", outcome, time.monotonic() - start, started_at=started, error=error
            )
            if outcome == "pass" or attempt == retries - 1:
                return result
            time.sleep(delay)
        raise AssertionError("Unreachable retry state")


def finish_execution(index_path: Path, execution_id: str) -> None:
    """Select complete validation; explicitly mark unobserved scenarios interrupted."""
    index = json.loads(index_path.read_text())
    if not any(e["execution_id"] == execution_id for e in index["executions"]):
        raise ValueError("Unknown execution")
    recorder = AttemptRecorder(index_path, execution_id)
    interrupted = False
    for scenario in index["scenarios"]:
        attempts = [
            a
            for a in index["attempts"]
            if a["execution_id"] == execution_id and a["scenario_id"] == scenario["scenario_id"]
        ]
        if not attempts or attempts[-1]["outcome"] is None:
            interrupted = True
            if not attempts:
                recorder.record(
                    scenario["name"],
                    "exec",
                    None,
                    0,
                    error="Execution interrupted before a terminal outcome",
                )
    with _locked(index_path):
        index = json.loads(index_path.read_text())
        index["final_execution_id"] = None if interrupted else execution_id
        for execution in index["executions"]:
            if execution["execution_id"] == execution_id:
                execution["finished_at"] = _timestamp()
        if interrupted:
            index["coverage_gaps"].append(f"Execution {execution_id} interrupted")
        _write(index_path, index)


def capture_execution(
    state_path: Path, script_path: Path, *, service_url: str = "", timeout: int = 300
) -> dict:
    """Run once, retaining private stdout/stderr and original exit status."""
    import yaml

    state_path = state_path.resolve(strict=True)
    root = state_path.parent
    if not 1 <= timeout <= 1800:
        raise ValueError("Invalid capture timeout")
    script_path = script_path.absolute()
    if script_path.is_symlink() or not script_path.resolve(strict=True).is_relative_to(root):
        raise ValueError("Test script must be inside the run workspace")
    state = yaml.safe_load(state_path.read_text())
    run_id = state.setdefault("project", {}).setdefault("run_id", uuid.uuid4().hex)
    index_path = root / "attempt-index.json"
    execution = begin_execution(index_path, run_id, state["poc_plan"]["scenarios"])
    directory = root / "executions" / execution
    directory.mkdir(parents=True, mode=0o700)
    stdout_path, stderr_path = directory / "results.json", directory / "stderr.log"
    environment = {
        **os.environ,
        "AUTOPOC_ATTEMPT_INDEX": str(index_path),
        "AUTOPOC_EXECUTION_ID": execution,
    }
    status = state.setdefault("poc_execute", {})
    status.update(
        {
            "attempt_index_path": str(index_path),
            "execution_id": execution,
            "capture_status": "in_progress",
        }
    )
    _write(state_path, state)  # JSON is valid YAML; subsequent saves retain the YAML interface.
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        stdout_path.chmod(0o600)
        stderr_path.chmod(0o600)
        process = subprocess.Popen(
            [sys.executable, str(script_path), service_url],
            cwd=script_path.parent,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            exit_code = 124
    finish_execution(index_path, execution)
    index = json.loads(index_path.read_text())
    complete = index["final_execution_id"] == execution
    results = []
    for scenario in index["scenarios"]:
        observed = [
            a
            for a in index["attempts"]
            if a["execution_id"] == execution and a["scenario_id"] == scenario["scenario_id"]
        ][-1]
        results.append(
            {
                "scenario_name": scenario["name"],
                "status": observed["outcome"],
                "duration_seconds": observed["duration_seconds"],
            }
        )
    try:
        if stdout_path.stat().st_size > 1024 * 1024:
            raise ValueError("Oversized test result")
        reported = json.loads(stdout_path.read_text())["results"]
        claims = {r["scenario_name"]: r["status"] for r in reported}
        if (
            len(claims) != len(reported)
            or claims != {r["scenario_name"]: r["status"] for r in results}
            or (exit_code != 0 and all(r["status"] == "pass" for r in results))
        ):
            raise ValueError("Test results disagree with recorded attempts")
    except (ValueError, KeyError, TypeError, OSError):
        complete = False
        index["coverage_gaps"].append("Structured test output missing or inconsistent")
    if not complete:
        index["final_execution_id"] = None
        _write(index_path, index)
    status.update(
        {
            "results": results,
            "test_exit_code": exit_code,
            "capture_status": "completed" if complete else "incomplete",
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    )
    _write(state_path, state)
    return {
        "execution_id": execution,
        "exit_code": exit_code,
        "complete": complete,
        "attempt_index_path": str(index_path),
    }


def register_capture_commands(subparsers: Any) -> None:
    def command(args) -> None:
        try:
            result = capture_execution(
                args.state, args.script, service_url=args.service_url, timeout=args.timeout
            )
        except (ValueError, KeyError, OSError, subprocess.SubprocessError):
            print(
                json.dumps({"error": "Test capture failed; inspect private run state"}),
                file=sys.stderr,
            )
            raise SystemExit(1) from None
        print(json.dumps(result))
        if not result["complete"]:
            raise SystemExit(2)
        if result["exit_code"] != 0:
            raise SystemExit(1)

    parser = subparsers.add_parser("capture-execution", help="Capture original test attempts")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--service-url", default="")
    parser.add_argument("--timeout", type=int, default=300)
    parser.set_defaults(func=command)
