"""Tests for the Vale prose linting utility.

Tests cover:
- run_vale() subprocess handling and output parsing
- Graceful degradation when vale is not installed
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopoc.tools.vale_lint import (
    _format_findings_for_llm,
    _vale_available,
    run_vale,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_VALE_OUTPUT = {
    "/tmp/test.md": [
        {
            "Line": 5,
            "Severity": "warning",
            "Message": "Use 'run' instead of 'execute'.",
            "Check": "RedHat.TermsSuggestions",
            "Link": "https://example.com/rule",
        },
        {
            "Line": 10,
            "Severity": "suggestion",
            "Message": "Consider using active voice.",
            "Check": "RedHat.PassiveVoice",
            "Link": "",
        },
    ]
}


@pytest.fixture
def sample_md_file(tmp_path: Path) -> Path:
    """Create a sample markdown file for testing."""
    md_file = tmp_path / "test.md"
    md_file.write_text(
        "# Test Report\n\n"
        "The application was executed successfully.\n\n"
        "Tests were run and results were collected.\n",
        encoding="utf-8",
    )
    return md_file


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock config with vale settings."""
    config = MagicMock()
    config.max_vale_revisions = 3
    return config


# ---------------------------------------------------------------------------
# Tests for _vale_available
# ---------------------------------------------------------------------------


class TestValeAvailable:
    @patch("autopoc.tools.vale_lint.shutil.which", return_value="/usr/bin/vale")
    def test_vale_found(self, mock_which: MagicMock) -> None:
        assert _vale_available() is True
        mock_which.assert_called_once_with("vale")

    @patch("autopoc.tools.vale_lint.shutil.which", return_value=None)
    def test_vale_not_found(self, mock_which: MagicMock) -> None:
        assert _vale_available() is False


# ---------------------------------------------------------------------------
# Tests for run_vale
# ---------------------------------------------------------------------------


class TestRunVale:
    @patch("autopoc.tools.vale_lint._vale_available", return_value=False)
    def test_skips_when_vale_not_installed(
        self, _mock_available: MagicMock, sample_md_file: Path
    ) -> None:
        result = run_vale(sample_md_file)
        assert result == []

    def test_skips_when_file_missing(self, tmp_path: Path) -> None:
        result = run_vale(tmp_path / "nonexistent.md")
        assert result == []

    @patch("autopoc.tools.vale_lint._vale_available", return_value=True)
    @patch("autopoc.tools.vale_lint.subprocess.run")
    def test_parses_vale_json_output(
        self,
        mock_run: MagicMock,
        _mock_available: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,  # 1 = findings exist
            stdout=json.dumps(SAMPLE_VALE_OUTPUT),
            stderr="",
        )

        findings = run_vale(sample_md_file)

        assert len(findings) == 2
        assert findings[0]["line"] == 5
        assert findings[0]["severity"] == "warning"
        assert findings[0]["message"] == "Use 'run' instead of 'execute'."
        assert findings[0]["check"] == "RedHat.TermsSuggestions"
        assert findings[1]["line"] == 10
        assert findings[1]["severity"] == "suggestion"

    @patch("autopoc.tools.vale_lint._vale_available", return_value=True)
    @patch("autopoc.tools.vale_lint.subprocess.run")
    def test_returns_empty_on_no_findings(
        self,
        mock_run: MagicMock,
        _mock_available: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="{}",
            stderr="",
        )

        findings = run_vale(sample_md_file)
        assert findings == []

    @patch("autopoc.tools.vale_lint._vale_available", return_value=True)
    @patch("autopoc.tools.vale_lint.subprocess.run")
    def test_handles_vale_error_exit(
        self,
        mock_run: MagicMock,
        _mock_available: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=2,  # Error exit
            stdout="",
            stderr="Error: missing styles",
        )

        findings = run_vale(sample_md_file)
        assert findings == []

    @patch("autopoc.tools.vale_lint._vale_available", return_value=True)
    @patch("autopoc.tools.vale_lint.subprocess.run")
    def test_handles_invalid_json_output(
        self,
        mock_run: MagicMock,
        _mock_available: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="this is not JSON",
            stderr="",
        )

        findings = run_vale(sample_md_file)
        assert findings == []

    @patch("autopoc.tools.vale_lint._vale_available", return_value=True)
    @patch("autopoc.tools.vale_lint.subprocess.run", side_effect=FileNotFoundError)
    def test_handles_file_not_found_error(
        self,
        _mock_run: MagicMock,
        _mock_available: MagicMock,
        sample_md_file: Path,
    ) -> None:
        findings = run_vale(sample_md_file)
        assert findings == []

    @patch("autopoc.tools.vale_lint._vale_available", return_value=True)
    @patch(
        "autopoc.tools.vale_lint.subprocess.run",
        side_effect=__import__("subprocess").TimeoutExpired(cmd="vale", timeout=60),
    )
    def test_handles_timeout(
        self,
        _mock_run: MagicMock,
        _mock_available: MagicMock,
        sample_md_file: Path,
    ) -> None:
        findings = run_vale(sample_md_file)
        assert findings == []


# ---------------------------------------------------------------------------
# Tests for _format_findings_for_llm
# ---------------------------------------------------------------------------


class TestFormatFindings:
    def test_formats_findings(self) -> None:
        findings = [
            {
                "line": 5,
                "severity": "warning",
                "message": "Use 'run' instead.",
                "check": "RedHat.Terms",
                "link": "",
            },
        ]
        result = _format_findings_for_llm(findings)
        assert "Line 5" in result
        assert "WARNING" in result
        assert "RedHat.Terms" in result
        assert "Use 'run' instead." in result

    def test_empty_findings(self) -> None:
        result = _format_findings_for_llm([])
        assert result == ""
