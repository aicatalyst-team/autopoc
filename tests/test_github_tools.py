"""Tests for GitHub tools."""


def test_github_tools_import():
    """Test that GitHub tools can be imported."""
    from autopoc.tools.github_tools import (
        get_repository_topics,
        set_repository_topics,
        is_autopoc_repository,
        list_autopoc_repositories,
        force_sync_repository,
        create_autopoc_fork,
        check_github_repository_exists,
    )

    # Check all functions exist and have descriptions
    assert get_repository_topics.description is not None
    assert set_repository_topics.description is not None
    assert is_autopoc_repository.description is not None
    assert list_autopoc_repositories.description is not None
    assert force_sync_repository.description is not None
    assert create_autopoc_fork.description is not None
    assert check_github_repository_exists.description is not None


def test_github_tools_schema():
    """Test that GitHub tools have proper schemas."""
    from autopoc.tools.github_tools import get_repository_topics

    # Test that the tool has a proper args schema
    assert get_repository_topics.args_schema is not None
    assert hasattr(get_repository_topics.args_schema, "model_fields")

    # Check required fields exist
    fields = get_repository_topics.args_schema.model_fields
    assert "owner" in fields
    assert "repo" in fields
