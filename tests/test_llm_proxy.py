"""Tests for autopoc.llm_proxy module."""

from __future__ import annotations

import os
from unittest.mock import patch

from autopoc.config import AutoPoCConfig
from typing import Any

from autopoc.llm_proxy import resolve_llm_env_vars


def _make_config(**overrides: str) -> AutoPoCConfig:
    """Create a config with OGX fields set, plus minimal required fields."""
    env = {
        "ANTHROPIC_API_KEY": "sk-ant-test-key",
        "GITLAB_URL": "https://gitlab.example.com",
        "GITLAB_TOKEN": "glpat-test",
        "GITLAB_GROUP": "poc",
        "QUAY_ORG": "org",
        "QUAY_TOKEN": "tok",
        # OGX defaults
        "OGX_BASE_URL": "http://ogx-svc.ogx.svc.cluster.local:8321/v1",
        "OGX_MODEL": "qwen3-32b",
        "OGX_API_KEY": "none",
    }
    env.update(overrides)
    with patch.dict(os.environ, env, clear=True):
        return AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]


def _make_config_no_ogx() -> AutoPoCConfig:
    """Create a config without OGX fields set."""
    env = {
        "ANTHROPIC_API_KEY": "sk-ant-test-key",
        "GITLAB_URL": "https://gitlab.example.com",
        "GITLAB_TOKEN": "glpat-test",
        "GITLAB_GROUP": "poc",
        "QUAY_ORG": "org",
        "QUAY_TOKEN": "tok",
    }
    with patch.dict(os.environ, env, clear=True):
        return AutoPoCConfig(_env_file=None)  # type: ignore[call-arg]


class TestResolveLlmEnvVars:
    """Tests for resolve_llm_env_vars()."""

    def test_ogx_not_configured_passthrough(self) -> None:
        """When OGX is not configured, env vars pass through unchanged."""
        config = _make_config_no_ogx()
        env_vars = {"OPENAI_API_KEY": "required", "DATABASE_URL": "postgres://..."}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result is env_vars  # same object — no copy

    def test_llm_not_needed_passthrough(self) -> None:
        """When project doesn't need LLM API, env vars pass through unchanged."""
        config = _make_config()
        env_vars = {"DATABASE_URL": "postgres://...", "PORT": "8080"}
        infra: dict[str, Any] = {"needs_llm_api": False, "llm_env_pattern": None}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result is env_vars  # same object — no copy

    def test_needs_llm_api_missing_passthrough(self) -> None:
        """When needs_llm_api is not set at all, env vars pass through."""
        config = _make_config()
        env_vars = {"OPENAI_API_KEY": "required"}
        infra: dict[str, Any] = {}  # type: ignore[typeddict-item]

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result is env_vars

    def test_openai_pattern_substitutes_key_and_url(self) -> None:
        """OpenAI pattern: substitutes API key and adds base URL."""
        config = _make_config()
        env_vars = {"OPENAI_API_KEY": "required", "OPENAI_MODEL": "gpt-4"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["OPENAI_API_KEY"] == "none"
        assert result["OPENAI_MODEL"] == "qwen3-32b"
        assert result["OPENAI_BASE_URL"] == "http://ogx-svc.ogx.svc.cluster.local:8321/v1"

    def test_openai_pattern_adds_base_url_if_missing(self) -> None:
        """OpenAI pattern: adds OPENAI_BASE_URL even if not in original vars."""
        config = _make_config()
        env_vars = {"OPENAI_API_KEY": "required"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert "OPENAI_BASE_URL" in result
        assert result["OPENAI_BASE_URL"] == "http://ogx-svc.ogx.svc.cluster.local:8321/v1"
        assert result["OPENAI_API_KEY"] == "none"

    def test_openai_pattern_preserves_existing_base_url(self) -> None:
        """OpenAI pattern: substitutes existing OPENAI_BASE_URL."""
        config = _make_config()
        env_vars = {
            "OPENAI_API_KEY": "required",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
        }
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        # Existing key gets overwritten with OGX URL
        assert result["OPENAI_BASE_URL"] == "http://ogx-svc.ogx.svc.cluster.local:8321/v1"

    def test_anthropic_pattern(self) -> None:
        """Anthropic pattern: substitutes ANTHROPIC_API_KEY."""
        config = _make_config()
        env_vars = {"ANTHROPIC_API_KEY": "required"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "anthropic"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["ANTHROPIC_API_KEY"] == "none"
        # Also adds OPENAI_BASE_URL for proxy
        assert result["OPENAI_BASE_URL"] == "http://ogx-svc.ogx.svc.cluster.local:8321/v1"

    def test_langchain_pattern(self) -> None:
        """LangChain pattern: same as openai — OPENAI_BASE_URL and OPENAI_API_KEY."""
        config = _make_config()
        env_vars = {"OPENAI_API_KEY": "required"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "langchain"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["OPENAI_API_KEY"] == "none"
        assert result["OPENAI_BASE_URL"] == "http://ogx-svc.ogx.svc.cluster.local:8321/v1"

    def test_custom_pattern(self) -> None:
        """Custom pattern: ensures at least OPENAI_BASE_URL is set."""
        config = _make_config()
        env_vars = {"CUSTOM_LLM_KEY": "required"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "custom"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        # Custom key with "required" value gets replaced (catch-all for *_KEY patterns)
        # But CUSTOM_LLM_KEY doesn't end with _API_KEY, so it stays
        assert result["CUSTOM_LLM_KEY"] == "required"
        # Base URL is still added for custom pattern
        assert result["OPENAI_BASE_URL"] == "http://ogx-svc.ogx.svc.cluster.local:8321/v1"

    def test_catchall_api_key_with_required_value(self) -> None:
        """Catch-all: any *_API_KEY with value 'required' gets replaced."""
        config = _make_config()
        env_vars = {"MY_LLM_API_KEY": "required", "OTHER_API_KEY": "placeholder-replace-me"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["MY_LLM_API_KEY"] == "none"
        assert result["OTHER_API_KEY"] == "none"

    def test_catchall_api_key_with_real_value_untouched(self) -> None:
        """Catch-all: *_API_KEY with a real value (not 'required') is untouched."""
        config = _make_config()
        env_vars = {"MY_SERVICE_API_KEY": "actual-key-123"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        # Not a known API key var, and value isn't "required", so it stays
        assert result["MY_SERVICE_API_KEY"] == "actual-key-123"

    def test_non_llm_env_vars_untouched(self) -> None:
        """Non-LLM env vars are not modified."""
        config = _make_config()
        env_vars = {
            "OPENAI_API_KEY": "required",
            "DATABASE_URL": "postgres://localhost/mydb",
            "PORT": "8080",
            "DEBUG": "true",
        }
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["DATABASE_URL"] == "postgres://localhost/mydb"
        assert result["PORT"] == "8080"
        assert result["DEBUG"] == "true"
        # But OPENAI_API_KEY is substituted
        assert result["OPENAI_API_KEY"] == "none"

    def test_model_name_vars_substituted(self) -> None:
        """All model name env var patterns are substituted."""
        config = _make_config()
        env_vars = {
            "OPENAI_API_KEY": "required",
            "MODEL_NAME": "gpt-4o",
            "LLM_MODEL": "claude-3-opus",
            "CHAT_MODEL": "gpt-3.5-turbo",
            "MODEL": "some-model",
        }
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["MODEL_NAME"] == "qwen3-32b"
        assert result["LLM_MODEL"] == "qwen3-32b"
        assert result["CHAT_MODEL"] == "qwen3-32b"
        assert result["MODEL"] == "qwen3-32b"

    def test_openai_api_base_substituted(self) -> None:
        """OPENAI_API_BASE (older convention) is also substituted."""
        config = _make_config()
        env_vars = {
            "OPENAI_API_KEY": "required",
            "OPENAI_API_BASE": "https://api.openai.com",
        }
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["OPENAI_API_BASE"] == "http://ogx-svc.ogx.svc.cluster.local:8321/v1"

    def test_custom_ogx_model(self) -> None:
        """Custom OGX model name is used when configured."""
        config = _make_config(OGX_MODEL="llama-3.3-70b")
        env_vars = {"OPENAI_API_KEY": "required", "OPENAI_MODEL": "gpt-4"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["OPENAI_MODEL"] == "llama-3.3-70b"

    def test_custom_ogx_api_key(self) -> None:
        """Custom OGX API key is used when configured."""
        config = _make_config(OGX_API_KEY="my-secret-key")
        env_vars = {"OPENAI_API_KEY": "required"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["OPENAI_API_KEY"] == "my-secret-key"

    def test_empty_env_vars_with_openai_pattern(self) -> None:
        """Empty env vars dict still gets OPENAI_BASE_URL and OPENAI_API_KEY added."""
        config = _make_config()
        env_vars: dict[str, str] = {}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["OPENAI_BASE_URL"] == "http://ogx-svc.ogx.svc.cluster.local:8321/v1"
        assert result["OPENAI_API_KEY"] == "none"

    def test_default_pattern_is_openai(self) -> None:
        """When llm_env_pattern is None, defaults to openai behavior."""
        config = _make_config()
        env_vars = {"OPENAI_API_KEY": "required"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": None}

        result = resolve_llm_env_vars(env_vars, infra, config)

        assert result["OPENAI_API_KEY"] == "none"
        assert result["OPENAI_BASE_URL"] == "http://ogx-svc.ogx.svc.cluster.local:8321/v1"

    def test_original_dict_not_mutated(self) -> None:
        """The original env vars dict is not mutated — a new dict is returned."""
        config = _make_config()
        env_vars = {"OPENAI_API_KEY": "required"}
        infra: dict[str, Any] = {"needs_llm_api": True, "llm_env_pattern": "openai"}

        result = resolve_llm_env_vars(env_vars, infra, config)

        # Original should be unchanged
        assert env_vars["OPENAI_API_KEY"] == "required"
        assert "OPENAI_BASE_URL" not in env_vars
        # Result should be different
        assert result["OPENAI_API_KEY"] == "none"
        assert result is not env_vars
