"""Tests for OpenCode skill file validation.

Validates that all skill files:
- Exist in the expected locations
- Have valid YAML frontmatter with required fields
- Reference files that actually exist
- Follow naming conventions
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parent.parent / ".opencode" / "skills"


class TestSkillDiscovery:
    """Test that all expected skill directories exist."""

    def test_run_poc_skill_exists(self) -> None:
        assert (SKILLS_DIR / "run-poc" / "SKILL.md").exists()

    def test_run_sheet_skill_exists(self) -> None:
        assert (SKILLS_DIR / "run-sheet" / "SKILL.md").exists()

    def test_blog_create_skill_exists(self) -> None:
        assert (SKILLS_DIR / "blog-create" / "SKILL.md").exists()


class TestSkillFrontmatter:
    """Test that skill files have valid frontmatter."""

    @pytest.fixture(params=["run-poc", "run-sheet", "blog-create"])
    def skill_content(self, request: pytest.FixtureRequest) -> tuple[str, str]:
        skill_name = request.param
        path = SKILLS_DIR / skill_name / "SKILL.md"
        return skill_name, path.read_text(encoding="utf-8")

    def test_has_frontmatter(self, skill_content: tuple[str, str]) -> None:
        name, content = skill_content
        assert content.startswith("---"), f"Skill {name} must start with YAML frontmatter (---)"
        # Find closing ---
        second_dash = content.index("---", 3)
        assert second_dash > 3, f"Skill {name} must have closing --- for frontmatter"

    def test_frontmatter_has_name(self, skill_content: tuple[str, str]) -> None:
        name, content = skill_content
        frontmatter = content[: content.index("---", 3)]
        assert "name:" in frontmatter, f"Skill {name} frontmatter must include 'name:'"

    def test_frontmatter_has_description(self, skill_content: tuple[str, str]) -> None:
        name, content = skill_content
        frontmatter = content[: content.index("---", 3)]
        assert "description:" in frontmatter, (
            f"Skill {name} frontmatter must include 'description:'"
        )

    def test_frontmatter_name_matches_directory(self, skill_content: tuple[str, str]) -> None:
        name, content = skill_content
        frontmatter = content[: content.index("---", 3)]
        # Extract name value
        match = re.search(r"name:\s*(\S+)", frontmatter)
        assert match, f"Could not parse name from frontmatter of {name}"
        assert match.group(1) == name, (
            f"Skill name '{match.group(1)}' doesn't match directory '{name}'"
        )

    def test_name_follows_convention(self, skill_content: tuple[str, str]) -> None:
        name, _ = skill_content
        assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name), (
            f"Skill name '{name}' doesn't match naming convention"
        )


class TestRunPocReferences:
    """Test that run-poc skill references exist."""

    EXPECTED_REFS = [
        "intake.md",
        "poc-plan.md",
        "containerize.md",
        "deploy.md",
        "poc-execute.md",
        "poc-report.md",
        "state-schema.md",
        "retry-strategy.md",
        "error-triage.md",
        "ubi-dockerfile-rules.md",
    ]

    @pytest.fixture(params=EXPECTED_REFS)
    def ref_name(self, request: pytest.FixtureRequest) -> str:
        return request.param

    def test_reference_file_exists(self, ref_name: str) -> None:
        ref_path = SKILLS_DIR / "run-poc" / "references" / ref_name
        assert ref_path.exists(), f"Missing reference: {ref_path}"

    def test_reference_file_not_empty(self, ref_name: str) -> None:
        ref_path = SKILLS_DIR / "run-poc" / "references" / ref_name
        content = ref_path.read_text(encoding="utf-8")
        assert len(content) > 100, f"Reference {ref_name} seems too short ({len(content)} chars)"


class TestRunSheetReferences:
    """Test that run-sheet skill references exist."""

    def test_prefilter_reference_exists(self) -> None:
        assert (SKILLS_DIR / "run-sheet" / "references" / "prefilter.md").exists()


class TestBlogCreateReferences:
    """Test that blog-create skill references and assets exist."""

    EXPECTED_REFS = [
        "scoring.md",
        "reviewer-architect.md",
        "reviewer-content.md",
        "reviewer-formatting.md",
        "reviewer-image.md",
        "html-preview-guide.md",
    ]

    @pytest.fixture(params=EXPECTED_REFS)
    def ref_name(self, request: pytest.FixtureRequest) -> str:
        return request.param

    def test_reference_file_exists(self, ref_name: str) -> None:
        ref_path = SKILLS_DIR / "blog-create" / "references" / ref_name
        assert ref_path.exists(), f"Missing reference: {ref_path}"

    def test_html_template_exists(self) -> None:
        template = SKILLS_DIR / "blog-create" / "assets" / "blog-template.html"
        assert template.exists()

    def test_html_template_has_placeholders(self) -> None:
        template = SKILLS_DIR / "blog-create" / "assets" / "blog-template.html"
        content = template.read_text(encoding="utf-8")
        assert "{{TITLE}}" in content
        assert "{{BODY_CONTENT}}" in content
        assert "{{AUTHOR}}" in content


class TestSkillContentQuality:
    """Test that skill content is well-structured."""

    def test_run_poc_has_all_phases(self) -> None:
        content = (SKILLS_DIR / "run-poc" / "SKILL.md").read_text(encoding="utf-8")
        for phase in [
            "Phase 1: Intake",
            "Phase 2: Evaluate",
            "Phase 3: Fork",
            "Phase 4: PoC Plan",
            "Phase 5: Containerize",
            "Phase 6: Build",
            "Phase 7: Deploy",
            "Phase 8: Apply",
            "Phase 9: PoC Execute",
            "Phase 10: PoC Report",
            "Phase 11: Blog Post",
        ]:
            assert phase in content, f"Missing phase: {phase}"

    def test_run_poc_references_cli_tools(self) -> None:
        content = (SKILLS_DIR / "run-poc" / "SKILL.md").read_text(encoding="utf-8")
        assert "python -m autopoc.cli_tools" in content

    def test_state_schema_has_all_phases(self) -> None:
        content = (SKILLS_DIR / "run-poc" / "references" / "state-schema.md").read_text(
            encoding="utf-8"
        )
        for section in [
            "intake:",
            "evaluate:",
            "fork:",
            "poc_plan:",
            "containerize:",
            "build:",
            "deploy:",
            "apply:",
            "poc_execute:",
            "poc_report:",
        ]:
            assert section in content, f"Missing state section: {section}"

    def test_retry_strategy_has_all_loops(self) -> None:
        content = (SKILLS_DIR / "run-poc" / "references" / "retry-strategy.md").read_text(
            encoding="utf-8"
        )
        assert "Build Retry Loop" in content
        assert "Deploy Retry Loop" in content
        assert "Container Fix" in content

    def test_run_poc_has_mandatory_phase_classification(self) -> None:
        content = (SKILLS_DIR / "run-poc" / "SKILL.md").read_text(encoding="utf-8")
        assert "MANDATORY" in content
        assert "NON-BLOCKING" in content
        assert "Never hallucinate success" in content

    def test_poc_report_mentions_mermaid(self) -> None:
        content = (SKILLS_DIR / "run-poc" / "references" / "poc-report.md").read_text(
            encoding="utf-8"
        )
        assert "mermaid" in content.lower()

    def test_blog_create_mentions_mermaid(self) -> None:
        content = (SKILLS_DIR / "blog-create" / "SKILL.md").read_text(encoding="utf-8")
        assert "mermaid" in content.lower()

    def test_html_template_has_mermaid_js(self) -> None:
        content = (SKILLS_DIR / "blog-create" / "assets" / "blog-template.html").read_text(
            encoding="utf-8"
        )
        assert "mermaid" in content
        assert "cdn.jsdelivr.net" in content

    def test_html_preview_guide_has_mermaid_section(self) -> None:
        content = (SKILLS_DIR / "blog-create" / "references" / "html-preview-guide.md").read_text(
            encoding="utf-8"
        )
        assert "Mermaid" in content
