"""Tests for the unified CLI tools wrapper (autopoc.cli_tools).

Tests cover:
- Argument parser construction and subcommand registration
- repo-digest subcommand against test fixtures
- strategy subcommand (load, load-baseline, dimensions)
- vale subcommand (delegates to run_vale)
- Error handling (missing args, invalid subcommands)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from autopoc.cli_tools import build_parser, cmd_repo_digest, cmd_strategy, cmd_vale

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestBuildParser:
    """Test that the argument parser is constructed correctly."""

    def test_parser_has_all_subcommands(self) -> None:
        parser = build_parser()
        # Extract subcommand names
        subparsers = parser._subparsers._group_actions[0]
        command_names = list(subparsers.choices.keys())
        expected = [
            "repo-digest",
            "gitlab",
            "github",
            "quay",
            "strategy",
            "llm-proxy",
            "artifacts",
            "vale",
            "sheet-reader",
            "sheet-writer",
        ]
        for cmd in expected:
            assert cmd in command_names, f"Missing subcommand: {cmd}"

    def test_repo_digest_requires_path(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["repo-digest"])

    def test_repo_digest_accepts_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["repo-digest", "/tmp/test-repo"])
        assert args.repo_path == "/tmp/test-repo"
        assert args.max_chars == 20_000

    def test_strategy_requires_action(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["strategy"])

    def test_gitlab_requires_action_and_name(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["gitlab"])

    def test_vale_requires_file_path(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["vale"])


class TestRepoDigest:
    """Test the repo-digest subcommand."""

    def test_flask_app_fixture(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test repo digest generation against the flask fixture."""
        parser = build_parser()
        args = parser.parse_args(["repo-digest", str(FIXTURES_DIR / "python-flask-app")])
        cmd_repo_digest(args)
        output = capsys.readouterr().out
        assert "python-flask-app" in output
        assert "flask" in output.lower()
        assert "app.py" in output

    def test_monorepo_fixture(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test repo digest generation against the monorepo fixture."""
        parser = build_parser()
        args = parser.parse_args(["repo-digest", str(FIXTURES_DIR / "node-monorepo")])
        cmd_repo_digest(args)
        output = capsys.readouterr().out
        assert "node-monorepo" in output

    def test_custom_max_chars(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test that max-chars parameter is respected."""
        parser = build_parser()
        args = parser.parse_args(
            ["repo-digest", str(FIXTURES_DIR / "python-flask-app"), "--max-chars", "500"]
        )
        cmd_repo_digest(args)
        output = capsys.readouterr().out
        # Output should be truncated
        assert len(output) <= 600  # Some slack for the truncation message


class TestStrategy:
    """Test the strategy subcommand."""

    def test_load_strategy(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        args = parser.parse_args(["strategy", "load"])
        cmd_strategy(args)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "impact_dimensions" in data or "name" in data

    def test_load_baseline(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        args = parser.parse_args(["strategy", "load-baseline"])
        cmd_strategy(args)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_dimensions(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        args = parser.parse_args(["strategy", "dimensions"])
        cmd_strategy(args)
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "dimensions" in data
        assert "max_score" in data
        assert data["max_score"] > 0


class TestVale:
    """Test the vale subcommand."""

    def test_vale_on_missing_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        args = parser.parse_args(["vale", "/nonexistent/file.md"])
        cmd_vale(args)
        output = capsys.readouterr().out
        findings = json.loads(output)
        assert findings == []

    def test_vale_on_real_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        md = tmp_path / "test.md"
        md.write_text("# Hello\n\nSome text here.\n")
        parser = build_parser()
        args = parser.parse_args(["vale", str(md)])
        cmd_vale(args)
        output = capsys.readouterr().out
        findings = json.loads(output)
        assert isinstance(findings, list)


class TestModuleInvocation:
    """Test that the module can be invoked via python -m."""

    def test_help_output(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "autopoc.cli_tools", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "repo-digest" in result.stdout
        assert "gitlab" in result.stdout
        assert "strategy" in result.stdout

    def test_repo_digest_via_module(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "autopoc.cli_tools",
                "repo-digest",
                str(FIXTURES_DIR / "python-flask-app"),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "flask" in result.stdout.lower()

    def test_strategy_dimensions_via_module(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "autopoc.cli_tools", "strategy", "dimensions"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "dimensions" in data
