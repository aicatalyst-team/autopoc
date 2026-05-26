"""LLM proxy resolution for PoC projects.

When an OGX server is configured, this module transforms LLM-related
environment variables to point at the OGX proxy instead of requiring
real API keys from external providers.

The OGX server (formerly LlamaStack) sits between PoC apps and our
vLLM backend, exposing an OpenAI-compatible API. This means PoC projects
that need OPENAI_API_KEY can be deployed without real API keys — requests
are routed through OGX to our own Qwen3-32B inference server.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autopoc.config import AutoPoCConfig

logger = logging.getLogger(__name__)

# Environment variable names that hold LLM API keys.
_API_KEY_VARS = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    }
)

# Environment variable names that hold LLM base URLs.
_BASE_URL_VARS = frozenset(
    {
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
    }
)

# Environment variable names that hold model names.
_MODEL_VARS = frozenset(
    {
        "OPENAI_MODEL",
        "MODEL_NAME",
        "LLM_MODEL",
        "CHAT_MODEL",
        "MODEL",
    }
)


def resolve_llm_env_vars(
    extra_env_vars: dict[str, str],
    infrastructure: dict[str, Any],
    config: AutoPoCConfig,
) -> dict[str, str]:
    """Resolve LLM-related env vars by substituting OGX proxy details.

    If OGX is configured and the project needs LLM API access,
    replaces placeholder API keys with OGX connection details.

    Args:
        extra_env_vars: Original env vars from PoC plan.
        infrastructure: PoC infrastructure requirements.
        config: AutoPoC configuration.

    Returns:
        Modified env vars dict with OGX substitutions applied.
        If OGX is not configured or the project doesn't need LLM
        access, returns the original dict unchanged.
    """
    if not config.ogx_base_url:
        return extra_env_vars

    if not infrastructure.get("needs_llm_api"):
        return extra_env_vars

    resolved = dict(extra_env_vars)
    pattern = infrastructure.get("llm_env_pattern") or "openai"

    logger.info(
        "Resolving LLM env vars through OGX proxy (pattern=%s, url=%s, model=%s)",
        pattern,
        config.ogx_base_url,
        config.ogx_model,
    )

    # --- Substitute known env var names ---

    for key in list(resolved.keys()):
        if key in _API_KEY_VARS:
            resolved[key] = config.ogx_api_key
        elif key in _BASE_URL_VARS:
            resolved[key] = config.ogx_base_url
        elif key in _MODEL_VARS:
            resolved[key] = config.ogx_model
        elif key.endswith("_API_KEY") and resolved[key] in (
            "required",
            "placeholder-replace-me",
        ):
            # Catch-all for any *_API_KEY with placeholder value
            resolved[key] = config.ogx_api_key

    # --- Ensure required vars are present for each pattern ---

    if pattern in ("openai", "langchain"):
        resolved.setdefault("OPENAI_BASE_URL", config.ogx_base_url)
        resolved.setdefault("OPENAI_API_KEY", config.ogx_api_key)
    elif pattern == "anthropic":
        # OGX supports the Anthropic Messages API at the same endpoint
        resolved.setdefault("ANTHROPIC_API_KEY", config.ogx_api_key)
        # Many projects also accept OPENAI_BASE_URL for Anthropic via proxy
        resolved.setdefault("OPENAI_BASE_URL", config.ogx_base_url)
    elif pattern == "custom":
        # For custom patterns, just ensure at least one base URL is set
        resolved.setdefault("OPENAI_BASE_URL", config.ogx_base_url)
        resolved.setdefault("OPENAI_API_KEY", config.ogx_api_key)

    logger.info("Resolved %d LLM env vars through OGX proxy", len(resolved))
    return resolved
