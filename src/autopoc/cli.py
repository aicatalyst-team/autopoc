"""CLI entry point for AutoPoC."""

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from autopoc.config import load_config
from autopoc.credentials import validate_credentials
from autopoc.graph import build_graph
from autopoc.logging_config import setup_logging
from autopoc.state import PoCPhase, PoCState

app = typer.Typer(
    name="autopoc",
    help="AutoPoC — Automate PoC deployments on OpenShift AI",
    no_args_is_help=True,
)
console = Console()
logger = logging.getLogger(__name__)


def _extract_plan_preview(plan_content: str, max_lines: int = 15) -> str:
    """Extract a concise preview from the PoC plan markdown.

    Tries to show the most useful sections: Project Classification,
    PoC Objectives, and Test Scenarios summary. Falls back to the
    first max_lines lines if no sections are found.
    """
    lines = plan_content.strip().splitlines()
    if not lines:
        return ""

    preview_parts: list[str] = []
    in_section = False
    section_count = 0
    target_sections = {
        "project classification",
        "poc objectives",
        "infrastructure requirements",
        "test scenarios",
    }

    for line in lines:
        stripped = line.strip().lower()
        # Detect section headers (## level)
        if stripped.startswith("## "):
            section_name = stripped.lstrip("# ").strip()
            if any(target in section_name for target in target_sections):
                in_section = True
                section_count += 1
                preview_parts.append(line)
                continue
            else:
                if in_section:
                    in_section = False
                continue
        # Detect next section at same or higher level (stop current)
        if stripped.startswith("# ") and in_section:
            in_section = False
            continue

        if in_section:
            preview_parts.append(line)

    if preview_parts:
        return "\n".join(preview_parts).strip()

    # Fallback: return the first max_lines lines, skipping the title
    start = 1 if lines[0].startswith("# ") else 0
    return "\n".join(lines[start : start + max_lines]).strip()


def _generate_thread_id(project_name: str) -> str:
    """Generate a unique thread ID for a pipeline run."""
    short_id = uuid.uuid4().hex[:8]
    return f"{project_name}-{short_id}"


def _get_checkpoint_dir(work_dir: str) -> Path:
    """Get the checkpoints directory, creating it if needed."""
    checkpoint_dir = Path(work_dir) / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir


def _get_checkpointer(work_dir: str):
    """Create a SQLite checkpointer for state persistence.

    Returns None if langgraph-checkpoint-sqlite is not installed.
    """
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        db_path = _get_checkpoint_dir(work_dir) / "autopoc.db"
        return SqliteSaver.from_conn_string(str(db_path))
    except ImportError:
        # Fall back to MemorySaver (no persistence across runs)
        from langgraph.checkpoint.memory import MemorySaver

        logger.debug("langgraph-checkpoint-sqlite not installed, using in-memory checkpointer")
        return MemorySaver()


def _print_results(result: dict, verbose: bool = False) -> None:
    """Print pipeline results as rich tables and panels."""
    if result.get("repo_summary"):
        console.print("\n[bold]Repository Summary:[/bold]")
        console.print(f"  {result['repo_summary']}")

    components = result.get("components", [])
    if components:
        console.print(f"\n[bold]Components ({len(components)}):[/bold]")
        comp_table = Table(show_header=True, header_style="bold cyan")
        comp_table.add_column("Name")
        comp_table.add_column("Language")
        comp_table.add_column("Port")
        comp_table.add_column("Dockerfile.ubi")
        comp_table.add_column("ML")
        for comp in components:
            comp_table.add_row(
                comp.get("name", "?"),
                comp.get("language", "?"),
                str(comp.get("port", "-")),
                comp.get("dockerfile_ubi_path", "-"),
                "yes" if comp.get("is_ml_workload") else "no",
            )
        console.print(comp_table)

    # PoC Plan info
    poc_type = result.get("poc_type")
    if poc_type:
        console.print(f"\n[bold]PoC Type:[/bold] {poc_type}")

    poc_plan_content = result.get("poc_plan", "")
    poc_plan_path = result.get("poc_plan_path", "")

    if poc_plan_content:
        if verbose:
            console.print("\n[bold]PoC Plan:[/bold]")
            console.print(poc_plan_content)
        else:
            preview = _extract_plan_preview(poc_plan_content)
            if preview:
                console.print(f"\n[bold]PoC Plan Summary:[/bold]")
                console.print(preview)

    if poc_plan_path:
        p = Path(poc_plan_path)
        if p.exists():
            console.print(f"[dim]Full plan:[/dim] {poc_plan_path}")
        else:
            console.print(f"[dim]Plan path:[/dim] {poc_plan_path} [yellow](not written)[/yellow]")

    # PoC Test Results
    poc_results = result.get("poc_results", [])
    if poc_results:
        console.print(f"\n[bold]PoC Test Results ({len(poc_results)}):[/bold]")
        result_table = Table(show_header=True, header_style="bold cyan")
        result_table.add_column("Scenario")
        result_table.add_column("Status")
        result_table.add_column("Duration")
        result_table.add_column("Details")
        for r in poc_results:
            status = r.get("status", "unknown")
            status_display = {
                "pass": "[green]PASS[/green]",
                "fail": "[red]FAIL[/red]",
                "error": "[red]ERROR[/red]",
                "skip": "[yellow]SKIP[/yellow]",
            }.get(status, status)
            detail = r.get("error_message") or r.get("output", "")[:80]
            result_table.add_row(
                r.get("scenario_name", "?"),
                status_display,
                f"{r.get('duration_seconds', 0):.1f}s",
                detail,
            )
        console.print(result_table)

        total = len(poc_results)
        passed = sum(1 for r in poc_results if r.get("status") == "pass")
        console.print(f"  {passed}/{total} passed")

    # PoC scenarios summary (show if plan has scenarios but execution hasn't run)
    poc_scenarios = result.get("poc_scenarios", [])
    if poc_scenarios and not poc_results:
        console.print(f"\n[bold]Planned Test Scenarios ({len(poc_scenarios)}):[/bold]")
        for s in poc_scenarios:
            endpoint = s.get("endpoint", "")
            endpoint_str = f" ({endpoint})" if endpoint else ""
            console.print(f"  - {s.get('name', '?')}: {s.get('description', '')}{endpoint_str}")

    poc_report_path = result.get("poc_report_path", "")
    if poc_report_path:
        p = Path(poc_report_path)
        if p.exists():
            console.print(f"\n[bold]PoC Report:[/bold] {poc_report_path}")
            if verbose:
                report_content = p.read_text(encoding="utf-8")
                console.print(report_content)
        else:
            console.print(
                f"\n[bold]PoC Report:[/bold] {poc_report_path} [yellow](not written)[/yellow]"
            )

    if result.get("gitlab_repo_url"):
        console.print(f"\n[bold]GitLab:[/bold] {result['gitlab_repo_url']}")

    if result.get("routes"):
        console.print(f"\n[bold]Routes:[/bold]")
        for route in result["routes"]:
            console.print(f"  - {route}")

    if result.get("error"):
        console.print(f"\n[bold red]Error:[/bold red] {result['error']}")


@app.command()
def graph(
    format: Annotated[
        str, typer.Option("--format", "-f", help="Output format: mermaid or ascii")
    ] = "mermaid",
) -> None:
    """Print the AutoPoC LangGraph state graph structure."""
    import warnings

    warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")

    graph_obj = build_graph()
    compiled_graph = graph_obj.get_graph()

    if format == "mermaid":
        mermaid_data = compiled_graph.draw_mermaid()
        mermaid_data = mermaid_data.replace("&nbsp;", " ")
        console.print(mermaid_data)
    elif format == "ascii":
        console.print(compiled_graph.draw_ascii())
    else:
        console.print(f"[bold red]Unsupported format:[/bold red] {format}")
        raise typer.Exit(code=1)


@app.command()
def run(
    name: Annotated[str, typer.Option("--name", "-n", help="Project name for the PoC")],
    repo: Annotated[str, typer.Option("--repo", "-r", help="GitHub repository URL")],
    model: Annotated[
        str | None, typer.Option("--model", "-m", help="LLM model name to override config")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
    skip_validation: Annotated[
        bool,
        typer.Option("--skip-validation", help="Skip credential validation at startup"),
    ] = False,
) -> None:
    """Run the full AutoPoC pipeline: intake, fork, containerize, build, deploy."""

    # Set up centralized logging
    setup_logging(verbose=verbose, console=console)

    # Load and validate config
    try:
        config = load_config()
        if model:
            config.llm_model = model
    except ValidationError as e:
        console.print("[bold red]Configuration error:[/bold red]")
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            console.print(f"  - {field}: {error['msg']}")
        raise typer.Exit(code=1)

    # Display config summary
    console.print("\n[bold]AutoPoC Configuration[/bold]")
    config_table = Table(show_header=True, header_style="bold cyan")
    config_table.add_column("Setting", style="dim")
    config_table.add_column("Value")
    for key, value in config.masked_summary().items():
        config_table.add_row(key, value)
    console.print(config_table)

    # Validate credentials (fail-fast)
    if not skip_validation:
        console.print()
        all_ok = validate_credentials(config, console=console, fail_fast=False)
        if not all_ok:
            console.print(
                "\n[bold yellow]Warning:[/bold yellow] Some credential checks failed. "
                "The pipeline may fail mid-run. Use --skip-validation to bypass."
            )
            # Don't hard-fail — let the user decide. Cred checks can fail
            # for non-critical reasons (e.g., Quay on localhost without TLS).

    # Generate thread ID for checkpointing
    thread_id = _generate_thread_id(name)

    # Build initial state
    initial_state: PoCState = {
        "project_name": name,
        "source_repo_url": repo,
        "current_phase": PoCPhase.INTAKE,
        "error": None,
        "messages": [],
        "gitlab_repo_url": None,
        "local_clone_path": None,
        "repo_summary": "",
        "components": [],
        "has_helm_chart": False,
        "has_kustomize": False,
        "has_compose": False,
        "existing_ci_cd": None,
        "repo_digest": "",
        "poc_plan": "",
        "poc_plan_path": "",
        "poc_plan_error": None,
        "poc_scenarios": [],
        "poc_infrastructure": {},
        "poc_type": "",
        "built_images": [],
        "build_retries": 0,
        "deployed_resources": [],
        "routes": [],
        "deploy_retries": 0,
        "poc_results": [],
        "poc_script_path": "",
        "poc_report_path": "",
    }

    console.print(
        Panel(
            f"[bold]Project:[/bold] {name}\n"
            f"[bold]Source:[/bold]  {repo}\n"
            f"[bold]Thread:[/bold] {thread_id}",
            title="AutoPoC Run",
            border_style="green",
        )
    )

    # Build and run the graph with checkpointer
    checkpointer = _get_checkpointer(config.work_dir)
    compiled_graph = build_graph(checkpointer=checkpointer)

    console.print("[bold cyan]Starting pipeline...[/bold cyan]")
    start_time = time.time()

    try:
        result = asyncio.run(
            compiled_graph.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": thread_id}},
            )
        )
    except Exception as e:
        elapsed = time.time() - start_time
        console.print(f"\n[bold red]Pipeline failed[/bold red] after {elapsed:.1f}s: {e}")
        if verbose:
            console.print_exception(show_locals=True)
        else:
            console.print("Run with --verbose to see the full traceback.")
        console.print(f"[dim]Thread ID: {thread_id}[/dim]")
        raise typer.Exit(code=1)

    elapsed = time.time() - start_time

    # Print results
    phase = result.get("current_phase", "unknown")
    if result.get("error"):
        console.print(
            Panel(
                f"[bold red]Pipeline finished with error[/bold red] ({elapsed:.1f}s)\n"
                f"Phase: {phase}",
                border_style="red",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold green]Pipeline complete[/bold green] ({elapsed:.1f}s)\nPhase: {phase}",
                border_style="green",
            )
        )

    _print_results(result, verbose=verbose)

    console.print(f"\n[dim]Thread ID: {thread_id}[/dim]")


@app.command()
def resume(
    thread_id: Annotated[
        str, typer.Option("--thread-id", "-t", help="Thread ID of a previous run")
    ],
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
) -> None:
    """Resume a previously interrupted pipeline run from its last checkpoint."""

    setup_logging(verbose=verbose, console=console)

    try:
        config = load_config()
    except ValidationError as e:
        console.print("[bold red]Configuration error:[/bold red]")
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            console.print(f"  - {field}: {error['msg']}")
        raise typer.Exit(code=1)

    checkpointer = _get_checkpointer(config.work_dir)

    # Check if we can actually resume (requires SqliteSaver)
    from langgraph.checkpoint.memory import MemorySaver

    if isinstance(checkpointer, MemorySaver):
        console.print(
            "[bold red]Cannot resume:[/bold red] No persistent checkpointer available.\n"
            "Install langgraph-checkpoint-sqlite: pip install langgraph-checkpoint-sqlite"
        )
        raise typer.Exit(code=1)

    compiled_graph = build_graph(checkpointer=checkpointer)

    # Try to get the latest state for this thread
    checkpoint_config = {"configurable": {"thread_id": thread_id}}
    state = compiled_graph.get_state(checkpoint_config)

    if state is None or not state.values:
        console.print(f"[bold red]No checkpoint found for thread ID:[/bold red] {thread_id}")
        raise typer.Exit(code=1)

    current_phase = state.values.get("current_phase", "unknown")
    project_name = state.values.get("project_name", "unknown")

    console.print(
        Panel(
            f"[bold]Resuming:[/bold] {project_name}\n"
            f"[bold]Thread:[/bold]  {thread_id}\n"
            f"[bold]Phase:[/bold]   {current_phase}",
            title="AutoPoC Resume",
            border_style="yellow",
        )
    )

    start_time = time.time()

    try:
        result = asyncio.run(compiled_graph.ainvoke(None, config=checkpoint_config))
    except Exception as e:
        elapsed = time.time() - start_time
        console.print(f"\n[bold red]Resumed pipeline failed[/bold red] after {elapsed:.1f}s: {e}")
        if verbose:
            console.print_exception(show_locals=True)
        raise typer.Exit(code=1)

    elapsed = time.time() - start_time
    console.print(
        Panel(
            f"[bold green]Pipeline complete[/bold green] ({elapsed:.1f}s)",
            border_style="green",
        )
    )
    _print_results(result, verbose=verbose)


@app.command(name="status")
def show_status(
    thread_id: Annotated[str, typer.Option("--thread-id", "-t", help="Thread ID to check")],
) -> None:
    """Show the current state of a pipeline run."""

    setup_logging(verbose=False, console=console)

    try:
        config = load_config()
    except ValidationError as e:
        console.print("[bold red]Configuration error:[/bold red]")
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            console.print(f"  - {field}: {error['msg']}")
        raise typer.Exit(code=1)

    checkpointer = _get_checkpointer(config.work_dir)
    from langgraph.checkpoint.memory import MemorySaver

    if isinstance(checkpointer, MemorySaver):
        console.print(
            "[bold red]No persistent checkpointer available.[/bold red]\n"
            "Install langgraph-checkpoint-sqlite: pip install langgraph-checkpoint-sqlite"
        )
        raise typer.Exit(code=1)

    compiled_graph = build_graph(checkpointer=checkpointer)
    state = compiled_graph.get_state({"configurable": {"thread_id": thread_id}})

    if state is None or not state.values:
        console.print(f"[bold red]No checkpoint found for thread ID:[/bold red] {thread_id}")
        raise typer.Exit(code=1)

    values = state.values

    table = Table(title=f"Run Status: {thread_id}", show_header=True, header_style="bold cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Project", values.get("project_name", "?"))
    table.add_row("Source", values.get("source_repo_url", "?"))
    table.add_row("Phase", str(values.get("current_phase", "?")))
    table.add_row("Error", values.get("error") or "None")
    table.add_row("PoC Type", values.get("poc_type") or "-")
    table.add_row("Components", str(len(values.get("components", []))))
    table.add_row("Built Images", str(len(values.get("built_images", []))))
    table.add_row("Deployed Resources", str(len(values.get("deployed_resources", []))))
    table.add_row("Routes", ", ".join(values.get("routes", [])) or "-")
    table.add_row(
        "PoC Results",
        f"{sum(1 for r in values.get('poc_results', []) if r.get('status') == 'pass')}"
        f"/{len(values.get('poc_results', []))} passed"
        if values.get("poc_results")
        else "-",
    )
    table.add_row("Build Retries", str(values.get("build_retries", 0)))
    table.add_row("Deploy Retries", str(values.get("deploy_retries", 0)))

    console.print(table)

    # Show next steps
    next_nodes = state.next
    if next_nodes:
        console.print(f"\n[bold]Next node(s):[/bold] {', '.join(next_nodes)}")
        console.print(f"[dim]Resume with: autopoc resume --thread-id {thread_id}[/dim]")
    else:
        console.print("\n[dim]Run is complete (no pending nodes).[/dim]")


if __name__ == "__main__":
    app()
