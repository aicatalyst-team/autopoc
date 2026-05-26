"""Standalone CLI wrappers for AutoPoC tools.

These are invoked by OpenCode via bash to perform specific operations.
Each subcommand is a thin wrapper around an existing Python function,
reading configuration from environment variables and outputting JSON
or text to stdout.

Usage:
    python -m autopoc.cli_tools <command> [args...]

Commands:
    repo-digest <repo_path>                     Build repo digest (text output)
    gitlab create-project <name>                Create GitLab project (JSON output)
    gitlab get-clone-url <name>                 Get clone URL with token (text output)
    gitlab project-exists <name>                Check if project exists (JSON output)
    github fork <owner> <repo>                  Fork a GitHub repo (JSON output)
    github get-fork <owner> <repo>              Get existing fork (JSON output)
    github wait-for-fork <owner> <repo>         Wait for async fork (JSON output)
    github get-clone-url <owner> <repo>         Get fork clone URL (text output)
    quay ensure-repo <org> <name>               Ensure Quay repo exists (JSON output)
    quay repo-exists <org> <name>               Check if repo exists (JSON output)
    strategy load                               Load active strategy (JSON output)
    strategy load-baseline                      Load strategy baseline (JSON output)
    strategy dimensions                         Get scoring dimensions (JSON output)
    llm-proxy <env_vars_json>                   Resolve LLM env vars (JSON output)
    artifacts <clone_path> <files...>           Commit files to artifacts branch
    vale <file_path>                            Run Vale linting (JSON output)
    sheet-reader [--sheet-id ID] [--credentials PATH] [--max-tabs N]
    sheet-writer [--sheet-id ID] [--credentials PATH] [--tab TAB]
                 [--row ROW] [--results JSON]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _load_config():
    """Load AutoPoCConfig from environment."""
    from autopoc.config import AutoPoCConfig

    return AutoPoCConfig()


# --------------------------------------------------------------------------- #
# repo-digest
# --------------------------------------------------------------------------- #


def cmd_repo_digest(args: argparse.Namespace) -> None:
    from autopoc.tools.repo_digest import build_repo_digest

    digest = build_repo_digest(args.repo_path, max_total_chars=args.max_chars)
    print(digest)


# --------------------------------------------------------------------------- #
# gitlab
# --------------------------------------------------------------------------- #


def cmd_gitlab(args: argparse.Namespace) -> None:
    from autopoc.tools.gitlab_tools import GitLabClient

    config = _load_config()

    with GitLabClient(config) as client:
        if args.action == "create-project":
            result = client.create_project(args.name)
            print(json.dumps(result, indent=2))
        elif args.action == "get-clone-url":
            project = client.get_project(args.name)
            if project is None:
                print(
                    json.dumps({"error": f"Project '{args.name}' not found"}),
                    file=sys.stderr,
                )
                sys.exit(1)
            url = client.get_project_clone_url(project)
            print(url)
        elif args.action == "project-exists":
            exists = client.project_exists(args.name)
            print(json.dumps({"exists": exists}))
        elif args.action == "get-project":
            project = client.get_project(args.name)
            print(json.dumps(project, indent=2))


# --------------------------------------------------------------------------- #
# github
# --------------------------------------------------------------------------- #


def cmd_github(args: argparse.Namespace) -> None:
    from autopoc.tools.github_tools import GitHubClient

    config = _load_config()

    with GitHubClient(config) as client:
        if args.action == "fork":
            result = client.fork_repo(args.owner, args.repo)
            print(json.dumps(result, indent=2))
        elif args.action == "get-fork":
            result = client.get_fork(args.owner, args.repo)
            print(json.dumps(result, indent=2))
        elif args.action == "wait-for-fork":
            fork_owner = args.owner
            if config.github_org:
                fork_owner = config.github_org
            else:
                user = client.get_authenticated_user()
                fork_owner = user.get("login", args.owner)
            result = client.wait_for_fork(fork_owner, args.repo)
            print(json.dumps(result, indent=2))
        elif args.action == "get-clone-url":
            fork = client.get_fork(args.owner, args.repo)
            if fork is None:
                print(
                    json.dumps({"error": "Fork not found"}),
                    file=sys.stderr,
                )
                sys.exit(1)
            url = client.get_clone_url(fork)
            print(url)


# --------------------------------------------------------------------------- #
# quay
# --------------------------------------------------------------------------- #


def cmd_quay(args: argparse.Namespace) -> None:
    from autopoc.tools.quay_tools import QuayClient

    config = _load_config()

    with QuayClient(config) as client:
        if args.action == "ensure-repo":
            result = client.ensure_repo(args.org, args.name)
            print(json.dumps({"repo": result}))
        elif args.action == "repo-exists":
            exists = client.repo_exists(args.org, args.name)
            print(json.dumps({"exists": exists}))


# --------------------------------------------------------------------------- #
# strategy
# --------------------------------------------------------------------------- #


def cmd_strategy(args: argparse.Namespace) -> None:
    from autopoc.tools.strategy import (
        compute_max_score,
        get_scoring_dimensions,
        load_strategy,
        load_strategy_baseline,
    )

    if args.action == "load":
        strategy = load_strategy()
        print(json.dumps(strategy, indent=2, default=str))
    elif args.action == "load-baseline":
        baseline = load_strategy_baseline()
        print(json.dumps(baseline, indent=2, default=str))
    elif args.action == "dimensions":
        strategy = load_strategy()
        dims = get_scoring_dimensions(strategy)
        max_score = compute_max_score(strategy)
        print(json.dumps({"dimensions": dims, "max_score": max_score}, indent=2, default=str))


# --------------------------------------------------------------------------- #
# llm-proxy
# --------------------------------------------------------------------------- #


def cmd_llm_proxy(args: argparse.Namespace) -> None:
    from autopoc.llm_proxy import resolve_llm_env_vars

    config = _load_config()
    env_vars = json.loads(args.env_vars_json)

    # Build a minimal infrastructure dict
    infrastructure = {
        "needs_llm_api": True,
        "llm_env_pattern": args.pattern or "openai",
    }

    resolved = resolve_llm_env_vars(env_vars, infrastructure, config)
    print(json.dumps(resolved, indent=2))


# --------------------------------------------------------------------------- #
# artifacts
# --------------------------------------------------------------------------- #


def cmd_artifacts(args: argparse.Namespace) -> None:
    from autopoc.tools.git_tools import commit_to_artifacts_branch

    commit_to_artifacts_branch(
        clone_path=args.clone_path,
        files=args.files,
        message=args.message or "Add AutoPoC artifacts",
    )
    print(json.dumps({"status": "ok"}))


# --------------------------------------------------------------------------- #
# build (container image build via configured strategy)
# --------------------------------------------------------------------------- #


def cmd_build(args: argparse.Namespace) -> None:
    from autopoc.tools.build_strategy import get_build_strategy

    config = _load_config()
    strategy = get_build_strategy(config)

    if args.action == "login":
        registry = args.registry or os.environ.get("QUAY_REGISTRY", "quay.io")
        username = args.username or os.environ.get("QUAY_USERNAME", "")
        password = args.password or os.environ.get("QUAY_TOKEN", "")
        result = strategy.login(registry, username, password)
        print(json.dumps({"status": "ok", "message": result}))
    elif args.action == "build":
        output = strategy.build(
            context_path=args.context,
            dockerfile=args.dockerfile,
            tag=args.tag,
        )
        print(json.dumps({"status": "ok", "output": output[:5000]}))
    elif args.action == "push":
        output = strategy.push(image=args.tag)
        print(json.dumps({"status": "ok", "output": output[:2000]}))


# --------------------------------------------------------------------------- #
# vale
# --------------------------------------------------------------------------- #


def cmd_vale(args: argparse.Namespace) -> None:
    from autopoc.tools.vale_lint import run_vale

    findings = run_vale(args.file_path)
    print(json.dumps(findings, indent=2))


# --------------------------------------------------------------------------- #
# sheet-reader
# --------------------------------------------------------------------------- #


def cmd_sheet_reader(args: argparse.Namespace) -> None:
    from autopoc.sheet import filter_projects, read_sheet

    sheet_id = args.sheet_id or os.environ.get("AUTOPOC_SHEET_ID", "")
    credentials = args.credentials or os.environ.get(
        "AUTOPOC_SHEET_CREDENTIALS", "/etc/autopoc/google-sa/credentials.json"
    )
    max_tabs = args.max_tabs or int(os.environ.get("MAX_EVALUATED_SHEETS", "4"))

    if not sheet_id:
        print("Error: --sheet-id or AUTOPOC_SHEET_ID required", file=sys.stderr)
        sys.exit(1)
    if not Path(credentials).exists():
        print(f"Error: credentials file not found: {credentials}", file=sys.stderr)
        sys.exit(1)

    rows = read_sheet(credentials, sheet_id, max_tabs=max_tabs)
    filtered = filter_projects(rows)
    print(json.dumps(filtered, indent=2, default=str))


# --------------------------------------------------------------------------- #
# sheet-writer
# --------------------------------------------------------------------------- #


def cmd_sheet_writer(args: argparse.Namespace) -> None:
    from autopoc.sheet import (
        build_sheets_service,
        ensure_result_columns,
        read_sheet,
        write_poc_results,
    )

    sheet_id = args.sheet_id or os.environ.get("AUTOPOC_SHEET_ID", "")
    credentials = args.credentials or os.environ.get(
        "AUTOPOC_SHEET_CREDENTIALS", "/etc/autopoc/google-sa/credentials.json"
    )

    if not sheet_id:
        print("Error: --sheet-id or AUTOPOC_SHEET_ID required", file=sys.stderr)
        sys.exit(1)

    results = json.loads(args.results)
    service = build_sheets_service(credentials)

    # Read headers to get column indices
    raw_rows = read_sheet(credentials, sheet_id, max_tabs=1)
    # Get headers from first row's keys
    headers = list(raw_rows[0].keys()) if raw_rows else []

    col_indices = ensure_result_columns(service, sheet_id, args.tab, headers, tab_gid=0)

    write_poc_results(
        service,
        sheet_id,
        args.tab,
        args.row,
        col_indices,
        fork_repo_url=results.get("poc_repo"),
        fork_target=results.get("fork_target", "gitlab"),
        built_images=[results["poc_image"]] if results.get("poc_image") else None,
        poc_report_path=results.get("poc_report"),
        blog_post_path=results.get("poc_blog"),
    )
    print(json.dumps({"status": "ok"}))


# --------------------------------------------------------------------------- #
# Argument parser
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autopoc-tools",
        description="Standalone CLI wrappers for AutoPoC tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # repo-digest
    p = sub.add_parser("repo-digest", help="Build repo digest")
    p.add_argument("repo_path", help="Path to cloned repository")
    p.add_argument("--max-chars", type=int, default=20_000, help="Max output chars")
    p.set_defaults(func=cmd_repo_digest)

    # gitlab
    p = sub.add_parser("gitlab", help="GitLab operations")
    p.add_argument(
        "action",
        choices=["create-project", "get-clone-url", "project-exists", "get-project"],
    )
    p.add_argument("name", help="Project name")
    p.set_defaults(func=cmd_gitlab)

    # github
    p = sub.add_parser("github", help="GitHub operations")
    p.add_argument("action", choices=["fork", "get-fork", "wait-for-fork", "get-clone-url"])
    p.add_argument("owner", help="Repository owner")
    p.add_argument("repo", help="Repository name")
    p.set_defaults(func=cmd_github)

    # quay
    p = sub.add_parser("quay", help="Quay registry operations")
    p.add_argument("action", choices=["ensure-repo", "repo-exists"])
    p.add_argument("org", help="Quay organization")
    p.add_argument("name", help="Repository name")
    p.set_defaults(func=cmd_quay)

    # strategy
    p = sub.add_parser("strategy", help="RHOAI strategy operations")
    p.add_argument("action", choices=["load", "load-baseline", "dimensions"])
    p.set_defaults(func=cmd_strategy)

    # llm-proxy
    p = sub.add_parser("llm-proxy", help="Resolve LLM env vars via OGX proxy")
    p.add_argument("env_vars_json", help="JSON string of env vars")
    p.add_argument("--pattern", default=None, help="LLM env pattern (openai/anthropic)")
    p.set_defaults(func=cmd_llm_proxy)

    # artifacts
    p = sub.add_parser("artifacts", help="Commit files to artifacts branch")
    p.add_argument("clone_path", help="Path to cloned repository")
    p.add_argument("files", nargs="+", help="Files to commit")
    p.add_argument("--message", default=None, help="Commit message")
    p.set_defaults(func=cmd_artifacts)

    # build
    p = sub.add_parser("build", help="Build/push container images via configured strategy")
    p.add_argument("action", choices=["login", "build", "push"])
    p.add_argument("--registry", default=None, help="Registry hostname")
    p.add_argument("--username", default=None, help="Registry username")
    p.add_argument("--password", default=None, help="Registry password/token")
    p.add_argument("--context", default=".", help="Build context directory")
    p.add_argument("--dockerfile", default="Dockerfile.ubi", help="Dockerfile path")
    p.add_argument("--tag", default=None, help="Image tag (e.g. quay.io/org/name:latest)")
    p.set_defaults(func=cmd_build)

    # vale
    p = sub.add_parser("vale", help="Run Vale linting")
    p.add_argument("file_path", help="Path to markdown file")
    p.set_defaults(func=cmd_vale)

    # sheet-reader
    p = sub.add_parser("sheet-reader", help="Read candidates from Google Sheet")
    p.add_argument("--sheet-id", default=None, help="Google Sheet ID")
    p.add_argument("--credentials", default=None, help="SA credentials JSON path")
    p.add_argument("--max-tabs", type=int, default=None, help="Max tabs to read")
    p.set_defaults(func=cmd_sheet_reader)

    # sheet-writer
    p = sub.add_parser("sheet-writer", help="Write results to Google Sheet")
    p.add_argument("--sheet-id", default=None, help="Google Sheet ID")
    p.add_argument("--credentials", default=None, help="SA credentials JSON path")
    p.add_argument("--tab", required=True, help="Tab name")
    p.add_argument("--row", type=int, required=True, help="Row number")
    p.add_argument("--results", required=True, help="JSON results string")
    p.set_defaults(func=cmd_sheet_writer)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
