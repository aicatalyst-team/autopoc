"""LangGraph orchestration — wires agents into a pipeline.

Defines the StateGraph with all agent nodes and edges, including
parallel fan-out/fan-in for PoC planning, conditional routing for
retry loops, and the PoC execution/report tail.

Full graph:
    intake → [poc_plan ∥ fork] → containerize ⟲ build → deploy → apply ⟲ poc_execute → poc_report → END

The deploy/apply split mirrors containerize/build:
- containerize generates Dockerfiles, build runs podman
- deploy generates K8s manifests, apply runs kubectl
"""

import logging

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from autopoc.agents.apply import apply_agent
from autopoc.agents.build import build_agent
from autopoc.agents.containerize import containerize_agent
from autopoc.agents.deploy import deploy_agent
from autopoc.agents.fork import fork_agent
from autopoc.agents.intake import intake_agent
from autopoc.agents.poc_execute import poc_execute_agent
from autopoc.agents.poc_plan import poc_plan_agent
from autopoc.agents.poc_report import poc_report_agent
from autopoc.config import load_config
from autopoc.state import PoCPhase, PoCState

logger = logging.getLogger(__name__)


def route_after_build(state: PoCState) -> str:
    """Determine the next step after a build attempt.

    If the build succeeded, proceed to deploy.
    If the build failed but we have retries left, loop back to containerize to fix the Dockerfile.
    If retries are exhausted or it's a permanent failure, fail.
    """
    error = state.get("error")
    if error is None:
        return "deploy"

    # Check if this is a permanent failure (shouldn't retry)
    if "permanent" in error.lower() or "cannot be fixed by retrying" in error.lower():
        logger.error("Build failed with permanent error. Failing pipeline.")
        logger.error("Error: %s", error[:200])  # Log first 200 chars
        return "failed"

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


def route_after_apply(state: PoCState) -> str:
    """Determine the next step after an apply attempt.

    If apply succeeded (no error), proceed to PoC execution.
    If apply failed but we have retries left, loop back to deploy to fix manifests,
    then re-apply.
    If retries are exhausted, fail.
    """
    error = state.get("error")

    # Success: no error → proceed to PoC execution
    if error is None:
        return "poc_execute"

    # Failed: check if we can retry
    config = load_config()
    retries = state.get("deploy_retries", 0)

    if retries < config.max_deploy_retries:
        logger.warning(
            "Apply failed (retry %d/%d). Looping back to deploy to fix manifests.",
            retries,
            config.max_deploy_retries,
        )
        return "deploy"

    logger.error("Apply failed after %d retries. Failing pipeline.", retries)
    return "failed"


def build_graph(checkpointer=None) -> CompiledStateGraph:
    """Build and compile the AutoPoC pipeline graph.

    Full graph:
        intake → [poc_plan ∥ fork] → containerize ⟲ build → deploy → apply ⟲ poc_execute → poc_report → END

    Key features:
    - Parallel fan-out: after intake, poc_plan and fork run concurrently
    - Fan-in: containerize waits for both poc_plan and fork to complete
    - Build retry loop: build failure → containerize → build (up to max_build_retries)
    - Deploy/Apply split: deploy generates manifests, apply runs kubectl
    - Apply retry loop: apply failure → deploy (fix manifests) → apply (up to max_deploy_retries)
    - PoC tail: after successful apply, execute tests and generate report

    Args:
        checkpointer: Optional LangGraph checkpointer for state persistence.
            Enables resuming interrupted runs. Pass a SqliteSaver or MemorySaver.

    Returns:
        Compiled LangGraph ready for invocation.
    """
    graph = StateGraph(PoCState)

    # Add nodes
    graph.add_node("intake", intake_agent)
    graph.add_node("poc_plan", poc_plan_agent)
    graph.add_node("fork", fork_agent)
    graph.add_node("containerize", containerize_agent)
    graph.add_node("build", build_agent)
    graph.add_node("deploy", deploy_agent)
    graph.add_node("apply", apply_agent)
    graph.add_node("poc_execute", poc_execute_agent)
    graph.add_node("poc_report", poc_report_agent)

    # Wire edges
    graph.set_entry_point("intake")

    # Fan-out: intake feeds both poc_plan and fork in parallel
    graph.add_edge("intake", "poc_plan")
    graph.add_edge("intake", "fork")

    # Fan-in: both poc_plan and fork must complete before containerize runs
    graph.add_edge("poc_plan", "containerize")
    graph.add_edge("fork", "containerize")

    # containerize → build
    graph.add_edge("containerize", "build")

    # Conditional routing after build
    graph.add_conditional_edges(
        "build",
        route_after_build,
        {
            "deploy": "deploy",
            "containerize": "containerize",  # retry loop
            "failed": END,
        },
    )

    # deploy → apply (deploy generates manifests, apply runs kubectl)
    graph.add_edge("deploy", "apply")

    # Conditional routing after apply
    graph.add_conditional_edges(
        "apply",
        route_after_apply,
        {
            "poc_execute": "poc_execute",  # success → run PoC tests
            "deploy": "deploy",  # retry: go back to deploy to fix manifests
            "failed": END,
        },
    )

    # PoC execution → report → END
    graph.add_edge("poc_execute", "poc_report")
    graph.add_edge("poc_report", END)

    # Compile (with optional checkpointer for state persistence)
    compiled = graph.compile(checkpointer=checkpointer)
    logger.info(
        "Graph compiled: intake → [poc_plan ∥ fork] → containerize ⟲ build → deploy → apply ⟲ poc_execute → poc_report → END"
    )
    if checkpointer is not None:
        logger.info("Checkpointer enabled: %s", type(checkpointer).__name__)

    return compiled
