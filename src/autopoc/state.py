"""Shared state definitions for the AutoPoC LangGraph pipeline.

All agents read from and write to PoCState as it flows through the graph.
"""

from enum import Enum
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class PoCPhase(str, Enum):
    """Current phase of the PoC pipeline."""

    INTAKE = "intake"
    FORK = "fork"
    POC_PLAN = "poc_plan"
    CONTAINERIZE = "containerize"
    BUILD = "build"
    DEPLOY = "deploy"
    APPLY = "apply"
    POC_EXECUTE = "poc_execute"
    POC_REPORT = "poc_report"
    DONE = "done"
    FAILED = "failed"


class ComponentInfo(TypedDict, total=False):
    """Information about a single component/app detected in the repository.

    Fields marked total=False are optional and populated progressively
    as the pipeline advances through phases.
    """

    # Populated by intake agent
    name: str  # e.g. "frontend", "api", "worker"
    language: str  # e.g. "python", "node", "go", "java"
    build_system: str  # e.g. "pip", "npm", "maven", "cargo"
    entry_point: str  # e.g. "main.py", "dist/index.js"
    port: int | None  # Exposed port, if applicable
    existing_dockerfile: str | None  # Path to existing Dockerfile, if any
    is_ml_workload: bool  # Whether this is an ML serving / pipeline component
    source_dir: str  # Relative path within repo (e.g. "." or "api/")

    # Populated by containerize agent
    dockerfile_ubi_path: str  # Path where Dockerfile.ubi was written

    # Populated by build agent
    image_name: str  # Full quay.io/org/name:tag


class PoCScenario(TypedDict, total=False):
    """A single PoC test scenario defined by the PoC Plan agent.

    Each scenario describes a concrete, executable test that proves
    some aspect of the PoC works correctly.
    """

    name: str  # e.g. "inference-test", "health-check"
    description: str  # What this test verifies
    type: str  # "http", "script", "cli"
    endpoint: str | None  # Target endpoint (if HTTP-based)
    input_data: str | None  # Sample input (prompt, query, request body, etc.)
    expected_behavior: str  # What success looks like
    timeout_seconds: int  # Max wait time


class PoCInfrastructure(TypedDict, total=False):
    """Infrastructure requirements determined by the PoC Plan agent.

    Influences how the Dockerfile is built and how the deployment
    is structured (sidecars, PVCs, GPU, etc.).
    """

    needs_inference_server: bool  # e.g. vLLM, TGI, Triton
    inference_server_type: str | None  # "vllm", "tgi", "triton", "custom"
    needs_vector_db: bool  # e.g. Milvus, ChromaDB, Qdrant
    vector_db_type: str | None  # "milvus", "chromadb", "qdrant", "in-memory"
    needs_embedding_model: bool  # Whether an embedding model is needed
    embedding_model: str | None  # e.g. "sentence-transformers/all-MiniLM-L6-v2"
    needs_gpu: bool  # GPU resource requirements
    gpu_type: str | None  # "nvidia-a10g", "nvidia-t4", etc.
    needs_pvc: bool  # Persistent storage for models/data
    pvc_size: str | None  # e.g. "10Gi", "50Gi"
    sidecar_containers: list[dict]  # Additional containers to deploy alongside
    extra_env_vars: dict[str, str]  # Environment variables for the main container
    odh_components: list[str]  # ODH components needed: "model-mesh", "kserve", etc.
    resource_profile: str  # "small", "medium", "large", "gpu"

    # Runtime / deployment model — guides containerize + deploy decisions
    deployment_model: str  # "deployment" | "job" | "cronjob" | "cli-only"
    listens_on_port: bool  # Whether the app binds to a network port
    long_running: bool  # Whether it runs continuously (server, worker) vs exits (CLI, batch)
    entrypoint_suggestion: str | None  # Suggested ENTRYPOINT/CMD for Dockerfile
    test_strategy: str  # "http" | "cli" | "exec" — how to validate after deploy


class PoCResult(TypedDict, total=False):
    """Result of a single PoC test scenario execution."""

    scenario_name: str  # Matches PoCScenario.name
    status: str  # "pass", "fail", "skip", "error"
    output: str  # Captured output/response
    error_message: str | None  # Error details if failed
    duration_seconds: float  # How long it took


class PoCState(TypedDict, total=False):
    """Full state flowing through the AutoPoC LangGraph pipeline.

    Fields use total=False because state is populated progressively
    by each agent/node as the pipeline executes.
    """

    # --- Input (set at pipeline start) ---
    project_name: str
    source_repo_url: str  # GitHub URL

    # --- Phase tracking ---
    current_phase: PoCPhase
    error: str | None
    messages: Annotated[list, add_messages]  # LangGraph message history

    # --- Fork phase output ---
    gitlab_repo_url: str | None
    local_clone_path: str | None

    # --- Intake/analysis output ---
    repo_digest: str  # Pre-generated text digest of the repo (procedural, no LLM)
    repo_summary: str  # LLM-generated summary of the repo
    components: list[ComponentInfo]  # Detected components/apps
    has_helm_chart: bool
    has_kustomize: bool
    has_compose: bool
    existing_ci_cd: str | None  # e.g. "github-actions", "gitlab-ci", etc.

    # --- PoC Plan output ---
    poc_plan: str  # Raw markdown content of the PoC plan
    poc_plan_path: str  # Path to poc-plan.md in the repo
    poc_plan_error: (
        str | None
    )  # Set when poc_plan fails; separate from error to avoid parallel state conflict with fork
    poc_components: list[str]  # Component names relevant for the PoC (subset of components)
    poc_scenarios: list[PoCScenario]  # Structured test scenarios
    poc_infrastructure: PoCInfrastructure  # Infrastructure requirements
    poc_type: str  # "model-serving", "rag", "training", "web-app", etc.

    # --- Build phase output ---
    built_images: list[str]  # List of pushed image refs (quay.io/org/name:tag)
    build_retries: int  # Current retry count for build failures

    # --- Deploy phase output ---
    deployed_resources: list[str]  # List of created K8s resource identifiers
    routes: list[str]  # Accessible URLs for deployed services
    deploy_retries: int  # Current retry count for deployment failures

    # --- PoC Execute output ---
    poc_results: list[PoCResult]  # Test execution results
    poc_script_path: str  # Path to generated test script

    # --- PoC Report output ---
    poc_report_path: str  # Path to poc-report.md in the repo
