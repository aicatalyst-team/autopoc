"""Capture real retries while retaining a single final scenario outcome."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from autopoc.capture import AttemptRecorder, begin_execution, capture_execution, finish_execution


def test_http_retry_records_failure_then_pass_without_response_body(tmp_path):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(1)
            self.send_response(503 if len(calls) == 1 else 200)
            self.end_headers()
            self.wfile.write(b"private response body")

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    index = tmp_path / "attempt-index.json"
    execution = begin_execution(index, "run", [{"name": "health"}])
    try:
        result = AttemptRecorder(index, execution).http(
            "health",
            f"http://127.0.0.1:{server.server_port}/",
            retries=2,
            delay=0,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    finish_execution(index, execution)
    recorded = json.loads(index.read_text())
    assert result["status"] == "pass"
    assert [a["outcome"] for a in recorded["attempts"]] == ["fail", "pass"]
    assert len({a["attempt_id"] for a in recorded["attempts"]}) == 2
    assert recorded["final_execution_id"] == execution
    assert b"private response body" not in b"".join(
        p.read_bytes() for p in tmp_path.rglob("*.json")
    )


def test_interrupted_execution_does_not_select_completed_validation(tmp_path):
    index = tmp_path / "attempt-index.json"
    execution = begin_execution(index, "run", [{"name": "first"}, {"name": "missing"}])
    AttemptRecorder(index, execution).record("first", "cli", "fail", 0.5)
    finish_execution(index, execution)
    data = json.loads(index.read_text())
    assert data["final_execution_id"] is None
    assert any(a["outcome"] is None for a in data["attempts"])
    assert "interrupted" in " ".join(data["coverage_gaps"])


def test_expected_http_error_status_is_a_successful_negative_check(tmp_path, monkeypatch):
    import io
    import urllib.error
    import urllib.request

    index = tmp_path / "attempt-index.json"
    execution = begin_execution(index, "run", [{"name": "unauthenticated"}])

    def denied(*args, **kwargs):
        raise urllib.error.HTTPError(
            "http://example.test/", 401, "Denied", None, io.BytesIO(b"authentication required")
        )

    monkeypatch.setattr(urllib.request, "urlopen", denied)
    result = AttemptRecorder(index, execution).http(
        "unauthenticated",
        "http://example.test/",
        expected_status=401,
        expected_content="required",
        retries=1,
    )
    assert result["status"] == "pass"
    assert json.loads(index.read_text())["attempts"][0]["outcome"] == "pass"


def test_later_execution_preserves_prior_failure_history(tmp_path):
    index = tmp_path / "attempt-index.json"
    first = begin_execution(index, "run", [{"name": "test"}])
    AttemptRecorder(index, first).record("test", "exec", "fail", 1)
    finish_execution(index, first)
    second = begin_execution(index, "run", [{"name": "test"}])
    AttemptRecorder(index, second).record("test", "exec", "pass", 1)
    finish_execution(index, second)
    data = json.loads(index.read_text())
    assert data["final_execution_id"] == second
    assert [a["outcome"] for a in data["attempts"]] == ["fail", "pass"]


def test_wrapper_keeps_script_exit_code_and_rejects_unrecorded_pass(tmp_path):
    state = tmp_path / "poc-state.yaml"
    state.write_text(
        json.dumps(
            {
                "project": {"run_id": "run", "current_phase": "poc_execute"},
                "poc_plan": {"scenarios": [{"name": "health"}]},
            }
        )
    )
    script = tmp_path / "test.py"
    script.write_text(
        'import json; print(json.dumps({"results": [{"scenario_name":"health", "status":"pass"}]}))'
    )
    result = capture_execution(state, script, timeout=10)
    assert result["exit_code"] == 0
    assert result["complete"] is False
    index = json.loads((tmp_path / "attempt-index.json").read_text())
    assert index["final_execution_id"] is None
    assert index["attempts"][0]["outcome"] is None


def test_wrapper_records_observed_failure_and_keeps_phase_cursor(tmp_path):
    import yaml

    state = tmp_path / "poc-state.yaml"
    state.write_text(
        json.dumps(
            {
                "project": {"run_id": "run", "current_phase": "poc_execute"},
                "poc_plan": {"scenarios": [{"name": "health"}]},
            }
        )
    )
    script = tmp_path / "test.py"
    script.write_text(
        "from autopoc.capture import AttemptRecorder\nimport json,sys\n"
        'r=AttemptRecorder.from_environment().record("health","cli","fail",1)\n'
        'print(json.dumps({"results":[r]}))\nsys.exit(1)\n'
    )
    result = capture_execution(state, script, timeout=10)
    assert result["exit_code"] == 1
    assert result["complete"] is True
    saved = yaml.safe_load(state.read_text())
    assert saved["poc_execute"]["results"][0]["status"] == "fail"
    assert saved["project"]["current_phase"] == "poc_execute"
