"""Build strategy abstraction for container image builds.

Supports pluggable build backends:
- PodmanBuildStrategy: Shells out to local podman CLI (default, existing behavior).
- OpenShiftBuildStrategy: Uses OpenShift BuildConfig / oc start-build to build
  images on-cluster without requiring a local container runtime.

Usage:
    strategy = get_build_strategy(config)
    strategy.login(registry, username, password)
    success, output = strategy.build(context_dir, dockerfile, image_tag)
    success, output = strategy.push(image_tag)
"""

import json
import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

# Timeouts
BUILD_TIMEOUT = 600  # 10 minutes for builds
DEFAULT_TIMEOUT = 120  # 2 minutes for other operations


class BuildStrategy(ABC):
    """Abstract interface for container image build strategies."""

    @abstractmethod
    def login(
        self,
        registry: str,
        username: str,
        password: str,
        *,
        tls_verify: bool = True,
    ) -> str:
        """Authenticate to a container registry.

        Args:
            registry: Registry hostname (e.g. 'quay.io').
            username: Registry username.
            password: Registry password/token.
            tls_verify: Whether to verify TLS certificates.

        Returns:
            Login output message.

        Raises:
            RuntimeError: If login fails.
        """
        ...

    @abstractmethod
    def build(
        self,
        context_path: str,
        dockerfile: str,
        tag: str,
        *,
        tls_verify: bool = True,
    ) -> str:
        """Build a container image.

        Args:
            context_path: Path to the build context directory.
            dockerfile: Path to the Dockerfile.
            tag: Full image tag (e.g. quay.io/org/repo:tag).
            tls_verify: Whether to verify TLS certificates.

        Returns:
            Build output/log.

        Raises:
            RuntimeError: If the build fails.
        """
        ...

    @abstractmethod
    def push(
        self,
        image: str,
        *,
        tls_verify: bool = True,
    ) -> str:
        """Push a container image to a registry.

        Args:
            image: Full image tag to push.
            tls_verify: Whether to verify TLS certificates.

        Returns:
            Push output/log.

        Raises:
            RuntimeError: If the push fails.
        """
        ...


class PodmanBuildStrategy(BuildStrategy):
    """Build container images using local podman CLI.

    This wraps the existing podman_build/podman_push/podman_login functions
    from podman_tools.py to conform to the BuildStrategy interface.
    """

    def login(self, registry, username, password, *, tls_verify=True):
        from autopoc.tools.podman_tools import podman_login

        return podman_login(
            registry=registry,
            username=username,
            password=password,
            tls_verify=tls_verify,
        )

    def build(self, context_path, dockerfile, tag, *, tls_verify=True):
        from autopoc.tools.podman_tools import podman_build

        return podman_build.invoke(
            {
                "context_path": context_path,
                "dockerfile": dockerfile,
                "tag": tag,
                "tls_verify": tls_verify,
            }
        )

    def push(self, image, *, tls_verify=True):
        from autopoc.tools.podman_tools import podman_push

        return podman_push.invoke({"image": image, "tls_verify": tls_verify})


class OpenShiftBuildStrategy(BuildStrategy):
    """Build container images using OpenShift BuildConfig and Binary Builds.

    This strategy uploads the local build context to an OpenShift cluster
    which performs the container build server-side. No local container
    runtime (podman/docker) is required.

    Flow:
    1. login() — creates/updates a docker-registry Secret on the cluster
       with push credentials for the target registry.
    2. build() — creates a BuildConfig (if needed) that does a Docker
       build from uploaded sources, then starts a binary build by streaming
       the build context. The resulting image is pushed to the external
       registry directly via the BuildConfig's output.
    3. push() — no-op, because OpenShift pushes the image as part of the
       build (the BuildConfig output points to the external registry).

    Prerequisites:
    - `oc` or `kubectl` CLI configured to talk to an OpenShift cluster.
    - The cluster must support OpenShift Builds (builds.openshift.io API).
    - The user/service-account must have permissions to create BuildConfig,
      Build, and Secret resources in the target namespace.
    """

    def __init__(self, namespace: str = "autopoc-builds"):
        """Initialize the OpenShift build strategy.

        Args:
            namespace: Namespace to create BuildConfigs and run builds in.
        """
        self.namespace = namespace
        self._push_secret_name = "autopoc-registry-push"
        self._oc = self._find_oc_binary()

    def _find_oc_binary(self) -> str:
        """Find oc or kubectl binary on PATH."""
        import shutil

        for binary in ("oc", "kubectl"):
            if shutil.which(binary):
                return binary
        raise RuntimeError(
            "Neither 'oc' nor 'kubectl' found on PATH. "
            "OpenShift Build strategy requires the oc or kubectl CLI."
        )

    def _run(
        self,
        args: list[str],
        timeout: int = DEFAULT_TIMEOUT,
        stdin_data: bytes | None = None,
    ) -> str:
        """Run an oc/kubectl command and return output.

        Args:
            args: Command arguments (without the oc/kubectl prefix).
            timeout: Timeout in seconds.
            stdin_data: Optional bytes to pipe to stdin.

        Returns:
            Combined stdout + stderr.

        Raises:
            RuntimeError: On non-zero exit or timeout.
        """
        cmd = [self._oc] + args
        logger.debug("Running: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                input=stdin_data,
                capture_output=True,
                text=stdin_data is None,
                timeout=timeout,
            )
            if stdin_data is not None:
                stdout = result.stdout.decode("utf-8", errors="replace") if isinstance(result.stdout, bytes) else result.stdout
                stderr = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else result.stderr
            else:
                stdout = result.stdout
                stderr = result.stderr
            output = (stdout + "\n" + stderr).strip()
            if result.returncode != 0:
                raise RuntimeError(
                    f"{self._oc} {' '.join(args[:3])}... failed "
                    f"(exit {result.returncode}):\n{output}"
                )
            return output
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"{self._oc} {' '.join(args[:3])}... timed out after {timeout}s"
            )

    def _ensure_namespace(self) -> None:
        """Create the build namespace if it doesn't exist."""
        try:
            self._run(["get", "namespace", self.namespace])
            logger.debug("Namespace %s already exists", self.namespace)
        except RuntimeError:
            logger.info("Creating namespace %s", self.namespace)
            self._run(["create", "namespace", self.namespace])

    def login(self, registry, username, password, *, tls_verify=True):
        """Create/update a docker-registry Secret for pushing images.

        OpenShift Builds use a Secret linked to the BuildConfig to
        authenticate pushes to external registries.
        """
        self._ensure_namespace()

        # Delete existing secret if present (idempotent update)
        try:
            self._run([
                "delete", "secret", self._push_secret_name,
                "-n", self.namespace,
                "--ignore-not-found=true",
            ])
        except RuntimeError:
            pass  # Ignore if it doesn't exist

        # Create the docker-registry secret
        self._run([
            "create", "secret", "docker-registry", self._push_secret_name,
            f"--docker-server={registry}",
            f"--docker-username={username}",
            f"--docker-password={password}",
            "-n", self.namespace,
        ])

        logger.info(
            "Created registry push secret '%s' in namespace '%s' for %s",
            self._push_secret_name,
            self.namespace,
            registry,
        )
        return f"Registry secret created for {registry}"

    def _create_buildconfig(self, name: str, tag: str, dockerfile_path: str) -> None:
        """Create or update a BuildConfig for binary Docker builds.

        Args:
            name: BuildConfig name (derived from component).
            tag: Full image tag for the output (e.g. quay.io/org/repo:latest).
            dockerfile_path: Relative path to the Dockerfile within the context.
        """
        bc_manifest = {
            "apiVersion": "build.openshift.io/v1",
            "kind": "BuildConfig",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": {
                    "app": "autopoc",
                    "autopoc.io/build-strategy": "openshift",
                },
            },
            "spec": {
                "source": {
                    "type": "Binary",
                },
                "strategy": {
                    "type": "Docker",
                    "dockerStrategy": {
                        "dockerfilePath": dockerfile_path,
                    },
                },
                "output": {
                    "to": {
                        "kind": "DockerImage",
                        "name": tag,
                    },
                    "pushSecret": {
                        "name": self._push_secret_name,
                    },
                },
            },
        }

        manifest_json = json.dumps(bc_manifest)

        # Apply (create or update) the BuildConfig
        self._run(
            ["apply", "-f", "-", "-n", self.namespace],
            stdin_data=manifest_json.encode("utf-8"),
        )
        logger.info("BuildConfig '%s' created/updated in namespace '%s'", name, self.namespace)

    def _start_binary_build(self, bc_name: str, context_path: str) -> str:
        """Start a binary build by uploading the build context.

        Uses `oc start-build --from-dir` to stream the local directory
        to the OpenShift builder pod.

        Args:
            bc_name: Name of the BuildConfig.
            context_path: Local path to the build context directory.

        Returns:
            Build log output.

        Raises:
            RuntimeError: If the build fails.
        """
        logger.info(
            "Starting binary build '%s' from directory '%s'",
            bc_name,
            context_path,
        )

        # start-build --from-dir streams the context and waits for completion
        # --follow streams the build log to stdout
        # --wait blocks until the build finishes
        output = self._run(
            [
                "start-build", bc_name,
                f"--from-dir={context_path}",
                "--follow",
                "--wait",
                "-n", self.namespace,
            ],
            timeout=BUILD_TIMEOUT,
        )

        return output

    def _get_build_status(self, bc_name: str) -> dict:
        """Get the status of the latest build for a BuildConfig.

        Returns:
            Dict with 'phase' (Complete, Failed, Running, etc.) and 'message'.
        """
        try:
            output = self._run([
                "get", "builds",
                "-l", f"buildconfig={bc_name}",
                "--sort-by=.metadata.creationTimestamp",
                "-o", "jsonpath={.items[-1].status.phase}",
                "-n", self.namespace,
            ])
            return {"phase": output.strip(), "message": ""}
        except RuntimeError as e:
            return {"phase": "Unknown", "message": str(e)}

    def build(self, context_path, dockerfile, tag, *, tls_verify=True):
        """Build an image using OpenShift Binary Build.

        Creates a BuildConfig (if needed) and starts a binary build
        that uploads the local context to the OpenShift cluster. The
        cluster builds the image and pushes it to the external registry.

        Args:
            context_path: Path to the build context directory.
            dockerfile: Path to the Dockerfile (absolute or relative).
            tag: Full image tag (e.g. quay.io/org/repo:latest).
            tls_verify: Ignored for OpenShift builds (TLS is handled by
                the cluster's registry configuration and push secret).

        Returns:
            Build log output.

        Raises:
            RuntimeError: If the build fails.
        """
        self._ensure_namespace()

        # Derive a BuildConfig name from the image tag
        # e.g. quay.io/org/my-project-app:latest -> my-project-app
        bc_name = self._bc_name_from_tag(tag)

        # Compute relative dockerfile path within the context
        context = Path(context_path).resolve()
        df = Path(dockerfile).resolve()
        try:
            dockerfile_rel = str(df.relative_to(context))
        except ValueError:
            # Dockerfile is outside the context — use the basename
            dockerfile_rel = df.name

        # Create/update the BuildConfig
        self._create_buildconfig(bc_name, tag, dockerfile_rel)

        # Start the binary build
        try:
            output = self._start_binary_build(bc_name, context_path)
        except RuntimeError as e:
            # Enrich the error with build status
            status = self._get_build_status(bc_name)
            raise RuntimeError(
                f"OpenShift build failed for BuildConfig '{bc_name}'.\n"
                f"Build phase: {status['phase']}\n"
                f"Error: {e}"
            ) from e

        logger.info("OpenShift build completed for %s", tag)
        return output

    def push(self, image, *, tls_verify=True):
        """No-op: OpenShift builds push the image as part of the build.

        The BuildConfig's output.to points to the external registry with
        a push secret, so the build controller pushes automatically.
        """
        logger.debug(
            "push() is a no-op for OpenShift builds — image %s was "
            "pushed during the build step",
            image,
        )
        return f"Image {image} was pushed during the OpenShift build"

    @staticmethod
    def _bc_name_from_tag(tag: str) -> str:
        """Derive a valid BuildConfig name from an image tag.

        Examples:
            quay.io/org/my-project-app:latest -> my-project-app
            quay.io/org/my-project-app:experiment-1 -> my-project-app

        OpenShift names must be lowercase, alphanumeric + hyphens, max 63 chars.
        """
        # Strip registry and tag portions
        # quay.io/org/repo:tag -> repo
        name = tag
        if "/" in name:
            name = name.rsplit("/", 1)[-1]  # repo:tag
        if ":" in name:
            name = name.split(":")[0]  # repo

        # Sanitize for k8s naming: lowercase, replace _ with -, strip invalid chars
        name = name.lower().replace("_", "-")
        name = "".join(c for c in name if c.isalnum() or c == "-")
        name = name.strip("-")

        # Truncate to 63 chars (k8s name limit)
        if len(name) > 63:
            name = name[:63].rstrip("-")

        return name or "autopoc-build"


def get_build_strategy(config) -> BuildStrategy:
    """Factory function to create the appropriate build strategy.

    Args:
        config: AutoPoCConfig instance with build_strategy field.

    Returns:
        BuildStrategy implementation.

    Raises:
        ValueError: If the configured strategy is unknown.
    """
    strategy_name = getattr(config, "build_strategy", "podman")

    if strategy_name == "podman":
        return PodmanBuildStrategy()
    elif strategy_name == "openshift":
        namespace = getattr(config, "openshift_namespace_prefix", "poc") + "-builds"
        return OpenShiftBuildStrategy(namespace=namespace)
    else:
        raise ValueError(
            f"Unknown build strategy: '{strategy_name}'. "
            f"Valid options are 'podman' or 'openshift'."
        )
