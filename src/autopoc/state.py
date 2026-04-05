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
    CONTAINERIZE = "containerize"
    BUILD = "build"
    DEPLOY = "deploy"
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
    repo_summary: str  # LLM-generated summary of the repo
    components: list[ComponentInfo]  # Detected components/apps
    has_helm_chart: bool
    has_kustomize: bool
    has_compose: bool
    existing_ci_cd: str | None  # e.g. "github-actions", "gitlab-ci", etc.

    # --- Build phase output ---
    built_images: list[str]  # List of pushed image refs (quay.io/org/name:tag)
    build_retries: int  # Current retry count for build failures

    # --- Deploy phase output ---
    deployed_resources: list[str]  # List of created K8s resource identifiers
    routes: list[str]  # Accessible URLs for deployed services
