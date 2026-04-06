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
        "built_images": [],
        "build_retries": 0,
        "deployed_resources": [],
        "routes": [],
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

    if result.get("gitlab_repo_url"):
        console.print(f"\n[bold]GitLab:[/bold] {result['gitlab_repo_url']}")

    if result.get("error"):
        console.print(f"\n[bold red]Error:[/bold red] {result['error']}")


if __name__ == "__main__":
    app()
