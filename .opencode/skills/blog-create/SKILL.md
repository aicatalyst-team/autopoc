---
name: blog-create
description: Create a developer blog post from PoC results or from scratch. Uses a multi-reviewer pipeline with iterative quality improvement. Use this skill when asked to write a blog post, create blog content, or when invoked from the run-poc skill after successful PoC tests.
---

# blog-create

A multi-reviewer blog creation skill for developer blog posts about OpenShift AI PoC deployments. Handles two modes -- creating blogs from PoC results (automated) and creating blogs from scratch (interactive). Uses four specialized sub-agent reviewers for iterative quality improvement.

## Modes

### Mode 1: From PoC Results (automated, invoked by run-poc)

When invoked from the `run-poc` skill, the blog-create skill receives context from the PoC state file (`poc-state.yaml`). The qualifying and abstract phases are auto-filled:

1. Read `poc-state.yaml` for: project name, repo URL, fork URL, components, PoC plan, test results, routes, infrastructure
2. Skip Phase 1 (Qualify) -- auto-generate from PoC context
3. Auto-generate abstract from PoC report
4. Proceed directly to Phase 3 (Draft)

### Mode 2: From Scratch (interactive)

When invoked directly, follow the full workflow starting from Phase 1.

## Workflow

```
Phase 1: Qualify (skip if from PoC) -> Phase 2: Abstract -> Phase 3: Draft -> Phase 4: Review Loop -> Phase 5: Finalize
```

## Phase 1: Qualify (interactive mode only)

Gather requirements through conversational questions. Read `references/qualifying-questions.md` for the full question framework.

**Inputs to gather:**
- Blog type (Red Hat Blog vs Developer Blog)
- Core thesis
- Target audience
- Products/projects involved
- Source material
- Demo/code component
- CTA target

**For PoC mode:** Auto-fill:
- Blog type: "Red Hat Developer Blog"
- Thesis: "Deploying {project} on OpenShift AI proves {poc_type} workloads work seamlessly"
- Audience: "Platform engineers and ML engineers"
- Products: "Red Hat OpenShift AI, Open Data Hub"
- Source: PoC report and test results
- Demo: Yes (the deployment itself)
- CTA: "Try deploying your own project with AutoPoC"

## Phase 2: Abstract

Create `$WORK_DIR/repos/$PROJECT_NAME/.autopoc/blog/abstract.md` containing:
- Thesis statement
- Target audience
- Blog type
- Key points (3 max)
- Products/projects
- CTA
- Proposed section outline

For PoC mode, derive the abstract from PoC results:
- What the project is and why it matters
- How it was containerized and deployed
- What the test results showed
- What was learned

## Phase 3: Draft

Generate the first draft at `$WORK_DIR/repos/$PROJECT_NAME/.autopoc/blog/drafts/v1.md`.

### Content Structure (for PoC blogs)
1. **What is {project_name}?** -- Brief description from repo summary
2. **Why it matters for OpenShift AI** -- ODH relevance, use cases
3. **Setting up for deployment** -- Repository analysis, component detection
4. **Containerizing for OpenShift** -- UBI Dockerfiles, OpenShift compatibility
5. **Deploying to the cluster** -- K8s manifests, namespace, resources
6. **Running the PoC tests** -- Test scenarios and results
7. **What we learned** -- Challenges, workarounds, insights
8. **Try it yourself** -- How to reproduce, CTA

### Target Word Count
800-1300 words for a standard PoC blog post.

### Image Placeholders
Include 2-3 image placeholders with generation prompts:

```
--------------------
**[Image Placeholder N: description]**

**Placement rationale**: Why an image belongs here
**Image generation prompt**: Detailed prompt with Red Hat brand colors (#EE0000, #A30000, #151515, #F0F0F0), clean modern style, aspect ratio
**Alt text**: Descriptive, accessible alt text

--------------------
```

### Writing Rules
- First person plural ("we")
- Sentence case headings, no H1 in body
- Use contractions aggressively
- Active voice
- No marketing tropes ("game-changer", "cutting-edge")
- No filler transitions ("Moreover", "Furthermore")
- No em dashes (use commas, colons, or sentence breaks)
- Be specific over vague
- Oxford commas

## Phase 4: Review Loop

Iteratively improve the draft using four parallel sub-agent reviewers.

### For each iteration:

1. **Spawn four reviewers in parallel** using the Task tool. Each reviewer reads:
   - Current draft
   - Abstract
   - Their specific rubric (from `references/`)

   Reviewer sub-agent prompt:
   ```
   You are the [Architect/Content/Formatting/Image] reviewer for a developer blog post.
   Review the draft against your rubric. Score each dimension 1-10, multiply by weight.
   
   Read: [draft path], [abstract path]
   Read your rubric: .opencode/skills/blog-create/references/reviewer-[type].md
   
   Write your review to: [draft_dir]/reviews/v[N]-[type].md
   Follow the output format in your rubric exactly.
   ```

2. **Collect reviews** from `drafts/reviews/vN-*.md`

3. **Aggregate scores** per `references/scoring.md`:
   - Architect: 30%, Content: 30%, Formatting: 20%, Image: 20%
   - Pass criteria: overall >= 8.0, no dimension below 6.0

4. **If passed**: Proceed to Phase 5.

5. **If not passed**: Revise and create `drafts/v(N+1).md`:
   - Fix dimensions below 6.0 first (blockers)
   - Address lowest-scoring dimension
   - Apply editorial fixes
   - Include brief changelog at top

6. **Repeat** up to 3 autonomous iterations, then checkpoint.

### Iteration Controls
- Max 3 autonomous iterations before checkpoint
- At checkpoint (for interactive mode): continue, steer, accept, or abandon
- For PoC mode (non-interactive): auto-accept after 3 iterations if best score >= 7.0
- Hard ceiling: 9 iterations

Read `references/scoring.md` for full rules.

## Phase 5: Finalize

1. Strip internal changelog from passing draft
2. Write `final.md` with clean draft
3. Generate `seo.md` with meta title, description, keywords, slug
4. Generate `blog-preview.html` using template from `assets/blog-template.html` -- read `references/html-preview-guide.md` for conversion rules
5. Run Vale linting (optional):
   ```bash
   vale --output=JSON final.md 2>/dev/null || true
   ```
6. Commit to artifacts branch:
   ```bash
   python -m autopoc.tools.artifacts "$CLONE_PATH" blog-post.md blog-seo.md blog-preview.html
   ```

## Important Reminders

- Never overwrite drafts -- create new version files (v1, v2, v3...)
- Reviews are also versioned -- vN-architect.md, vN-content.md, etc.
- For PoC mode, strip any URL credentials from the blog (GitLab tokens, etc.)
- No em dashes in the final output
- All product names must be official (Red Hat OpenShift AI, not RHOAI)
