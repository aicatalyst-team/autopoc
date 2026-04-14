"""CLI entry point for AutoPoC."""

import asyncio
import logging
import time
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from autopoc.config import load_config
from autopoc.graph import build_graph
from autopoc.state import PoCPhase, PoCState

app = typer.Typer(
    name="autopoc",
    help="AutoPoC — Automate PoC deployments on OpenShift AI",
    no_args_is_help=True,
)
console = Console()


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
) -> None:
    """Run the full AutoPoC pipeline: intake, fork, containerize, build, deploy."""

    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=True, console=console, show_path=True)],
        )
        # Suppress noisy external loggers
        logging.getLogger("httpx").setLevel(logging.WARNING)

    # Load and validate config
    try:
        config = load_config()
        # Override config model if explicitly passed via CLI
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
        "poc_plan": "",
        "poc_plan_path": "",
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

    console.print(f"\n[bold green]Project:[/bold green] {name}")
    console.print(f"[bold green]Source:[/bold green]  {repo}")
    console.print()

    # Build and run the graph
    graph = build_graph()

    console.print("[bold cyan]Starting pipeline...[/bold cyan]")
    start_time = time.time()

    try:
        result = asyncio.run(graph.ainvoke(initial_state))
    except Exception as e:
        console.print(f"\n[bold red]Pipeline failed:[/bold red] {e}")
        if verbose:
            console.print_exception(show_locals=True)
        else:
            console.print("\nRun with --verbose to see the full traceback.")
        raise typer.Exit(code=1)

    elapsed = time.time() - start_time

    # Print results
    console.print(f"\n[bold green]Pipeline complete[/bold green] ({elapsed:.1f}s)")
    console.print(f"[bold]Phase:[/bold] {result.get('current_phase', 'unknown')}")

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
            # Full plan in verbose mode
            console.print("\n[bold]PoC Plan:[/bold]")
            console.print(poc_plan_content)
        else:
            # Show a preview: objectives/first meaningful section
            preview = _extract_plan_preview(poc_plan_content)
            if preview:
                console.print(f"\n[bold]PoC Plan Summary:[/bold]")
                console.print(preview)

    if poc_plan_path:
        from pathlib import Path as _Path

        if _Path(poc_plan_path).exists():
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

    # PoC scenarios summary (always show if plan has scenarios)
    poc_scenarios = result.get("poc_scenarios", [])
    if poc_scenarios and not poc_results:
        # Show planned scenarios if we haven't reached execution yet
        console.print(f"\n[bold]Planned Test Scenarios ({len(poc_scenarios)}):[/bold]")
        for s in poc_scenarios:
            endpoint = s.get("endpoint", "")
            endpoint_str = f" ({endpoint})" if endpoint else ""
            console.print(f"  - {s.get('name', '?')}: {s.get('description', '')}{endpoint_str}")

    poc_report_path = result.get("poc_report_path", "")
    if poc_report_path:
        from pathlib import Path as _Path

        if _Path(poc_report_path).exists():
            console.print(f"\n[bold]PoC Report:[/bold] {poc_report_path}")
            if verbose:
                report_content = _Path(poc_report_path).read_text(encoding="utf-8")
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


if __name__ == "__main__":
    app()
