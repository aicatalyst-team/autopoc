"""Tests for autopoc.agents.blog_post module."""

from __future__ import annotations

from autopoc.agents.blog_post import (
    _compute_overall_score,
    _finalize_draft,
    _inline_format,
    _markdown_to_html,
    _parse_dimension_scores,
    _parse_reviewer_score,
    _strip_url_credentials,
)
from autopoc.graph import route_after_poc_report
from autopoc.state import PoCState


# ---------------------------------------------------------------------------
# Score parsing
# ---------------------------------------------------------------------------


class TestParseReviewerScore:
    """Tests for _parse_reviewer_score()."""

    def test_parses_integer_score(self) -> None:
        text = "SCORES:\n- foo: 8/10\nOVERALL: 8/10\n"
        assert _parse_reviewer_score(text) == 8.0

    def test_parses_float_score(self) -> None:
        text = "OVERALL: 7.5/10\n"
        assert _parse_reviewer_score(text) == 7.5

    def test_fallback_on_missing_score(self) -> None:
        text = "No score here at all."
        assert _parse_reviewer_score(text) == 5.0

    def test_fallback_on_malformed_score(self) -> None:
        text = "OVERALL: abc/10\n"
        assert _parse_reviewer_score(text) == 5.0


class TestParseDimensionScores:
    """Tests for _parse_dimension_scores()."""

    def test_parses_multiple_dimensions(self) -> None:
        text = """SCORES:
- thesis_clarity: 8/10
- section_flow: 7/10
- depth_calibration: 9/10
OVERALL: 8.0/10
"""
        scores = _parse_dimension_scores(text)
        assert scores == [8.0, 7.0, 9.0]

    def test_empty_on_no_scores_block(self) -> None:
        text = "Just some text without scores."
        assert _parse_dimension_scores(text) == []


class TestComputeOverallScore:
    """Tests for _compute_overall_score()."""

    def test_weighted_average(self) -> None:
        reviews = {
            "architect": "OVERALL: 8.0/10",
            "content": "OVERALL: 7.0/10",
            "formatting": "OVERALL: 9.0/10",
        }
        score, passes = _compute_overall_score(reviews)
        # 8.0*0.35 + 7.0*0.40 + 9.0*0.25 = 2.8 + 2.8 + 2.25 = 7.85
        assert round(score, 2) == 7.85
        assert passes is True

    def test_fails_below_threshold(self) -> None:
        reviews = {
            "architect": "OVERALL: 5.0/10",
            "content": "OVERALL: 5.0/10",
            "formatting": "OVERALL: 5.0/10",
        }
        score, passes = _compute_overall_score(reviews)
        assert score == 5.0
        assert passes is False

    def test_fails_on_low_dimension(self) -> None:
        """Even if overall >= 7.0, a single dimension below 5.0 fails."""
        reviews = {
            "architect": "SCORES:\n- thesis_clarity: 4/10\n- section_flow: 10/10\nOVERALL: 8.0/10",
            "content": "OVERALL: 8.0/10",
            "formatting": "OVERALL: 8.0/10",
        }
        score, passes = _compute_overall_score(reviews)
        assert score >= 7.0  # overall is high
        assert passes is False  # but dimension 4.0 < 5.0 blocks

    def test_passes_on_exact_threshold(self) -> None:
        reviews = {
            "architect": "OVERALL: 7.0/10",
            "content": "OVERALL: 7.0/10",
            "formatting": "OVERALL: 7.0/10",
        }
        score, passes = _compute_overall_score(reviews)
        assert score == 7.0
        assert passes is True


# ---------------------------------------------------------------------------
# Draft finalization
# ---------------------------------------------------------------------------


class TestFinalizeDraft:
    """Tests for _finalize_draft()."""

    def test_strips_changelog(self) -> None:
        draft = """<!-- CHANGELOG — will be removed during finalization
v2 changes:
- Structure: Improved opening hook
-->

## What is MyProject?

Content here.
"""
        result = _finalize_draft(draft)
        assert "CHANGELOG" not in result
        assert "## What is MyProject?" in result
        assert "Content here." in result

    def test_strips_preamble(self) -> None:
        draft = """Here is the revised blog post:

## What is MyProject?

Content here.
"""
        result = _finalize_draft(draft)
        assert result.startswith("## What is MyProject?")
        assert "Here is the revised" not in result

    def test_clean_draft_unchanged(self) -> None:
        draft = "## What is MyProject?\n\nContent here.\n"
        result = _finalize_draft(draft)
        assert result == draft


# ---------------------------------------------------------------------------
# Markdown to HTML
# ---------------------------------------------------------------------------


class TestMarkdownToHtml:
    """Tests for _markdown_to_html()."""

    def test_headings(self) -> None:
        md = "## My Heading\n\n### Sub heading\n"
        html = _markdown_to_html(md)
        assert "<h2>My Heading</h2>" in html
        assert "<h3>Sub heading</h3>" in html

    def test_code_block(self) -> None:
        md = "```yaml\napiVersion: v1\nkind: Service\n```\n"
        html = _markdown_to_html(md)
        assert '<pre><code class="language-yaml">' in html
        assert "apiVersion: v1" in html

    def test_paragraphs(self) -> None:
        md = "This is a paragraph.\n\nAnother paragraph.\n"
        html = _markdown_to_html(md)
        assert "<p>This is a paragraph.</p>" in html
        assert "<p>Another paragraph.</p>" in html

    def test_list_items(self) -> None:
        md = "- Item one\n- Item two\n"
        html = _markdown_to_html(md)
        assert "<ul>" in html
        assert "<li>Item one</li>" in html
        assert "<li>Item two</li>" in html
        assert "</ul>" in html

    def test_image_placeholder_divs_closed(self) -> None:
        """Image placeholder blocks should produce matched open/close divs."""
        md = """Some text before.

--------------------
**[Image Placeholder 1: Architecture diagram]**

**Placement rationale**: Shows the system architecture

**Alt text**: Architecture diagram
--------------------

## Next section

More text here.
"""
        html = _markdown_to_html(md)
        open_count = html.count('<div class="image-placeholder">')
        close_count = html.count("</div>")
        assert open_count == 1, f"Expected 1 open div, got {open_count}"
        assert close_count == 1, f"Expected 1 close div, got {close_count}"
        # Content after the placeholder should NOT be inside the div
        assert "</div>\n<h2>Next section</h2>" in html

    def test_multiple_image_placeholders(self) -> None:
        """Multiple image placeholder blocks should each be self-contained."""
        md = """--------------------
**[Image Placeholder 1: First]**
--------------------

Some text between.

--------------------
**[Image Placeholder 2: Second]**
--------------------
"""
        html = _markdown_to_html(md)
        open_count = html.count('<div class="image-placeholder">')
        close_count = html.count("</div>")
        assert open_count == 2
        assert close_count == 2

    def test_unclosed_image_placeholder(self) -> None:
        """An image placeholder missing its closing separator gets auto-closed."""
        md = """--------------------
**[Image Placeholder 1: Missing close]**

Some content inside.
"""
        html = _markdown_to_html(md)
        assert html.count('<div class="image-placeholder">') == 1
        assert html.count("</div>") == 1


class TestInlineFormat:
    """Tests for _inline_format()."""

    def test_bold(self) -> None:
        assert "<strong>bold</strong>" in _inline_format("This is **bold** text")

    def test_italic(self) -> None:
        assert "<em>italic</em>" in _inline_format("This is *italic* text")

    def test_code(self) -> None:
        assert "<code>code</code>" in _inline_format("This is `code` text")

    def test_link(self) -> None:
        result = _inline_format("Click [here](https://example.com)")
        assert '<a href="https://example.com">here</a>' in result


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TestRouteAfterPocReport:
    """Tests for route_after_poc_report()."""

    def test_routes_to_blog_on_majority_pass(self) -> None:
        state: PoCState = {
            "poc_results": [
                {"scenario_name": "a", "status": "pass"},
                {"scenario_name": "b", "status": "pass"},
                {"scenario_name": "c", "status": "fail"},
            ],
        }  # type: ignore[typeddict-item]
        assert route_after_poc_report(state) == "blog_post"

    def test_routes_to_end_on_majority_fail(self) -> None:
        state: PoCState = {
            "poc_results": [
                {"scenario_name": "a", "status": "fail"},
                {"scenario_name": "b", "status": "fail"},
                {"scenario_name": "c", "status": "pass"},
            ],
        }  # type: ignore[typeddict-item]
        assert route_after_poc_report(state) == "end"

    def test_routes_to_end_on_no_results(self) -> None:
        state: PoCState = {}  # type: ignore[typeddict-item]
        assert route_after_poc_report(state) == "end"

    def test_routes_to_end_on_empty_results(self) -> None:
        state: PoCState = {"poc_results": []}  # type: ignore[typeddict-item]
        assert route_after_poc_report(state) == "end"

    def test_routes_to_blog_on_all_pass(self) -> None:
        state: PoCState = {
            "poc_results": [
                {"scenario_name": "a", "status": "pass"},
                {"scenario_name": "b", "status": "pass"},
            ],
        }  # type: ignore[typeddict-item]
        assert route_after_poc_report(state) == "blog_post"

    def test_routes_to_end_on_even_split(self) -> None:
        """50/50 is NOT a majority — need strictly more than half."""
        state: PoCState = {
            "poc_results": [
                {"scenario_name": "a", "status": "pass"},
                {"scenario_name": "b", "status": "fail"},
            ],
        }  # type: ignore[typeddict-item]
        assert route_after_poc_report(state) == "end"

    def test_routes_to_blog_on_single_pass(self) -> None:
        """Single scenario that passes — 1/1 is a majority."""
        state: PoCState = {
            "poc_results": [
                {"scenario_name": "a", "status": "pass"},
            ],
        }  # type: ignore[typeddict-item]
        assert route_after_poc_report(state) == "blog_post"


# ---------------------------------------------------------------------------
# URL credential stripping
# ---------------------------------------------------------------------------


class TestStripUrlCredentials:
    """Tests for _strip_url_credentials()."""

    def test_strips_github_token(self) -> None:
        url = "https://ghp_abc123xyz@github.com/org/repo.git"
        assert _strip_url_credentials(url) == "https://github.com/org/repo.git"

    def test_strips_gitlab_token(self) -> None:
        url = "https://oauth2:glpat-abc123@gitlab.example.com/group/repo.git"
        assert _strip_url_credentials(url) == "https://gitlab.example.com/group/repo.git"

    def test_preserves_clean_url(self) -> None:
        url = "https://github.com/org/repo"
        assert _strip_url_credentials(url) == "https://github.com/org/repo"

    def test_handles_empty_string(self) -> None:
        assert _strip_url_credentials("") == ""

    def test_preserves_port(self) -> None:
        url = "https://token@gitlab.example.com:8929/group/repo.git"
        assert _strip_url_credentials(url) == "https://gitlab.example.com:8929/group/repo.git"

    def test_strips_user_password(self) -> None:
        url = "https://user:password@host.com/path"
        assert _strip_url_credentials(url) == "https://host.com/path"
