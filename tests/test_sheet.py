"""Tests for autopoc.sheet module — Google Sheet reader and project selection."""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopoc.sheet import (
    SheetProject,
    SheetRowOrigin,
    _ORIGIN_KEY,
    _build_artifacts_branch_url,
    _build_report_url,
    _check_url_exists,
    _col_index_to_letter,
    _derive_project_name,
    _has_poc_results,
    _is_github_url,
    _parse_rows,
    _row_to_project,
    _strip_credentials_from_url,
    derive_fork_browse_url,
    derive_quay_search_url,
    ensure_result_columns,
    filter_projects,
    find_approved_unprocessed_projects,
    find_monthly_report_tab,
    read_sheet,
    select_project,
    write_poc_results,
)

# Path to the reference CSV fixture.
CSV_PATH = Path(__file__).resolve().parent / "fixtures" / "poc_explorer_sample.csv"


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
        assert (
            _derive_project_name("https://github.com/microsoft/TRELLIS.2", "microsoft/TRELLIS.2")
            == "trellis.2"
        )

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
        assert (
            _derive_project_name("https://github.com/Org/CyberVerse", "Org/CyberVerse")
            == "cyberverse"
        )

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
            (
                "https://github.com/vishalmdi/ai-native-pm-os",
                "vishalmdi/ai-native-pm-os",
                "ai-native-pm-os",
            ),
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
            {
                "title": "org/project-a",
                "link": "https://github.com/org/project-a",
                "category": "rag",
            },
            {
                "title": "org/project-b",
                "link": "https://github.com/org/project-b",
                "category": "agents",
            },
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
            "sheets": [{"properties": {"title": "20260428#1", "sheetId": 0}}]
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
            result = read_sheet("/fake/sa.json", "sheet-id-123", monthly_mode=False)

        # Verify auth — scope is read-write for write-back support
        mock_auth.assert_called_once_with(
            "/fake/sa.json",
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        mock_build.assert_called_once_with(
            "sheets", "v4", credentials=mock_creds, cache_discovery=False
        )

        # Verify we got the right number of parsed rows
        assert len(result) == 15
        assert result[0]["title"] == "microsoft/TRELLIS.2"

        # Verify origin metadata is injected
        origin = result[0][_ORIGIN_KEY]
        assert isinstance(origin, SheetRowOrigin)
        assert origin.tab_name == "20260428#1"
        assert origin.tab_gid == 0
        assert origin.row_number == 4  # 2 metadata + 1 header + 1 (first data row)

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
                read_sheet("/fake/sa.json", "sheet-id-123", monthly_mode=False)

    def test_read_sheet_multi_tab(self) -> None:
        """read_sheet with max_tabs=2 reads two tabs and aggregates rows."""
        tab1_rows = [
            ["metadata"],
            ["review"],
            ["title", "link", "category"],
            ["ProjectA", "https://github.com/org/a", "rag"],
        ]
        tab2_rows = [
            ["metadata"],
            ["review"],
            ["title", "link", "category"],
            ["ProjectB", "https://github.com/org/b", "agents"],
            ["ProjectC", "https://github.com/org/c", "inference"],
        ]

        mock_creds = MagicMock()
        mock_service = MagicMock()
        mock_spreadsheets = mock_service.spreadsheets.return_value

        mock_spreadsheets.get.return_value.execute.return_value = {
            "sheets": [
                {"properties": {"title": "Week1", "sheetId": 0}},
                {"properties": {"title": "Week2", "sheetId": 42}},
                {"properties": {"title": "Week3", "sheetId": 99}},
            ]
        }

        # values().get() returns different data per tab
        def fake_values_get(spreadsheetId, range):
            mock_result = MagicMock()
            if "Week1" in range:
                mock_result.execute.return_value = {"values": tab1_rows}
            elif "Week2" in range:
                mock_result.execute.return_value = {"values": tab2_rows}
            else:
                mock_result.execute.return_value = {"values": []}
            return mock_result

        mock_spreadsheets.values.return_value.get = fake_values_get

        with (
            patch("autopoc.sheet.Credentials.from_service_account_file", return_value=mock_creds),
            patch("autopoc.sheet.build", return_value=mock_service),
        ):
            result = read_sheet("/fake/sa.json", "sheet-id-123", max_tabs=2, monthly_mode=False)

        # Should have 3 rows total (1 from tab1 + 2 from tab2)
        assert len(result) == 3
        assert result[0]["title"] == "ProjectA"
        assert result[1]["title"] == "ProjectB"
        assert result[2]["title"] == "ProjectC"

        # Verify tab 1 origin
        assert result[0][_ORIGIN_KEY].tab_name == "Week1"
        assert result[0][_ORIGIN_KEY].tab_gid == 0
        assert result[0][_ORIGIN_KEY].row_number == 4

        # Verify tab 2 origin (non-zero tab!) — key requirement
        assert result[1][_ORIGIN_KEY].tab_name == "Week2"
        assert result[1][_ORIGIN_KEY].tab_gid == 42
        assert result[1][_ORIGIN_KEY].row_number == 4
        assert result[2][_ORIGIN_KEY].tab_name == "Week2"
        assert result[2][_ORIGIN_KEY].tab_gid == 42
        assert result[2][_ORIGIN_KEY].row_number == 5

    def test_read_sheet_skips_invalid_tab(self) -> None:
        """read_sheet skips tabs that don't have enough rows for metadata + header."""
        good_tab = [
            ["metadata"],
            ["review"],
            ["title", "link"],
            ["A", "https://github.com/org/a"],
        ]
        bad_tab = [["only-one-row"]]

        mock_creds = MagicMock()
        mock_service = MagicMock()
        mock_spreadsheets = mock_service.spreadsheets.return_value

        mock_spreadsheets.get.return_value.execute.return_value = {
            "sheets": [
                {"properties": {"title": "BadTab", "sheetId": 1}},
                {"properties": {"title": "GoodTab", "sheetId": 2}},
            ]
        }

        def fake_values_get(spreadsheetId, range):
            mock_result = MagicMock()
            if "BadTab" in range:
                mock_result.execute.return_value = {"values": bad_tab}
            else:
                mock_result.execute.return_value = {"values": good_tab}
            return mock_result

        mock_spreadsheets.values.return_value.get = fake_values_get

        with (
            patch("autopoc.sheet.Credentials.from_service_account_file", return_value=mock_creds),
            patch("autopoc.sheet.build", return_value=mock_service),
        ):
            result = read_sheet("/fake/sa.json", "sheet-id", max_tabs=2, monthly_mode=False)

        assert len(result) == 1
        assert result[0]["title"] == "A"
        assert result[0][_ORIGIN_KEY].tab_name == "GoodTab"

    def test_read_sheet_respects_max_tabs(self) -> None:
        """read_sheet only reads max_tabs tabs even if more exist."""
        tab_rows = [
            ["metadata"],
            ["review"],
            ["title", "link"],
            ["X", "https://github.com/org/x"],
        ]

        mock_creds = MagicMock()
        mock_service = MagicMock()
        mock_spreadsheets = mock_service.spreadsheets.return_value

        mock_spreadsheets.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": f"Tab{i}", "sheetId": i}} for i in range(10)]
        }

        call_count = 0

        def fake_values_get(spreadsheetId, range):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_result.execute.return_value = {"values": tab_rows}
            return mock_result

        mock_spreadsheets.values.return_value.get = fake_values_get

        with (
            patch("autopoc.sheet.Credentials.from_service_account_file", return_value=mock_creds),
            patch("autopoc.sheet.build", return_value=mock_service),
        ):
            result = read_sheet("/fake/sa.json", "sheet-id", max_tabs=3, monthly_mode=False)

        # Should have read exactly 3 tabs
        assert call_count == 3
        assert len(result) == 3


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


# ---------------------------------------------------------------------------
# Already-processed filter
# ---------------------------------------------------------------------------


class TestAlreadyProcessedFilter:
    """Tests for skipping rows that already have PoC results."""

    def test_rows_with_poc_repo_skipped(self) -> None:
        """Rows with a non-empty poc_repo value are excluded."""
        rows = [
            {
                "title": "A",
                "link": "https://github.com/org/a",
                "poc_repo": "https://github.com/fork/a/tree/autopoc-artifacts",
                "poc_image": "",
                "poc_report": "",
            },
            {
                "title": "B",
                "link": "https://github.com/org/b",
                "poc_repo": "",
                "poc_image": "",
                "poc_report": "",
            },
        ]
        result = filter_projects(rows)
        assert len(result) == 1
        assert result[0]["title"] == "B"

    def test_rows_with_poc_image_skipped(self) -> None:
        """Rows with a non-empty poc_image value are excluded."""
        rows = [
            {
                "title": "A",
                "link": "https://github.com/org/a",
                "poc_image": "quay.io/org/a:latest",
            },
        ]
        result = filter_projects(rows)
        assert len(result) == 0

    def test_rows_with_poc_report_skipped(self) -> None:
        """Rows with a non-empty poc_report value are excluded."""
        rows = [
            {
                "title": "A",
                "link": "https://github.com/org/a",
                "poc_report": "https://github.com/fork/a/blob/autopoc-artifacts/poc-report.md",
            },
        ]
        result = filter_projects(rows)
        assert len(result) == 0

    def test_rows_with_failed_values_are_skipped(self) -> None:
        """Rows where poc_repo=FAILED are considered already-processed."""
        rows = [
            {
                "title": "A",
                "link": "https://github.com/org/a",
                "poc_repo": "FAILED",
                "poc_image": "FAILED",
                "poc_report": "FAILED",
            },
        ]
        result = filter_projects(rows)
        assert len(result) == 0

    def test_rows_without_poc_columns_pass(self) -> None:
        """Rows without any poc_* columns pass the filter."""
        rows = [
            {"title": "A", "link": "https://github.com/org/a"},
        ]
        result = filter_projects(rows)
        assert len(result) == 1

    def test_whitespace_only_poc_values_pass(self) -> None:
        """Rows with whitespace-only poc_* values are NOT skipped."""
        rows = [
            {
                "title": "A",
                "link": "https://github.com/org/a",
                "poc_repo": "  ",
                "poc_image": "",
                "poc_report": "",
            },
        ]
        result = filter_projects(rows)
        assert len(result) == 1

    def test_has_poc_results_helper(self) -> None:
        """_has_poc_results correctly detects existing results."""
        assert _has_poc_results({"poc_repo": "something"}) is True
        assert _has_poc_results({"poc_image": "something"}) is True
        assert _has_poc_results({"poc_report": "something"}) is True
        assert _has_poc_results({"poc_repo": "", "poc_image": "", "poc_report": ""}) is False
        assert _has_poc_results({"title": "A"}) is False


# ---------------------------------------------------------------------------
# Origin tracking and _row_to_project
# ---------------------------------------------------------------------------


class TestRowToProject:
    """Tests for _row_to_project with origin metadata."""

    def test_with_origin_metadata(self) -> None:
        """Origin metadata populates tab_name, tab_gid, and row_index."""
        row = {
            "title": "org/repo",
            "link": "https://github.com/org/repo",
            "category": "rag",
            _ORIGIN_KEY: SheetRowOrigin(tab_name="Week2", tab_gid=42, row_number=7),
        }
        project = _row_to_project(row)
        assert project.name == "repo"
        assert project.tab_name == "Week2"
        assert project.tab_gid == 42
        assert project.row_index == 7

    def test_without_origin_uses_fallback(self) -> None:
        """Without origin metadata, fallback_row_index is used."""
        row = {
            "title": "org/repo",
            "link": "https://github.com/org/repo",
        }
        project = _row_to_project(row, fallback_row_index=10)
        assert project.row_index == 10
        assert project.tab_name == ""
        assert project.tab_gid == 0

    def test_tab_not_zero(self) -> None:
        """Projects from a non-first tab retain the correct tab info."""
        row = {
            "title": "org/ml-project",
            "link": "https://github.com/org/ml-project",
            "category": "inference",
            _ORIGIN_KEY: SheetRowOrigin(tab_name="Sprint3", tab_gid=99, row_number=12),
        }
        project = _row_to_project(row)
        assert project.tab_name == "Sprint3"
        assert project.tab_gid == 99
        assert project.row_index == 12
        assert project.name == "ml-project"

    def test_select_project_uses_origin(self) -> None:
        """select_project delegates to _row_to_project and preserves origin."""
        rows = [
            {
                "title": "org/project-a",
                "link": "https://github.com/org/project-a",
                "category": "rag",
                _ORIGIN_KEY: SheetRowOrigin(tab_name="Tab5", tab_gid=55, row_number=9),
            },
        ]
        project = select_project(rows)
        assert project.name == "project-a"
        assert project.tab_name == "Tab5"
        assert project.tab_gid == 55
        assert project.row_index == 9


# ---------------------------------------------------------------------------
# Credential stripping
# ---------------------------------------------------------------------------


class TestStripCredentials:
    """Tests for _strip_credentials_from_url."""

    def test_github_token(self) -> None:
        url = "https://ghp_abc123@github.com/org/repo.git"
        assert _strip_credentials_from_url(url) == "https://github.com/org/repo"

    def test_gitlab_oauth(self) -> None:
        url = "https://oauth2:glpat-xyz@gitlab.example.com/group/project.git"
        assert _strip_credentials_from_url(url) == "https://gitlab.example.com/group/project"

    def test_no_credentials(self) -> None:
        url = "https://github.com/org/repo"
        assert _strip_credentials_from_url(url) == "https://github.com/org/repo"

    def test_no_git_suffix(self) -> None:
        url = "https://token@github.com/org/repo"
        assert _strip_credentials_from_url(url) == "https://github.com/org/repo"

    def test_empty_url(self) -> None:
        assert _strip_credentials_from_url("") == ""


# ---------------------------------------------------------------------------
# Artifacts branch URL building
# ---------------------------------------------------------------------------


class TestBuildUrls:
    """Tests for _build_artifacts_branch_url and _build_report_url."""

    def test_github_artifacts_url(self) -> None:
        url = _build_artifacts_branch_url("https://token@github.com/org/repo.git", "github")
        assert url == "https://github.com/org/repo/tree/autopoc-artifacts"

    def test_gitlab_artifacts_url(self) -> None:
        url = _build_artifacts_branch_url(
            "https://oauth2:token@gitlab.example.com/g/p.git", "gitlab"
        )
        assert url == "https://gitlab.example.com/g/p/-/tree/autopoc-artifacts"

    def test_github_report_url(self) -> None:
        url = _build_report_url("https://token@github.com/org/repo.git", "github")
        assert url == "https://github.com/org/repo/blob/autopoc-artifacts/poc-report.md"

    def test_gitlab_report_url(self) -> None:
        url = _build_report_url("https://oauth2:token@gitlab.example.com/g/p.git", "gitlab")
        assert url == "https://gitlab.example.com/g/p/-/blob/autopoc-artifacts/poc-report.md"


# ---------------------------------------------------------------------------
# derive_fork_browse_url
# ---------------------------------------------------------------------------


class TestDeriveForkBrowseUrl:
    """Tests for derive_fork_browse_url fallback URL construction."""

    def test_github_with_org(self) -> None:
        url = derive_fork_browse_url(
            "https://github.com/upstream/repo",
            "github",
            github_org="my-org",
        )
        assert url == "https://github.com/my-org/repo"

    def test_github_strips_git_suffix(self) -> None:
        url = derive_fork_browse_url(
            "https://github.com/upstream/repo.git",
            "github",
            github_org="my-org",
        )
        assert url == "https://github.com/my-org/repo"

    def test_gitlab_with_group(self) -> None:
        url = derive_fork_browse_url(
            "https://github.com/upstream/repo",
            "gitlab",
            gitlab_url="https://gitlab.example.com",
            gitlab_group="poc-demos",
        )
        assert url == "https://gitlab.example.com/poc-demos/repo"

    def test_gitlab_strips_trailing_slash(self) -> None:
        url = derive_fork_browse_url(
            "https://github.com/upstream/repo",
            "gitlab",
            gitlab_url="https://gitlab.example.com/",
            gitlab_group="poc-demos",
        )
        assert url == "https://gitlab.example.com/poc-demos/repo"

    def test_github_no_org_returns_none(self) -> None:
        """Without github_org, we can't derive the fork owner."""
        url = derive_fork_browse_url(
            "https://github.com/upstream/repo",
            "github",
        )
        assert url is None

    def test_gitlab_missing_config_returns_none(self) -> None:
        url = derive_fork_browse_url(
            "https://github.com/upstream/repo",
            "gitlab",
        )
        assert url is None

    def test_invalid_url_returns_none(self) -> None:
        url = derive_fork_browse_url("not-a-url", "github", github_org="org")
        assert url is None

    def test_url_with_only_one_path_segment(self) -> None:
        url = derive_fork_browse_url(
            "https://github.com/owner-only",
            "github",
            github_org="org",
        )
        assert url is None


# ---------------------------------------------------------------------------
# derive_quay_search_url
# ---------------------------------------------------------------------------


class TestDeriveQuaySearchUrl:
    """Tests for derive_quay_search_url."""

    def test_basic(self) -> None:
        url = derive_quay_search_url("my-project", "quay.io", "my-org")
        assert url == "https://quay.io/organization/my-org?tab=repositories&q=my-project"

    def test_strips_scheme(self) -> None:
        url = derive_quay_search_url("proj", "https://quay.io", "org")
        assert url == "https://quay.io/organization/org?tab=repositories&q=proj"

    def test_strips_trailing_slash(self) -> None:
        url = derive_quay_search_url("proj", "quay.io/", "org")
        assert url == "https://quay.io/organization/org?tab=repositories&q=proj"

    def test_custom_registry(self) -> None:
        url = derive_quay_search_url("proj", "registry.example.com", "team")
        assert url == "https://registry.example.com/organization/team?tab=repositories&q=proj"


# ---------------------------------------------------------------------------
# _check_url_exists
# ---------------------------------------------------------------------------


class TestCheckUrlExists:
    """Tests for _check_url_exists with mocked httpx."""

    def test_200_returns_true(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("httpx.head", return_value=mock_response):
            assert _check_url_exists("https://example.com/file") is True

    def test_301_redirect_returns_true(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 301
        with patch("httpx.head", return_value=mock_response):
            assert _check_url_exists("https://example.com/file") is True

    def test_404_returns_false(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch("httpx.head", return_value=mock_response):
            assert _check_url_exists("https://example.com/missing") is False

    def test_network_error_returns_false(self) -> None:
        with patch("httpx.head", side_effect=Exception("connection refused")):
            assert _check_url_exists("https://example.com/down") is False

    def test_timeout_returns_false(self) -> None:
        import httpx as httpx_mod

        with patch("httpx.head", side_effect=httpx_mod.TimeoutException("timeout")):
            assert _check_url_exists("https://example.com/slow") is False


# ---------------------------------------------------------------------------
# Column index to letter
# ---------------------------------------------------------------------------


class TestColIndexToLetter:
    def test_single_letters(self) -> None:
        assert _col_index_to_letter(0) == "A"
        assert _col_index_to_letter(1) == "B"
        assert _col_index_to_letter(25) == "Z"

    def test_double_letters(self) -> None:
        assert _col_index_to_letter(26) == "AA"
        assert _col_index_to_letter(27) == "AB"
        assert _col_index_to_letter(51) == "AZ"
        assert _col_index_to_letter(52) == "BA"


# ---------------------------------------------------------------------------
# ensure_result_columns
# ---------------------------------------------------------------------------


class TestEnsureResultColumns:
    """Tests for ensure_result_columns."""

    def test_creates_missing_columns(self) -> None:
        """Expands grid and appends all PoC result columns when missing."""
        mock_service = MagicMock()
        headers = ["title", "link", "category"]

        col_indices = ensure_result_columns(mock_service, "sheet-123", "Tab1", headers, tab_gid=42)

        # Should have expanded the grid first
        batch_update = mock_service.spreadsheets.return_value.batchUpdate
        batch_update.assert_called_once()
        batch_body = batch_update.call_args.kwargs["body"]
        append_req = batch_body["requests"][0]["appendDimension"]
        assert append_req["sheetId"] == 42
        assert append_req["dimension"] == "COLUMNS"
        assert append_req["length"] == 4

        # Then should have written the header values
        values_update = mock_service.spreadsheets.return_value.values.return_value.update
        values_update.assert_called_once()
        call_kwargs = values_update.call_args
        assert call_kwargs.kwargs["body"]["values"] == [
            ["poc_repo", "poc_image", "poc_report", "poc_blog"]
        ]

        # Column indices should be correct
        assert col_indices["poc_repo"] == 3
        assert col_indices["poc_image"] == 4
        assert col_indices["poc_report"] == 5
        assert col_indices["poc_blog"] == 6

    def test_columns_already_exist(self) -> None:
        """No API call when all columns already exist."""
        mock_service = MagicMock()
        headers = ["title", "link", "poc_repo", "poc_image", "poc_report", "poc_blog"]

        col_indices = ensure_result_columns(mock_service, "sheet-123", "Tab1", headers, tab_gid=0)

        # No grid expansion or value update
        mock_service.spreadsheets.return_value.batchUpdate.assert_not_called()
        mock_service.spreadsheets.return_value.values.return_value.update.assert_not_called()

        assert col_indices["poc_repo"] == 2
        assert col_indices["poc_image"] == 3
        assert col_indices["poc_report"] == 4
        assert col_indices["poc_blog"] == 5

    def test_partial_columns_exist(self) -> None:
        """Only appends the missing columns and expands grid accordingly."""
        mock_service = MagicMock()
        headers = ["title", "link", "poc_repo"]

        col_indices = ensure_result_columns(mock_service, "sheet-123", "Tab1", headers, tab_gid=7)

        # Grid should be expanded by 3 (poc_image, poc_report, poc_blog missing)
        batch_body = mock_service.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"]
        assert batch_body["requests"][0]["appendDimension"]["length"] == 3
        assert batch_body["requests"][0]["appendDimension"]["sheetId"] == 7

        call_kwargs = mock_service.spreadsheets.return_value.values.return_value.update.call_args
        assert call_kwargs.kwargs["body"]["values"] == [["poc_image", "poc_report", "poc_blog"]]

        assert col_indices["poc_repo"] == 2
        assert col_indices["poc_image"] == 3
        assert col_indices["poc_report"] == 4
        assert col_indices["poc_blog"] == 5


# ---------------------------------------------------------------------------
# write_poc_results
# ---------------------------------------------------------------------------


class TestWritePocResults:
    """Tests for write_poc_results."""

    def test_writes_successful_results(self) -> None:
        """Writes correct values for a successful pipeline run."""
        mock_service = MagicMock()
        col_indices = {"poc_repo": 3, "poc_image": 4, "poc_report": 5, "poc_blog": 6}

        write_poc_results(
            mock_service,
            "sheet-123",
            "Tab1",
            row_number=7,
            col_indices=col_indices,
            fork_repo_url="https://token@github.com/org/repo.git",
            fork_target="github",
            built_images=["quay.io/org/repo:latest"],
            poc_report_path="/tmp/autopoc/repo/poc-report.md",
        )

        # Should have 4 update calls (one per column)
        update_mock = mock_service.spreadsheets.return_value.values.return_value.update
        assert update_mock.call_count == 4

    def test_writes_failed_values(self) -> None:
        """Writes FAILED for required columns, empty for optional (blog)."""
        mock_service = MagicMock()
        col_indices = {"poc_repo": 3, "poc_image": 4, "poc_report": 5, "poc_blog": 6}

        write_poc_results(
            mock_service,
            "sheet-123",
            "Tab1",
            row_number=5,
            col_indices=col_indices,
            fork_repo_url=None,
            fork_target=None,
            built_images=None,
            poc_report_path=None,
        )

        update_mock = mock_service.spreadsheets.return_value.values.return_value.update
        # Collect all written values
        written_values = []
        for c in update_mock.call_args_list:
            written_values.append(c.kwargs["body"]["values"][0][0])

        # First 3 (poc_repo, poc_image, poc_report) should be FAILED
        assert written_values[0] == "FAILED"
        assert written_values[1] == "FAILED"
        assert written_values[2] == "FAILED"
        # poc_blog is optional — empty, not FAILED
        assert written_values[3] == ""

    def test_poc_image_override(self) -> None:
        """poc_image_override bypasses built_images logic."""
        mock_service = MagicMock()
        col_indices = {"poc_repo": 0, "poc_image": 1, "poc_report": 2, "poc_blog": 3}

        write_poc_results(
            mock_service,
            "sheet-123",
            "Tab1",
            row_number=4,
            col_indices=col_indices,
            fork_repo_url=None,
            fork_target="github",
            built_images=None,
            poc_report_path=None,
            poc_image_override="https://quay.io/organization/org?tab=repositories&q=proj",
        )

        update_mock = mock_service.spreadsheets.return_value.values.return_value.update
        written_values = [c.kwargs["body"]["values"][0][0] for c in update_mock.call_args_list]
        # poc_image should be the override, not FAILED
        assert written_values[1] == "https://quay.io/organization/org?tab=repositories&q=proj"

    def test_poc_report_override(self) -> None:
        """poc_report_override bypasses local file check."""
        mock_service = MagicMock()
        col_indices = {"poc_repo": 0, "poc_image": 1, "poc_report": 2, "poc_blog": 3}

        write_poc_results(
            mock_service,
            "sheet-123",
            "Tab1",
            row_number=4,
            col_indices=col_indices,
            fork_repo_url=None,
            fork_target="github",
            built_images=None,
            poc_report_path=None,
            poc_report_override="https://github.com/org/repo/blob/autopoc-artifacts/poc-report.md",
        )

        update_mock = mock_service.spreadsheets.return_value.values.return_value.update
        written_values = [c.kwargs["body"]["values"][0][0] for c in update_mock.call_args_list]
        # poc_report should be the override, not FAILED
        assert (
            written_values[2] == "https://github.com/org/repo/blob/autopoc-artifacts/poc-report.md"
        )

    def test_overrides_take_precedence(self) -> None:
        """Overrides win even when primary values are available."""
        mock_service = MagicMock()
        col_indices = {"poc_repo": 0, "poc_image": 1, "poc_report": 2, "poc_blog": 3}

        write_poc_results(
            mock_service,
            "sheet-123",
            "Tab1",
            row_number=4,
            col_indices=col_indices,
            fork_repo_url="https://token@github.com/org/repo.git",
            fork_target="github",
            built_images=["quay.io/org/img:latest"],
            poc_report_path=None,
            poc_image_override="override-image-url",
            poc_report_override="override-report-url",
        )

        update_mock = mock_service.spreadsheets.return_value.values.return_value.update
        written_values = [c.kwargs["body"]["values"][0][0] for c in update_mock.call_args_list]
        assert written_values[1] == "override-image-url"
        assert written_values[2] == "override-report-url"


# ---------------------------------------------------------------------------
# Monthly Mode Functions
# ---------------------------------------------------------------------------


class TestMonthlyReportTab:
    """Test find_monthly_report_tab function."""

    def test_exact_match_monthly_report(self) -> None:
        """Should find exact matches for Monthly Report patterns."""
        sheets = [
            {"properties": {"title": "Sheet1", "sheetId": 1}},
            {"properties": {"title": "Monthly Report 2026-05", "sheetId": 2}},
            {"properties": {"title": "Sheet2", "sheetId": 3}},
        ]

        result = find_monthly_report_tab(sheets, "2026-05")
        assert result is not None
        assert result["properties"]["title"] == "Monthly Report 2026-05"
        assert result["properties"]["sheetId"] == 2

    def test_fuzzy_match_monthly_tab(self) -> None:
        """Should find fuzzy matches for monthly tabs."""
        sheets = [
            {"properties": {"title": "Sheet1", "sheetId": 1}},
            {"properties": {"title": "May 2026 Report", "sheetId": 2}},
            {"properties": {"title": "Sheet2", "sheetId": 3}},
        ]

        result = find_monthly_report_tab(sheets, "2026-05")
        assert result is not None
        assert result["properties"]["title"] == "May 2026 Report"

    def test_case_insensitive_match(self) -> None:
        """Should match case-insensitively."""
        sheets = [
            {"properties": {"title": "monthly report 2026-05", "sheetId": 1}},
        ]

        result = find_monthly_report_tab(sheets, "2026-05")
        assert result is not None
        assert result["properties"]["title"] == "monthly report 2026-05"

    def test_no_match_found(self) -> None:
        """Should return None when no monthly tab is found."""
        sheets = [
            {"properties": {"title": "Sheet1", "sheetId": 1}},
            {"properties": {"title": "Sheet2", "sheetId": 2}},
        ]

        result = find_monthly_report_tab(sheets, "2026-05")
        assert result is None

    def test_current_month_default(self) -> None:
        """Should use current month when target_month is None."""
        from datetime import datetime

        current_month = datetime.now().strftime("%Y-%m")

        sheets = [
            {"properties": {"title": f"Monthly Report {current_month}", "sheetId": 1}},
        ]

        result = find_monthly_report_tab(sheets, None)
        assert result is not None
        assert result["properties"]["title"] == f"Monthly Report {current_month}"


class TestApprovedUnprocessedProjects:
    """Test find_approved_unprocessed_projects function."""

    def test_find_approved_unprocessed(self) -> None:
        """Should find approved projects without PoC results."""
        rows = [
            {
                "title": "Project 1",
                "link": "https://github.com/org/project1",
                "pm_decision": "approve",
                "poc_repo": "",
                "poc_image": "",
                "poc_report": "",
            },
            {
                "title": "Project 2",
                "link": "https://github.com/org/project2",
                "pm_decision": "approve",
                "poc_repo": "https://github.com/org/project2-poc",
                "poc_image": "",
                "poc_report": "",
            },
            {
                "title": "Project 3",
                "link": "https://github.com/org/project3",
                "pm_decision": "approve",
                "poc_repo": "",
                "poc_image": "",
                "poc_report": "",
            },
        ]

        result = find_approved_unprocessed_projects(rows, max_projects=5)
        assert len(result) == 2  # Only projects 1 and 3 (project 2 has poc_repo)
        assert result[0]["title"] == "Project 1"
        assert result[1]["title"] == "Project 3"

    def test_limit_max_projects(self) -> None:
        """Should limit results to max_projects."""
        rows = [
            {
                "title": f"Project {i}",
                "link": f"https://github.com/org/project{i}",
                "pm_decision": "approve",
                "poc_repo": "",
                "poc_image": "",
                "poc_report": "",
            }
            for i in range(1, 8)  # 7 projects
        ]

        result = find_approved_unprocessed_projects(rows, max_projects=3)
        assert len(result) == 3

    def test_no_approved_projects(self) -> None:
        """Should return empty list when no approved projects found."""
        rows = [
            {
                "title": "Project 1",
                "link": "https://github.com/org/project1",
                "pm_decision": "reject",
                "poc_repo": "",
                "poc_image": "",
                "poc_report": "",
            },
        ]

        result = find_approved_unprocessed_projects(rows, max_projects=5)
        assert len(result) == 0


class TestReadSheetMonthlyMode:
    """Test read_sheet with monthly_mode=True."""

    @patch("autopoc.sheet.build_sheets_service")
    def test_monthly_mode_success(self, mock_build_service) -> None:
        """Should read from monthly report tab when monthly_mode=True."""
        # Mock the service and spreadsheet response
        mock_service = MagicMock()
        mock_build_service.return_value = mock_service

        # Mock spreadsheet metadata with a monthly report tab
        mock_service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [
                {"properties": {"title": "Sheet1", "sheetId": 1}},
                {"properties": {"title": "Monthly Report 2026-05", "sheetId": 2}},
            ]
        }

        # Mock the sheet data
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": _load_csv_rows()
        }

        # Call with monthly mode
        result = read_sheet(
            credentials_file="dummy.json",
            sheet_id="test-sheet-id",
            monthly_mode=True,
            target_month="2026-05",
        )

        # Should have found the monthly tab and read from it
        assert len(result) > 0
        get_call = mock_service.spreadsheets.return_value.get.call_args
        assert get_call[1]["spreadsheetId"] == "test-sheet-id"

        values_call = mock_service.spreadsheets.return_value.values.return_value.get.call_args
        assert "'Monthly Report 2026-05'!A1:ZZ" in values_call[1]["range"]

    @patch("autopoc.sheet.build_sheets_service")
    def test_monthly_mode_tab_not_found(self, mock_build_service) -> None:
        """Should raise ValueError when monthly tab is not found."""
        mock_service = MagicMock()
        mock_build_service.return_value = mock_service

        # Mock spreadsheet without monthly report tab
        mock_service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [
                {"properties": {"title": "Sheet1", "sheetId": 1}},
                {"properties": {"title": "Sheet2", "sheetId": 2}},
            ]
        }

        with pytest.raises(ValueError, match="No monthly report tab found for 2026-05"):
            read_sheet(
                credentials_file="dummy.json",
                sheet_id="test-sheet-id",
                monthly_mode=True,
                target_month="2026-05",
            )

    @patch("autopoc.sheet.build_sheets_service")
    def test_monthly_mode_is_default(self, mock_build_service) -> None:
        """Monthly mode should be the default when no mode is specified."""
        mock_service = MagicMock()
        mock_build_service.return_value = mock_service

        # Mock spreadsheet metadata with a monthly report tab for current month
        from datetime import datetime

        current_month = datetime.now().strftime("%Y-%m")
        mock_service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [
                {"properties": {"title": "Sheet1", "sheetId": 1}},
                {"properties": {"title": f"Monthly Report {current_month}", "sheetId": 2}},
            ]
        }

        # Mock the sheet data
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": _load_csv_rows()
        }

        # Call without specifying monthly_mode (should default to True)
        result = read_sheet(credentials_file="dummy.json", sheet_id="test-sheet-id")

        # Should have used monthly mode by default and found current month's tab
        assert len(result) > 0
        values_call = mock_service.spreadsheets.return_value.values.return_value.get.call_args
        assert f"'Monthly Report {current_month}'!A1:ZZ" in values_call[1]["range"]
