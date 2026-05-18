"""Batch PoC pipeline: read candidates from Google Sheet, evaluate, run, and write back."""

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from autopoc.cli import app, console, _load_and_configure, _run_pipeline
from autopoc.config import AutoPoCConfig
from autopoc.sheet import (
    SheetProject,
    SheetRowOrigin,
    _ORIGIN_KEY,
    build_sheets_service,
    ensure_result_columns,
    filter_projects,
    read_sheet,
    select_project,
    write_poc_results,
)
from autopoc.sheet_write import derive_fork_browse_url, derive_quay_search_url

logger = logging.getLogger(__name__)


def _print_candidate_comparison(results: list) -> None:
    """Display a comparison table of evaluated candidates."""
    table = Table(
        show_header=True,
        header_style="bold magenta",
        title="Candidate Comparison",
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Project", min_width=20)
    table.add_column("Score", justify="right", width=7)
    table.add_column("Relationship", min_width=20)
    table.add_column("Areas")

    for i, r in enumerate(results):
        score = r.evaluation.get("total_score", 0)
        max_score = r.evaluation.get("max_possible_score", 100)
        relationship = r.evaluation.get("relationship", "—")
        areas = r.evaluation.get("strategy_areas", [])
        areas_str = ", ".join(areas) if areas else "—"
        error_flag = " [red](error)[/red]" if r.error else ""

        # Highlight winner (first row)
        style = "bold green" if i == 0 else ""
        marker = " *" if i == 0 else ""

        table.add_row(
            str(i + 1),
            f"{r.project.name}{marker}{error_flag}",
            f"{score}/{max_score}",
            relationship,
            areas_str,
            style=style,
        )

    console.print()
    console.print(table)

    if results:
        winner = results[0]
        score = winner.evaluation.get("total_score", 0)
        max_score = winner.evaluation.get("max_possible_score", 100)
        console.print(
            f"\n  [bold green]Winner:[/bold green] {winner.project.name} ({score}/{max_score})"
        )
    console.print()


def _write_back_poc_results(
    service,
    sheet_id: str,
    project: SheetProject,
    pipeline_result: dict,
    config: AutoPoCConfig,
    rows: list[dict[str, str]],
    tab_col_indices: dict[str, dict[str, int]],
) -> None:
    """Write PoC results back to the Google Sheet for a completed pipeline.

    When the pipeline result is missing artifacts (fork URL, built images,
    report), best-effort fallbacks are used:

    - **Fork URL**: derived from source repo URL + config (github_org /
      gitlab_url + gitlab_group).
    - **Image URL**: a Quay organisation search URL filtered by the
      project name (always resolves to a valid page).
    - **Report URL**: derived from the fork browse URL and verified with
      an HTTP HEAD check; written only if the remote file exists.

    Handles column creation and error recovery gracefully.
    """
    from autopoc.sheet_write import (
        _build_report_url,
        _check_url_exists,
    )

    try:
        # Ensure result columns exist (cached per tab)
        if project.tab_name not in tab_col_indices:
            tab_rows = [
                r
                for r in rows
                if (origin := r.get(_ORIGIN_KEY))
                and isinstance(origin, SheetRowOrigin)
                and origin.tab_name == project.tab_name
            ]
            if tab_rows:
                headers = [k for k in tab_rows[0] if k != _ORIGIN_KEY]
            else:
                headers = []

            col_indices = ensure_result_columns(
                service,
                sheet_id,
                project.tab_name,
                headers,
                tab_gid=project.tab_gid,
            )
            tab_col_indices[project.tab_name] = col_indices

        col_indices = tab_col_indices[project.tab_name]

        # --- Resolve fork URL (fallback: derive from config) ---
        fork_repo_url = pipeline_result.get("fork_repo_url")
        fork_target = pipeline_result.get("fork_target") or config.fork_target

        if not fork_repo_url:
            derived = derive_fork_browse_url(
                project.repo_url,
                fork_target,
                github_org=config.github_org,
                gitlab_url=config.gitlab_url,
                gitlab_group=config.gitlab_group,
            )
            if derived:
                fork_repo_url = derived
                logger.info(
                    "Derived fork URL for %s: %s",
                    project.name,
                    derived,
                )

        # --- Resolve image URL (fallback: Quay search page) ---
        built_images = pipeline_result.get("built_images")
        poc_image_override = None
        if not built_images:
            poc_image_override = derive_quay_search_url(
                project.name,
                config.quay_registry,
                config.quay_org,
            )
            logger.info(
                "No built images for %s — using Quay search URL: %s",
                project.name,
                poc_image_override,
            )

        # --- Resolve report URL (fallback: check remote existence) ---
        poc_report_path = pipeline_result.get("poc_report_path")
        poc_report_override = None
        local_report_exists = poc_report_path and Path(poc_report_path).exists()

        if not local_report_exists and fork_repo_url:
            candidate_url = _build_report_url(fork_repo_url, fork_target)
            if _check_url_exists(candidate_url):
                poc_report_override = candidate_url
                logger.info(
                    "Report file verified remotely for %s: %s",
                    project.name,
                    candidate_url,
                )

        write_poc_results(
            service,
            sheet_id,
            project.tab_name,
            project.row_index,
            col_indices,
            fork_repo_url=fork_repo_url,
            fork_target=fork_target,
            built_images=built_images,
            poc_report_path=poc_report_path,
            poc_image_override=poc_image_override,
            poc_report_override=poc_report_override,
        )
        console.print(
            f"  [green]Results written to tab '{project.tab_name}' row {project.row_index}[/green]"
        )
    except Exception as e:
        console.print(f"  [yellow]Warning: Failed to write results to sheet: {e}[/yellow]")
        logger.warning("Sheet write-back failed for %s: %s", project.name, e)


@app.command("run-sheet")
def run_sheet(
    sheet_id: Annotated[
        str | None,
        typer.Option(
            "--sheet-id",
            envvar="AUTOPOC_SHEET_ID",
            help="Google Sheet ID (or set AUTOPOC_SHEET_ID env var)",
        ),
    ] = None,
    credentials: Annotated[
        str | None,
        typer.Option(
            "--credentials",
            envvar="AUTOPOC_SHEET_CREDENTIALS",
            help="Path to Google SA credentials JSON (or set AUTOPOC_SHEET_CREDENTIALS)",
        ),
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", "-m", help="LLM model name to override config")
    ] = None,
    target: Annotated[
        str | None,
        typer.Option(
            "--target",
            "-t",
            help="Fork target: 'gitlab' or 'github' (overrides FORK_TARGET env var)",
        ),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
    skip_validation: Annotated[
        bool,
        typer.Option("--skip-validation", help="Skip credential validation at startup"),
    ] = False,
    stop_after: Annotated[
        str | None,
        typer.Option(
            "--stop-after",
            help="Stop pipeline after this phase (e.g. 'build', 'deploy'). "
            "Valid: intake, evaluate, poc_plan, fork, containerize, build, deploy, apply, poc_execute, poc_report",
        ),
    ] = None,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Dump failed LLM response parses to debug/ for diagnosis"),
    ] = False,
    max_candidates: Annotated[
        int,
        typer.Option(
            "--max-candidates",
            help="Maximum number of candidates to fully evaluate when multiple exist (default: 5)",
        ),
    ] = 5,
    skip_evaluation: Annotated[
        bool,
        typer.Option(
            "--skip-evaluation",
            help="Skip RHOAI evaluation and use first-row selection (legacy behavior)",
        ),
    ] = False,
    max_evaluated_sheets: Annotated[
        int,
        typer.Option(
            "--max-evaluated-sheets",
            envvar="MAX_EVALUATED_SHEETS",
            help="Maximum number of sheet tabs to scan for candidates (default: 4)",
        ),
    ] = 4,
    max_batched_poc: Annotated[
        int,
        typer.Option(
            "--max-batched-poc",
            envvar="MAX_BATCHED_POC",
            help="Maximum number of PoC pipelines to run in this session (default: 2)",
        ),
    ] = 2,
) -> None:
    """Run AutoPoC for top projects from a Google Sheet.

    Reads a POC Explorer spreadsheet (scanning up to --max-evaluated-sheets
    tabs), filters to approved GitHub repos that haven't been PoC'd yet,
    and runs up to --max-batched-poc pipelines sequentially.  Results are
    written back to the sheet after each pipeline completes.
    """
    # Validate required sheet inputs
    if not sheet_id:
        console.print(
            "[bold red]Error:[/bold red] --sheet-id is required (or set AUTOPOC_SHEET_ID env var)"
        )
        raise typer.Exit(code=1)
    if not credentials:
        console.print(
            "[bold red]Error:[/bold red] --credentials is required "
            "(or set AUTOPOC_SHEET_CREDENTIALS env var)"
        )
        raise typer.Exit(code=1)

    # Validate credentials file exists
    credentials_path = Path(credentials).expanduser()
    if not credentials_path.is_file():
        console.print(f"[bold red]Error:[/bold red] Credentials file not found: {credentials_path}")
        raise typer.Exit(code=1)

    config = _load_and_configure(
        model=model,
        target=target,
        verbose=verbose,
        skip_validation=skip_validation,
    )

    # Read and filter the sheet
    console.print(
        Panel(
            f"[bold]Sheet ID:[/bold]    {sheet_id}\n"
            f"[bold]Credentials:[/bold] {credentials_path}\n"
            f"[bold]Tabs to scan:[/bold] {max_evaluated_sheets}\n"
            f"[bold]Max PoCs:[/bold]    {max_batched_poc}",
            title="Google Sheet Ingestion",
            border_style="cyan",
        )
    )

    try:
        console.print("[bold cyan]Reading sheet...[/bold cyan]")
        rows = read_sheet(str(credentials_path), sheet_id, max_tabs=max_evaluated_sheets)
        console.print(f"  Rows read: {len(rows)}")

        filtered = filter_projects(rows)
        github_count = sum(1 for r in rows if "github.com" in r.get("link", ""))
        console.print(f"  GitHub repos: {github_count}")
        console.print(f"  After filters: {len(filtered)}")
    except ValueError as e:
        console.print(f"\n[bold red]Sheet error:[/bold red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"\n[bold red]Failed to read sheet:[/bold red] {e}")
        if verbose:
            console.print_exception(show_locals=True)
        raise typer.Exit(code=1)

    if not filtered:
        console.print(
            "\n[bold yellow]No projects remain after filtering — nothing to PoC.[/bold yellow]"
        )
        raise typer.Exit(code=0)

    # --- Select projects to PoC ---
    projects_to_run: list[SheetProject] = []

    if len(filtered) <= 1 or skip_evaluation:
        # Single candidate or evaluation skipped: legacy first-row selection
        try:
            project = select_project(filtered)
            projects_to_run.append(project)
        except ValueError as e:
            console.print(f"\n[bold red]Sheet error:[/bold red] {e}")
            raise typer.Exit(code=1)
    else:
        # Multiple candidates: pre-filter, evaluate, pick top N
        from autopoc.sheet import (
            _row_to_project,
            cleanup_candidate_clones,
            evaluate_candidates,
            prefilter_candidates,
        )

        console.print(
            f"\n[bold cyan]Multiple candidates ({len(filtered)}). "
            f"Evaluating top {min(max_candidates, len(filtered))}...[/bold cyan]"
        )

        async def _do_evaluation():
            console.print("[bold cyan]Pre-filtering candidates...[/bold cyan]")
            prefiltered = await prefilter_candidates(filtered, max_candidates=max_candidates)
            console.print(f"  Pre-filtered to {len(prefiltered)} candidates")

            def on_progress(idx, total, name):
                console.print(f"  [cyan]Evaluating candidate {idx + 1}/{total}:[/cyan] {name}")

            results = await evaluate_candidates(
                prefiltered,
                config,
                max_candidates=max_candidates,
                on_progress=on_progress,
            )
            return results

        try:
            results = asyncio.run(_do_evaluation())
        except Exception as e:
            console.print(f"\n[bold red]Evaluation failed:[/bold red] {e}")
            if verbose:
                console.print_exception(show_locals=True)
            # Fall back to first N candidates in sheet order
            console.print("[yellow]Falling back to first candidate(s)...[/yellow]")
            for row in filtered[:max_batched_poc]:
                try:
                    projects_to_run.append(_row_to_project(row))
                except ValueError:
                    continue
            if not projects_to_run:
                console.print("\n[bold red]Sheet error:[/bold red] No valid projects found")
                raise typer.Exit(code=1)
            results = None

        if results is not None:
            # Display comparison table
            _print_candidate_comparison(results)

            # Select top N winners
            winners = results[:max_batched_poc]
            losers = results[max_batched_poc:]

            # Clean up non-winner clones
            if losers:
                best = winners[0]
                cleanup_candidate_clones(losers, best)

            for w in winners:
                projects_to_run.append(w.project)

    # --- Print selection summary ---
    for i, project in enumerate(projects_to_run):
        console.print(
            Panel(
                f"[bold]Selected:[/bold]  {project.name}\n"
                f"[bold]Repo:[/bold]      {project.repo_url}\n"
                f"[bold]Category:[/bold]  {project.category}\n"
                f"[bold]Tab:[/bold]       {project.tab_name}\n"
                f"[bold]Sheet row:[/bold] {project.row_index}",
                title=f"Project {i + 1}/{len(projects_to_run)}",
                border_style="green",
            )
        )

    # --- Build sheets service for write-back ---
    sheets_service = None
    tab_col_indices: dict[str, dict[str, int]] = {}  # cache per tab
    try:
        sheets_service = build_sheets_service(str(credentials_path))
    except Exception as e:
        console.print(
            f"[yellow]Warning: Could not create sheets service for write-back: {e}[/yellow]"
        )

    # --- Run pipelines sequentially, writing results after each ---
    for i, project in enumerate(projects_to_run):
        console.print(
            f"\n[bold cyan]Running PoC {i + 1}/{len(projects_to_run)}: {project.name}[/bold cyan]"
        )

        pipeline_result = _run_pipeline(
            project.name,
            project.repo_url,
            config,
            verbose=verbose,
            debug=debug,
            stop_after=stop_after,
        )

        # Write results back to the sheet
        if sheets_service and sheet_id and project.tab_name:
            _write_back_poc_results(
                sheets_service,
                sheet_id,
                project,
                pipeline_result,
                config,
                rows,
                tab_col_indices,
            )
