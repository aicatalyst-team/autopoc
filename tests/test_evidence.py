import hashlib
import json
import zipfile
from pathlib import Path

import pytest


def setup_run(root: Path):
    root.mkdir(exist_ok=True)
    payload = {"scenario_id": "health", "status": "pass", "duration_seconds": 1}
    raw = json.dumps(payload).encode()
    (root / "attempt.json").write_bytes(raw)
    state = {
        "project": {"run_id": "run-1", "name": "demo"},
        "poc_report": {"canonical_path": "report.md"},
        "env": {"TOKEN": "never-retain"},
    }
    (root / "state.json").write_text(json.dumps(state))
    (root / "report.md").write_text("# Report\nAuthorization: Bearer secret-value\n")
    index = {
        "schema_version": 1,
        "run_id": "run-1",
        "scenarios": [{"scenario_id": "health", "name": "Health"}],
        "executions": [
            {"run_id": "run-1", "execution_id": "exec-1", "order": 1, "plan_revision": "abc"}
        ],
        "attempts": [
            {
                "run_id": "run-1",
                "scenario_id": "health",
                "execution_id": "exec-1",
                "attempt_id": "attempt-1",
                "sequence": 1,
                "mechanism": "scenario",
                "started_at": None,
                "finished_at": None,
                "outcome": "pass",
                "duration_seconds": 1,
                "payload_path": "attempt.json",
                "payload_sha256": hashlib.sha256(raw).hexdigest(),
            }
        ],
        "final_execution_id": "exec-1",
        "coverage_gaps": [],
    }
    (root / "attempt-index.json").write_text(json.dumps(index))
    return state, index


def collect(root):
    from autopoc.evidence import create_bundle

    return create_bundle(root / "state.json", root / "attempt-index.json", root / "bundles")


def test_roundtrip_deterministic_sanitized(tmp_path):
    from autopoc.evidence import verify_bundle

    setup_run(tmp_path)
    bundle = collect(tmp_path)
    assert collect(tmp_path) == bundle
    index = verify_bundle(bundle)
    assert index["final_results"]["totals"]["pass"] == 1
    assert index["eligible_for_render"]
    with zipfile.ZipFile(bundle) as archive:
        assert b"never-retain" not in archive.read("state.json")
        assert b"secret-value" not in archive.read("report.md")
    assert bundle.stem == hashlib.sha256(bundle.read_bytes()).hexdigest()


def test_missing_report_and_missing_outcome_incomplete(tmp_path):
    from autopoc.evidence import verify_bundle

    _, index = setup_run(tmp_path)
    (tmp_path / "report.md").unlink()
    index["final_execution_id"] = None
    (tmp_path / "attempt-index.json").write_text(json.dumps(index))
    result = verify_bundle(collect(tmp_path))
    assert not result["eligible_for_render"]
    assert result["final_results"]["totals"]["incomplete"] == 1
    assert "missing_report" in result["coverage_gaps"]


@pytest.mark.parametrize("change", ["run_id", "duplicate", "hash", "path", "status", "duration"])
def test_rejects_invalid_input(tmp_path, change):
    from autopoc.evidence import EvidenceError

    state, index = setup_run(tmp_path)
    if change == "run_id":
        state["project"]["run_id"] = "../bad"
    elif change == "duplicate":
        index["attempts"].append(index["attempts"][0])
    elif change == "hash":
        index["attempts"][0]["payload_sha256"] = "0" * 64
    elif change == "path":
        index["attempts"][0]["payload_path"] = "../attempt.json"
    elif change == "status":
        index["attempts"][0]["outcome"] = "success"
    else:
        index["attempts"][0]["duration_seconds"] = -1
    (tmp_path / "state.json").write_text(json.dumps(state))
    (tmp_path / "attempt-index.json").write_text(json.dumps(index))
    with pytest.raises(EvidenceError):
        collect(tmp_path)


def test_rejects_symlink_parent(tmp_path):
    from autopoc.evidence import EvidenceError, create_bundle

    setup_run(tmp_path / "real")
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(EvidenceError):
        create_bundle(
            tmp_path / "link/state.json", tmp_path / "link/attempt-index.json", tmp_path / "out"
        )


@pytest.mark.parametrize("mutation", ["tamper", "undeclared", "traversal", "duplicate", "corrupt"])
def test_verifier_rejects_bad_archive(tmp_path, mutation):
    from autopoc.evidence import EvidenceError, verify_bundle

    setup_run(tmp_path)
    original = collect(tmp_path)
    target = tmp_path / "bad.zip"
    if mutation == "corrupt":
        target.write_bytes(b"not zip")
    else:
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(target, "w") as out:
            for name in source.namelist():
                out.writestr(
                    name,
                    b"{}" if mutation == "tamper" and name == "state.json" else source.read(name),
                )
            if mutation == "undeclared":
                out.writestr("extra.json", "{}")
            elif mutation == "traversal":
                out.writestr("../escape", "{}")
            elif mutation == "duplicate":
                with pytest.warns(UserWarning):
                    out.writestr("state.json", "{}")
    with pytest.raises(EvidenceError):
        verify_bundle(target)


def test_zip_bomb_rejected_before_read(tmp_path, monkeypatch):
    from autopoc import evidence

    target = tmp_path / "bomb.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr("index.json", "a" * 4096)
    monkeypatch.setattr(evidence, "MAX_BYTES", 1024)
    with pytest.raises(evidence.EvidenceError):
        evidence.verify_bundle(target)


def test_retries_history_kept_final_scenarios_counted_once(tmp_path):
    from autopoc.evidence import verify_bundle

    _, index = setup_run(tmp_path)
    first = index["attempts"][0]
    earlier = {
        **first,
        "attempt_id": "earlier",
        "execution_id": "exec-0",
        "outcome": "fail",
        "payload_path": "earlier.json",
    }
    raw = json.dumps({"scenario_id": "health", "status": "fail", "error": "timeout"}).encode()
    (tmp_path / "earlier.json").write_bytes(raw)
    earlier["payload_sha256"] = hashlib.sha256(raw).hexdigest()
    retry = {**earlier, "attempt_id": "retry", "mechanism": "http_retry", "sequence": 2}
    index["executions"].insert(
        0, {"run_id": "run-1", "execution_id": "exec-0", "order": 0, "plan_revision": "old"}
    )
    index["attempts"] = [earlier, retry, first]
    (tmp_path / "attempt-index.json").write_text(json.dumps(index))
    bundle = collect(tmp_path)
    assert verify_bundle(bundle)["final_results"]["totals"]["pass"] == 1
    with zipfile.ZipFile(bundle) as archive:
        assert len(json.loads(archive.read("attempt-index.json"))["attempts"]) == 3


@pytest.mark.parametrize(
    "text",
    [
        "password=supersecret",
        "ghp_abcdefghijklmnopqrstuvwxyz",
        "-----BEGIN RSA PRIVATE KEY-----\nverysecret\n-----END RSA PRIVATE KEY-----",
        "API_KEY=my-credential-value",
    ],
)
def test_secret_text_redacted(tmp_path, text):
    setup_run(tmp_path)
    (tmp_path / "report.md").write_text(text)
    with zipfile.ZipFile(collect(tmp_path)) as archive:
        report = archive.read("report.md").decode()
        assert "[REDACTED]" in report
        assert "supersecret" not in report and "verysecret" not in report


def test_supplied_environment_secret_and_suspicious_text(tmp_path, monkeypatch):
    from autopoc.evidence import EvidenceError

    setup_run(tmp_path)
    monkeypatch.setenv("CUSTOM_TOKEN", "opaque-sensitive-value")
    (tmp_path / "report.md").write_text("opaque-sensitive-value")
    with zipfile.ZipFile(collect(tmp_path)) as archive:
        assert archive.read("report.md") == b"[REDACTED]"
    (tmp_path / "report.md").write_text("Basic YWxhZGRpbjpvcGVuc2VzYW1l")
    with pytest.raises(EvidenceError, match="Suspicious"):
        collect(tmp_path)


def test_oversize_input_rejected(tmp_path, monkeypatch):
    from autopoc import evidence

    setup_run(tmp_path)
    monkeypatch.setattr(evidence, "MAX_BYTES", 32)
    with pytest.raises(evidence.EvidenceError, match="size limit"):
        collect(tmp_path)


def test_missing_payload_rejected(tmp_path):
    from autopoc.evidence import EvidenceError

    setup_run(tmp_path)
    (tmp_path / "attempt.json").unlink()
    with pytest.raises(EvidenceError):
        collect(tmp_path)


def test_malformed_and_empty_results_never_all_pass(tmp_path):
    from autopoc.evidence import EvidenceError, verify_bundle

    _, index = setup_run(tmp_path)
    index.update(scenarios=[], executions=[], attempts=[], final_execution_id=None)
    (tmp_path / "attempt-index.json").write_text(json.dumps(index))
    result = verify_bundle(collect(tmp_path))
    assert result["eligible_for_render"]
    assert not result["final_results"]["complete"]
    (tmp_path / "state.json").write_text("{secret invalid")
    with pytest.raises(EvidenceError):
        collect(tmp_path)


def test_null_outcome_not_passed(tmp_path):
    from autopoc.evidence import verify_bundle

    _, index = setup_run(tmp_path)
    payload = json.dumps({"scenario_id": "health", "status": None}).encode()
    (tmp_path / "attempt.json").write_bytes(payload)
    index["attempts"][0].update(outcome=None, payload_sha256=hashlib.sha256(payload).hexdigest())
    (tmp_path / "attempt-index.json").write_text(json.dumps(index))
    result = verify_bundle(collect(tmp_path))
    assert result["final_results"]["totals"]["incomplete"] == 1
    assert result["eligible_for_render"]
    assert "incomplete_validation" in result["coverage_gaps"]


@pytest.mark.parametrize("name,passed,failed", [("omnigent", 5, 0), ("synthetic", 1, 1)])
def test_representative_fixtures(tmp_path, name, passed, failed):
    from autopoc.evidence import create_bundle, verify_bundle

    fixture = Path(__file__).parent / "fixtures/evidence" / name
    result = verify_bundle(
        create_bundle(fixture / "state.json", fixture / "attempt-index.json", tmp_path)
    )
    assert result["final_results"]["totals"]["pass"] == passed
    assert result["final_results"]["totals"]["fail"] == failed
    if name == "omnigent":
        assert result["provenance"]["kind"] == "reconstructed-state"
        assert "historical_retry_history_missing" in result["coverage_gaps"]
        source = (
            Path(__file__).parent.parent
            / "presentations/omnigent-2026-10-20/public/evidence/test-results.json"
        )
        assert (fixture / "original-test-results.json").read_bytes() == source.read_bytes()


def test_raw_output_nested_state_and_provenance_omitted(tmp_path):
    setup_run(tmp_path)
    state = json.loads((tmp_path / "state.json").read_text())
    state["provenance"] = {
        "kind": "original-run",
        "output": "unsafe-body",
        "nested": {"body": "unsafe-body"},
    }
    state["build"] = {"status": "complete", "images": [{"name": "demo", "output": "unsafe-body"}]}
    (tmp_path / "state.json").write_text(json.dumps(state))
    with zipfile.ZipFile(collect(tmp_path)) as archive:
        assert b"unsafe-body" not in archive.read("state.json")


def test_symlink_dotdot_cannot_hide_parent(tmp_path):
    from autopoc.evidence import EvidenceError, create_bundle

    setup_run(tmp_path)
    (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(EvidenceError):
        create_bundle(
            tmp_path / "link/../state.json", tmp_path / "attempt-index.json", tmp_path / "out"
        )


def test_openshift_token_sanitized():
    from autopoc.evidence import sanitize_text

    assert sanitize_text("sha256~abcdefghijklmno1234567890") == "[REDACTED]"


@pytest.mark.parametrize(
    "assignment",
    [
        'password: "quoted secret"',
        "token='single secret'",
        r'password: "secret with \"escaped\" quotes"',
    ],
)
def test_quoted_credentials_report_and_error_redacted(tmp_path, assignment):
    from autopoc.evidence import sanitize_text

    _, index = setup_run(tmp_path)
    (tmp_path / "report.md").write_text(assignment)
    payload = {
        "scenario_id": "health",
        "status": "pass",
        "duration_seconds": 1,
        "error": assignment,
    }
    raw = json.dumps(payload).encode()
    (tmp_path / "attempt.json").write_bytes(raw)
    index["attempts"][0]["payload_sha256"] = hashlib.sha256(raw).hexdigest()
    (tmp_path / "attempt-index.json").write_text(json.dumps(index))
    with zipfile.ZipFile(collect(tmp_path)) as archive:
        report = archive.read("report.md").decode()
        error = json.loads(archive.read("attempts/attempt-1.json"))["error"]
        assert "secret" not in report
        assert "secret" not in error
        assert "[REDACTED]" in report and "[REDACTED]" in error
    document = json.dumps({"message": assignment, "safe": "unchanged"})
    sanitized = json.loads(sanitize_text(document))
    assert "secret" not in sanitized["message"]
    assert sanitized["safe"] == "unchanged"


@pytest.mark.parametrize(
    "timestamp", ["password=leaked-value", "2026-99-99T99:99:99Z", 123, "2026-10-20"]
)
def test_invalid_capture_timestamp_rejected(tmp_path, timestamp):
    from autopoc.evidence import EvidenceError

    state, _ = setup_run(tmp_path)
    state["project"]["capture_timestamp"] = timestamp
    (tmp_path / "state.json").write_text(json.dumps(state))
    with pytest.raises(EvidenceError):
        collect(tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("capture_timestamp", "password=metadata-secret"),
        ("extra", {"note": 'token: "metadata-secret"'}),
    ],
)
def test_verifier_scans_all_index_metadata(tmp_path, field, value):
    from autopoc.evidence import EvidenceError, verify_bundle

    setup_run(tmp_path)
    original = collect(tmp_path)
    modified = tmp_path / "modified.zip"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(modified, "w") as target:
        for name in source.namelist():
            raw = source.read(name)
            if name == "index.json":
                index = json.loads(raw)
                index[field] = value
                raw = json.dumps(index).encode()
            target.writestr(name, raw)
    with pytest.raises(EvidenceError):
        verify_bundle(modified)


def test_basic_auth_header_is_rejected_like_a_bare_basic_credential():
    """A header-prefixed Basic credential must fail closed, not slip past the guard."""
    from autopoc.evidence import EvidenceError, sanitize_text

    with pytest.raises(EvidenceError, match="Suspicious"):
        sanitize_text(
            'curl -H "Authorization: Basic YWRtaW46UzNjci10LVAhc3N3MHJk" https://poc.example.com'
        )


def test_suffixed_secret_key_names_are_redacted_in_prose():
    from autopoc.evidence import sanitize_text

    for text in (
        "secret_key: AbCdEf1234567890xyz",
        "api_key_id: AbCdEf1234567890xyz",
        "client_secret_value: AbCdEf1234567890xyz",
    ):
        assert "AbCdEf1234567890xyz" not in sanitize_text(text), text


def test_known_constraint_basic_guard_also_rejects_ordinary_prose():
    """Pins a deliberate false positive. The residual guard cannot distinguish
    `Basic <base64>` from English, because base64 shares the alphabet. Keeping
    it strict is intentional; the wording constraint is documented for report
    authors in .opencode/skills/run-poc/references/executive-summary.md. If the
    guard is ever narrowed, update that note and the poc_report prompt too."""
    from autopoc.evidence import EvidenceError, sanitize_text

    for credential in ("Basic YWRtaW46UzNjci10LVAhc3N3MHJk", "Basic dXNlcjpwYXNzd29yZDEyMw=="):
        with pytest.raises(EvidenceError, match="Suspicious"):
            sanitize_text(credential)
    with pytest.raises(EvidenceError, match="Suspicious"):
        sanitize_text("The server supports Basic authentication on /login.")
    # Documented rephrasings that let a report describe the scheme and still seal.
    for allowed in (
        "HTTP Basic credentials were rejected by the endpoint.",
        "The endpoint uses the Basic scheme.",
    ):
        assert sanitize_text(allowed) == allowed
