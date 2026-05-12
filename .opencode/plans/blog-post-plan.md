# Phase 15: Blog Post Generation

> Detailed implementation plan for automated developer blog post generation
> from PoC results. Runs after `poc_report`, gated on PoC success (majority
> of test scenarios pass). Uses a 3-reviewer autonomous review loop to
> produce a polished draft with SEO metadata and an HTML preview.

---

## Problem Statement

After a successful PoC run, the pipeline produces a technical report
(`poc-report.md`) aimed at internal stakeholders. But we also want a
**developer blog post** that tells the story of the PoC — what the project
does, why it matters for OpenShift AI, how we deployed it, and what we
found. This post can be published (after human editing) to showcase the
platform's capabilities.

Currently, someone has to manually write this post from the report data.
This phase automates the first draft.

---

## Overview

### Pipeline Position

```
... → poc_execute → poc_report → blog_post → END
                                  ↑
                                  only if majority of test scenarios pass
```

The `blog_post` node is **conditional** — it only runs when the PoC was
successful enough to be worth writing about. It is also **non-blocking** —
if blog generation fails, the pipeline still completes successfully (the
report is the primary deliverable).

### Success Gate

The blog post agent runs only when **more than half** of the test scenarios
passed:

```python
passed = sum(1 for r in poc_results if r.get("status") == "pass")
total = len(poc_results)
if passed > total / 2:
    # generate blog post
```

If no test results exist (e.g., `--stop-after poc_report`), the blog node
is skipped.

### Blog Style

**Developer blog** — hands-on, first-person ("We deployed X on OpenShift AI,
here's what happened"). Includes code snippets, YAML fragments, architecture
notes, and concrete results. Aimed at platform engineers and developers
evaluating OpenShift AI.

---

## Architecture: 3-Reviewer Review Loop

```
┌─────────────┐
│ Generate v1 │ ← one-shot LLM call with all PoC data
└──────┬──────┘
       │
  ┌────▼────┐
  │ Review  │ ← 3 parallel LLM calls
  │ (3 sub) │   architect, content, formatting
  └────┬────┘
       │
   Pass?──yes──► Finalize (clean draft + SEO + HTML preview)
       │
      no (and iterations < 3)
       │
  ┌────▼────┐
  │ Revise  │ ← one-shot LLM call with review feedback
  └────┬────┘
       │
       └──► back to Review
```

### Scoring

**Three reviewers**, each scoring 1-10:

| Reviewer | Weight | What It Scores |
|----------|--------|---------------|
| **Architect** | 35% | Thesis clarity, section flow, depth calibration, opening hook, closing strength |
| **Content** | 40% | Technical accuracy (vs PoC data), developer voice, audience alignment, originality, evidence/examples |
| **Formatting** | 25% | Heading hierarchy, code block formatting, CTA placement, image placeholders, word count |

**Overall score:** `(architect * 0.35) + (content * 0.40) + (formatting * 0.25)`

### Pass Criteria

- Overall weighted score >= **7.0**
- No individual reviewer score below **5.0**

### Iteration Controls

- **Max 3 iterations** — no human checkpoints
- If passing after iteration 1, accept immediately (skip remaining iterations)
- If not passing after 3 iterations, accept the **best-scoring** draft
- Each iteration produces `drafts/v{n}.md` and `drafts/reviews/v{n}-{reviewer}.md`

### Revision Priority

When revising, the LLM receives all three reviewer reports and is instructed to:
1. Fix any dimension below 5.0 first (blockers)
2. Address the lowest-scoring reviewer next
3. Apply quick editorial fixes last

---

## Data Model

### New State Fields (`PoCState`)

```python
# --- Blog Post output ---
blog_post_path: str        # Path to blog-post.md (final clean draft)
blog_seo_path: str         # Path to blog-seo.md
blog_preview_path: str     # Path to blog-preview.html
```

### New Phase

```python
class PoCPhase(str, Enum):
    ...
    BLOG_POST = "blog_post"
```

---

## Output Artifacts

### Directory Structure

All blog artifacts are written to the cloned repo directory:

```
{clone_path}/
  blog-post.md          # Final clean draft
  blog-seo.md           # SEO metadata
  blog-preview.html     # HTML preview
```

### Blog Post Format (`blog-post.md`)

Developer blog style with these conventions:

- **No H1 in body** — the H1 is the page title, set separately
- **Sentence case headings** — cascading H2/H3/H4
- **First person plural voice** — "We deployed...", "Here's what we found..."
- **Code blocks** with language tags for commands, YAML, Python
- **Image placeholders** in a consistent format:

```markdown
--------------------
**[Image Placeholder N: <short description>]**

**Placement rationale**: Why an image belongs here

**Image generation prompt**: Detailed prompt for image generation

**Alt text**: Descriptive, accessible alt text
--------------------
```

- **Word count target**: 800-1300 words
- **CTA** linking to the fork repo, container images, and ODH docs

### Blog Structure Template

```markdown
## What is {project_name}?

{Brief description from repo_summary — what the project does,
 what problem it solves, key technologies}

## Why this matters for OpenShift AI

{ODH relevance from RHOAI evaluation — strategy areas,
 platform leverage, audience value}

## Setting up the PoC

{Infrastructure requirements — resource profile, GPU needs,
 vector DB, sidecar containers, env vars.
 What decisions we made and why.}

## Containerizing with UBI

{Dockerfile approach — UBI base image, build system,
 key Dockerfile decisions, any challenges overcome.
 Include a relevant Dockerfile snippet.}

## Deploying to Kubernetes

{Manifest approach — Deployment vs Job, Services,
 PVCs, Secrets. Include a relevant YAML snippet.
 Mention sidecar containers if applicable.}

## Test results

{Scenario results table, key findings,
 what worked and what didn't.
 Include actual numbers (durations, pass/fail counts).}

## What we learned

{Key takeaways, recommendations for production,
 ODH components that would enhance the deployment.
 Honest assessment — what went well and what needs work.}

## Try it yourself

{Links to: fork repo, container images on Quay,
 the full PoC report, ODH documentation.
 Clear next steps for a reader who wants to reproduce this.}
```

### SEO Metadata (`blog-seo.md`)

```markdown
# SEO Metadata

- **Meta Title:** {50-60 chars, keywords front-loaded}
- **Meta Description:** {150-160 chars, action-oriented}
- **Primary Keywords:** {3-5 keywords}
- **Secondary Keywords:** {3-5 keywords}
- **Suggested Slug:** deploying-{project-name}-on-openshift-ai
- **Internal Links:** {links to ODH docs, related content}
```

### HTML Preview (`blog-preview.html`)

A clean, readable HTML page generated from the blog post markdown. Uses
a template with placeholder substitution:

| Placeholder | Source |
|-------------|--------|
| `{{TITLE}}` | First H2 or project name |
| `{{SUBTITLE}}` | PoC plan summary |
| `{{META_DESCRIPTION}}` | From blog-seo.md |
| `{{AUTHOR}}` | "AutoPoC" (default) |
| `{{DATE}}` | Current date |
| `{{READ_TIME}}` | ceil(word_count / 200) |
| `{{BODY_CONTENT}}` | Markdown converted to HTML |

The template is a minimal, clean design — no heavy branding, just good
typography, syntax highlighting for code blocks, and responsive layout.

---

## Implementation

### New Files

| File | Purpose |
|------|---------|
| `src/autopoc/agents/blog_post.py` | Blog post agent — orchestrates generation, review loop, finalization |
| `src/autopoc/prompts/blog_post.md` | System prompt for draft generation |
| `src/autopoc/prompts/blog_review_architect.md` | Architect reviewer rubric |
| `src/autopoc/prompts/blog_review_content.md` | Content reviewer rubric |
| `src/autopoc/prompts/blog_review_formatting.md` | Formatting reviewer rubric |
| `src/autopoc/templates/blog-preview.html` | HTML preview template |
| `tests/test_blog_post.py` | Unit tests |

### Modified Files

| File | Change |
|------|--------|
| `src/autopoc/state.py` | Add `blog_post_path`, `blog_seo_path`, `blog_preview_path`, `BLOG_POST` phase |
| `src/autopoc/graph.py` | Add `blog_post` node, `route_after_poc_report`, update `PIPELINE_PHASES` |
| `src/autopoc/cli.py` | Display blog post path in output |

### Agent Implementation (`blog_post.py`)

The blog post agent is a **single Python function** that orchestrates the
full generate → review → revise loop internally. It is NOT a ReAct agent —
it uses direct LLM calls (like `poc_report`), but with a loop.

```python
async def blog_post_agent(state: PoCState, *, llm: BaseChatModel | None = None) -> dict:
    """Generate a developer blog post from PoC results.

    Orchestrates:
    1. Draft generation (one-shot LLM)
    2. 3-reviewer parallel scoring (3 concurrent LLM calls)
    3. Revision loop (up to 3 iterations)
    4. Finalization (SEO + HTML preview)

    Non-blocking: failures return empty paths, pipeline continues.
    """
```

Key internal functions:

```python
async def _generate_draft(state, llm, system_prompt, revision_feedback=None) -> str:
    """Generate or revise a blog post draft."""

async def _review_draft(draft, llm, reviewer_prompts) -> dict:
    """Run 3 parallel reviewer LLM calls, return scores + feedback."""

def _compute_score(reviews) -> tuple[float, bool]:
    """Compute weighted score, check pass criteria."""

def _generate_seo(draft, llm) -> str:
    """Generate SEO metadata from the blog post."""

def _generate_html_preview(draft, seo, template) -> str:
    """Render HTML preview from markdown draft."""
```

### Graph Changes (`graph.py`)

```python
# New routing function
def route_after_poc_report(state: PoCState) -> str:
    """Route to blog_post if PoC was successful, otherwise END."""
    poc_results = state.get("poc_results", [])
    if not poc_results:
        return "end"

    passed = sum(1 for r in poc_results if r.get("status") == "pass")
    total = len(poc_results)

    if passed > total / 2:
        return "blog_post"

    logger.info(
        "Skipping blog post: only %d/%d scenarios passed (need majority).",
        passed, total,
    )
    return "end"


# In build_graph():
graph.add_node("blog_post", blog_post_agent)

# Replace: graph.add_edge("poc_report", END)
# With:
graph.add_conditional_edges(
    "poc_report",
    route_after_poc_report,
    {"blog_post": "blog_post", "end": END},
)
graph.add_edge("blog_post", END)
```

`PIPELINE_PHASES` updated to include `"blog_post"` after `"poc_report"`.

---

## Task Breakdown

### Task 15.1 — State + Phase Additions

**Files:** `src/autopoc/state.py`

**Work:**
- Add `BLOG_POST = "blog_post"` to `PoCPhase` enum
- Add to `PoCState`:
  - `blog_post_path: str`
  - `blog_seo_path: str`
  - `blog_preview_path: str`

**Acceptance criteria:**
- New fields accessible from `PoCState`
- New phase exists in `PoCPhase`
- No test regressions

---

### Task 15.2 — Blog Draft System Prompt

**Files:** `src/autopoc/prompts/blog_post.md`

**Work:**
- Write the system prompt for blog draft generation
- Include the blog structure template (H2 sections)
- Specify developer blog voice, formatting conventions
- Specify image placeholder format
- Specify word count target (800-1300)
- Instruct LLM to use actual PoC data, not hypotheticals

**Acceptance criteria:**
- Prompt produces a well-structured developer blog post
- Output is clean markdown (no preamble, no code fences)

---

### Task 15.3 — Reviewer Prompts

**Files:**
- `src/autopoc/prompts/blog_review_architect.md`
- `src/autopoc/prompts/blog_review_content.md`
- `src/autopoc/prompts/blog_review_formatting.md`

**Work:**
- **Architect** (35%): Score thesis clarity, section flow, depth
  calibration, opening hook, closing strength. Each dimension 1-10.
- **Content** (40%): Score technical accuracy (cross-reference PoC data),
  developer voice, audience alignment, originality, evidence/examples.
- **Formatting** (25%): Score heading hierarchy, code block formatting,
  CTA placement, image placeholders, word count compliance.
- Each reviewer outputs: per-dimension scores, overall score (1-10),
  specific revision suggestions with line references.
- Output format: structured markdown that can be parsed for scores.

**Acceptance criteria:**
- Each prompt produces a parseable review with scores
- Dimensions cover all quality aspects
- Review feedback is specific and actionable

---

### Task 15.4 — HTML Preview Template

**Files:** `src/autopoc/templates/blog-preview.html`

**Work:**
- Clean, minimal HTML template with:
  - Good typography (system fonts, comfortable line height)
  - Syntax highlighting for code blocks (inline CSS)
  - Responsive layout (max-width 800px, mobile-friendly)
  - Placeholder tokens: `{{TITLE}}`, `{{SUBTITLE}}`, `{{AUTHOR}}`,
    `{{DATE}}`, `{{READ_TIME}}`, `{{META_DESCRIPTION}}`,
    `{{BODY_CONTENT}}`
- Style image placeholder blocks with dashed borders
- Dark-themed code blocks

**Acceptance criteria:**
- Template renders a readable blog preview in a browser
- Placeholder substitution produces valid HTML
- Looks professional without heavy branding

---

### Task 15.5 — Blog Post Agent Implementation

**Files:** `src/autopoc/agents/blog_post.py`

**Depends on:** Tasks 15.1-15.4

**Work:**
- Implement `blog_post_agent(state, *, llm=None) -> dict`
- Build user message from state: project name, repo summary, components,
  PoC plan, infrastructure, test results, RHOAI evaluation, fork URL,
  built images, routes
- Generate v1 draft via one-shot LLM call
- Run review loop:
  1. Call 3 reviewers in parallel (`asyncio.gather`)
  2. Parse scores from reviewer output
  3. Check pass criteria (overall >= 7.0, no dimension < 5.0)
  4. If passing: break and finalize
  5. If not passing and iterations < 3: build revision prompt with
     all three review reports, generate next draft version
  6. If not passing after 3 iterations: use best-scoring draft
- Generate SEO metadata via one-shot LLM call
- Render HTML preview via template substitution (markdown → HTML
  using Python's `markdown` library or simple regex conversion)
- Write all artifacts to disk
- Commit to artifacts branch
- Return state update with paths
- All failure paths return empty paths (non-blocking)

**Acceptance criteria:**
- Agent produces blog-post.md, blog-seo.md, blog-preview.html
- Review loop runs up to 3 iterations
- Score-based exit works (passes early if score is good)
- Best-draft selection works when 3 iterations don't reach threshold
- Failures don't crash the pipeline

---

### Task 15.6 — Graph Integration

**Files:** `src/autopoc/graph.py`

**Depends on:** Task 15.5

**Work:**
- Import `blog_post_agent`
- Add `"blog_post"` to `PIPELINE_PHASES`
- Add `blog_post` node to graph
- Replace `graph.add_edge("poc_report", END)` with conditional edge
  via `route_after_poc_report`
- Handle `stop_after="poc_report"` (skip blog, existing behavior)
- Handle `stop_after="blog_post"` (stop after blog)

**Acceptance criteria:**
- Graph compiles with all `stop_after` values
- Blog node runs only when majority of scenarios pass
- Blog node is skipped when `--stop-after poc_report`
- Blog failure doesn't crash the pipeline

---

### Task 15.7 — CLI Display Updates

**Files:** `src/autopoc/cli.py`

**Depends on:** Task 15.6

**Work:**
- Display blog post paths in pipeline output (blog-post.md,
  blog-seo.md, blog-preview.html)
- Show "Blog post skipped (insufficient passing scenarios)" when
  the success gate is not met
- Support `--stop-after blog_post`

**Acceptance criteria:**
- Blog artifacts shown in CLI output when generated
- Skip message shown when gate is not met

---

### Task 15.8 — Unit Tests

**Files:** `tests/test_blog_post.py`

**Depends on:** Task 15.5

**Work:**
- Test draft generation with mocked LLM
- Test review scoring (pass, fail, edge cases)
- Test score computation (weighted average, threshold checks)
- Test revision loop (passes on first try, passes on retry,
  max iterations reached)
- Test success gate (majority pass, majority fail, no results)
- Test SEO generation
- Test HTML preview rendering
- Test non-blocking failure handling
- Test route_after_poc_report routing logic

**Acceptance criteria:**
- All agent behaviors tested
- Review loop edge cases covered
- Non-blocking behavior verified
- All tests pass

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Review loop is expensive (up to 12 LLM calls worst case) | Higher LLM cost per pipeline run | Max 3 iterations. Each call is small (~2-4K tokens). Skip with `--stop-after poc_report`. |
| Blog quality inconsistent | Published posts need heavy editing | Review loop catches structural and content issues. This is a first draft — human editing is expected. |
| Blog contains inaccurate claims about PoC results | Credibility risk | Content reviewer specifically scores technical accuracy against the PoC data provided in the prompt. |
| Markdown-to-HTML conversion imperfect | Preview doesn't match final | Use Python `markdown` library for conversion. Preview is approximate — final rendering happens in the CMS. |
| Long pipeline runtime | User waits too long | Blog is the last step. Can be skipped entirely with `--stop-after poc_report`. |
| Reviewer score parsing fails | Loop can't determine pass/fail | Structured output format with regex fallbacks. If parsing fails, accept current draft. |
