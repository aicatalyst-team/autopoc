# 0010 -- Vale Prose Linting with LLM Revision Loop

## Status

Accepted

## Context

AutoPoC generates several markdown artifacts as pipeline outputs: `poc-plan.md`,
`poc-report.md`, and `blog-post.md`. These documents are customer-facing or
shared with stakeholders, so prose quality matters. LLM-generated text sometimes
has style inconsistencies, passive voice overuse, or terminology that doesn't
match Red Hat's style guide.

Vale is an open-source prose linter with a Red Hat style package already
configured in the repo (`.vale.ini`). Running it manually after the pipeline is
one option, but integrating it into the pipeline itself -- with automatic LLM
revision -- closes the feedback loop without human intervention.

The key tension is between style compliance and technical accuracy. Vale's Red
Hat rules are designed for product documentation, not PoC reports. Some rules
(e.g., trademark capitalization, product name preferences) may not apply to the
generated content. The LLM needs latitude to ignore irrelevant suggestions.

## Decision

Add a post-generation vale lint step as a shared utility function
(`vale_lint_and_revise`) that any agent can call after writing a markdown
artifact. The function:

1. Runs `vale --output=JSON` on the file.
2. If findings exist, feeds them to the LLM with the original content and a
   system prompt instructing conservative, selective revision.
3. Re-runs Vale on the revised text.
4. Repeats up to `max_vale_revisions` times (configurable, default 3).

The revision prompt explicitly tells the LLM to treat Vale findings as
suggestions and to prioritize technical accuracy over style compliance.

Vale availability is treated as optional: if the binary is not installed or
styles are not synced, linting is silently skipped with a warning log.

## Alternatives Considered

### Run vale as a separate post-pipeline step

Simpler but requires human intervention to fix findings. Doesn't close the
feedback loop. Selected against because the LLM is already available and can
self-correct cheaply.

### Add vale as a graph node (new pipeline node)

Would add a `vale_lint` node after `poc_report` that re-invokes the originating
agent on findings. Rejected because it adds graph complexity (new edges, new
state routing) for what is essentially a local concern of each agent. A shared
utility function called within each agent is simpler and more flexible.

### Fail the pipeline on vale findings above a threshold

Too strict. Vale's Red Hat rules include many suggestions that are valid for
product docs but irrelevant for PoC reports (e.g., trademark rules for third-
party project names). A hard gate would cause false failures.

## Consequences

### Positive

- Generated prose is automatically improved for style and clarity
- Uses existing Vale + Red Hat style infrastructure already in the repo
- Self-healing: no human intervention needed for common style issues
- Graceful degradation: pipeline works fine without vale installed

### Negative

- Additional LLM calls increase cost and latency (up to 3 extra calls per
  artifact, typically 1-2 in practice)
- Risk of LLM introducing regressions during revision (mitigated by validation
  checks and conservative prompt)

### Neutral

- `vale sync` must be run before the pipeline to download styles (same as any
  dev tool setup)
- Vale findings summary is stored in state but not currently surfaced in the
  CLI output (could be added later)
