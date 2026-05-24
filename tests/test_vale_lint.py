"""Tests for the Vale prose linting utility.

Tests cover:
- run_vale() subprocess handling and output parsing
- vale_lint_and_revise() loop logic with mocked LLM and subprocess
- Graceful degradation when vale is not installed
- Content validation (truncation guard)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from autopoc.tools.vale_lint import (
    _format_findings_for_llm,
    _vale_available,
    run_vale,
    vale_lint_and_revise,
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


# ---------------------------------------------------------------------------
# Tests for vale_lint_and_revise
# ---------------------------------------------------------------------------


class TestValeLintAndRevise:
    @pytest.mark.asyncio
    @patch("autopoc.tools.vale_lint.load_config")
    @patch("autopoc.tools.vale_lint.run_vale", return_value=[])
    async def test_returns_early_when_no_findings(
        self,
        _mock_run_vale: MagicMock,
        mock_config: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_config.return_value.max_vale_revisions = 3
        mock_llm = AsyncMock()

        content, findings = await vale_lint_and_revise(sample_md_file, mock_llm)

        assert content == sample_md_file.read_text(encoding="utf-8")
        assert findings == []
        mock_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    @patch("autopoc.tools.vale_lint.load_config")
    @patch("autopoc.tools.vale_lint.run_vale")
    async def test_revision_loop_fixes_issues(
        self,
        mock_run_vale: MagicMock,
        mock_config: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_config.return_value.max_vale_revisions = 3

        # First call: findings exist. Second call (after revision): no findings.
        mock_run_vale.side_effect = [
            [{"line": 5, "severity": "warning", "message": "Issue", "check": "X", "link": ""}],
            [],  # No more issues after revision
        ]

        revised_content = "# Test Report\n\nThe application ran successfully.\n\nTests ran and results were collected.\n"
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content=revised_content)

        content, findings = await vale_lint_and_revise(sample_md_file, mock_llm)

        assert content == revised_content.strip()
        assert len(findings) == 1  # Initial findings
        assert findings[0]["message"] == "Issue"
        mock_llm.ainvoke.assert_called_once()
        # File should be updated on disk
        assert sample_md_file.read_text(encoding="utf-8") == revised_content.strip()

    @pytest.mark.asyncio
    @patch("autopoc.tools.vale_lint.load_config")
    @patch("autopoc.tools.vale_lint.run_vale")
    async def test_respects_max_revisions(
        self,
        mock_run_vale: MagicMock,
        mock_config: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_config.return_value.max_vale_revisions = 2
        original_content = sample_md_file.read_text(encoding="utf-8")

        # Findings persist through all revisions
        finding = [{"line": 5, "severity": "warning", "message": "Issue", "check": "X", "link": ""}]
        mock_run_vale.return_value = finding

        revised = original_content + "\n<!-- revised -->"
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content=revised)

        content, findings = await vale_lint_and_revise(sample_md_file, mock_llm)

        # LLM should be called exactly max_revisions times
        assert mock_llm.ainvoke.call_count == 2

    @pytest.mark.asyncio
    @patch("autopoc.tools.vale_lint.load_config")
    @patch("autopoc.tools.vale_lint.run_vale")
    async def test_rejects_truncated_revision(
        self,
        mock_run_vale: MagicMock,
        mock_config: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_config.return_value.max_vale_revisions = 3
        original_content = sample_md_file.read_text(encoding="utf-8")

        mock_run_vale.return_value = [
            {"line": 5, "severity": "warning", "message": "Issue", "check": "X", "link": ""}
        ]

        # LLM returns very short content (less than 50% of original)
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="# Test")

        content, findings = await vale_lint_and_revise(sample_md_file, mock_llm)

        # Should keep original content since revision was too short
        assert content == original_content
        mock_llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    @patch("autopoc.tools.vale_lint.load_config")
    @patch("autopoc.tools.vale_lint.run_vale")
    async def test_handles_llm_failure(
        self,
        mock_run_vale: MagicMock,
        mock_config: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_config.return_value.max_vale_revisions = 3
        original_content = sample_md_file.read_text(encoding="utf-8")

        mock_run_vale.return_value = [
            {"line": 5, "severity": "warning", "message": "Issue", "check": "X", "link": ""}
        ]

        # LLM raises an exception
        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = RuntimeError("API error")

        content, findings = await vale_lint_and_revise(sample_md_file, mock_llm)

        # Should return original content
        assert content == original_content
        assert len(findings) == 1

    @pytest.mark.asyncio
    async def test_handles_missing_file(self, tmp_path: Path) -> None:
        mock_llm = AsyncMock()
        content, findings = await vale_lint_and_revise(
            tmp_path / "missing.md", mock_llm, max_revisions=3
        )
        assert content == ""
        assert findings == []

    @pytest.mark.asyncio
    @patch("autopoc.tools.vale_lint.load_config")
    @patch("autopoc.tools.vale_lint.run_vale")
    async def test_strips_wrapping_code_fences(
        self,
        mock_run_vale: MagicMock,
        mock_config: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_config.return_value.max_vale_revisions = 3

        mock_run_vale.side_effect = [
            [{"line": 5, "severity": "warning", "message": "Issue", "check": "X", "link": ""}],
            [],
        ]

        # LLM wraps response in code fences
        inner = "# Test Report\n\nThe app ran successfully.\n\nResults were collected.\n"
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content=f"```markdown\n{inner}\n```")

        content, findings = await vale_lint_and_revise(sample_md_file, mock_llm)

        assert content == inner.strip()

    @pytest.mark.asyncio
    @patch("autopoc.tools.vale_lint.load_config")
    @patch("autopoc.tools.vale_lint.run_vale")
    async def test_uses_explicit_max_revisions(
        self,
        mock_run_vale: MagicMock,
        mock_config: MagicMock,
        sample_md_file: Path,
    ) -> None:
        """When max_revisions is passed explicitly, config is not loaded."""
        original_content = sample_md_file.read_text(encoding="utf-8")

        finding = [{"line": 5, "severity": "warning", "message": "Issue", "check": "X", "link": ""}]
        mock_run_vale.return_value = finding

        revised = original_content + "\n<!-- revised -->"
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content=revised)

        content, findings = await vale_lint_and_revise(sample_md_file, mock_llm, max_revisions=1)

        # Should call LLM exactly 1 time
        assert mock_llm.ainvoke.call_count == 1
        # Config should NOT have been loaded
        mock_config.assert_not_called()

    @pytest.mark.asyncio
    @patch("autopoc.tools.vale_lint.load_config")
    @patch("autopoc.tools.vale_lint.run_vale")
    async def test_handles_multipart_llm_content(
        self,
        mock_run_vale: MagicMock,
        mock_config: MagicMock,
        sample_md_file: Path,
    ) -> None:
        mock_config.return_value.max_vale_revisions = 3

        mock_run_vale.side_effect = [
            [{"line": 5, "severity": "warning", "message": "Issue", "check": "X", "link": ""}],
            [],
        ]

        # LLM returns multi-part content (Claude-style)
        revised = "# Test Report\n\nThe app ran successfully.\n\nResults were collected.\n"
        mock_response = MagicMock()
        mock_response.content = [{"text": revised}]

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_response

        content, findings = await vale_lint_and_revise(sample_md_file, mock_llm)

        assert content == revised.strip()
