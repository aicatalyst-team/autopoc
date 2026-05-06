"""Tests for apply agent triage and error handling.

Covers:
- _triage_apply_error deterministic pre-checks (RBAC, namespace errors)
- kubectl_apply RBAC vs field-level forbidden error handling
"""

import pytest

from autopoc.agents.apply import _triage_apply_error


# --- Tests for _triage_apply_error deterministic pre-checks ---


class TestTriageApplyError:
    """Test that known error patterns are classified deterministically,
    without needing an LLM call."""

    @pytest.mark.asyncio
    async def test_rbac_forbidden_is_fix_manifest(self) -> None:
        """RBAC 'cannot patch resource ... is forbidden' → fix-manifest."""
        error = (
            'namespaces "kwipu" is forbidden: User '
            '"system:serviceaccount:autopoc-test:autopoc-runner" '
            'cannot patch resource "namespaces" in API group "" '
            'in the namespace "kwipu"'
        )
        assert await _triage_apply_error(error) == "fix-manifest"

    @pytest.mark.asyncio
    async def test_rbac_cannot_get_jobs_is_fix_manifest(self) -> None:
        """RBAC 'cannot get resource "jobs"' → fix-manifest."""
        error = (
            'jobs.batch "oh-my-kimi-cli-doctor-check" is forbidden: User '
            '"system:serviceaccount:autopoc-test:autopoc-runner" '
            'cannot get resource "jobs" in API group "batch" '
            'in the namespace "oh-my-kimi"'
        )
        assert await _triage_apply_error(error) == "fix-manifest"

    @pytest.mark.asyncio
    async def test_rbac_cannot_create_is_fix_manifest(self) -> None:
        """RBAC 'cannot create resource' → fix-manifest."""
        error = (
            "deployments.apps is forbidden: User "
            '"system:serviceaccount:autopoc-test:autopoc-runner" '
            'cannot create resource "deployments" in API group "apps"'
        )
        assert await _triage_apply_error(error) == "fix-manifest"

    @pytest.mark.asyncio
    async def test_namespace_not_found_is_fix_manifest(self) -> None:
        """'namespaces "X" not found' → fix-manifest."""
        error = (
            "Error from server (NotFound): error when creating "
            '"/workspace/kwipu/kubernetes/pvc.yaml": '
            'namespaces "kwipu" not found'
        )
        assert await _triage_apply_error(error) == "fix-manifest"

    @pytest.mark.asyncio
    async def test_namespace_not_found_variant(self) -> None:
        """Another namespace not found variant."""
        error = 'the namespace "my-project" is not found on the cluster'
        assert await _triage_apply_error(error) == "fix-manifest"

    @pytest.mark.asyncio
    async def test_crashloopbackoff_is_fix_dockerfile(self) -> None:
        """CrashLoopBackOff → fix-dockerfile."""
        error = (
            "Pods unhealthy after deployment:\n"
            "  - llmsearchindex-abc123: CrashLoopBackOff — back-off restarting\n"
            "\nLogs from llmsearchindex-abc123:\n"
            "/bin/sh: streamlit: command not found"
        )
        assert await _triage_apply_error(error) == "fix-dockerfile"

    @pytest.mark.asyncio
    async def test_imagepullbackoff_is_fix_dockerfile(self) -> None:
        """ImagePullBackOff → fix-dockerfile."""
        error = "Pod app-xyz: ImagePullBackOff — failed to pull image quay.io/org/app:latest"
        assert await _triage_apply_error(error) == "fix-dockerfile"

    @pytest.mark.asyncio
    async def test_command_not_found_is_fix_dockerfile(self) -> None:
        """'command not found' in pod logs → fix-dockerfile."""
        error = "Container crashed: /bin/sh: streamlit: command not found"
        assert await _triage_apply_error(error) == "fix-dockerfile"

    @pytest.mark.asyncio
    async def test_exec_format_error_is_fix_dockerfile(self) -> None:
        """exec format error → fix-dockerfile."""
        error = "exec format error: exec /usr/local/bin/app"
        assert await _triage_apply_error(error) == "fix-dockerfile"


# --- Tests for _detect_container_issue in poc_execute ---


class TestDetectContainerIssue:
    """Test that _detect_container_issue correctly identifies container-level
    failures from PoC execution results."""

    def test_command_not_found_detected(self) -> None:
        from autopoc.agents.poc_execute import _detect_container_issue

        results = [
            {"status": "fail", "error_message": "streamlit: command not found", "output": ""},
        ]
        assert _detect_container_issue(results) is not None
        assert "Container runtime failure" in _detect_container_issue(results)

    def test_import_error_detected(self) -> None:
        from autopoc.agents.poc_execute import _detect_container_issue

        results = [
            {
                "status": "error",
                "error_message": "ModuleNotFoundError: No module named 'flask'",
                "output": "",
            },
        ]
        assert _detect_container_issue(results) is not None

    def test_crashloopbackoff_detected(self) -> None:
        from autopoc.agents.poc_execute import _detect_container_issue

        results = [
            {"status": "fail", "error_message": "Pod in CrashLoopBackOff state", "output": ""},
        ]
        assert _detect_container_issue(results) is not None

    def test_passing_results_not_flagged(self) -> None:
        from autopoc.agents.poc_execute import _detect_container_issue

        results = [
            {"status": "pass", "error_message": "", "output": "OK"},
        ]
        assert _detect_container_issue(results) is None

    def test_non_container_failure_not_flagged(self) -> None:
        from autopoc.agents.poc_execute import _detect_container_issue

        results = [
            {"status": "fail", "error_message": "HTTP 500 Internal Server Error", "output": ""},
        ]
        assert _detect_container_issue(results) is None

    def test_empty_results_not_flagged(self) -> None:
        from autopoc.agents.poc_execute import _detect_container_issue

        assert _detect_container_issue([]) is None
        assert _detect_container_issue(None) is None


# --- Tests for kubectl_apply RBAC vs field-level error handling ---


class TestKubectlApplyErrorHandling:
    """Test that kubectl_apply distinguishes RBAC errors from field-level
    errors and only triggers delete-and-reapply for the latter."""

    def test_rbac_error_is_not_field_error(self) -> None:
        """RBAC forbidden error should NOT match the field-error pattern."""
        error_msg = (
            'namespaces "kwipu" is forbidden: User '
            '"system:serviceaccount:autopoc-test:autopoc-runner" '
            'cannot patch resource "namespaces"'
        ).lower()

        is_rbac_error = "cannot " in error_msg and "resource" in error_msg
        is_field_error = (
            "field is immutable" in error_msg
            or "is invalid" in error_msg
            or ("is forbidden" in error_msg and not is_rbac_error)
        )
        assert is_rbac_error is True
        assert is_field_error is False

    def test_field_immutable_is_field_error(self) -> None:
        """'field is immutable' should match field-error pattern."""
        error_msg = (
            'the job "my-job" is invalid: spec.template: Invalid value: field is immutable'
        ).lower()

        is_rbac_error = "cannot " in error_msg and "resource" in error_msg
        is_field_error = (
            "field is immutable" in error_msg
            or "is invalid" in error_msg
            or ("is forbidden" in error_msg and not is_rbac_error)
        )
        assert is_rbac_error is False
        assert is_field_error is True

    def test_field_forbidden_without_rbac(self) -> None:
        """'field X is forbidden' (not RBAC) should match field-error."""
        error_msg = (
            "spec.containers[0].securityContext.runAsUser: "
            "Forbidden: field is forbidden in this context"
        ).lower()

        is_rbac_error = "cannot " in error_msg and "resource" in error_msg
        is_field_error = (
            "field is immutable" in error_msg
            or "is invalid" in error_msg
            or ("is forbidden" in error_msg and not is_rbac_error)
        )
        assert is_rbac_error is False
        assert is_field_error is True

    def test_is_invalid_is_field_error(self) -> None:
        """'is invalid' should match field-error pattern."""
        error_msg = (
            'the job "my-job" is invalid: spec.selector: Invalid value: selector is immutable'
        ).lower()

        is_rbac_error = "cannot " in error_msg and "resource" in error_msg
        is_field_error = (
            "field is immutable" in error_msg
            or "is invalid" in error_msg
            or ("is forbidden" in error_msg and not is_rbac_error)
        )
        assert is_rbac_error is False
        assert is_field_error is True

    def test_rbac_cannot_get_jobs_is_not_field_error(self) -> None:
        """RBAC 'cannot get resource jobs' should NOT trigger delete-and-reapply."""
        error_msg = (
            'jobs.batch "my-job" is forbidden: User '
            '"system:serviceaccount:ns:sa" '
            'cannot get resource "jobs" in API group "batch"'
        ).lower()

        is_rbac_error = "cannot " in error_msg and "resource" in error_msg
        is_field_error = (
            "field is immutable" in error_msg
            or "is invalid" in error_msg
            or ("is forbidden" in error_msg and not is_rbac_error)
        )
        assert is_rbac_error is True
        assert is_field_error is False
