"""CLI integration tests for the `autopoc run-sheet` command."""

import os
import re
from unittest.mock import patch

from typer.testing import CliRunner

from autopoc.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for assertion matching."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)

# Minimal env vars to satisfy config validation (for tests that get past
# the sheet-specific arg checks).
VALID_ENV = {
    "ANTHROPIC_API_KEY": "sk-test",
    "GITLAB_URL": "https://gitlab.example.com",
    "GITLAB_TOKEN": "glpat-test",
    "GITLAB_GROUP": "poc",
    "QUAY_ORG": "org",
    "QUAY_TOKEN": "token",
    "OPENSHIFT_API_URL": "https://api.example.com:6443",
    "OPENSHIFT_TOKEN": "sha256~token",
}


class TestRunSheetArgs:
    """Tests for argument validation."""

    def test_missing_sheet_id(self) -> None:
        """run-sheet without --sheet-id or AUTOPOC_SHEET_ID exits with error."""
        result = runner.invoke(app, ["run-sheet"])
        assert result.exit_code == 1
        assert "sheet-id" in result.stdout.lower() or "AUTOPOC_SHEET_ID" in result.stdout

    def test_missing_credentials(self) -> None:
        """run-sheet without --credentials or AUTOPOC_SHEET_CREDENTIALS exits with error."""
        result = runner.invoke(app, ["run-sheet", "--sheet-id", "fake123"])
        assert result.exit_code == 1
        assert "credentials" in result.stdout.lower() or "AUTOPOC_SHEET_CREDENTIALS" in result.stdout

    def test_credentials_file_not_found(self) -> None:
        """run-sheet with nonexistent credentials file exits with error."""
        result = runner.invoke(
            app,
            ["run-sheet", "--sheet-id", "fake123", "--credentials", "/nonexistent/sa.json"],
        )
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_sheet_id_from_env(self) -> None:
        """AUTOPOC_SHEET_ID env var is picked up when --sheet-id is omitted."""
        env = {"AUTOPOC_SHEET_ID": "env-sheet-id"}
        with patch.dict(os.environ, env):
            # Should get past the sheet_id check and fail on credentials
            result = runner.invoke(app, ["run-sheet"])
            assert result.exit_code == 1
            assert "credentials" in result.stdout.lower() or "AUTOPOC_SHEET_CREDENTIALS" in result.stdout

    def test_credentials_from_env(self, tmp_path) -> None:
        """AUTOPOC_SHEET_CREDENTIALS env var is picked up when --credentials is omitted."""
        sa_file = tmp_path / "sa.json"
        sa_file.write_text('{"type": "service_account"}')
        env = {
            **VALID_ENV,
            "AUTOPOC_SHEET_ID": "env-sheet-id",
            "AUTOPOC_SHEET_CREDENTIALS": str(sa_file),
        }
        # Should get past arg validation and fail trying to read the sheet
        with patch.dict(os.environ, env, clear=True):
            with patch("autopoc.cli.read_sheet", side_effect=ValueError("mocked")):
                result = runner.invoke(app, ["run-sheet", "--skip-validation"])
                assert result.exit_code == 1
                assert "mocked" in result.stdout

    def test_help_shows_options(self) -> None:
        """run-sheet --help shows all expected options."""
        result = runner.invoke(app, ["run-sheet", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.stdout)
        assert "sheet-id" in output
        assert "credentials" in output
        assert "AUTOPOC_SHEET_ID" in output
        assert "AUTOPOC_SHEET_CREDENTIALS" in output
        assert "stop-after" in output
        assert "verbose" in output


class TestRunSheetFlow:
    """Tests for the sheet reading and project selection flow."""

    def test_no_projects_after_filter(self, tmp_path) -> None:
        """Exits with error when no projects remain after filtering."""
        sa_file = tmp_path / "sa.json"
        sa_file.write_text('{"type": "service_account"}')

        mock_rows = [
            {"title": "A", "link": "https://www.reddit.com/r/test", "pm_decision": ""},
        ]

        env = {**VALID_ENV}
        with patch.dict(os.environ, env, clear=True):
            with patch("autopoc.cli.read_sheet", return_value=mock_rows):
                result = runner.invoke(
                    app,
                    [
                        "run-sheet",
                        "--sheet-id", "test-sheet",
                        "--credentials", str(sa_file),
                        "--skip-validation",
                    ],
                )
                assert result.exit_code == 1
                assert "No projects remain" in result.stdout

    def test_selects_approved_github_project(self, tmp_path) -> None:
        """Selects the first approved GitHub project and attempts pipeline run."""
        sa_file = tmp_path / "sa.json"
        sa_file.write_text('{"type": "service_account"}')

        mock_rows = [
            {
                "title": "reddit-post",
                "link": "https://www.reddit.com/r/test",
                "category": "agents",
                "pm_decision": "Approve(user1)",
            },
            {
                "title": "org/my-project",
                "link": "https://github.com/org/my-project",
                "category": "rag",
                "pm_decision": "Approve(user1)",
            },
            {
                "title": "org/other-project",
                "link": "https://github.com/org/other-project",
                "category": "agents",
                "pm_decision": "",
            },
        ]

        env = {**VALID_ENV}
        with patch.dict(os.environ, env, clear=True):
            with (
                patch("autopoc.cli.read_sheet", return_value=mock_rows),
                patch("autopoc.cli._run_pipeline") as mock_pipeline,
            ):
                result = runner.invoke(
                    app,
                    [
                        "run-sheet",
                        "--sheet-id", "test-sheet",
                        "--credentials", str(sa_file),
                        "--skip-validation",
                    ],
                )
                # Should have selected my-project (first approved GitHub row)
                assert "my-project" in result.stdout
                assert "github.com/org/my-project" in result.stdout

                # Pipeline should have been called with derived name
                mock_pipeline.assert_called_once()
                call_args = mock_pipeline.call_args
                assert call_args[0][0] == "my-project"  # name
                assert call_args[0][1] == "https://github.com/org/my-project"  # repo

    def test_sheet_api_error_handled(self, tmp_path) -> None:
        """Google API errors are caught and reported cleanly."""
        sa_file = tmp_path / "sa.json"
        sa_file.write_text('{"type": "service_account"}')

        env = {**VALID_ENV}
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "autopoc.cli.read_sheet",
                side_effect=Exception("403 Permission denied"),
            ):
                result = runner.invoke(
                    app,
                    [
                        "run-sheet",
                        "--sheet-id", "test-sheet",
                        "--credentials", str(sa_file),
                        "--skip-validation",
                    ],
                )
                assert result.exit_code == 1
                assert "Failed to read sheet" in result.stdout
                assert "Permission denied" in result.stdout

    def test_prints_filter_summary(self, tmp_path) -> None:
        """Output includes row counts from filtering."""
        sa_file = tmp_path / "sa.json"
        sa_file.write_text('{"type": "service_account"}')

        mock_rows = [
            {
                "title": "org/repo-a",
                "link": "https://github.com/org/repo-a",
                "category": "rag",
                "pm_decision": "Approve(u1)",
            },
            {
                "title": "reddit-post",
                "link": "https://www.reddit.com/r/test",
                "category": "agents",
                "pm_decision": "",
            },
        ]

        env = {**VALID_ENV}
        with patch.dict(os.environ, env, clear=True):
            with (
                patch("autopoc.cli.read_sheet", return_value=mock_rows),
                patch("autopoc.cli._run_pipeline"),
            ):
                result = runner.invoke(
                    app,
                    [
                        "run-sheet",
                        "--sheet-id", "test-sheet",
                        "--credentials", str(sa_file),
                        "--skip-validation",
                    ],
                )
                # Should show row counts
                assert "Rows read: 2" in result.stdout
                assert "GitHub repos: 1" in result.stdout
