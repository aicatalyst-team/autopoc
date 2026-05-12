"""Blog post agent — generates a developer blog post from PoC results.

Runs after poc_report when a majority of test scenarios pass. Produces
a developer-style blog post with a 3-reviewer autonomous review loop
(architect, content, formatting), plus SEO metadata and an HTML preview.

Non-agentic: uses direct LLM calls (no ReAct, no tools). The review
loop runs up to 3 iterations with score-based exit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from autopoc.llm import create_llm, strip_think_tags
from autopoc.state import PoCPhase, PoCState
from autopoc.tools.git_tools import commit_to_artifacts_branch

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Review loop configuration
MAX_ITERATIONS = 3
PASS_OVERALL = 7.0
PASS_MIN_DIMENSION = 5.0

# Reviewer weights
REVIEWER_WEIGHTS = {
    "architect": 0.35,
    "content": 0.40,
    "formatting": 0.25,
}


# ---------------------------------------------------------------------------
# Helpers: build the user message from pipeline state
# ---------------------------------------------------------------------------


def _strip_url_credentials(url: str) -> str:
    """Remove embedded credentials from a URL.

    Git clone URLs often contain tokens (e.g., https://ghp_xxx@github.com/...).
    These must be stripped before passing to the LLM or writing to artifacts,
    otherwise GitHub push protection will reject the commit.
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            # Rebuild without credentials
            clean = parsed._replace(
                netloc=parsed.hostname + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(clean)
    except Exception:
        pass
    # Fallback: regex strip for token patterns
    return re.sub(r"https?://[^@]+@", lambda m: m.group(0).split("//")[0] + "//", url)


def _build_blog_context(state: PoCState) -> str:
    """Build the context message for blog draft generation from pipeline state."""
    parts: list[str] = []
    project_name = state.get("project_name", "unknown")

    parts.append("Write a developer blog post about the following PoC project.\n")
    parts.append(f"**Project name:** {project_name}")
    parts.append(f"**Source URL:** {_strip_url_credentials(state.get('source_repo_url', ''))}")
    fork_url = _strip_url_credentials(
        state.get("fork_repo_url") or state.get("gitlab_repo_url") or ""
    )
    if fork_url:
        parts.append(f"**Fork URL:** {fork_url}")
    parts.append("")

    # Repo summary
    repo_summary = state.get("repo_summary", "")
    if repo_summary:
        parts.append(f"## Repository Summary\n{repo_summary}\n")

    # Components
    components = state.get("components", [])
    if components:
        parts.append("## Components\n")
        parts.append("| Name | Language | Build System | ML Workload | Port |")
        parts.append("|------|----------|-------------|-------------|------|")
        for comp in components:
            parts.append(
                f"| {comp.get('name', '?')} | {comp.get('language', '?')} "
                f"| {comp.get('build_system', '?')} "
                f"| {'Yes' if comp.get('is_ml_workload') else 'No'} "
                f"| {comp.get('port', '-')} |"
            )
        parts.append("")

    # PoC type and plan
    poc_type = state.get("poc_type", "")
    if poc_type:
        parts.append(f"**PoC Type:** {poc_type}\n")

    poc_plan = state.get("poc_plan", "")
    if poc_plan:
        parts.append(f"## PoC Plan\n{poc_plan[:3000]}\n")

    # Infrastructure
    poc_infrastructure = state.get("poc_infrastructure", {})
    if poc_infrastructure:
        parts.append("## Infrastructure Requirements")
        parts.append(f"```json\n{json.dumps(poc_infrastructure, indent=2)}\n```\n")

    # RHOAI evaluation
    rhoai_eval = state.get("rhoai_evaluation", {})
    if rhoai_eval:
        parts.append("## RHOAI Fitness Evaluation")
        total = rhoai_eval.get("total_score", 0)
        max_score = rhoai_eval.get("max_possible_score", 100)
        parts.append(f"**Score:** {total}/{max_score}")
        areas = rhoai_eval.get("strategy_areas", [])
        if areas:
            parts.append(f"**Strategy areas:** {', '.join(areas)}")
        rationale = rhoai_eval.get("rationale", "")
        if rationale:
            parts.append(f"**Assessment:** {rationale}")
        parts.append("")

    # Built images
    built_images = state.get("built_images", [])
    if built_images:
        parts.append("## Built Images")
        for img in built_images:
            parts.append(f"- `{img}`")
        parts.append("")

    # Routes
    routes = state.get("routes", [])
    if routes:
        parts.append("## Service URLs")
        for route in routes:
            parts.append(f"- `{route}`")
        parts.append("")

    # Test results
    poc_results = state.get("poc_results", [])
    if poc_results:
        parts.append("## Test Results\n")
        parts.append("| Scenario | Status | Duration |")
        parts.append("|----------|--------|----------|")
        for r in poc_results:
            status = r.get("status", "unknown").upper()
            parts.append(
                f"| {r.get('scenario_name', '?')} | {status} "
                f"| {r.get('duration_seconds', 0):.1f}s |"
            )
        total = len(poc_results)
        passed = sum(1 for r in poc_results if r.get("status") == "pass")
        parts.append(f"\n**Summary:** {passed}/{total} passed\n")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Review scoring
# ---------------------------------------------------------------------------

_SCORE_RE = re.compile(r"OVERALL:\s*([\d.]+)/10")
_DIMENSION_RE = re.compile(r"-\s*\w+:\s*([\d.]+)/10")


def _parse_reviewer_score(review_text: str) -> float:
    """Extract the OVERALL score from a reviewer's output.

    Returns the score (1-10), or 5.0 as a fallback if parsing fails.
    """
    match = _SCORE_RE.search(review_text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    logger.warning("Could not parse OVERALL score from reviewer output, defaulting to 5.0")
    return 5.0


def _parse_dimension_scores(review_text: str) -> list[float]:
    """Extract individual dimension scores from a reviewer's SCORES block."""
    scores = []
    in_scores = False
    for line in review_text.splitlines():
        if line.strip().startswith("SCORES:"):
            in_scores = True
            continue
        if in_scores:
            if line.strip().startswith("OVERALL:"):
                break
            m = _DIMENSION_RE.match(line.strip())
            if m:
                try:
                    scores.append(float(m.group(1)))
                except ValueError:
                    pass
            elif line.strip() and not line.strip().startswith("-"):
                break
    return scores


def _compute_overall_score(reviews: dict[str, str]) -> tuple[float, bool]:
    """Compute the weighted overall score and whether it passes.

    Args:
        reviews: Mapping of reviewer name to review text.

    Returns:
        Tuple of (weighted_score, passes).
    """
    weighted_sum = 0.0
    all_dimensions: list[float] = []

    for name, text in reviews.items():
        score = _parse_reviewer_score(text)
        weight = REVIEWER_WEIGHTS.get(name, 0.33)
        weighted_sum += score * weight

        dims = _parse_dimension_scores(text)
        all_dimensions.extend(dims)

    passes = weighted_sum >= PASS_OVERALL
    if all_dimensions:
        min_dim = min(all_dimensions)
        if min_dim < PASS_MIN_DIMENSION:
            passes = False

    return weighted_sum, passes


# ---------------------------------------------------------------------------
# SEO generation
# ---------------------------------------------------------------------------


def _build_seo_prompt() -> str:
    return """Generate SEO metadata for the blog post provided below.

Output EXACTLY this format (no preamble):

# SEO Metadata

- **Meta Title:** {50-60 chars, keywords front-loaded}
- **Meta Description:** {150-160 chars, action-oriented}
- **Primary Keywords:** {3-5 comma-separated keywords}
- **Secondary Keywords:** {3-5 comma-separated keywords}
- **Suggested Slug:** {url-slug-format}
- **Internal Links:** {2-3 relevant links to OpenShift AI / ODH documentation}
"""


# ---------------------------------------------------------------------------
# HTML preview
# ---------------------------------------------------------------------------


def _markdown_to_html(md: str) -> str:
    """Simple markdown-to-HTML conversion for the preview.

    Handles headings, paragraphs, code blocks, bold, italic, lists, links,
    tables, and image placeholders. Not a full markdown parser — just enough
    for a readable preview.
    """
    lines = md.splitlines()
    html_lines: list[str] = []
    in_code_block = False
    in_list = False
    in_table = False
    in_image_placeholder = False

    for line in lines:
        stripped = line.strip()

        # Code blocks
        if stripped.startswith("```"):
            if in_code_block:
                html_lines.append("</code></pre>")
                in_code_block = False
            else:
                lang = stripped[3:].strip()
                html_lines.append(f'<pre><code class="language-{lang}">')
                in_code_block = True
            continue
        if in_code_block:
            html_lines.append(line.replace("<", "&lt;").replace(">", "&gt;"))
            continue

        # Image placeholders — toggle on each ---- separator (>= 10 dashes)
        if stripped.startswith("----") and len(stripped) >= 10 and all(c == "-" for c in stripped):
            if in_image_placeholder:
                html_lines.append("</div>")
                in_image_placeholder = False
            else:
                html_lines.append('<div class="image-placeholder">')
                in_image_placeholder = True
            continue

        # Tables
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                html_lines.append("<table>")
                in_table = True
            if all(c in "-| " for c in stripped):
                continue  # separator row
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            tag = (
                "th"
                if not any("td" in line for line in html_lines[-5:] if "<t" in line)
                and html_lines[-1] == "<table>"
                else "td"
            )
            row = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
            continue
        if in_table and not stripped.startswith("|"):
            html_lines.append("</table>")
            in_table = False

        # Close list if we're no longer in one
        if in_list and not stripped.startswith("- ") and not stripped.startswith("* "):
            html_lines.append("</ul>")
            in_list = False

        # Headings
        if stripped.startswith("#### "):
            html_lines.append(f"<h4>{stripped[5:]}</h4>")
            continue
        if stripped.startswith("### "):
            html_lines.append(f"<h3>{stripped[4:]}</h3>")
            continue
        if stripped.startswith("## "):
            html_lines.append(f"<h2>{stripped[3:]}</h2>")
            continue
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{stripped[2:]}</h1>")
            continue

        # Lists
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = stripped[2:]
            content = _inline_format(content)
            html_lines.append(f"<li>{content}</li>")
            continue

        # Empty lines
        if not stripped:
            continue

        # Paragraphs
        content = _inline_format(stripped)
        html_lines.append(f"<p>{content}</p>")

    # Close any open elements
    if in_code_block:
        html_lines.append("</code></pre>")
    if in_list:
        html_lines.append("</ul>")
    if in_table:
        html_lines.append("</table>")
    if in_image_placeholder:
        html_lines.append("</div>")

    return "\n".join(html_lines)


def _inline_format(text: str) -> str:
    """Apply inline markdown formatting: bold, italic, code, links."""
    # Code (backticks) — do first to avoid interference
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _render_html_preview(
    draft: str,
    seo_text: str,
    project_name: str,
    poc_plan_summary: str,
) -> str:
    """Render the HTML preview by substituting template placeholders."""
    template_path = TEMPLATES_DIR / "blog-preview.html"
    template = template_path.read_text(encoding="utf-8")

    # Extract meta description from SEO
    meta_desc = ""
    for line in seo_text.splitlines():
        if "Meta Description:" in line:
            meta_desc = line.split(":", 1)[-1].strip().strip("*").strip()
            break

    # Word count → read time
    word_count = len(draft.split())
    read_time = f"{math.ceil(word_count / 200)} min read"

    body_html = _markdown_to_html(draft)
    now = datetime.now(tz=timezone.utc)

    html = template.replace("{{TITLE}}", f"Deploying {project_name} on OpenShift AI")
    html = html.replace("{{SUBTITLE}}", poc_plan_summary or "A proof-of-concept deployment")
    html = html.replace("{{META_DESCRIPTION}}", meta_desc)
    html = html.replace("{{AUTHOR}}", "AutoPoC")
    html = html.replace("{{DATE}}", now.strftime("%B %Y"))
    html = html.replace("{{READ_TIME}}", read_time)
    html = html.replace("{{BODY_CONTENT}}", body_html)

    return html


# ---------------------------------------------------------------------------
# Strip preamble / changelog for finalization
# ---------------------------------------------------------------------------


def _finalize_draft(draft: str) -> str:
    """Produce the final clean draft: strip changelog comments and preamble."""
    # Remove changelog HTML comments
    clean = re.sub(r"<!--\s*CHANGELOG.*?-->", "", draft, flags=re.DOTALL).strip()

    # Strip any LLM preamble before first heading
    lines = clean.split("\n")
    for i, line in enumerate(lines):
        if line.strip().startswith("#"):
            clean = "\n".join(lines[i:])
            break

    return clean.strip() + "\n"


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------


async def blog_post_agent(
    state: PoCState,
    *,
    llm: BaseChatModel | None = None,
) -> dict:
    """Generate a developer blog post from PoC results.

    Orchestrates:
    1. Draft generation (one-shot LLM)
    2. 3-reviewer parallel scoring (3 concurrent LLM calls)
    3. Revision loop (up to MAX_ITERATIONS)
    4. Finalization (SEO + HTML preview)

    Non-blocking: failures return empty paths, pipeline continues.
    """
    project_name = state.get("project_name", "unknown")
    clone_path = state.get("local_clone_path", "")

    logger.info("=== Blog Post Generation for %s ===", project_name)

    if llm is None:
        llm = create_llm()

    blog_post_path = str(Path(clone_path or ".") / "blog-post.md")
    blog_seo_path = str(Path(clone_path or ".") / "blog-seo.md")
    blog_preview_path = str(Path(clone_path or ".") / "blog-preview.html")

    try:
        # Load prompts
        draft_prompt = (PROMPTS_DIR / "blog_post.md").read_text(encoding="utf-8")
        reviewer_prompts = {
            "architect": (PROMPTS_DIR / "blog_review_architect.md").read_text(encoding="utf-8"),
            "content": (PROMPTS_DIR / "blog_review_content.md").read_text(encoding="utf-8"),
            "formatting": (PROMPTS_DIR / "blog_review_formatting.md").read_text(encoding="utf-8"),
        }

        blog_context = _build_blog_context(state)

        # === Phase 1: Generate initial draft ===
        logger.info("Generating initial blog draft (v1)")
        response = await llm.ainvoke(
            [
                SystemMessage(content=draft_prompt),
                HumanMessage(content=blog_context),
            ]
        )
        current_draft = strip_think_tags(
            response.content
            if isinstance(response.content, str)
            else "".join(
                p["text"] if isinstance(p, dict) and "text" in p else str(p)
                for p in response.content
            )
        )

        best_draft = current_draft
        best_score = 0.0

        # === Phase 2: Review loop ===
        for iteration in range(1, MAX_ITERATIONS + 1):
            logger.info("Review iteration %d/%d", iteration, MAX_ITERATIONS)

            # Run 3 reviewers in parallel
            review_tasks = []
            for name, prompt in reviewer_prompts.items():
                review_msg = f"## Blog Post Draft\n\n{current_draft}"
                if name == "content":
                    # Content reviewer also gets the original PoC data
                    review_msg += f"\n\n## Original PoC Data\n\n{blog_context}"

                review_tasks.append(
                    llm.ainvoke(
                        [
                            SystemMessage(content=prompt),
                            HumanMessage(content=review_msg),
                        ]
                    )
                )

            review_responses = await asyncio.gather(*review_tasks, return_exceptions=True)

            reviews: dict[str, str] = {}
            reviewer_names = list(reviewer_prompts.keys())
            for i, resp in enumerate(review_responses):
                name = reviewer_names[i]
                if isinstance(resp, Exception):
                    logger.warning("Reviewer %s failed: %s", name, resp)
                    reviews[name] = f"OVERALL: 5.0/10\n\nReviewer error: {resp}"
                else:
                    text = resp.content if isinstance(resp.content, str) else str(resp.content)
                    reviews[name] = strip_think_tags(text)

            # Compute score
            overall_score, passes = _compute_overall_score(reviews)
            logger.info(
                "Iteration %d score: %.1f/10 (pass threshold: %.1f, passes: %s)",
                iteration,
                overall_score,
                PASS_OVERALL,
                passes,
            )

            # Track best draft
            if overall_score > best_score:
                best_score = overall_score
                best_draft = current_draft

            if passes:
                logger.info(
                    "Blog draft passed review at iteration %d (score: %.1f)",
                    iteration,
                    overall_score,
                )
                break

            if iteration >= MAX_ITERATIONS:
                logger.info(
                    "Max iterations reached (%d). Using best draft (score: %.1f)",
                    MAX_ITERATIONS,
                    best_score,
                )
                break

            # === Revise ===
            logger.info("Revising draft (v%d → v%d)", iteration, iteration + 1)
            revision_feedback = "\n\n".join(
                f"### {name.title()} Review\n{text}" for name, text in reviews.items()
            )

            response = await llm.ainvoke(
                [
                    SystemMessage(content=draft_prompt),
                    HumanMessage(
                        content=(
                            f"{blog_context}\n\n"
                            f"## Previous Draft (v{iteration})\n\n{current_draft}\n\n"
                            f"## Reviewer Feedback\n\n{revision_feedback}\n\n"
                            f"Please produce a COMPLETE revised blog post (v{iteration + 1}) "
                            f"incorporating the feedback above. Include a changelog comment at the top."
                        )
                    ),
                ]
            )
            current_draft = strip_think_tags(
                response.content
                if isinstance(response.content, str)
                else "".join(
                    p["text"] if isinstance(p, dict) and "text" in p else str(p)
                    for p in response.content
                )
            )

        # === Phase 3: Finalize ===
        final_draft = _finalize_draft(best_draft)

        # Generate SEO metadata
        logger.info("Generating SEO metadata")
        seo_response = await llm.ainvoke(
            [
                SystemMessage(content=_build_seo_prompt()),
                HumanMessage(content=final_draft),
            ]
        )
        seo_text = strip_think_tags(
            seo_response.content
            if isinstance(seo_response.content, str)
            else str(seo_response.content)
        )

        # Generate HTML preview
        logger.info("Generating HTML preview")
        subtitle = state.get("repo_summary", "") or "A proof-of-concept deployment"
        # Truncate to first sentence if it's too long for a subtitle
        if len(subtitle) > 200:
            dot = subtitle.find(".", 0, 200)
            subtitle = subtitle[: dot + 1] if dot > 0 else subtitle[:200] + "..."
        html_preview = _render_html_preview(
            final_draft,
            seo_text,
            project_name,
            subtitle,
        )

        # === Write artifacts ===
        Path(blog_post_path).parent.mkdir(parents=True, exist_ok=True)

        Path(blog_post_path).write_text(final_draft, encoding="utf-8")
        logger.info("Blog post written to %s (%d words)", blog_post_path, len(final_draft.split()))

        Path(blog_seo_path).write_text(seo_text, encoding="utf-8")
        logger.info("SEO metadata written to %s", blog_seo_path)

        Path(blog_preview_path).write_text(html_preview, encoding="utf-8")
        logger.info("HTML preview written to %s", blog_preview_path)

        # Commit to artifacts branch
        if clone_path:
            commit_to_artifacts_branch(
                clone_path,
                files=["blog-post.md", "blog-seo.md", "blog-preview.html"],
                message="Add blog post, SEO metadata, and HTML preview",
            )

        return {
            "current_phase": PoCPhase.BLOG_POST,
            "blog_post_path": blog_post_path,
            "blog_seo_path": blog_seo_path,
            "blog_preview_path": blog_preview_path,
        }

    except Exception as e:
        logger.error("Blog post generation failed: %s", e, exc_info=True)
        return {
            "current_phase": PoCPhase.BLOG_POST,
            "blog_post_path": "",
            "blog_seo_path": "",
            "blog_preview_path": "",
            # Intentionally NOT setting error — blog failure is non-blocking
        }
