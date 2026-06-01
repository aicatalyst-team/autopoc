"""Tests for cleanup tools."""


def test_cleanup_tools_import():
    """Test that cleanup tools can be imported."""
    from autopoc.tools.cleanup_tools import (
        cleanup_openshift_build_resources,
        cleanup_local_build_images,
        cleanup_previous_build_failure,
        capture_deployment_failure_state,
        cleanup_failed_deployment,
        reset_deployment_namespace,
    )

    # Check all functions exist and have descriptions
    assert cleanup_openshift_build_resources.description is not None
    assert cleanup_local_build_images.description is not None
    assert cleanup_previous_build_failure.description is not None
    assert capture_deployment_failure_state.description is not None
    assert cleanup_failed_deployment.description is not None
    assert reset_deployment_namespace.description is not None


def test_cleanup_tools_schema():
    """Test that cleanup tools have proper schemas."""
    from autopoc.tools.cleanup_tools import cleanup_openshift_build_resources

    # Test that the tool has a proper args schema
    assert cleanup_openshift_build_resources.args_schema is not None
    assert hasattr(cleanup_openshift_build_resources.args_schema, "model_fields")

    # Check required fields exist
    fields = cleanup_openshift_build_resources.args_schema.model_fields
    assert "namespace" in fields
    assert "project_name" in fields
