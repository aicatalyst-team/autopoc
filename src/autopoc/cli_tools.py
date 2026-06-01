"""Standalone CLI wrappers for AutoPoC tools.

Only wraps operations that have no native CLI equivalent and contain
non-trivial Python logic. Everything else (git, kubectl, podman, oc,
vale, gh, curl) is invoked directly by OpenCode via bash.

Usage:
    python -m autopoc.cli_tools <command> [args...]

Commands:
    llm-proxy <env_vars_json>                   Resolve LLM env vars (JSON output)
    sheet-reader [--sheet-id ID] [--credentials PATH] [--max-tabs N] [--monthly-mode | --no-monthly-mode] [--target-month YYYY-MM]
    sheet-writer [--sheet-id ID] [--credentials PATH] [--tab TAB]
                 [--row ROW] [--results JSON]
    monthly-pocs [--sheet-id ID] [--credentials PATH] [--target-month YYYY-MM] [--max-pocs N]
    google-docs-upload <markdown_file> [--project-name NAME] [--credentials PATH] [--folder-id ID]
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
# llm-proxy
# --------------------------------------------------------------------------- #


def cmd_llm_proxy(args: argparse.Namespace) -> None:
    from autopoc.llm_proxy import resolve_llm_env_vars

    config = _load_config()
    env_vars = json.loads(args.env_vars_json)

    infrastructure = {
        "needs_llm_api": True,
        "llm_env_pattern": args.pattern or "openai",
    }

    resolved = resolve_llm_env_vars(env_vars, infrastructure, config)
    print(json.dumps(resolved, indent=2))


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
    # Monthly mode is enabled by default, disable only if explicitly disabled
    if args.no_monthly_mode:
        monthly_mode = False
    elif args.monthly_mode:
        monthly_mode = True
    else:
        # Check environment variable, default to True (monthly mode enabled)
        env_value = os.environ.get("AUTOPOC_MONTHLY_MODE", "true").lower()
        monthly_mode = env_value not in ("false", "no", "0", "off")
    target_month = args.target_month or os.environ.get("AUTOPOC_TARGET_MONTH")

    if not sheet_id:
        print("Error: --sheet-id or AUTOPOC_SHEET_ID required", file=sys.stderr)
        sys.exit(1)
    if not Path(credentials).exists():
        print(f"Error: credentials file not found: {credentials}", file=sys.stderr)
        sys.exit(1)

    rows = read_sheet(
        credentials,
        sheet_id,
        max_tabs=max_tabs,
        monthly_mode=monthly_mode,
        target_month=target_month,
    )
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

    raw_rows = read_sheet(credentials, sheet_id, max_tabs=1)
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
# monthly-pocs
# --------------------------------------------------------------------------- #


def cmd_monthly_pocs(args: argparse.Namespace) -> None:
    """Find approved unprocessed projects from monthly report and optionally run PoCs."""
    from autopoc.sheet import find_approved_unprocessed_projects, read_sheet

    sheet_id = args.sheet_id or os.environ.get("AUTOPOC_SHEET_ID", "")
    credentials = args.credentials or os.environ.get(
        "AUTOPOC_SHEET_CREDENTIALS", "/etc/autopoc/google-sa/credentials.json"
    )
    target_month = args.target_month or os.environ.get("AUTOPOC_TARGET_MONTH")
    max_pocs = args.max_pocs or int(os.environ.get("MAX_MONTHLY_POCS", "5"))

    if not sheet_id:
        print("Error: --sheet-id or AUTOPOC_SHEET_ID required", file=sys.stderr)
        sys.exit(1)
    if not Path(credentials).exists():
        print(f"Error: credentials file not found: {credentials}", file=sys.stderr)
        sys.exit(1)

    # Read from monthly report tab
    rows = read_sheet(credentials, sheet_id, monthly_mode=True, target_month=target_month)

    # Find approved unprocessed projects
    projects = find_approved_unprocessed_projects(rows, max_pocs)

    result = {
        "target_month": target_month or "current",
        "projects_found": len(projects),
        "max_pocs": max_pocs,
        "projects": projects,
    }

    print(json.dumps(result, indent=2, default=str))


# --------------------------------------------------------------------------- #
# google-docs-upload
# --------------------------------------------------------------------------- #


def cmd_google_docs_upload(args: argparse.Namespace) -> None:
    """Upload a blog post to Google Docs with template table."""
    from autopoc.tools.google_docs_tools import create_google_docs_service, extract_blog_metadata

    config = _load_config()

    # Use provided credentials or fall back to config
    credentials_path = args.credentials or config.sheet_credentials
    folder_id = args.folder_id or config.google_docs_folder_id

    if not credentials_path:
        print(json.dumps({"error": "No Google credentials available"}), file=sys.stderr)
        sys.exit(1)

    if not Path(str(credentials_path)).exists():
        print(
            json.dumps({"error": f"Credentials file not found: {credentials_path}"}),
            file=sys.stderr,
        )
        sys.exit(1)

    if not Path(args.markdown_file).exists():
        print(
            json.dumps({"error": f"Markdown file not found: {args.markdown_file}"}), file=sys.stderr
        )
        sys.exit(1)

    try:
        # Create Google Docs service
        docs_service = create_google_docs_service(credentials_path)

        # Extract metadata for template table
        markdown_content = Path(args.markdown_file).read_text(encoding="utf-8")
        table_data = extract_blog_metadata(markdown_content)

        # Create document title
        project_name = args.project_name or "Project"
        doc_title = f"[AutoPoC] {table_data.get('Title', project_name)} Blog Post"

        # Upload to Google Docs
        doc_url = docs_service.upload_blog_as_doc(
            markdown_path=args.markdown_file,
            doc_title=doc_title,
            parent_folder_id=folder_id,
            table_data=table_data,
        )

        # Output result as JSON
        result = {
            "success": True,
            "doc_url": doc_url,
            "doc_title": doc_title,
            "table_data": table_data,
        }
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"error": f"Failed to upload to Google Docs: {e}"}), file=sys.stderr)
        sys.exit(1)


# --------------------------------------------------------------------------- #
# Build parser & main
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autopoc-tools",
        description="Standalone CLI wrappers for AutoPoC tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # llm-proxy
    p = sub.add_parser("llm-proxy", help="Resolve LLM env vars via OGX proxy")
    p.add_argument("env_vars_json", help="JSON string of env vars")
    p.add_argument("--pattern", default=None, help="LLM env pattern (openai/anthropic)")
    p.set_defaults(func=cmd_llm_proxy)

    # sheet-reader
    p = sub.add_parser("sheet-reader", help="Read candidates from Google Sheet")
    p.add_argument("--sheet-id", default=None, help="Google Sheet ID")
    p.add_argument("--credentials", default=None, help="SA credentials JSON path")
    p.add_argument("--max-tabs", type=int, default=None, help="Max tabs to read")
    monthly_group = p.add_mutually_exclusive_group()
    monthly_group.add_argument(
        "--monthly-mode", action="store_true", help="Read from monthly report tab (default)"
    )
    monthly_group.add_argument(
        "--no-monthly-mode", action="store_true", help="Use legacy mode (last N tabs)"
    )
    p.add_argument("--target-month", default=None, help="Target month in YYYY-MM format")
    p.set_defaults(func=cmd_sheet_reader)

    # sheet-writer
    p = sub.add_parser("sheet-writer", help="Write results to Google Sheet")
    p.add_argument("--sheet-id", default=None, help="Google Sheet ID")
    p.add_argument("--credentials", default=None, help="SA credentials JSON path")
    p.add_argument("--tab", required=True, help="Tab name")
    p.add_argument("--row", type=int, required=True, help="Row number")
    p.add_argument("--results", required=True, help="JSON results string")
    p.set_defaults(func=cmd_sheet_writer)

    # monthly-pocs
    p = sub.add_parser(
        "monthly-pocs", help="Find approved unprocessed projects from monthly report"
    )
    p.add_argument("--sheet-id", default=None, help="Google Sheet ID")
    p.add_argument("--credentials", default=None, help="SA credentials JSON path")
    p.add_argument("--target-month", default=None, help="Target month in YYYY-MM format")
    p.add_argument("--max-pocs", type=int, default=None, help="Maximum number of PoCs to find")
    p.set_defaults(func=cmd_monthly_pocs)

    # google-docs-upload
    p = sub.add_parser("google-docs-upload", help="Upload blog post to Google Docs")
    p.add_argument("markdown_file", help="Path to markdown file to upload")
    p.add_argument("--project-name", default=None, help="Project name for document title")
    p.add_argument(
        "--credentials", default=None, help="Google service account credentials JSON path"
    )
    p.add_argument("--folder-id", default=None, help="Google Drive folder ID")
    p.set_defaults(func=cmd_google_docs_upload)

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
