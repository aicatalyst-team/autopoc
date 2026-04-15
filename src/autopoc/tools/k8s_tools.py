"""Kubernetes tools for deploying to local clusters (k3d, minikube, kind).

These tools use kubectl for local E2E testing. For production OpenShift deployments,
use openshift_tools.py (to be implemented).
"""

import json
import logging
import subprocess
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _run_kubectl(args: list[str], timeout: int = 60, check: bool = True) -> str:
    """Run kubectl command and return output.

    Args:
        args: kubectl arguments (without 'kubectl' itself)
        timeout: Command timeout in seconds
        check: Whether to raise on non-zero exit

    Returns:
        Combined stdout+stderr

    Raises:
        RuntimeError: If command fails and check=True (includes actual error output)
    """
    cmd = ["kubectl", *args]
    logger.debug("Running: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,  # Don't raise automatically, we'll handle it
    )

    output = result.stdout + result.stderr

    # If command failed and check=True, raise with actual error message
    if check and result.returncode != 0:
        error_msg = f"kubectl command failed (exit {result.returncode}): {' '.join(cmd)}\n"
        if result.stderr:
            error_msg += f"Error: {result.stderr.strip()}\n"
        if result.stdout:
            error_msg += f"Output: {result.stdout.strip()}\n"
        raise RuntimeError(error_msg.strip())

    return output.strip()


@tool
def kubectl_apply(manifest_path: str, namespace: str) -> str:
    """Apply a Kubernetes manifest file.

    If the apply fails because a resource is immutable (e.g., Jobs), the existing
    resource is deleted and the manifest is re-applied. This is safe because
    everything is in a PoC namespace created minutes ago.

    Args:
        manifest_path: Path to YAML manifest file
        namespace: Target namespace

    Returns:
        kubectl apply output
    """
    try:
        return _run_kubectl(["apply", "-f", manifest_path, "-n", namespace])
    except RuntimeError as e:
        error_msg = str(e).lower()
        # Detect immutable field errors (common with Jobs, which can't be updated)
        if "field is immutable" in error_msg or "is invalid" in error_msg:
            logger.info(
                "Apply failed due to immutable field, deleting and re-applying: %s",
                manifest_path,
            )
            # Delete existing resource(s) defined in the manifest, then re-apply
            _run_kubectl(
                ["delete", "-f", manifest_path, "-n", namespace, "--ignore-not-found=true"],
                check=False,
            )
            return _run_kubectl(["apply", "-f", manifest_path, "-n", namespace])
        raise


@tool
def kubectl_apply_from_string(manifest: str, namespace: str) -> str:
    """Apply a Kubernetes manifest from a YAML string.

    If the apply fails because a resource is immutable, deletes and re-applies.

    Args:
        manifest: YAML manifest content
        namespace: Target namespace

    Returns:
        kubectl apply output
    """
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(manifest)
        temp_path = f.name

    try:
        try:
            return _run_kubectl(["apply", "-f", temp_path, "-n", namespace])
        except RuntimeError as e:
            error_msg = str(e).lower()
            if "field is immutable" in error_msg or "is invalid" in error_msg:
                logger.info(
                    "Apply from string failed due to immutable field, deleting and re-applying"
                )
                _run_kubectl(
                    ["delete", "-f", temp_path, "-n", namespace, "--ignore-not-found=true"],
                    check=False,
                )
                return _run_kubectl(["apply", "-f", temp_path, "-n", namespace])
            raise
    finally:
        Path(temp_path).unlink(missing_ok=True)


@tool
def kubectl_create_namespace(name: str) -> str:
    """Create a Kubernetes namespace if it doesn't exist.

    Args:
        name: Namespace name

    Returns:
        Success message
    """
    try:
        # Check if namespace exists
        _run_kubectl(["get", "namespace", name], check=False)
        return f"Namespace '{name}' already exists"
    except subprocess.CalledProcessError:
        # Namespace doesn't exist, create it
        output = _run_kubectl(["create", "namespace", name])
        return output


@tool
def kubectl_get(resource: str, name: str, namespace: str) -> str:
    """Get a Kubernetes resource as JSON.

    Args:
        resource: Resource type (e.g., 'pod', 'deployment', 'service')
        name: Resource name
        namespace: Namespace

    Returns:
        Resource JSON string
    """
    return _run_kubectl(["get", resource, name, "-n", namespace, "-o", "json"])


@tool
def kubectl_logs(pod: str, namespace: str, tail: int = 100) -> str:
    """Get logs from a pod.

    Args:
        pod: Pod name
        namespace: Namespace
        tail: Number of lines to show (default 100)

    Returns:
        Pod logs
    """
    return _run_kubectl(["logs", pod, "-n", namespace, f"--tail={tail}"])


@tool
def kubectl_wait_for_rollout(deployment: str, namespace: str, timeout: int = 300) -> str:
    """Wait for a deployment to roll out successfully.

    Args:
        deployment: Deployment name
        namespace: Namespace
        timeout: Timeout in seconds (default 300)

    Returns:
        Success message
    """
    return _run_kubectl(
        ["rollout", "status", f"deployment/{deployment}", "-n", namespace, f"--timeout={timeout}s"],
        timeout=timeout + 10,
    )


@tool
def kubectl_get_service_url(service: str, namespace: str) -> str:
    """Get the external URL for a service.

    For local clusters, this typically returns a NodePort or LoadBalancer IP.

    Args:
        service: Service name
        namespace: Namespace

    Returns:
        Service URL or IP:Port
    """
    # Get service details
    svc_json = _run_kubectl(["get", "service", service, "-n", namespace, "-o", "json"])
    svc = json.loads(svc_json)

    # Check service type
    svc_type = svc.get("spec", {}).get("type", "ClusterIP")

    if svc_type == "LoadBalancer":
        # Try to get external IP
        lb_ingress = svc.get("status", {}).get("loadBalancer", {}).get("ingress", [])
        if lb_ingress:
            ip = lb_ingress[0].get("ip") or lb_ingress[0].get("hostname")
            port = svc["spec"]["ports"][0]["port"]
            return f"http://{ip}:{port}"
        return "LoadBalancer IP pending..."

    elif svc_type == "NodePort":
        # Get node IP and NodePort
        nodes_json = _run_kubectl(["get", "nodes", "-o", "json"])
        nodes = json.loads(nodes_json)

        if nodes["items"]:
            # Get first node's internal IP
            addresses = nodes["items"][0]["status"]["addresses"]
            node_ip = next(
                (a["address"] for a in addresses if a["type"] == "InternalIP"), "localhost"
            )

            node_port = svc["spec"]["ports"][0]["nodePort"]
            return f"http://{node_ip}:{node_port}"

    # ClusterIP - just return the cluster IP
    cluster_ip = svc["spec"].get("clusterIP", "")
    port = svc["spec"]["ports"][0]["port"]
    return f"http://{cluster_ip}:{port} (cluster-internal only)"


@tool
def kubectl_delete(resource: str, name: str, namespace: str) -> str:
    """Delete a Kubernetes resource.

    Args:
        resource: Resource type (e.g., 'deployment', 'service')
        name: Resource name
        namespace: Namespace

    Returns:
        Deletion confirmation
    """
    return _run_kubectl(["delete", resource, name, "-n", namespace, "--ignore-not-found=true"])
