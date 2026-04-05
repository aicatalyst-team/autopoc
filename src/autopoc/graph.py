"""LangGraph orchestration — wires agents into a pipeline.

Defines the StateGraph with all agent nodes and edges, including
conditional routing for retry loops.
"""

import logging

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from autopoc.agents.build import build_agent
from autopoc.agents.containerize import containerize_agent
from autopoc.agents.fork import fork_agent
from autopoc.agents.intake import intake_agent
from autopoc.config import load_config
from autopoc.state import PoCPhase, PoCState

logger = logging.getLogger(__name__)


def route_after_build(state: PoCState) -> str:
    """Determine the next step after a build attempt.

    If the build succeeded, proceed to deploy.
    If the build failed but we have retries left, loop back to containerize to fix the Dockerfile.
    If retries are exhausted, fail.
    """
    if state.get("error") is None:
        return "deploy"

    config = load_config()
    retries = state.get("build_retries", 0)

    if retries < config.max_build_retries:
        logger.warning(
            "Build failed (retry %d/%d). Looping back to containerize.",
            retries,
            config.max_build_retries,
        )
        return "containerize"

    logger.error("Build failed after %d retries. Failing pipeline.", retries)
    return "failed"


def build_graph() -> CompiledStateGraph:
    """Build and compile the AutoPoC pipeline graph.

    Current graph (Phase 2):
        intake → fork → containerize → END

    Future phases will add build and deploy nodes with conditional edges.

    Returns:
        Compiled LangGraph ready for invocation.
    """
    graph = StateGraph(PoCState)

    # Add nodes
    graph.add_node("intake", intake_agent)
    graph.add_node("fork", fork_agent)
    graph.add_node("containerize", containerize_agent)
    graph.add_node("build", build_agent)

    # Wire edges
    graph.set_entry_point("intake")
    graph.add_edge("intake", "fork")
    graph.add_edge("fork", "containerize")
    graph.add_edge("containerize", "build")

    # Conditional routing after build
    # We don't have deploy yet, so map deploy to END
    graph.add_conditional_edges(
        "build",
        route_after_build,
        {
            "deploy": END,
            "containerize": "containerize",
            "failed": END,
        },
    )

    # Compile
    compiled = graph.compile()
    logger.info("Graph compiled: intake → fork → containerize ⟲ build → END")

    return compiled
