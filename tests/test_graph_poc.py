"""Integration tests for the full PoC-aware graph.

Tests the complete graph with all new Phase 7 nodes:
- Parallel fan-out: intake → [poc_plan ∥ fork]
- Fan-in: [poc_plan, fork] → containerize
- Deploy/Apply split: deploy generates manifests, apply runs kubectl
- PoC tail: apply → poc_execute → poc_report → END
- Failure modes: apply failure routes back to deploy, exhausted retries → END
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from autopoc.state import PoCPhase, PoCState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo that looks like a Python Flask app."""
    repo = tmp_path / "sample-repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    (repo / "app.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
    (repo / "requirements.txt").write_text("flask==3.0.0\n")
    (repo / "README.md").write_text("# Sample App\n")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def gitlab_bare(tmp_path: Path) -> Path:
    """Create a bare git repo to act as GitLab remote."""
    bare = tmp_path / "gitlab.git"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


@pytest.fixture
def env_patch(tmp_path: Path) -> dict:
    """Environment variables for config."""
    return {
        "ANTHROPIC_API_KEY": "sk-test",
        "GITLAB_URL": "https://gitlab.test",
        "GITLAB_TOKEN": "tok",
        "GITLAB_GROUP": "poc",
        "QUAY_ORG": "org",
        "QUAY_TOKEN": "tok",
        "OPENSHIFT_API_URL": "https://api.test:6443",
        "OPENSHIFT_TOKEN": "tok",
        "WORK_DIR": str(tmp_path / "work"),
        "MAX_BUILD_RETRIES": "2",
        "MAX_DEPLOY_RETRIES": "1",
    }


@pytest.fixture
def initial_state(sample_repo: Path) -> PoCState:
    """Initial state for the graph."""
    return PoCState(
        project_name="sample-app",
        source_repo_url=str(sample_repo),
        current_phase=PoCPhase.INTAKE,
        error=None,
        messages=[],
        gitlab_repo_url=None,
        local_clone_path=None,
        repo_summary="",
        components=[],
        has_helm_chart=False,
        has_kustomize=False,
        has_compose=False,
        existing_ci_cd=None,
        poc_plan="",
        poc_plan_path="",
        poc_scenarios=[],
        poc_infrastructure={},
        poc_type="",
        built_images=[],
        build_retries=0,
        deployed_resources=[],
        routes=[],
        deploy_retries=0,
        poc_results=[],
        poc_script_path="",
        poc_report_path="",
    )


# ---------------------------------------------------------------------------
# Mock agent factories
# ---------------------------------------------------------------------------


def _mock_intake_agent():
    """Mock intake that returns a canned Flask analysis."""

    async def _intake(state, **kwargs):
        from autopoc.tools.git_tools import git_clone

        clone_path = state.get("local_clone_path")
        if not clone_path or not Path(clone_path).exists():
            source = state.get("source_repo_url", "")
            from autopoc.config import load_config

            config = load_config()
            work_dir = Path(config.work_dir) / state.get("project_name", "unknown")
            clone_path = git_clone.invoke({"url": source, "dest": str(work_dir)})

        return {
            "current_phase": PoCPhase.INTAKE,
            "local_clone_path": str(clone_path),
            "repo_summary": "A simple Flask web application.",
            "components": [
                {
                    "name": "app",
                    "language": "python",
                    "build_system": "pip",
                    "entry_point": "app.py",
                    "port": 5000,
                    "existing_dockerfile": None,
                    "is_ml_workload": False,
                    "source_dir": ".",
                }
            ],
            "has_helm_chart": False,
            "has_kustomize": False,
            "has_compose": False,
            "existing_ci_cd": None,
        }

    return _intake


def _mock_poc_plan_agent():
    """Mock poc_plan that returns a web-app classification."""

    async def _poc_plan(state, **kwargs):
        clone_path = state.get("local_clone_path", "")
        poc_plan_path = str(Path(clone_path) / "poc-plan.md") if clone_path else ""
        # Write the plan file if clone_path exists
        if clone_path and Path(clone_path).exists():
            (Path(clone_path) / "poc-plan.md").write_text(
                "# PoC Plan: sample-app\n\n## Project Classification\nType: web-app\n"
            )
        # NOTE: no current_phase here — runs in parallel with fork
        return {
            "poc_plan": "# PoC Plan\nDeploy and test Flask app endpoints.",
            "poc_plan_path": poc_plan_path,
            "poc_scenarios": [
                {
                    "name": "health-check",
                    "description": "Verify the Flask app responds",
                    "type": "http",
                    "endpoint": "/",
                    "input_data": None,
                    "expected_behavior": "Returns 200 OK",
                    "timeout_seconds": 30,
                },
                {
                    "name": "api-test",
                    "description": "Test the API endpoint",
                    "type": "http",
                    "endpoint": "/api/status",
                    "input_data": None,
                    "expected_behavior": "Returns JSON with status",
                    "timeout_seconds": 15,
                },
            ],
            "poc_infrastructure": {
                "needs_inference_server": False,
                "needs_vector_db": False,
                "needs_gpu": False,
                "needs_pvc": False,
                "resource_profile": "small",
                "sidecar_containers": [],
                "extra_env_vars": {},
                "odh_components": [],
            },
            "poc_type": "web-app",
        }

    return _poc_plan


def _mock_fork_agent(gitlab_bare: Path):
    """Mock fork that pushes to a local bare repo."""

    async def _fork(state, **kwargs):
        clone_path = state.get("local_clone_path", "")
        if clone_path and Path(clone_path).exists():
            # Add the bare repo as remote and push
            subprocess.run(
                ["git", "remote", "add", "gitlab", str(gitlab_bare)],
                cwd=clone_path,
                capture_output=True,
            )
            subprocess.run(
                ["git", "push", "gitlab", "--all"],
                cwd=clone_path,
                check=True,
                capture_output=True,
            )
        # NOTE: no current_phase here — runs in parallel with poc_plan
        return {
            "gitlab_repo_url": str(gitlab_bare),
        }

    return _fork


def _mock_containerize_agent():
    """Mock containerize that sets dockerfile path."""

    async def _containerize(state, **kwargs):
        comps = list(state.get("components", []))
        for comp in comps:
            comp["dockerfile_ubi_path"] = "Dockerfile.ubi"
        return {
            "current_phase": PoCPhase.CONTAINERIZE,
            "components": comps,
            "error": None,
        }

    return _containerize


def _mock_build_agent_success():
    """Mock build that always succeeds."""

    async def _build(state, **kwargs):
        project = state.get("project_name", "unknown")
        images = [
            f"quay.io/org/{project}-{c.get('name', 'x')}:latest"
            for c in state.get("components", [])
        ]
        return {
            "current_phase": PoCPhase.BUILD,
            "error": None,
            "built_images": images,
        }

    return _build


def _mock_build_agent_fail_then_succeed():
    """Mock build that fails first, succeeds on retry."""
    calls = []

    async def _build(state, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return {
                "current_phase": PoCPhase.BUILD,
                "error": "Build failed: missing dependency",
                "build_retries": state.get("build_retries", 0) + 1,
            }
        project = state.get("project_name", "unknown")
        images = [
            f"quay.io/org/{project}-{c.get('name', 'x')}:latest"
            for c in state.get("components", [])
        ]
        return {
            "current_phase": PoCPhase.BUILD,
            "error": None,
            "built_images": images,
        }

    return _build


def _mock_deploy_agent_success():
    """Mock deploy that generates manifests successfully."""

    async def _deploy(state, **kwargs):
        return {
            "current_phase": PoCPhase.DEPLOY,
            "error": None,
        }

    return _deploy


def _mock_deploy_agent_fail():
    """Mock deploy that fails manifest generation."""

    async def _deploy(state, **kwargs):
        return {
            "current_phase": PoCPhase.DEPLOY,
            "error": "Manifest generation failed: template error",
            "deploy_retries": state.get("deploy_retries", 0) + 1,
        }

    return _deploy


def _mock_apply_agent_success():
    """Mock apply that deploys resources and creates routes."""

    async def _apply(state, **kwargs):
        return {
            "current_phase": PoCPhase.APPLY,
            "deployed_resources": ["deployment/app", "service/app"],
            "routes": ["http://10.0.0.1:30080"],
            "error": None,
        }

    return _apply


def _mock_apply_agent_fail():
    """Mock apply that always fails (manifest-level error, no container fix)."""

    async def _apply(state, **kwargs):
        return {
            "current_phase": PoCPhase.APPLY,
            "deployed_resources": [],
            "routes": [],
            "error": "Apply failed: namespace not found",
            "deploy_retries": state.get("deploy_retries", 0) + 1,
            # Mark container fix retries as exhausted so the pipeline terminates
            # instead of escalating to containerize indefinitely.
            "container_fix_retries": 999,
            "container_fix_action": None,
        }

    return _apply


def _mock_poc_execute_agent():
    """Mock poc_execute that returns test results."""

    async def _poc_execute(state, **kwargs):
        clone_path = state.get("local_clone_path", "")
        return {
            "current_phase": PoCPhase.POC_EXECUTE,
            "poc_results": [
                {
                    "scenario_name": "health-check",
                    "status": "pass",
                    "output": "OK",
                    "error_message": None,
                    "duration_seconds": 0.5,
                },
                {
                    "scenario_name": "api-test",
                    "status": "fail",
                    "output": "",
                    "error_message": "404 Not Found",
                    "duration_seconds": 1.2,
                },
            ],
            "poc_script_path": f"{clone_path}/poc_test.py" if clone_path else "",
        }

    return _poc_execute


def _mock_poc_report_agent():
    """Mock poc_report that writes a report."""

    async def _poc_report(state, **kwargs):
        clone_path = state.get("local_clone_path", "")
        report_path = f"{clone_path}/poc-report.md" if clone_path else ""
        if clone_path and Path(clone_path).exists():
            (Path(clone_path) / "poc-report.md").write_text(
                "# PoC Report\n\n## Summary\nHealth check passed, API test failed.\n"
            )
        return {
            "current_phase": PoCPhase.POC_REPORT,
            "poc_report_path": report_path,
        }

    return _poc_report


# ---------------------------------------------------------------------------
# Helper: build a custom graph with mock agents
# ---------------------------------------------------------------------------


def _build_test_graph(
    intake_fn,
    poc_plan_fn,
    fork_fn,
    containerize_fn,
    build_fn,
    deploy_fn,
    apply_fn,
    poc_execute_fn,
    poc_report_fn,
):
    """Build the full graph with mock agent functions."""
    from langgraph.graph import StateGraph, END
    from autopoc.graph import route_after_intake, route_after_build, route_after_apply

    sg = StateGraph(PoCState)
    sg.add_node("intake", intake_fn)
    sg.add_node("poc_plan", poc_plan_fn)
    sg.add_node("fork", fork_fn)
    sg.add_node("containerize", containerize_fn)
    sg.add_node("build", build_fn)
    sg.add_node("deploy", deploy_fn)
    sg.add_node("apply", apply_fn)
    sg.add_node("poc_execute", poc_execute_fn)
    sg.add_node("poc_report", poc_report_fn)

    sg.set_entry_point("intake")
    sg.add_conditional_edges(
        "intake",
        route_after_intake,
        {"poc_plan": "poc_plan", "fork": "fork", "failed": END},
    )
    sg.add_edge("poc_plan", "containerize")
    sg.add_edge("fork", "containerize")
    sg.add_edge("containerize", "build")
    sg.add_conditional_edges(
        "build",
        route_after_build,
        {"deploy": "deploy", "containerize": "containerize", "failed": END},
    )
    sg.add_edge("deploy", "apply")
    sg.add_conditional_edges(
        "apply",
        route_after_apply,
        {
            "poc_execute": "poc_execute",
            "deploy": "deploy",
            "containerize": "containerize",
            "failed": END,
        },
    )
    sg.add_edge("poc_execute", "poc_report")
    sg.add_edge("poc_report", END)

    return sg.compile()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGraphPoCCompilation:
    """Test that the real graph compiles with all new nodes."""

    def test_graph_has_all_nodes(self):
        """Verify all 8 agent nodes are present."""
        from autopoc.graph import build_graph

        graph = build_graph()
        nodes = list(graph.get_graph().nodes.keys())
        expected = [
            "__start__",
            "intake",
            "poc_plan",
            "fork",
            "containerize",
            "build",
            "deploy",
            "apply",
            "poc_execute",
            "poc_report",
            "__end__",
        ]
        for node in expected:
            assert node in nodes, f"Missing node: {node}"

    def test_graph_parallel_edges(self):
        """Verify intake fans out to both poc_plan and fork (conditional edges)."""
        from autopoc.graph import build_graph

        graph = build_graph()
        mermaid = graph.get_graph().draw_mermaid()
        # Conditional edges use dotted arrows (-.->)
        assert "intake -.-> poc_plan" in mermaid
        assert "intake -.-> fork" in mermaid
        assert "poc_plan --> containerize" in mermaid
        assert "fork --> containerize" in mermaid

    def test_graph_poc_tail_edges(self):
        """Verify poc_execute → poc_report → END edges."""
        from autopoc.graph import build_graph

        graph = build_graph()
        mermaid = graph.get_graph().draw_mermaid()
        assert "poc_execute --> poc_report" in mermaid
        assert "poc_report --> __end__" in mermaid

    def test_graph_apply_to_containerize_edge(self):
        """Verify apply can route to containerize (outer loop)."""
        from autopoc.graph import build_graph

        graph = build_graph()
        mermaid = graph.get_graph().draw_mermaid()
        # Apply should have a conditional edge to containerize
        assert "apply -.-> containerize" in mermaid


class TestGraphPoCHappyPath:
    """Test the full happy-path: all nodes succeed."""

    @pytest.mark.asyncio
    async def test_full_pipeline_success(
        self,
        initial_state,
        gitlab_bare,
        env_patch,
    ):
        """Run the full graph: intake → [poc_plan ∥ fork] → containerize → build → deploy → poc_execute → poc_report."""
        with patch.dict(os.environ, env_patch, clear=True):
            graph = _build_test_graph(
                intake_fn=_mock_intake_agent(),
                poc_plan_fn=_mock_poc_plan_agent(),
                fork_fn=_mock_fork_agent(gitlab_bare),
                containerize_fn=_mock_containerize_agent(),
                build_fn=_mock_build_agent_success(),
                deploy_fn=_mock_deploy_agent_success(),
                apply_fn=_mock_apply_agent_success(),
                poc_execute_fn=_mock_poc_execute_agent(),
                poc_report_fn=_mock_poc_report_agent(),
            )
            result = await graph.ainvoke(initial_state)

        # --- Verify Intake ---
        assert result["repo_summary"] == "A simple Flask web application."
        assert len(result["components"]) == 1
        assert result["components"][0]["name"] == "app"

        # --- Verify PoC Plan (ran in parallel with fork) ---
        assert result["poc_type"] == "web-app"
        assert len(result["poc_scenarios"]) == 2
        assert result["poc_scenarios"][0]["name"] == "health-check"
        assert result["poc_infrastructure"]["resource_profile"] == "small"
        assert result["poc_infrastructure"]["needs_inference_server"] is False
        assert result["poc_plan"] != ""

        # --- Verify Fork ---
        assert result["gitlab_repo_url"] == str(gitlab_bare)

        # --- Verify Containerize ---
        assert result["components"][0]["dockerfile_ubi_path"] == "Dockerfile.ubi"

        # --- Verify Build ---
        assert len(result["built_images"]) == 1
        assert "quay.io/org/sample-app-app:latest" in result["built_images"]
        assert result["error"] is None

        # --- Verify Deploy ---
        assert "deployment/app" in result["deployed_resources"]
        assert "service/app" in result["deployed_resources"]
        assert "http://10.0.0.1:30080" in result["routes"]

        # --- Verify PoC Execute ---
        assert len(result["poc_results"]) == 2
        assert result["poc_results"][0]["scenario_name"] == "health-check"
        assert result["poc_results"][0]["status"] == "pass"
        assert result["poc_results"][1]["scenario_name"] == "api-test"
        assert result["poc_results"][1]["status"] == "fail"
        assert result["poc_script_path"] != ""

        # --- Verify PoC Report ---
        assert result["poc_report_path"] != ""
        assert result["poc_report_path"].endswith("poc-report.md")

    @pytest.mark.asyncio
    async def test_poc_plan_receives_intake_data(
        self,
        initial_state,
        gitlab_bare,
        env_patch,
    ):
        """Verify poc_plan agent receives components from intake."""
        received_state = {}

        async def _capturing_poc_plan(state, **kwargs):
            received_state.update(state)
            return await _mock_poc_plan_agent()(state)

        with patch.dict(os.environ, env_patch, clear=True):
            graph = _build_test_graph(
                intake_fn=_mock_intake_agent(),
                poc_plan_fn=_capturing_poc_plan,
                fork_fn=_mock_fork_agent(gitlab_bare),
                containerize_fn=_mock_containerize_agent(),
                build_fn=_mock_build_agent_success(),
                deploy_fn=_mock_deploy_agent_success(),
                apply_fn=_mock_apply_agent_success(),
                poc_execute_fn=_mock_poc_execute_agent(),
                poc_report_fn=_mock_poc_report_agent(),
            )
            await graph.ainvoke(initial_state)

        # poc_plan should have received the intake results
        assert received_state.get("repo_summary") == "A simple Flask web application."
        assert len(received_state.get("components", [])) == 1

    @pytest.mark.asyncio
    async def test_containerize_receives_poc_infrastructure(
        self,
        initial_state,
        gitlab_bare,
        env_patch,
    ):
        """Verify containerize agent receives poc_infrastructure from poc_plan."""
        received_state = {}

        async def _capturing_containerize(state, **kwargs):
            received_state.update(state)
            return await _mock_containerize_agent()(state)

        with patch.dict(os.environ, env_patch, clear=True):
            graph = _build_test_graph(
                intake_fn=_mock_intake_agent(),
                poc_plan_fn=_mock_poc_plan_agent(),
                fork_fn=_mock_fork_agent(gitlab_bare),
                containerize_fn=_capturing_containerize,
                build_fn=_mock_build_agent_success(),
                deploy_fn=_mock_deploy_agent_success(),
                apply_fn=_mock_apply_agent_success(),
                poc_execute_fn=_mock_poc_execute_agent(),
                poc_report_fn=_mock_poc_report_agent(),
            )
            await graph.ainvoke(initial_state)

        # containerize should have received poc_infrastructure
        assert received_state.get("poc_type") == "web-app"
        assert received_state.get("poc_infrastructure", {}).get("resource_profile") == "small"
        # Also should have fork results (fan-in)
        assert received_state.get("gitlab_repo_url") == str(gitlab_bare)


class TestGraphPoCBuildRetry:
    """Test build retry loop with PoC nodes present."""

    @pytest.mark.asyncio
    async def test_build_retry_then_poc_tail(
        self,
        initial_state,
        gitlab_bare,
        env_patch,
    ):
        """Build fails once, retries, succeeds, then full PoC tail runs."""
        with patch.dict(os.environ, env_patch, clear=True):
            graph = _build_test_graph(
                intake_fn=_mock_intake_agent(),
                poc_plan_fn=_mock_poc_plan_agent(),
                fork_fn=_mock_fork_agent(gitlab_bare),
                containerize_fn=_mock_containerize_agent(),
                build_fn=_mock_build_agent_fail_then_succeed(),
                deploy_fn=_mock_deploy_agent_success(),
                apply_fn=_mock_apply_agent_success(),
                poc_execute_fn=_mock_poc_execute_agent(),
                poc_report_fn=_mock_poc_report_agent(),
            )
            result = await graph.ainvoke(initial_state)

        # Build retried once then succeeded
        assert result["build_retries"] == 1
        assert result["error"] is None
        assert len(result["built_images"]) == 1

        # Full PoC tail should have executed
        assert len(result["poc_results"]) == 2
        assert result["poc_report_path"] != ""


class TestGraphPoCApplyFailure:
    """Test apply failure routes back to deploy, then exhausted retries end pipeline."""

    @pytest.mark.asyncio
    async def test_apply_failure_ends_without_poc(
        self,
        initial_state,
        gitlab_bare,
        env_patch,
    ):
        """Apply fails, retries exhausted → END (no poc_execute or poc_report)."""
        with patch.dict(os.environ, env_patch, clear=True):
            graph = _build_test_graph(
                intake_fn=_mock_intake_agent(),
                poc_plan_fn=_mock_poc_plan_agent(),
                fork_fn=_mock_fork_agent(gitlab_bare),
                containerize_fn=_mock_containerize_agent(),
                build_fn=_mock_build_agent_success(),
                deploy_fn=_mock_deploy_agent_success(),
                apply_fn=_mock_apply_agent_fail(),
                poc_execute_fn=_mock_poc_execute_agent(),
                poc_report_fn=_mock_poc_report_agent(),
            )
            result = await graph.ainvoke(initial_state)

        # Apply failed
        assert result["error"] is not None
        assert "namespace not found" in result["error"]
        assert result["deploy_retries"] >= 1

        # PoC execute and report should NOT have run
        assert result.get("poc_results") == []
        assert result.get("poc_report_path") == ""

        # But earlier phases should still have data
        assert result["poc_type"] == "web-app"
        assert len(result["poc_scenarios"]) == 2
        assert len(result["built_images"]) == 1


class TestRouteAfterApply:
    """Test the route_after_apply function with new routing."""

    def test_success_routes_to_poc_execute(self, env_patch):
        """On success, route to poc_execute."""
        with patch.dict(os.environ, env_patch, clear=True):
            from autopoc.graph import route_after_apply

            state = PoCState(
                error=None,
                routes=["http://10.0.0.1:30080"],
                deploy_retries=0,
            )
            assert route_after_apply(state) == "poc_execute"

    def test_failure_with_retries_routes_to_deploy(self, env_patch):
        """On failure with retries left, route back to deploy to fix manifests."""
        with patch.dict(os.environ, env_patch, clear=True):
            from autopoc.graph import route_after_apply

            state = PoCState(
                error="Apply failed",
                routes=[],
                deploy_retries=0,
            )
            assert route_after_apply(state) == "deploy"

    def test_failure_exhausted_routes_to_containerize_as_last_resort(self, env_patch):
        """On deploy retry exhaustion with container_fix available, escalate to containerize."""
        with patch.dict(os.environ, env_patch, clear=True):
            from autopoc.graph import route_after_apply

            state = PoCState(
                error="Apply failed",
                routes=[],
                deploy_retries=10,
                container_fix_retries=0,
                container_fix_action="fix-manifest",  # triage said manifest, but retries exhausted
            )
            assert route_after_apply(state) == "containerize"

    def test_failure_all_retries_exhausted_routes_to_failed(self, env_patch):
        """On failure with all retries exhausted, route to failed."""
        with patch.dict(os.environ, env_patch, clear=True):
            from autopoc.graph import route_after_apply

            state = PoCState(
                error="Apply failed",
                routes=[],
                deploy_retries=10,
                container_fix_retries=10,
            )
            assert route_after_apply(state) == "failed"

    def test_fix_dockerfile_routes_to_containerize(self, env_patch):
        """When triage says fix-dockerfile, route to containerize."""
        with patch.dict(os.environ, env_patch, clear=True):
            from autopoc.graph import route_after_apply

            state = PoCState(
                error="CrashLoopBackOff: ImportError: No module named 'flask'",
                routes=[],
                deploy_retries=0,
                container_fix_action="fix-dockerfile",
                container_fix_error="ImportError: No module named 'flask'",
                container_fix_retries=0,
            )
            assert route_after_apply(state) == "containerize"

    def test_experiment_routes_to_containerize(self, env_patch):
        """When triage says experiment, route to containerize."""
        with patch.dict(os.environ, env_patch, clear=True):
            from autopoc.graph import route_after_apply

            state = PoCState(
                error="Container exited: need different CMD",
                routes=[],
                deploy_retries=0,
                container_fix_action="experiment",
                container_fix_error="Container exited: need different CMD",
                container_fix_retries=0,
            )
            assert route_after_apply(state) == "containerize"

    def test_container_fix_retries_exhausted_routes_to_failed(self, env_patch):
        """When container fix retries are exhausted, fail."""
        with patch.dict(os.environ, env_patch, clear=True):
            from autopoc.graph import route_after_apply

            state = PoCState(
                error="Still crashing",
                routes=[],
                deploy_retries=0,
                container_fix_action="fix-dockerfile",
                container_fix_retries=10,  # way over limit
            )
            assert route_after_apply(state) == "failed"
