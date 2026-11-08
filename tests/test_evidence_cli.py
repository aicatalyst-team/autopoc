import argparse
import json

import pytest

from autopoc.evidence import register_evidence_commands
from tests.test_evidence import setup_run


def invoke(argv):
    parser = argparse.ArgumentParser()
    register_evidence_commands(parser.add_subparsers(required=True))
    args = parser.parse_args(argv)
    args.func(args)


def test_cli_roundtrip(tmp_path, capsys):
    setup_run(tmp_path)
    invoke(
        [
            "evidence-create",
            "--state",
            str(tmp_path / "state.json"),
            "--attempt-index",
            str(tmp_path / "attempt-index.json"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    invoke(["evidence-verify", result["bundle_path"]])
    verified = json.loads(capsys.readouterr().out)
    assert verified["run_id"] == result["run_id"] == "run-1"
    assert result["archive_sha256"]


def test_cli_sanitized_failure(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        invoke(["evidence-verify", str(tmp_path / "password=supersecret")])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert not output.out
    assert "supersecret" not in output.err
    assert json.loads(output.err)["error"]


def test_cli_missing_required_input(capsys):
    with pytest.raises(SystemExit) as error:
        invoke(["evidence-create"])
    assert error.value.code == 2
