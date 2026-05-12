"""Tests for LLM fallback behavior.

Verifies that when both a cloud provider (Anthropic/Vertex) and an
OpenAI-compatible endpoint (vLLM) are configured, the LLM factory
returns a fallback-wrapped model that retries on the vLLM endpoint
when the cloud provider returns retryable errors.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables.fallbacks import RunnableWithFallbacks

from autopoc.config import AutoPoCConfig


# ---------------------------------------------------------------------------
# Shared env helpers
# ---------------------------------------------------------------------------

# Base env vars required by AutoPoCConfig regardless of LLM setup
_BASE_ENV = {
    "GITLAB_URL": "https://gitlab.example.com",
    "GITLAB_TOKEN": "glpat-test-token",
    "GITLAB_GROUP": "poc-demos",
    "QUAY_ORG": "test-org",
    "QUAY_TOKEN": "quay-test-token",
}


def _env_cloud_only(**overrides: str) -> dict[str, str]:
    """Env with only a cloud provider (Anthropic direct)."""
    env = {**_BASE_ENV, "ANTHROPIC_API_KEY": "sk-ant-test-key-12345"}
    env.update(overrides)
    return env


def _env_vllm_only(**overrides: str) -> dict[str, str]:
    """Env with only an OpenAI-compatible endpoint."""
    env = {
        **_BASE_ENV,
        "LLM_BASE_URL": "http://vllm:8000/v1",
        "LLM_MODEL": "qwen2.5-coder-32b",
    }
    env.update(overrides)
    return env


def _env_both(**overrides: str) -> dict[str, str]:
    """Env with both cloud and vLLM configured (fallback mode)."""
    env = {
        **_BASE_ENV,
        "ANTHROPIC_API_KEY": "sk-ant-test-key-12345",
        "LLM_BASE_URL": "http://vllm:8000/v1",
        "LLM_MODEL": "qwen2.5-coder-32b",
    }
    env.update(overrides)
    return env


def _env_vertex_and_vllm(**overrides: str) -> dict[str, str]:
    """Env with Vertex AI as primary and vLLM as fallback."""
    env = {
        **_BASE_ENV,
        "VERTEX_PROJECT": "my-gcp-project",
        "VERTEX_LOCATION": "us-east5",
        "LLM_BASE_URL": "http://vllm:8000/v1",
        "LLM_MODEL": "qwen2.5-coder-32b",
    }
    env.update(overrides)
    return env


# =========================================================================
# Config property tests
# =========================================================================


class TestConfigFallbackProperties:
    """Tests for has_cloud_provider and has_fallback_provider."""

    def test_cloud_only_has_cloud_provider(self) -> None:
        with patch.dict(os.environ, _env_cloud_only(), clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            assert config.has_cloud_provider is True
            assert config.has_fallback_provider is False

    def test_vllm_only_no_cloud_provider(self) -> None:
        with patch.dict(os.environ, _env_vllm_only(), clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            assert config.has_cloud_provider is False
            assert config.has_fallback_provider is False

    def test_both_has_fallback(self) -> None:
        with patch.dict(os.environ, _env_both(), clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            assert config.has_cloud_provider is True
            assert config.has_fallback_provider is True

    def test_both_with_fallback_disabled(self) -> None:
        with patch.dict(os.environ, _env_both(LLM_FALLBACK_ENABLED="false"), clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            assert config.has_cloud_provider is True
            assert config.has_fallback_provider is False

    def test_vertex_has_cloud_provider(self) -> None:
        with patch.dict(os.environ, _env_vertex_and_vllm(), clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            assert config.has_cloud_provider is True
            assert config.has_fallback_provider is True


# =========================================================================
# create_llm() factory tests
# =========================================================================


class TestCreateLlmFactory:
    """Tests that create_llm() returns the correct type based on config."""

    @patch("autopoc.llm.load_config")
    def test_cloud_only_returns_plain_model(self, mock_load: MagicMock) -> None:
        """With only Anthropic configured, returns a plain ChatAnthropic."""
        with patch.dict(os.environ, _env_cloud_only(), clear=True):
            mock_load.return_value = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]

            from autopoc.llm import create_llm

            llm = create_llm()

            assert not isinstance(llm, RunnableWithFallbacks)
            # Should be a ChatAnthropic instance
            assert type(llm).__name__ == "ChatAnthropic"

    @patch("autopoc.llm.load_config")
    def test_vllm_only_returns_plain_model(self, mock_load: MagicMock) -> None:
        """With only vLLM configured, returns a plain ChatOpenAI."""
        with patch.dict(os.environ, _env_vllm_only(), clear=True):
            mock_load.return_value = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]

            from autopoc.llm import create_llm

            llm = create_llm()

            assert not isinstance(llm, RunnableWithFallbacks)
            assert type(llm).__name__ == "ChatOpenAI"

    @patch("autopoc.llm.load_config")
    def test_both_returns_fallback_wrapped(self, mock_load: MagicMock) -> None:
        """With both providers configured, returns RunnableWithFallbacks."""
        with patch.dict(os.environ, _env_both(), clear=True):
            mock_load.return_value = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]

            from autopoc.llm import create_llm

            llm = create_llm()

            assert isinstance(llm, RunnableWithFallbacks)
            # Primary should be ChatAnthropic
            assert type(llm.runnable).__name__ == "ChatAnthropic"
            # Fallback should be ChatOpenAI
            assert len(llm.fallbacks) == 1
            assert type(llm.fallbacks[0]).__name__ == "ChatOpenAI"

    @patch("autopoc.llm.load_config")
    def test_both_with_fallback_disabled_returns_plain(self, mock_load: MagicMock) -> None:
        """With fallback disabled, returns plain cloud model even when vLLM is configured."""
        with patch.dict(os.environ, _env_both(LLM_FALLBACK_ENABLED="false"), clear=True):
            mock_load.return_value = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]

            from autopoc.llm import create_llm

            llm = create_llm()

            assert not isinstance(llm, RunnableWithFallbacks)
            assert type(llm).__name__ == "ChatAnthropic"

    @patch("autopoc.llm.load_config")
    def test_vertex_plus_vllm_returns_fallback_wrapped(self, mock_load: MagicMock) -> None:
        """Vertex AI as primary + vLLM as fallback."""
        with patch.dict(os.environ, _env_vertex_and_vllm(), clear=True):
            mock_load.return_value = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]

            from autopoc.llm import create_llm

            llm = create_llm()

            assert isinstance(llm, RunnableWithFallbacks)
            assert type(llm.runnable).__name__ == "ChatAnthropicVertex"
            assert len(llm.fallbacks) == 1
            assert type(llm.fallbacks[0]).__name__ == "ChatOpenAI"


# =========================================================================
# Fallback behavior tests (mock LLM calls)
# =========================================================================


class TestFallbackBehavior:
    """Test that fallback actually triggers on retryable errors."""

    def test_fallback_triggers_on_rate_limit(self) -> None:
        """When primary raises RateLimitError, fallback is used."""
        from anthropic import RateLimitError as AnthropicRateLimitError
        from langchain_core.runnables import RunnableLambda

        from autopoc.llm import _get_retryable_exceptions

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        def fail_primary(_input: object) -> str:
            raise AnthropicRateLimitError(
                message="Rate limited",
                response=mock_response,
                body=None,
            )

        def succeed_fallback(_input: object) -> str:
            return "fallback worked"

        retryable = _get_retryable_exceptions()
        wrapped = RunnableLambda(fail_primary).with_fallbacks(
            [RunnableLambda(succeed_fallback)],
            exceptions_to_handle=retryable,
        )

        result = wrapped.invoke("test input")
        assert result == "fallback worked"

    def test_fallback_triggers_on_internal_server_error(self) -> None:
        """When primary raises InternalServerError (500), fallback is used."""
        from anthropic import InternalServerError as AnthropicInternalServerError

        from autopoc.llm import _get_retryable_exceptions

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}

        from langchain_core.runnables import RunnableLambda

        def fail_primary(_input: object) -> str:
            raise AnthropicInternalServerError(
                message="Internal error",
                response=mock_response,
                body=None,
            )

        def succeed_fallback(_input: object) -> str:
            return "fallback on 500"

        retryable = _get_retryable_exceptions()
        wrapped = RunnableLambda(fail_primary).with_fallbacks(
            [RunnableLambda(succeed_fallback)],
            exceptions_to_handle=retryable,
        )

        result = wrapped.invoke("test")
        assert result == "fallback on 500"

    def test_fallback_triggers_on_overloaded(self) -> None:
        """When primary raises OverloadedError (529), fallback is used."""
        try:
            from anthropic._exceptions import OverloadedError as AnthropicOverloadedError
        except ImportError:
            pytest.skip("OverloadedError not available in this anthropic version")

        from autopoc.llm import _get_retryable_exceptions

        mock_response = MagicMock()
        mock_response.status_code = 529
        mock_response.headers = {}

        from langchain_core.runnables import RunnableLambda

        def fail_primary(_input: object) -> str:
            raise AnthropicOverloadedError(
                message="Overloaded",
                response=mock_response,
                body=None,
            )

        def succeed_fallback(_input: object) -> str:
            return "fallback on 529"

        retryable = _get_retryable_exceptions()
        wrapped = RunnableLambda(fail_primary).with_fallbacks(
            [RunnableLambda(succeed_fallback)],
            exceptions_to_handle=retryable,
        )

        result = wrapped.invoke("test")
        assert result == "fallback on 529"

    def test_non_retryable_error_not_caught(self) -> None:
        """Non-retryable errors (e.g. ValueError) are NOT caught by fallback."""
        from autopoc.llm import _get_retryable_exceptions

        from langchain_core.runnables import RunnableLambda

        def fail_primary(_input: object) -> str:
            raise ValueError("bad input — not retryable")

        def succeed_fallback(_input: object) -> str:
            return "should not reach here"

        retryable = _get_retryable_exceptions()
        wrapped = RunnableLambda(fail_primary).with_fallbacks(
            [RunnableLambda(succeed_fallback)],
            exceptions_to_handle=retryable,
        )

        with pytest.raises(ValueError, match="bad input"):
            wrapped.invoke("test")

    def test_primary_success_does_not_use_fallback(self) -> None:
        """When primary succeeds, fallback is never called."""
        from autopoc.llm import _get_retryable_exceptions

        from langchain_core.runnables import RunnableLambda

        call_log: list[str] = []

        def succeed_primary(_input: object) -> str:
            call_log.append("primary")
            return "primary response"

        def succeed_fallback(_input: object) -> str:
            call_log.append("fallback")
            return "fallback response"

        retryable = _get_retryable_exceptions()
        wrapped = RunnableLambda(succeed_primary).with_fallbacks(
            [RunnableLambda(succeed_fallback)],
            exceptions_to_handle=retryable,
        )

        result = wrapped.invoke("test")
        assert result == "primary response"
        assert call_log == ["primary"]


# =========================================================================
# _get_retryable_exceptions tests
# =========================================================================


class TestRetryableExceptions:
    """Test that _get_retryable_exceptions collects the right types."""

    def test_includes_anthropic_exceptions(self) -> None:
        from anthropic import InternalServerError, RateLimitError

        from autopoc.llm import _get_retryable_exceptions

        retryable = _get_retryable_exceptions()
        assert RateLimitError in retryable
        assert InternalServerError in retryable

    def test_includes_openai_exceptions(self) -> None:
        from openai import InternalServerError, RateLimitError

        from autopoc.llm import _get_retryable_exceptions

        retryable = _get_retryable_exceptions()
        assert RateLimitError in retryable
        assert InternalServerError in retryable

    def test_includes_google_exceptions(self) -> None:
        from google.api_core.exceptions import ServerError, TooManyRequests

        from autopoc.llm import _get_retryable_exceptions

        retryable = _get_retryable_exceptions()
        assert TooManyRequests in retryable
        assert ServerError in retryable


# =========================================================================
# Credential check tests
# =========================================================================


class TestCheckLlmFallback:
    """Tests for check_llm_fallback credential check."""

    def test_returns_none_when_no_fallback(self) -> None:
        """Returns None when fallback is not configured."""
        from autopoc.credentials import check_llm_fallback

        with patch.dict(os.environ, _env_cloud_only(), clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            result = check_llm_fallback(config)
            assert result is None

    @patch("autopoc.credentials.httpx.get")
    def test_returns_ok_when_reachable(self, mock_get: MagicMock) -> None:
        """Returns OK when the vLLM endpoint is reachable."""
        from autopoc.credentials import check_llm_fallback

        mock_get.return_value = MagicMock(status_code=200)

        with patch.dict(os.environ, _env_both(), clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            result = check_llm_fallback(config)
            assert result is not None
            assert result.ok is True
            assert "vLLM" in result.service

    @patch("autopoc.credentials.httpx.get")
    def test_returns_fail_on_connection_error(self, mock_get: MagicMock) -> None:
        """Returns FAIL when the vLLM endpoint is unreachable."""
        import httpx

        from autopoc.credentials import check_llm_fallback

        mock_get.side_effect = httpx.ConnectError("Connection refused")

        with patch.dict(os.environ, _env_both(), clear=True):
            config = AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]
            result = check_llm_fallback(config)
            assert result is not None
            assert result.ok is False
            assert "cannot connect" in result.detail
