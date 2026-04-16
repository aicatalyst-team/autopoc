"""LangGraph orchestration — wires agents into a pipeline.

Defines the StateGraph with all agent nodes and edges, including
parallel fan-out/fan-in for PoC planning, conditional routing for
retry loops, and the PoC execution/report tail.

Full graph:
    intake → [poc_plan ∥ fork] → containerize ⟲ build → deploy ⟲ apply → poc_execute → poc_report → END
                                       ↑                          │
                                       └──────────────────────────┘  (outer loop: container fix)

The deploy/apply split mirrors containerize/build:
- containerize generates Dockerfiles, build runs podman
- deploy generates K8s manifests, apply runs kubectl

When apply detects a container-level failure (crash, missing dep) rather than
a manifest issue, it can escalate to containerize via the outer loop.
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


def route_after_intake(state: PoCState) -> list[str]:
    """Determine next steps after intake.

    If intake succeeded, fan out to both poc_plan and fork in parallel.
    If intake failed (e.g., 0 components, step exhaustion), stop the pipeline.
    """
    error = state.get("error")
    if error:
        logger.error("Intake failed: %s. Stopping pipeline.", error)
        return ["failed"]

    # Fan-out to both poc_plan and fork
    return ["poc_plan", "fork"]


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
    If apply failed, the apply agent's triage classified the error as one of:
    - fix-manifest  → loop back to deploy (inner loop)
    - fix-dockerfile / experiment → escalate to containerize (outer loop)

    Each loop has its own retry counter:
    - deploy_retries for the inner deploy↔apply loop
    - container_fix_retries for the outer apply→containerize escalation
    """
    error = state.get("error")

    # Success: no error → proceed to PoC execution
    if error is None:
        return "poc_execute"

    config = load_config()
    action = state.get("container_fix_action")

    # Container-level fix: escalate to containerize (outer loop)
    if action in ("fix-dockerfile", "experiment"):
        container_fix_retries = state.get("container_fix_retries", 0)
        if container_fix_retries < config.max_container_fix_retries:
            logger.warning(
                "Apply detected container issue (action=%s, retry %d/%d). "
                "Escalating to containerize.",
                action,
                container_fix_retries,
                config.max_container_fix_retries,
            )
            return "containerize"
        logger.error(
            "Container fix retries exhausted (%d/%d). Failing pipeline.",
            container_fix_retries,
            config.max_container_fix_retries,
        )
        return "failed"

    # Manifest-level fix: loop back to deploy (inner loop)
    retries = state.get("deploy_retries", 0)
    if retries < config.max_deploy_retries:
        logger.warning(
            "Apply failed (retry %d/%d). Looping back to deploy to fix manifests.",
            retries,
            config.max_deploy_retries,
        )
        return "deploy"

    # Deploy retries exhausted — as a last resort, check if this might be a
    # container issue that the triage missed (default was fix-manifest)
    container_fix_retries = state.get("container_fix_retries", 0)
    if container_fix_retries < config.max_container_fix_retries:
        logger.warning(
            "Deploy retries exhausted but container fix available (%d/%d). "
            "Escalating to containerize as last resort.",
            container_fix_retries,
            config.max_container_fix_retries,
        )
        return "containerize"

    logger.error(
        "Apply failed after %d deploy retries and %d container fix retries. Failing pipeline.",
        retries,
        container_fix_retries,
    )
    return "failed"


def build_graph(checkpointer=None) -> CompiledStateGraph:
    """Build and compile the AutoPoC pipeline graph.

    Full graph:
        intake → [poc_plan ∥ fork] → containerize ⟲ build → deploy ⟲ apply → poc_execute → poc_report → END
                                          ↑                          │
                                          └──────────────────────────┘  (outer loop)

    Key features:
    - Parallel fan-out: after intake, poc_plan and fork run concurrently
    - Fan-in: containerize waits for both poc_plan and fork to complete
    - Build retry loop: build failure → containerize → build (up to max_build_retries)
    - Deploy/Apply split: deploy generates manifests, apply runs kubectl
    - Apply inner loop: manifest issue → deploy (fix manifests) → apply (up to max_deploy_retries)
    - Apply outer loop: container issue → containerize → build → deploy → apply
      (up to max_container_fix_retries, resets deploy_retries on each escalation)
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

    # Conditional fan-out after intake: proceed to poc_plan + fork if success, END if failure
    graph.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "poc_plan": "poc_plan",
            "fork": "fork",
            "failed": END,
        },
    )

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
            "deploy": "deploy",  # inner retry: fix manifests
            "containerize": "containerize",  # outer loop: fix container image
            "failed": END,
        },
    )

    # PoC execution → report → END
    graph.add_edge("poc_execute", "poc_report")
    graph.add_edge("poc_report", END)

    # Compile (with optional checkpointer for state persistence)
    compiled = graph.compile(checkpointer=checkpointer)
    logger.info(
        "Graph compiled: intake → [poc_plan ∥ fork] → containerize ⟲ build → deploy ⟲ apply → poc_execute → poc_report → END"
    )
    if checkpointer is not None:
        logger.info("Checkpointer enabled: %s", type(checkpointer).__name__)

    return compiled
