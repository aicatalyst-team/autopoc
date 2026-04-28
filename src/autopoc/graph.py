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
from autopoc.state import PoCState

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


# Ordered list of pipeline phases for --stop-after validation.
# This matches the logical pipeline order (not the graph topology).
PIPELINE_PHASES = [
    "intake",
    "poc_plan",
    "fork",
    "containerize",
    "build",
    "deploy",
    "apply",
    "poc_execute",
    "poc_report",
]


def build_graph(checkpointer=None, *, stop_after: str | None = None) -> CompiledStateGraph:
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
        stop_after: Optional phase name to stop after (e.g. "build").
            The pipeline will end after this phase completes instead of
            continuing to the next phase. Valid values: see PIPELINE_PHASES.

    Returns:
        Compiled LangGraph ready for invocation.
    """
    if stop_after and stop_after not in PIPELINE_PHASES:
        raise ValueError(
            f"Invalid --stop-after value: '{stop_after}'. "
            f"Valid phases: {', '.join(PIPELINE_PHASES)}"
        )

    def _is_active(phase: str) -> bool:
        """Check if a phase should be included in the graph."""
        if stop_after is None:
            return True
        return PIPELINE_PHASES.index(phase) <= PIPELINE_PHASES.index(stop_after)

    graph = StateGraph(PoCState)

    # Add nodes — only include phases up to and including stop_after
    graph.add_node("intake", intake_agent)
    if _is_active("poc_plan"):
        graph.add_node("poc_plan", poc_plan_agent)
    if _is_active("fork"):
        graph.add_node("fork", fork_agent)
    if _is_active("containerize"):
        graph.add_node("containerize", containerize_agent)
    if _is_active("build"):
        graph.add_node("build", build_agent)
    if _is_active("deploy"):
        graph.add_node("deploy", deploy_agent)
    if _is_active("apply"):
        graph.add_node("apply", apply_agent)
    if _is_active("poc_execute"):
        graph.add_node("poc_execute", poc_execute_agent)
    if _is_active("poc_report"):
        graph.add_node("poc_report", poc_report_agent)

    # Wire edges
    graph.set_entry_point("intake")

    if stop_after == "intake":
        # Stop immediately after intake
        graph.add_edge("intake", END)
    else:
        # Conditional fan-out after intake: proceed to poc_plan + fork if success, END if failure
        if stop_after in ("poc_plan", "fork"):
            # Only fan out to the phases that are active
            targets = {}
            if _is_active("poc_plan"):
                targets["poc_plan"] = "poc_plan"
            if _is_active("fork"):
                targets["fork"] = "fork"
            targets["failed"] = END

            graph.add_conditional_edges("intake", route_after_intake, targets)

            # Stop after the active phase(s)
            if _is_active("poc_plan"):
                graph.add_edge("poc_plan", END)
            if _is_active("fork"):
                graph.add_edge("fork", END)
        else:
            # Normal fan-out
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

            if stop_after == "containerize":
                graph.add_edge("containerize", END)
            else:
                # containerize → build
                graph.add_edge("containerize", "build")

                if stop_after == "build":
                    # Stop after build — route success to END, but still allow retry loop
                    graph.add_conditional_edges(
                        "build",
                        route_after_build,
                        {
                            "deploy": END,  # success → stop instead of deploying
                            "containerize": "containerize",  # retry loop still works
                            "failed": END,
                        },
                    )
                else:
                    # Normal build routing
                    graph.add_conditional_edges(
                        "build",
                        route_after_build,
                        {
                            "deploy": "deploy",
                            "containerize": "containerize",
                            "failed": END,
                        },
                    )

                    if stop_after == "deploy":
                        graph.add_edge("deploy", END)
                    else:
                        # deploy → apply
                        graph.add_edge("deploy", "apply")

                        if stop_after == "apply":
                            # Stop after apply — route success to END, keep retry loops
                            graph.add_conditional_edges(
                                "apply",
                                route_after_apply,
                                {
                                    "poc_execute": END,  # success → stop
                                    "deploy": "deploy",
                                    "containerize": "containerize",
                                    "failed": END,
                                },
                            )
                        else:
                            # Normal apply routing
                            graph.add_conditional_edges(
                                "apply",
                                route_after_apply,
                                {
                                    "poc_execute": "poc_execute",
                                    "deploy": "deploy",
                                    "containerize": "containerize",
                                    "failed": END,
                                },
                            )

                            if stop_after == "poc_execute":
                                graph.add_edge("poc_execute", END)
                            else:
                                # Full pipeline
                                graph.add_edge("poc_execute", "poc_report")
                                graph.add_edge("poc_report", END)

    # Compile (with optional checkpointer for state persistence)
    compiled = graph.compile(checkpointer=checkpointer)

    if stop_after:
        logger.info("Graph compiled with --stop-after=%s", stop_after)
    else:
        logger.info(
            "Graph compiled: intake → [poc_plan ∥ fork] → containerize ⟲ build → deploy ⟲ apply → poc_execute → poc_report → END"
        )
    if checkpointer is not None:
        logger.info("Checkpointer enabled: %s", type(checkpointer).__name__)

    return compiled
