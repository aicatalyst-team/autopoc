"""AutoPoC tools package.

This package contains all the tools used by the AutoPoC pipeline for various
operations including file management, Kubernetes operations, containerization,
cleanup, and GitHub repository management.
"""

# Import all tool functions to make them available for the LangChain agent
from .cleanup_tools import (
    capture_deployment_failure_state,
    cleanup_failed_deployment,
    cleanup_local_build_images,
    cleanup_openshift_build_resources,
    cleanup_previous_build_failure,
    reset_deployment_namespace,
)
from .file_tools import (
    list_files,
    read_file,
    search_files,
    write_file,
)
from .github_tools import (
    check_github_repository_exists,
    create_autopoc_fork,
    force_sync_repository,
    get_repository_topics,
    is_autopoc_repository,
    list_autopoc_repositories,
    set_repository_topics,
)
from .k8s_tools import (
    kubectl_apply,
    kubectl_apply_from_string,
    kubectl_create_namespace,
    kubectl_delete,
    kubectl_get,
    kubectl_get_service_url,
    kubectl_logs,
    kubectl_wait_for_rollout,
)
from .podman_tools import (
    podman_build,
    podman_login,
    podman_push,
    podman_remove_image,
)
from .script_tools import run_script
from .template_tools import render_template

__all__ = [
    # Cleanup tools
    "capture_deployment_failure_state",
    "cleanup_failed_deployment",
    "cleanup_local_build_images",
    "cleanup_openshift_build_resources",
    "cleanup_previous_build_failure",
    "reset_deployment_namespace",
    # File tools
    "list_files",
    "read_file",
    "search_files",
    "write_file",
    # GitHub tools
    "check_github_repository_exists",
    "create_autopoc_fork",
    "force_sync_repository",
    "get_repository_topics",
    "is_autopoc_repository",
    "list_autopoc_repositories",
    "set_repository_topics",
    # Kubernetes tools
    "kubectl_apply",
    "kubectl_apply_from_string",
    "kubectl_create_namespace",
    "kubectl_delete",
    "kubectl_get",
    "kubectl_get_service_url",
    "kubectl_logs",
    "kubectl_wait_for_rollout",
    # Podman tools
    "podman_build",
    "podman_login",
    "podman_push",
    "podman_remove_image",
    # Script tools
    "run_script",
    # Template tools
    "render_template",
]
