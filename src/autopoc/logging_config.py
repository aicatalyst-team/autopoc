"""Centralized logging configuration for AutoPoC.

Sets up structured logging with Rich for both verbose and normal modes.
In normal mode, only WARNING+ messages are shown.
In verbose mode, INFO+ messages are shown with rich formatting.
"""

import logging
import os

from rich.console import Console
from rich.logging import RichHandler


def setup_logging(verbose: bool = False, console: Console | None = None) -> None:
    """Configure logging for the AutoPoC application.

    Args:
        verbose: If True, show INFO-level logs from autopoc modules.
                 If False, only WARNING+ from autopoc, suppressed externals.
        console: Rich console to use. If None, creates a new stderr console.
    """
    if console is None:
        console = Console(stderr=True)

    level = logging.DEBUG if verbose else logging.WARNING

    handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        show_path=verbose,
        show_time=verbose,
        markup=True,
    )
    handler.setLevel(level)

    # Configure root logger minimally
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    # Remove any existing handlers to avoid duplicates on re-init
    root.handlers.clear()
    root.addHandler(handler)

    # Set autopoc loggers to the appropriate level
    autopoc_logger = logging.getLogger("autopoc")
    autopoc_logger.setLevel(logging.DEBUG if verbose else logging.WARNING)

    # Suppress noisy external loggers
    for noisy in ("httpx", "httpcore", "urllib3", "google", "grpc"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # LangChain/LangGraph tracing: if LANGCHAIN_TRACING_V2 is set,
    # LangSmith tracing is automatically enabled by langchain-core.
    # Set a default project name if not already set.
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
        if not os.environ.get("LANGCHAIN_PROJECT"):
            os.environ["LANGCHAIN_PROJECT"] = "autopoc"
        if verbose:
            logging.getLogger("autopoc").info(
                "LangSmith tracing enabled (project: %s)",
                os.environ["LANGCHAIN_PROJECT"],
            )
