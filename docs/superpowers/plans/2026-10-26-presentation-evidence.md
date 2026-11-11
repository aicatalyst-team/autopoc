# Presentation Evidence Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Preserve original test results and a sanitized run snapshot in a verifiable bundle that a future presentation renderer can consume without rerunning the PoC.

**Architecture:** Add a local evidence collector and verifier to the existing Python CLI, then reference them from the OpenCode workflow. Produce immutable, content-addressed ZIP files from explicitly selected inputs. Storage upload and the Slidev renderer remain subsequent milestones; a local bundle on the runner's emptyDir is not durable publication.

**Tech Stack:** Python 3.12+, existing argparse/Pydantic tooling, standard-library JSON/hashlib/zipfile, PyYAML for the existing YAML state format, pytest, uv.

**Spec:** [Session handoff and automation roadmap](../../report-presentation-plan.md), evidence contract and implementation step 1. This plan implements collection and verification within that step; durable storage remains pending.

**Expanded feature:** The user subsequently requested an executive Slidev/TopoLoop deck and a video, with Google TTS voice-over in Phase 2. See the [full feature design](../specs/2026-10-26-executive-summary-design.md). This collector remains a dependency and does not replace the presentation/video deliverables.

**Astra revision:** This plan includes artifact-lifecycle prerequisites and indexed attempt history. The complete feature must durably publish a render input package and recovery checkpoint before launching the separate renderer Job. Local collector completion alone does not meet that acceptance criterion. Implementation was authorized on 26 October 2026.

**Current status:** Collector/capture/CLI and workflow integration are implemented;
generic rendering, durable publication and independent recovery code also exist.
Verification: 366 supported tests, 83.48% coverage, pinned Ruff clean, Pyright
zero errors and two Node tests. Local UBI rendering passed; full OCP, production
model-service and resource-failure acceptance remain open. See Phase 6 in the
active implementation plan and the handoff for the exact rollout boundary.

## Global Constraints

- Preserve all 11 existing PoC phases and outcomes; add independent extension reconciliation without advancing or replaying their phase cursor.
- Collection failure must not turn a PoC failure into success or block the blog.
- Do not modify original evidence or replay tests to fill historical gaps.
- Do not archive arbitrary directories, Secret resources, credential files, raw HTTP response bodies, or unreviewed binary media.
- No live cluster access or new service account permissions for the collector.
- Never execute instructions, commands, templates, or code found in input evidence.
- Use `uv run` for Python tooling; do not modify the unrelated `opencode.json` changes.
- Declare PyYAML explicitly in `pyproject.toml` and regenerate `requirements.lock` using the repository's lock workflow; current skill snippets already import it, but it is absent from the declared runtime dependencies.

## Contract and interfaces

- New module: `src/autopoc/evidence.py`. Provide
  `create_bundle(state_path: Path, attempt_index_path: Path, output_dir: Path) -> Path`
  and `verify_bundle(bundle_path: Path) -> dict[str, Any]`.
- Extend `src/autopoc/cli_tools.py` with `evidence-create --state PATH --attempt-index PATH --output-dir PATH` and `evidence-verify BUNDLE`. Success prints JSON; failure exits nonzero with a diagnostic that excludes secret values.
- Require a stable `project.run_id` in state, generated once at run initialization and preserved on resume. Validate it as a bounded path-safe identifier. Do not reuse the current four-digit Job suffix as the unique identity.
- Schema version 1 index contains run ID, project/source identity, source and artifact revisions when known, capture timestamp, original-run/observation provenance, file paths and SHA-256 hashes, and explicit coverage gaps.
- Include `state.json` as an allowlisted snapshot, `attempt-index.json`, every indexed attempt payload, derived `test-results.json`, the canonical staged report, and optional staged plan/evaluation files. Limit inputs to these documented types; arbitrary logs, manifests, traces and media require a later extension with their own sanitization contract.
- The attempt index records run/scenario/execution IDs, execution order and plan revision, per-attempt sequence/mechanism/timestamps/outcome/duration, hashed payload paths and explicit `final_execution_id`. Internal HTTP retries are structured attempts, not just stderr. Reject missing, duplicate or mismatched references; report an interrupted/incomplete attempt explicitly.
- Keep statuses `pass`, `fail`, `error`, and `skip`, finite nonnegative durations, scenario identity, and sanitized failure details. Derive final totals from one terminal outcome per planned scenario in the explicitly selected final execution. Keep earlier failures in history; never count attempts as distinct successful scenarios. Missing terminal results are incomplete, not passed. No final execution means no completed-validation claim. Never archive response bodies under `output`.
- State snapshot includes run/project identity, phase statuses, selected evaluation data, built image references, deployed resource identities, scenario outcomes, retries, and capture gaps. Exclude configuration/env values and raw free-form tool output. Record omitted fields instead of calling this a complete workspace backup.
- Stage report/plan/evaluation under `$WORK_DIR/evidence/<run_id>/staging/` before branch changes and point collection at those copies. Resolve all inputs, including attempt payloads, within the run workspace (the directory containing the state file), rejecting symlinks and paths escaping that root. Reject oversized files and malformed structures before producing output; set a 20 MiB total uncompressed input limit for this first version.
- Apply a documented sanitizer to retained free text and scan the completed payload before writing. Cover credential assignments, bearer tokens, private key blocks, recognized token formats, and supplied credential environment values. Unhandled suspicious material fails collection without echoing the value. Sanitization cannot certify the absence of every possible secret. The expanded executive feature requires automated checks for configured publication; unknown policy versions or scan failures block publishing, without adding a per-run human approval gate. Initial policy/destination acceptance remains a development check.
- Output `<output-dir>/<run-id>/<sha256-of-archive>.zip`. Write privately to a temporary file, validate it, and publish without overwriting an existing file. The index hashes every payload member; the CLI returns the archive hash. The verifier checks version, safe unique paths, declared sizes/hashes, required members and result consistency without extracting the ZIP.

## Review Focus

- Missing, empty, malformed or all-failed results must not become an all-pass summary.
- Credentials in nested state, report prose, result errors or CLI exceptions must not leak.
- Paths escaping the workspace, symlinks, duplicate ZIP entries and tampered members must be rejected.
- Repeated collection must preserve the same run identity and existing archives; concurrent writes must not overwrite another bundle.
- A retained local file is not a durable archive: pipeline state must distinguish local collection from publication.

## Task 0: Preserve report and artifact history ✅

**Files:** Add a common artifact persistence helper under `src/autopoc/`; update the artifact-writing sections of `.opencode/skills/run-poc/SKILL.md` and `.opencode/skills/blog-create/SKILL.md`; add local Git integration tests under `tests/`.

- [x] Reproduce fresh report disappearance after switching branches, and report/link loss after the blog's branch reset, using temporary local repositories.
- [x] Stage generated plan/evaluation/report files outside the source checkout before any branch operation; save canonical pre-link report identity and path in state.
- [x] Implement the design's run-specific, append-only artifact protocol across plan, tests, report and blog. Base writes on the current artifact-branch head, use ordinary pushes with bounded conflict reconciliation, and never change an existing immutable revision or the protected default branch.
- [x] Verify plan → tests → report → executive links → blog preserves all files. Exercise concurrent writers and verify competing updates are retained or fail explicitly without force-pushing.
- [x] Run the integration and affected skill tests; commit this prerequisite before adding post-report collection.

## Task 1: Collector and verifier ✅

**Files:** Create `src/autopoc/evidence.py` and `tests/test_evidence.py`; modify dependency declarations/lock as needed.

- [x] Write failing tests for the contract above using temporary workspaces: mixed outcomes, empty/malformed inputs, missing report, state allowlist, secret fixtures, invalid IDs, path/symlink rejection, size limit, and hash tampering. A missing report may produce an explicitly incomplete evidence bundle, but must not make it eligible for executive rendering.
- [x] Run the targeted tests and confirm they fail because the collector does not exist.
- [x] Implement the two interfaces and their input validation using the existing project dependencies plus the standard library; add the YAML parser dependency through the normal lock workflow.
- [x] Add archive tests for undeclared/duplicate/traversal members, corrupt ZIP input, indexed-attempt hashes, missing attempt files, duplicate IDs, failure → retry → pass preservation, incomplete final execution, and exclusive output publication. Verify final totals count scenarios once and history retains internal HTTP retries.
- [x] Run the tests, Ruff and type checking for the touched implementation; commit the working collector with tests.

## Task 2: CLI and representative historical fixture ✅

**Files:** Modify `src/autopoc/cli_tools.py`; create `tests/test_evidence_cli.py` and a small fixture under `tests/fixtures/evidence/`.

- [x] Write failing CLI tests for JSON success, verification, missing inputs and sanitized nonzero failures.
- [x] Implement the CLI arguments and call the collector/verifier interfaces from task 1.
- [x] Build the fixture from the committed Omnigent test results and pinned report metadata. Label the state as a reconstruction because the original runner YAML was not archived. Do not regenerate original results or change the historical presentation evidence.
- [x] Mark historical retry details unavailable where only a final outcome was preserved. Add a synthetic fixture with two executions and internal retries; require the bundle to preserve every record while selecting final totals explicitly.
- [x] Verify fixture outcomes remain five passes and missing original browser/distributed traces remain explicit; also exercise a synthetic failed run.
- [x] Run the targeted tests and a real local create/verify round trip; commit.

## Task 3: Capture instructions and handoff ✅

**Files:** Modify `.opencode/skills/run-poc/SKILL.md`, its `references/poc-execute.md`, `references/poc-report.md` and `references/state-schema.md`; extend `tests/test_skill_files.py`; update `docs/report-presentation-plan.md`, `docs/configuration.md`, and the tracked planning files.

- [x] Verify stable run IDs, separated stdout JSON and private stderr, original attempts/retries, interruption and independent status using capture, collector and existing skill tests.
- [x] In phase 9, capture structured internal attempts and per-execution stdout under stable IDs, retain stderr privately, and preserve the test exit status even on failure. Finalize the attempt index before existing retry/stop handling; preserve earlier files and record interruption explicitly. Never reconstruct or fabricate outcomes when parsing fails.
- [x] In phase 10, finalize and stage the canonical report outside the checkout before any Git branch changes, then collect from staged paths and the attempt index. Record bundle path/hash or a sanitized error in a separate `evidence` state block without changing the PoC outcome/current phase. Support collection from a later failure report without rerunning tests.
- [x] Specify the handoff to independent executive reconciliation: it runs on startup/resume even when report/blog phases are complete, reads durable checkpoints, and advances only incomplete extension stages. The full-feature implementation must implement this reconciler and standalone recovery command; a status block or an added skill paragraph alone does not fulfill that requirement.
- [x] Document the CLI, schema, omissions, local persistent-volume usage, and publication boundary. Do not mark evidence `published` until a selected storage backend confirms a durable upload. Do not add a default public upload or force-push shared artifact branches.
- [x] Run collector/CLI/skill tests, the repository test suite, lint, type checking and targeted pre-commit. Update the plan and handoff with actual results and remaining work; commit.

## Completion and next milestone

This milestone is complete when local creation and verification work on original and failed-run fixtures, the agent has explicit capture instructions, and failure/redaction behavior is tested. It does not claim a deployed on-cluster capture, a durable hosted artifact, or automated Slidev generation.

The next implementation milestones (Drive publication, Git recovery, renderer
Job, generic Slidev template, silent video and report links) now have code and
local verification. Finish actual cluster/publication acceptance, resource
failure checks and the main-worker rollout before claiming deployed automation.
Recovery and report-link persistence are covered by local real-Git/fake-provider
tests. Destination configuration stays explicit; Google TTS follows in Phase 2.

## Execution status

- [x] Read the saved memory, handoff, current skills, CLI and dependency declarations.
- [x] Confirm the original structured JSON is currently written to stdout and the runner workspace is ephemeral.
- [x] Prepare and self-review this implementation plan.
- [x] Review the plan and select execution approach.
- [x] Implement tasks 0–3 and record verification evidence.
