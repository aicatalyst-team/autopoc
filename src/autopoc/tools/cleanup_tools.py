"""Cleanup tools for AutoPoC build and deployment failures.

This module provides cleanup functionality to manage failed build and deployment
artifacts, ensuring that only the current failure state is preserved while
cleaning up previous attempts to prevent resource accumulation.
"""

import subprocess
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool


def _run_kubectl(args: list[str], timeout: int = 60, check: bool = True) -> str:
    """Run a kubectl command and return its output."""
    try:
        result = subprocess.run(["kubectl"] + args, capture_output=True, text=True, timeout=timeout)
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, "kubectl", result.stderr)
        return result.stdout
    except subprocess.CalledProcessError:
        if check:
            raise
        return ""
    except Exception:
        return ""


def _run_podman(args: list[str], timeout: int = 60) -> str:
    """Run a podman command and return its output."""
    try:
        result = subprocess.run(["podman"] + args, capture_output=True, text=True, timeout=timeout)
        return result.stdout
    except Exception:
        return ""


@tool
def cleanup_previous_build_failure(
    project_name: str, build_strategy: str, work_dir: str = "/tmp/autopoc"
) -> str:
    """Clean up previous build failure artifacts while preserving current failure info.

    Args:
        project_name: Name of the project
        build_strategy: Either 'podman' or 'openshift'
        work_dir: Working directory base path

    Returns:
        Status message about cleanup results
    """
    try:
        results = []

        if build_strategy == "openshift":
            # Clean up OpenShift build resources
            cleanup_result = cleanup_openshift_build_resources(
                namespace="poc-builds", project_name=project_name, keep_current=True
            )
            results.append(f"OpenShift: {cleanup_result}")

        elif build_strategy == "podman":
            # Clean up local podman images
            cleanup_result = cleanup_local_build_images(
                project_name=project_name, keep_current=True
            )
            results.append(f"Podman: {cleanup_result}")

        # Clean up build logs and artifacts in work directory (keeping current)
        work_path = Path(work_dir) / project_name
        if work_path.exists():
            build_logs = list(work_path.glob("build-*.log"))
            if len(build_logs) > 1:
                # Keep only the most recent build log
                build_logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                for log_file in build_logs[1:]:
                    log_file.unlink()
                results.append(f"Cleaned up {len(build_logs) - 1} old build logs")

        return f"Build cleanup completed: {'; '.join(results)}"

    except Exception as e:
        return f"Build cleanup failed: {e}"


@tool
def cleanup_openshift_build_resources(
    namespace: str, project_name: str, keep_current: bool = True
) -> str:
    """Clean up OpenShift BuildConfigs, ImageStreams, and build pods.

    Args:
        namespace: OpenShift namespace (typically 'poc-builds')
        project_name: Name of the project to clean up
        keep_current: If True, keep the most recent resources for debugging

    Returns:
        Status message about cleanup results
    """
    try:
        results = []

        # Get all BuildConfigs for this project
        buildconfigs_output = _run_kubectl(
            ["get", "buildconfig", "-l", f"app={project_name}", "-n", namespace], check=False
        )

        if buildconfigs_output and "No resources found" not in buildconfigs_output:
            if keep_current:
                # Keep only the most recent BuildConfig
                lines = [line for line in buildconfigs_output.strip().split("\n")[1:] if line]
                if len(lines) > 1:
                    # Delete older BuildConfigs (keeping the first one which is usually most recent)
                    for line in lines[1:]:
                        bc_name = line.split()[0]
                        _run_kubectl(
                            ["delete", f"buildconfig/{bc_name}", "-n", namespace], check=False
                        )
                        results.append(f"Deleted BuildConfig {bc_name}")
            else:
                # Delete all BuildConfigs for this project
                _run_kubectl(
                    ["delete", "buildconfig", "-l", f"app={project_name}", "-n", namespace],
                    check=False,
                )
                results.append(f"Deleted all BuildConfigs for {project_name}")

        # Get all ImageStreams for this project
        imagestreams_output = _run_kubectl(
            ["get", "imagestream", "-l", f"app={project_name}", "-n", namespace], check=False
        )

        if imagestreams_output and "No resources found" not in imagestreams_output:
            if keep_current:
                # Keep only the most recent ImageStream
                lines = [line for line in imagestreams_output.strip().split("\n")[1:] if line]
                if len(lines) > 1:
                    for line in lines[1:]:
                        is_name = line.split()[0]
                        _run_kubectl(
                            ["delete", f"imagestream/{is_name}", "-n", namespace], check=False
                        )
                        results.append(f"Deleted ImageStream {is_name}")
            else:
                # Delete all ImageStreams for this project
                _run_kubectl(
                    ["delete", "imagestream", "-l", f"app={project_name}", "-n", namespace],
                    check=False,
                )
                results.append(f"Deleted all ImageStreams for {project_name}")

        # Clean up failed/completed build pods
        pods_output = _run_kubectl(
            ["get", "pod", "-l", f"openshift.io/build.name={project_name}", "-n", namespace],
            check=False,
        )

        if pods_output and "No resources found" not in pods_output:
            lines = [line for line in pods_output.strip().split("\n")[1:] if line]
            pods_to_delete = []

            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    pod_name = parts[0]
                    status = parts[2]
                    # Delete failed, completed, or error pods (keep running/pending if keep_current)
                    if status in ["Failed", "Succeeded", "Error", "Completed"] or not keep_current:
                        pods_to_delete.append(pod_name)

            if keep_current and pods_to_delete:
                # Keep one pod for debugging (the most recent)
                pods_to_delete = pods_to_delete[:-1] if len(pods_to_delete) > 1 else []

            for pod_name in pods_to_delete:
                _run_kubectl(["delete", f"pod/{pod_name}", "-n", namespace], check=False)
                results.append(f"Deleted build pod {pod_name}")

        if not results:
            return f"No OpenShift build resources found for cleanup in {namespace}"

        return f"OpenShift cleanup in {namespace}: {'; '.join(results)}"

    except Exception as e:
        return f"OpenShift build cleanup failed: {e}"


@tool
def cleanup_local_build_images(project_name: str, keep_current: bool = True) -> str:
    """Clean up local podman images from previous builds.

    Args:
        project_name: Name of the project
        keep_current: If True, keep the most recent image for debugging

    Returns:
        Status message about cleanup results
    """
    try:
        # Find all images for this project
        images_output = _run_podman(
            [
                "images",
                "--filter",
                f"label=project={project_name}",
                "--format",
                "{{.ID}} {{.Created}} {{.Repository}}:{{.Tag}}",
            ]
        )

        if not images_output.strip():
            return f"No podman images found for project {project_name}"

        images = []
        for line in images_output.strip().split("\n"):
            parts = line.split(" ", 2)
            if len(parts) >= 3:
                image_id, created_str, repo_tag = parts
                images.append((image_id, created_str, repo_tag))

        if not images:
            return f"No podman images found for project {project_name}"

        # Sort by creation time (most recent first)
        images.sort(key=lambda x: x[1], reverse=True)

        images_to_delete = images
        if keep_current and len(images) > 1:
            # Keep the most recent image
            images_to_delete = images[1:]

        deleted_images = []
        for image_id, _, repo_tag in images_to_delete:
            try:
                _run_podman(["rmi", "--force", image_id])
                deleted_images.append(f"{repo_tag} ({image_id[:12]})")
            except Exception as e:
                # Continue with other images even if one fails
                deleted_images.append(f"{repo_tag} (failed: {e})")

        if deleted_images:
            return f"Deleted {len(deleted_images)} podman images: {', '.join(deleted_images)}"
        else:
            return f"No podman images deleted for {project_name}"

    except Exception as e:
        return f"Local build image cleanup failed: {e}"


@tool
def cleanup_failed_deployment(
    namespace: str, project_name: str, capture_state: bool = True
) -> dict:
    """Clean up failed deployment resources and return captured state information.

    Args:
        namespace: Kubernetes namespace to clean up
        project_name: Name of the project
        capture_state: If True, capture failure state before cleanup

    Returns:
        Dict with cleanup results and captured state information
    """
    try:
        result = {"status": "success", "cleaned_resources": [], "captured_state": {}, "errors": []}

        # Capture state before cleanup if requested
        if capture_state:
            result["captured_state"] = capture_deployment_failure_state(namespace, project_name)

        # Get all deployments in the namespace
        deployments = _run_kubectl(["get", "deployment", "-n", namespace], check=False)
        if deployments and "No resources found" not in deployments:
            lines = [line for line in deployments.strip().split("\n")[1:] if line]
            for line in lines:
                parts = line.split()
                if len(parts) >= 1:
                    deployment_name = parts[0]
                    try:
                        _run_kubectl(
                            ["delete", f"deployment/{deployment_name}", "-n", namespace],
                            check=False,
                        )
                        result["cleaned_resources"].append(f"deployment/{deployment_name}")
                    except Exception as e:
                        result["errors"].append(
                            f"Failed to delete deployment {deployment_name}: {e}"
                        )

        # Get all services in the namespace
        services = _run_kubectl(["get", "service", "-n", namespace], check=False)
        if services and "No resources found" not in services:
            lines = [line for line in services.strip().split("\n")[1:] if line]
            for line in lines:
                parts = line.split()
                if len(parts) >= 1:
                    service_name = parts[0]
                    # Skip the default kubernetes service
                    if service_name != "kubernetes":
                        try:
                            _run_kubectl(
                                ["delete", f"service/{service_name}", "-n", namespace], check=False
                            )
                            result["cleaned_resources"].append(f"service/{service_name}")
                        except Exception as e:
                            result["errors"].append(f"Failed to delete service {service_name}: {e}")

        # Get all pods in the namespace
        pods = _run_kubectl(["get", "pod", "-n", namespace], check=False)
        if pods and "No resources found" not in pods:
            lines = [line for line in pods.strip().split("\n")[1:] if line]
            for line in lines:
                parts = line.split()
                if len(parts) >= 1:
                    pod_name = parts[0]
                    try:
                        _run_kubectl(["delete", f"pod/{pod_name}", "-n", namespace], check=False)
                        result["cleaned_resources"].append(f"pod/{pod_name}")
                    except Exception as e:
                        result["errors"].append(f"Failed to delete pod {pod_name}: {e}")

        return result

    except Exception as e:
        return {
            "status": "error",
            "cleaned_resources": [],
            "captured_state": {},
            "errors": [f"Deployment cleanup failed: {e}"],
        }


@tool
def capture_deployment_failure_state(namespace: str, project_name: str) -> dict:
    """Capture detailed state of failed deployment for debugging.

    Args:
        namespace: Kubernetes namespace
        project_name: Name of the project

    Returns:
        Dict with captured failure state information
    """
    try:
        state = {
            "timestamp": datetime.now().isoformat(),
            "namespace": namespace,
            "project_name": project_name,
            "pods": {},
            "deployments": {},
            "services": {},
            "events": "",
        }

        # Capture pod status and logs
        pods = _run_kubectl(["get", "pod", "-n", namespace], check=False)
        if pods and "No resources found" not in pods:
            lines = [line for line in pods.strip().split("\n")[1:] if line]
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    pod_name = parts[0]
                    ready = parts[1]
                    status = parts[2]

                    state["pods"][pod_name] = {"ready": ready, "status": status, "logs": ""}

                    # Get pod logs if pod exists
                    try:
                        logs = _run_kubectl(["logs", pod_name, "-n", namespace], check=False)
                        state["pods"][pod_name]["logs"] = (
                            logs[:2000] if logs else "No logs available"
                        )
                    except Exception:
                        state["pods"][pod_name]["logs"] = "Failed to retrieve logs"

        # Capture deployment status
        deployments = _run_kubectl(["get", "deployment", "-n", namespace], check=False)
        if deployments and "No resources found" not in deployments:
            lines = [line for line in deployments.strip().split("\n")[1:] if line]
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    deployment_name = parts[0]
                    ready = parts[1]
                    up_to_date = parts[2]
                    available = parts[3]

                    state["deployments"][deployment_name] = {
                        "ready": ready,
                        "up_to_date": up_to_date,
                        "available": available,
                    }

        # Capture service status
        services = _run_kubectl(["get", "service", "-n", namespace], check=False)
        if services and "No resources found" not in services:
            lines = [line for line in services.strip().split("\n")[1:] if line]
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    service_name = parts[0]
                    service_type = parts[1]
                    cluster_ip = parts[2]

                    state["services"][service_name] = {
                        "type": service_type,
                        "cluster_ip": cluster_ip,
                    }

        # Capture recent events
        try:
            events = _run_kubectl(["get", "events", "-n", namespace], check=False)
            if events and "No resources found" not in events:
                # Take last 10 lines of events to avoid too much data
                event_lines = events.strip().split("\n")[-10:]
                state["events"] = "\n".join(event_lines)
        except Exception:
            state["events"] = "Failed to retrieve events"

        return state

    except Exception as e:
        return {
            "error": f"Failed to capture deployment failure state: {e}",
            "timestamp": datetime.now().isoformat(),
            "namespace": namespace,
            "project_name": project_name,
        }


@tool
def reset_deployment_namespace(namespace: str, project_name: str) -> str:
    """Reset namespace to clean state for deployment retry.

    Args:
        namespace: Kubernetes namespace to reset
        project_name: Name of the project

    Returns:
        Status message about reset results
    """
    try:
        # First capture state, then clean up everything
        cleanup_result = cleanup_failed_deployment(
            namespace=namespace, project_name=project_name, capture_state=True
        )

        if cleanup_result["status"] == "error":
            return f"Failed to reset namespace {namespace}: {'; '.join(cleanup_result['errors'])}"

        cleaned_count = len(cleanup_result["cleaned_resources"])
        error_count = len(cleanup_result["errors"])

        status_parts = [f"Cleaned {cleaned_count} resources from {namespace}"]

        if error_count > 0:
            status_parts.append(f"{error_count} errors occurred")

        if cleanup_result["captured_state"]:
            status_parts.append("failure state captured")

        return "; ".join(status_parts)

    except Exception as e:
        return f"Failed to reset namespace {namespace}: {e}"
