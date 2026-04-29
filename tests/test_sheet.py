"""Tests for autopoc.sheet module — Google Sheet reader and project selection."""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopoc.sheet import (
    SheetProject,
    _derive_project_name,
    _is_github_url,
    _parse_rows,
    filter_projects,
    read_sheet,
    select_project,
)

# Path to the reference CSV checked into the repo.
CSV_PATH = Path(__file__).resolve().parent.parent / "POCExplorer - 20260428#1.csv"


def _load_csv_rows() -> list[list[str]]:
    """Load the reference CSV as a list of lists (same shape as Sheets API)."""
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def _load_csv_as_dicts() -> list[dict[str, str]]:
    """Load the reference CSV and parse into dicts via _parse_rows."""
    return _parse_rows(_load_csv_rows())


# ---------------------------------------------------------------------------
# _is_github_url
# ---------------------------------------------------------------------------


class TestIsGitHubUrl:
    def test_github_url(self) -> None:
        assert _is_github_url("https://github.com/microsoft/TRELLIS.2") is True

    def test_github_url_with_www(self) -> None:
        assert _is_github_url("https://www.github.com/org/repo") is True

    def test_reddit_url(self) -> None:
        assert _is_github_url("https://www.reddit.com/r/LocalLLaMA/comments/xyz") is False

    def test_hackernews_url(self) -> None:
        assert _is_github_url("https://news.ycombinator.com/item?id=12345") is False

    def test_medium_url(self) -> None:
        assert _is_github_url("https://medium.com/some-article") is False

    def test_news_url(self) -> None:
        assert _is_github_url("https://english.kyodonews.net/articles/-/75029") is False

    def test_tomshardware_url(self) -> None:
        assert _is_github_url("https://www.tomshardware.com/tech-industry/ai") is False

    def test_empty_string(self) -> None:
        assert _is_github_url("") is False

    def test_not_a_url(self) -> None:
        assert _is_github_url("not-a-url") is False

    def test_huggingface_url(self) -> None:
        assert _is_github_url("https://huggingface.co/org/model") is False


# ---------------------------------------------------------------------------
# _parse_rows
# ---------------------------------------------------------------------------


class TestParseRows:
    def test_parse_csv_reference(self) -> None:
        """Parses the reference CSV correctly."""
        rows = _load_csv_rows()
        parsed = _parse_rows(rows)

        # CSV has 15 data rows (rows 4-18 in the file, i.e. indices 3-17)
        assert len(parsed) == 15

        # First data row is microsoft/TRELLIS.2
        first = parsed[0]
        assert first["title"] == "microsoft/TRELLIS.2"
        assert first["link"] == "https://github.com/microsoft/TRELLIS.2"
        assert first["category"] == "rag"
        assert "sources" in first

    def test_parse_preserves_all_columns(self) -> None:
        """All 34 header columns are present as keys."""
        parsed = _load_csv_as_dicts()
        first = parsed[0]
        assert "pm_decision" in first
        assert "pm_comments" in first
        assert "title" in first
        assert "link" in first

    def test_parse_too_few_rows(self) -> None:
        """Raises ValueError if not enough rows for metadata + header."""
        with pytest.raises(ValueError, match="expected at least 3"):
            _parse_rows([["metadata"], ["review"]])

    def test_parse_no_data_rows(self) -> None:
        """Header-only sheet returns empty list."""
        rows = [["metadata"], ["review"], ["title", "link"]]
        parsed = _parse_rows(rows)
        assert parsed == []

    def test_parse_ragged_rows(self) -> None:
        """Rows shorter than the header are padded with empty strings."""
        rows = [
            ["metadata"],
            ["review"],
            ["title", "link", "category"],
            ["Project A", "https://github.com/a/b"],  # missing 'category'
        ]
        parsed = _parse_rows(rows)
        assert len(parsed) == 1
        assert parsed[0]["title"] == "Project A"
        assert parsed[0]["link"] == "https://github.com/a/b"
        assert parsed[0]["category"] == ""  # padded

    def test_parse_empty_header_raises(self) -> None:
        """Raises ValueError if header row is empty."""
        rows = [["metadata"], ["review"], []]
        with pytest.raises(ValueError, match="Header row is empty"):
            _parse_rows(rows)


# ---------------------------------------------------------------------------
# filter_projects
# ---------------------------------------------------------------------------


class TestFilterProjects:
    def test_github_links_pass(self) -> None:
        """Rows with github.com links pass the link filter."""
        rows = [
            {"title": "A", "link": "https://github.com/org/repo", "pm_decision": ""},
            {"title": "B", "link": "https://www.reddit.com/r/test", "pm_decision": ""},
        ]
        result = filter_projects(rows)
        assert len(result) == 1
        assert result[0]["title"] == "A"

    def test_non_github_links_filtered(self) -> None:
        """Reddit, HN, Medium, news links are all filtered out."""
        rows = [
            {"title": "Reddit", "link": "https://www.reddit.com/r/test", "pm_decision": ""},
            {"title": "HN", "link": "https://news.ycombinator.com/item?id=1", "pm_decision": ""},
            {"title": "Medium", "link": "https://medium.com/article", "pm_decision": ""},
            {"title": "News", "link": "https://english.kyodonews.net/a", "pm_decision": ""},
        ]
        result = filter_projects(rows)
        assert result == []

    def test_pm_decision_approve_passes(self) -> None:
        """Rows with 'Approve' in pm_decision pass."""
        rows = [
            {
                "title": "A",
                "link": "https://github.com/org/a",
                "pm_decision": "Approve(egeiger)",
            },
            {"title": "B", "link": "https://github.com/org/b", "pm_decision": ""},
        ]
        result = filter_projects(rows)
        assert len(result) == 1
        assert result[0]["title"] == "A"

    def test_pm_decision_multiple_approvers(self) -> None:
        """Multiple approvers in pm_decision still passes."""
        rows = [
            {
                "title": "A",
                "link": "https://github.com/org/a",
                "pm_decision": "Approve(egeiger), Approve(rbelio)",
            },
        ]
        result = filter_projects(rows)
        assert len(result) == 1

    def test_pm_decision_case_insensitive(self) -> None:
        """pm_decision matching is case-insensitive."""
        rows = [
            {
                "title": "A",
                "link": "https://github.com/org/a",
                "pm_decision": "approve(user1)",
            },
        ]
        result = filter_projects(rows)
        assert len(result) == 1

    def test_no_pm_decision_column_skips_filter(self) -> None:
        """When no row has a pm_decision key, the filter is skipped."""
        rows = [
            {"title": "A", "link": "https://github.com/org/a"},
            {"title": "B", "link": "https://github.com/org/b"},
        ]
        result = filter_projects(rows)
        assert len(result) == 2

    def test_pm_decision_column_all_empty_skips_filter(self) -> None:
        """When pm_decision exists but is empty everywhere, filter is skipped."""
        rows = [
            {"title": "A", "link": "https://github.com/org/a", "pm_decision": ""},
            {"title": "B", "link": "https://github.com/org/b", "pm_decision": ""},
        ]
        result = filter_projects(rows)
        assert len(result) == 2

    def test_preserves_order(self) -> None:
        """Filtered results maintain original row order."""
        rows = [
            {
                "title": "C",
                "link": "https://github.com/org/c",
                "pm_decision": "Approve(u1)",
            },
            {
                "title": "A",
                "link": "https://github.com/org/a",
                "pm_decision": "Approve(u2)",
            },
            {
                "title": "B",
                "link": "https://github.com/org/b",
                "pm_decision": "Approve(u3)",
            },
        ]
        result = filter_projects(rows)
        assert [r["title"] for r in result] == ["C", "A", "B"]

    def test_both_filters_combined(self) -> None:
        """Link filter and pm_decision filter work together."""
        rows = [
            {
                "title": "GH-approved",
                "link": "https://github.com/org/a",
                "pm_decision": "Approve(u1)",
            },
            {
                "title": "GH-not-approved",
                "link": "https://github.com/org/b",
                "pm_decision": "",
            },
            {
                "title": "Reddit-approved",
                "link": "https://www.reddit.com/r/test",
                "pm_decision": "Approve(u1)",
            },
            {
                "title": "Reddit-not-approved",
                "link": "https://www.reddit.com/r/other",
                "pm_decision": "",
            },
        ]
        result = filter_projects(rows)
        assert len(result) == 1
        assert result[0]["title"] == "GH-approved"

    def test_filter_csv_reference(self) -> None:
        """Filtering the reference CSV produces expected results.

        In the reference CSV:
        - 6 rows have github.com links
        - pm_decision has a value in one row (a Reddit link with 'Approve')
        - Since pm_decision column has values, the approval filter applies
        - No GitHub row has pm_decision set → 0 results
        """
        parsed = _load_csv_as_dicts()
        result = filter_projects(parsed)
        # The only approved row is a Reddit link, so after both filters: 0
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _derive_project_name
# ---------------------------------------------------------------------------


class TestDeriveProjectName:
    def test_github_url_extracts_repo(self) -> None:
        """Extracts repo name from a standard GitHub URL."""
        assert _derive_project_name("https://github.com/microsoft/TRELLIS.2", "microsoft/TRELLIS.2") == "trellis.2"

    def test_github_url_with_trailing_slash(self) -> None:
        assert _derive_project_name("https://github.com/org/repo/", "org/repo") == "repo"

    def test_github_url_with_git_suffix(self) -> None:
        assert _derive_project_name("https://github.com/org/repo.git", "org/repo") == "repo"

    def test_owner_slash_repo_title(self) -> None:
        """Falls back to title when URL parsing fails."""
        assert _derive_project_name("not-a-url", "microsoft/TRELLIS.2") == "trellis.2"

    def test_simple_title_no_slash(self) -> None:
        assert _derive_project_name("not-a-url", "my-project") == "my-project"

    def test_lowercase(self) -> None:
        assert _derive_project_name("https://github.com/Org/CyberVerse", "Org/CyberVerse") == "cyberverse"

    def test_unsafe_chars_replaced(self) -> None:
        """Characters unsafe for paths/registries are replaced with hyphens."""
        assert _derive_project_name("https://github.com/org/my repo!", "org/my repo!") == "my-repo"

    def test_no_double_hyphens(self) -> None:
        assert _derive_project_name("https://github.com/org/a--b", "org/a--b") == "a-b"

    def test_empty_fallback(self) -> None:
        assert _derive_project_name("", "") == "unknown-project"

    def test_real_csv_names(self) -> None:
        """Verify all GitHub titles from the reference CSV produce clean names."""
        cases = [
            ("https://github.com/microsoft/TRELLIS.2", "microsoft/TRELLIS.2", "trellis.2"),
            ("https://github.com/dsd2077/CyberVerse", "dsd2077/CyberVerse", "cyberverse"),
            ("https://github.com/hpennington/agentswift", "hpennington/agentswift", "agentswift"),
            ("https://github.com/vishalmdi/ai-native-pm-os", "vishalmdi/ai-native-pm-os", "ai-native-pm-os"),
            ("https://github.com/Growth-Circle/cadis", "Growth-Circle/cadis", "cadis"),
            ("https://github.com/larksuite/aamp", "larksuite/aamp", "aamp"),
        ]
        for url, title, expected in cases:
            result = _derive_project_name(url, title)
            assert result == expected, f"{url} -> {result!r}, expected {expected!r}"


# ---------------------------------------------------------------------------
# select_project
# ---------------------------------------------------------------------------


class TestSelectProject:
    def test_selects_first_row(self) -> None:
        """Returns a SheetProject from the first row."""
        rows = [
            {"title": "org/project-a", "link": "https://github.com/org/project-a", "category": "rag"},
            {"title": "org/project-b", "link": "https://github.com/org/project-b", "category": "agents"},
        ]
        project = select_project(rows)
        assert project.name == "project-a"
        assert project.repo_url == "https://github.com/org/project-a"
        assert project.category == "rag"

    def test_empty_rows_raises(self) -> None:
        """Raises ValueError when no rows remain after filtering."""
        with pytest.raises(ValueError, match="No projects remain after filtering"):
            select_project([])

    def test_missing_title_raises(self) -> None:
        """Raises ValueError if the selected row has no 'title' column."""
        rows = [{"link": "https://github.com/org/a"}]
        with pytest.raises(ValueError, match="missing the 'title' column"):
            select_project(rows)

    def test_missing_link_raises(self) -> None:
        """Raises ValueError if the selected row has no 'link' column."""
        rows = [{"title": "Project A"}]
        with pytest.raises(ValueError, match="missing the 'link' column"):
            select_project(rows)

    def test_missing_category_defaults_empty(self) -> None:
        """Missing 'category' defaults to empty string."""
        rows = [{"title": "A", "link": "https://github.com/org/a"}]
        project = select_project(rows)
        assert project.category == ""

    def test_row_index_default(self) -> None:
        """Default row_index is 4 (1-based: 2 metadata + 1 header + 1)."""
        rows = [{"title": "A", "link": "https://github.com/org/a"}]
        project = select_project(rows)
        assert project.row_index == 4  # data_start_row=3, so 3+1=4

    def test_row_index_custom(self) -> None:
        """Custom data_start_row shifts the reported row_index."""
        rows = [{"title": "A", "link": "https://github.com/org/a"}]
        project = select_project(rows, data_start_row=5)
        assert project.row_index == 6

    def test_returns_sheet_project_type(self) -> None:
        """Return value is a SheetProject dataclass."""
        rows = [{"title": "A", "link": "https://github.com/org/a", "category": "agents"}]
        project = select_project(rows)
        assert isinstance(project, SheetProject)


# ---------------------------------------------------------------------------
# read_sheet (mocked Google API)
# ---------------------------------------------------------------------------


class TestReadSheet:
    def test_read_sheet_calls_api(self) -> None:
        """read_sheet authenticates, discovers tab name, and reads values."""
        # Simulate the Sheets API response matching our CSV structure
        csv_rows = _load_csv_rows()

        mock_creds = MagicMock()
        mock_service = MagicMock()
        mock_spreadsheets = mock_service.spreadsheets.return_value

        # Mock get() for tab name
        mock_spreadsheets.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "20260428#1"}}]
        }

        # Mock values().get() for cell data
        mock_spreadsheets.values.return_value.get.return_value.execute.return_value = {
            "values": csv_rows,
        }

        with (
            patch(
                "autopoc.sheet.Credentials.from_service_account_file",
                return_value=mock_creds,
            ) as mock_auth,
            patch("autopoc.sheet.build", return_value=mock_service) as mock_build,
        ):
            result = read_sheet("/fake/sa.json", "sheet-id-123")

        # Verify auth
        mock_auth.assert_called_once_with(
            "/fake/sa.json",
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        mock_build.assert_called_once_with(
            "sheets", "v4", credentials=mock_creds, cache_discovery=False
        )

        # Verify we got the right number of parsed rows
        assert len(result) == 15
        assert result[0]["title"] == "microsoft/TRELLIS.2"

    def test_read_sheet_empty_spreadsheet(self) -> None:
        """read_sheet raises ValueError for a spreadsheet with no tabs."""
        mock_creds = MagicMock()
        mock_service = MagicMock()
        mock_spreadsheets = mock_service.spreadsheets.return_value

        mock_spreadsheets.get.return_value.execute.return_value = {"sheets": []}

        with (
            patch(
                "autopoc.sheet.Credentials.from_service_account_file",
                return_value=mock_creds,
            ),
            patch("autopoc.sheet.build", return_value=mock_service),
        ):
            with pytest.raises(ValueError, match="has no tabs"):
                read_sheet("/fake/sa.json", "sheet-id-123")


# ---------------------------------------------------------------------------
# End-to-end: CSV reference data through the full pipeline
# ---------------------------------------------------------------------------


class TestEndToEndCSV:
    """Integration tests using the reference CSV as a stand-in for sheet data."""

    def test_full_pipeline_no_approved_github(self) -> None:
        """With the reference CSV data, no GitHub projects are approved.

        This matches the real data: the only 'Approve' row is a Reddit link.
        """
        parsed = _load_csv_as_dicts()
        filtered = filter_projects(parsed)

        with pytest.raises(ValueError, match="No projects remain"):
            select_project(filtered)

    def test_full_pipeline_with_approved_github(self) -> None:
        """Simulates a sheet where a GitHub project is approved."""
        parsed = _load_csv_as_dicts()

        # Patch the first GitHub row to have approval
        for row in parsed:
            if "github.com" in row.get("link", ""):
                row["pm_decision"] = "Approve(testuser)"
                break

        filtered = filter_projects(parsed)
        assert len(filtered) >= 1

        project = select_project(filtered)
        assert project.name == "trellis.2"
        assert project.repo_url == "https://github.com/microsoft/TRELLIS.2"
        assert isinstance(project, SheetProject)

    def test_github_rows_in_csv(self) -> None:
        """Verify the expected number of GitHub rows in the reference CSV."""
        parsed = _load_csv_as_dicts()
        github_rows = [r for r in parsed if "github.com" in r.get("link", "")]
        # CSV has 6 GitHub links: TRELLIS.2, CyberVerse, agentswift,
        # ai-native-pm-os, cadis, aamp
        assert len(github_rows) == 6
