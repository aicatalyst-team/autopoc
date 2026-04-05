"""Tests for autopoc.config module."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from autopoc.config import AutoPoCConfig


class TestAutoPoCConfig:
    """Tests for configuration loading and validation."""

    def test_load_with_all_vars(self, env_vars: dict[str, str]) -> None:
        """Config loads successfully when all env vars are set."""
        config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]

        assert config.anthropic_api_key == "sk-ant-test-key-12345"
        assert config.gitlab_url == "https://gitlab.example.com"
        assert config.gitlab_token == "glpat-test-token-67890"
        assert config.gitlab_group == "poc-demos"
        assert config.quay_registry == "quay.io"
        assert config.quay_org == "test-org"
        assert config.quay_token == "quay-test-token-abc"
        assert config.openshift_api_url == "https://api.cluster.example.com:6443"
        assert config.openshift_token == "sha256~test-token-xyz"
        assert config.openshift_namespace_prefix == "poc"
        assert config.max_build_retries == 3
        assert config.work_dir == "/tmp/autopoc-test"

    def test_load_with_minimal_vars_uses_defaults(self, env_vars_minimal: dict[str, str]) -> None:
        """Config uses defaults for optional fields when not explicitly set."""
        # Use _env_file=None to prevent .env on disk from leaking values
        config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]

        # Defaults applied
        assert config.quay_registry == "quay.io"
        assert config.openshift_namespace_prefix == "poc"
        assert config.max_build_retries == 3
        assert config.work_dir == "/tmp/autopoc"

    def test_missing_required_var_raises_validation_error(self) -> None:
        """Missing a required env var raises ValidationError naming the field."""
        # Set everything except ANTHROPIC_API_KEY and VERTEX_PROJECT
        env = {
            "GITLAB_URL": "https://gitlab.example.com",
            "GITLAB_TOKEN": "glpat-test",
            "GITLAB_GROUP": "poc",
            "QUAY_ORG": "org",
            "QUAY_TOKEN": "token",
            "OPENSHIFT_API_URL": "https://api.example.com:6443",
            "OPENSHIFT_TOKEN": "sha256~token",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                # Use _env_file=None to skip .env file on disk
                AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            # Verify the error mentions the missing field requirement
            assert "Either ANTHROPIC_API_KEY or VERTEX_PROJECT must be provided" in str(
                exc_info.value
            )

    def test_missing_multiple_required_vars(self) -> None:
        """Missing multiple required vars reports all of them."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            error_str = str(exc_info.value)
            assert "gitlab_url" in error_str
            assert "gitlab_token" in error_str
            assert "quay_org" in error_str

    def test_max_build_retries_is_int(self, env_vars: dict[str, str]) -> None:
        """max_build_retries is parsed as an integer from env string."""
        config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
        assert isinstance(config.max_build_retries, int)
        assert config.max_build_retries == 3

    def test_custom_defaults_override(self) -> None:
        """Optional fields can be overridden via env vars."""
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-key",
            "GITLAB_URL": "https://gitlab.example.com",
            "GITLAB_TOKEN": "glpat-test",
            "GITLAB_GROUP": "poc",
            "QUAY_REGISTRY": "quay.internal.example.com",
            "QUAY_ORG": "org",
            "QUAY_TOKEN": "token",
            "OPENSHIFT_API_URL": "https://api.example.com:6443",
            "OPENSHIFT_TOKEN": "sha256~token",
            "OPENSHIFT_NAMESPACE_PREFIX": "demo",
            "MAX_BUILD_RETRIES": "5",
            "WORK_DIR": "/data/autopoc",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            assert config.quay_registry == "quay.internal.example.com"
            assert config.openshift_namespace_prefix == "demo"
            assert config.max_build_retries == 5
            assert config.work_dir == "/data/autopoc"


class TestMaskedSummary:
    """Tests for the masked_summary display method."""

    def test_secrets_are_masked(self, env_vars: dict[str, str]) -> None:
        """Secret fields are masked in summary output."""
        config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
        summary = config.masked_summary()

        # Secrets should be masked
        assert "****" in summary["anthropic_api_key"]
        assert "****" in summary["gitlab_token"]
        assert "****" in summary["quay_token"]
        assert "****" in summary["openshift_token"]

        # Non-secrets should be clear
        assert summary["gitlab_url"] == "https://gitlab.example.com"
        assert summary["gitlab_group"] == "poc-demos"
        assert summary["quay_org"] == "test-org"

    def test_masked_secrets_show_partial(self, env_vars: dict[str, str]) -> None:
        """Masked secrets show first 4 and last 4 characters."""
        config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
        summary = config.masked_summary()

        # "sk-ant-test-key-12345" -> "sk-a****2345"
        masked_key = summary["anthropic_api_key"]
        assert masked_key.startswith("sk-a")
        assert masked_key.endswith("2345")

    def test_short_secret_fully_masked(self) -> None:
        """Secrets 8 chars or shorter are fully masked."""
        env = {
            "ANTHROPIC_API_KEY": "short",
            "GITLAB_URL": "https://gitlab.example.com",
            "GITLAB_TOKEN": "12345678",
            "GITLAB_GROUP": "poc",
            "QUAY_ORG": "org",
            "QUAY_TOKEN": "tok",
            "OPENSHIFT_API_URL": "https://api.example.com:6443",
            "OPENSHIFT_TOKEN": "sha",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            summary = config.masked_summary()
            assert summary["anthropic_api_key"] == "****"
            assert summary["gitlab_token"] == "****"
            assert summary["quay_token"] == "****"
