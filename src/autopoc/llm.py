"""LLM factory for AutoPoC agents.

Centralizes LLM creation so the API key from our config is always used,
regardless of whether it's set as an environment variable.

Supported providers:
- Anthropic via Vertex AI: VERTEX_PROJECT + VERTEX_LOCATION
- Anthropic (direct): ANTHROPIC_API_KEY
- OpenAI-compatible (vLLM, Ollama, etc.): LLM_BASE_URL + LLM_MODEL

When both a cloud provider and LLM_BASE_URL are configured, the cloud
provider is used as primary and LLM_BASE_URL as automatic fallback on
retryable errors (429, 500, 502, 503, 529).
"""

import logging
import re

from anthropic import APIConnectionError as AnthropicAPIConnectionError
from anthropic import InternalServerError as AnthropicInternalServerError
from anthropic import RateLimitError as AnthropicRateLimitError
from anthropic._exceptions import OverloadedError as AnthropicOverloadedError
from google.api_core.exceptions import ServerError as GoogleServerError
from google.api_core.exceptions import TooManyRequests as GoogleTooManyRequests
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_google_vertexai.model_garden import ChatAnthropicVertex
from langchain_openai import ChatOpenAI
from openai import APIConnectionError as OpenAIAPIConnectionError
from openai import InternalServerError as OpenAIInternalServerError
from openai import RateLimitError as OpenAIRateLimitError

from autopoc.config import AutoPoCConfig, load_config

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

# Claude models have 200K context — 16K output is safe.
# Smaller models (Qwen3-32B has 40K context) need a lower value
# to leave room for the input prompt.
ANTHROPIC_MAX_OUTPUT_TOKENS = 16384

# For OpenAI-compatible endpoints (vLLM, Ollama), use a conservative
# default. A Dockerfile is ~100 lines (~1K tokens), a PoC plan is
# ~2K tokens. 4096 is generous for any single agent response while
# leaving most of the context for input.
# Override with LLM_MAX_TOKENS env var if needed.
OPENAI_COMPAT_MAX_OUTPUT_TOKENS = 4096

# Retryable exception types that trigger fallback to the local LLM.
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    # Anthropic SDK
    AnthropicRateLimitError,  # 429
    AnthropicInternalServerError,  # 500, 502, 503, 504 (>= 500 catch-all)
    AnthropicOverloadedError,  # 529 (sibling of InternalServerError)
    AnthropicAPIConnectionError,  # network errors + timeouts
    # Google / Vertex AI
    GoogleTooManyRequests,  # 429 (+ ResourceExhausted as subclass)
    GoogleServerError,  # 500, 502, 503, 504 (all 5xx)
    # OpenAI SDK (used by vLLM endpoint)
    OpenAIRateLimitError,  # 429
    OpenAIInternalServerError,  # 500, 502, 503, 504 (>= 500 catch-all)
    OpenAIAPIConnectionError,  # network errors + timeouts
)


def _get_retryable_exceptions() -> tuple[type[BaseException], ...]:
    """Return the retryable exception types for fallback handling."""
    return _RETRYABLE_EXCEPTIONS


def _build_cloud_llm(config: AutoPoCConfig, model: str | None = None) -> BaseChatModel | None:
    """Build the primary cloud LLM (Anthropic/Vertex), or None if not configured."""
    actual_model = model or config.llm_model or DEFAULT_MODEL

    # Anthropic via Vertex AI
    if config.vertex_project:
        if actual_model == "claude-3-5-sonnet-20241022":
            actual_model = "claude-3-5-sonnet-v2@20241022"

        return ChatAnthropicVertex(
            project=config.vertex_project,
            location=config.vertex_location,
            model_name=actual_model,
            max_retries=config.llm_max_retries,
            max_output_tokens=config.llm_max_tokens or ANTHROPIC_MAX_OUTPUT_TOKENS,
        )

    # Anthropic direct
    if config.anthropic_api_key:
        return ChatAnthropic(
            model_name=actual_model,
            api_key=config.anthropic_api_key,
            max_retries=config.llm_max_retries,
            max_tokens=config.llm_max_tokens or ANTHROPIC_MAX_OUTPUT_TOKENS,
        )  # type: ignore[call-arg]

    return None


def _build_openai_compat_llm(config: AutoPoCConfig, model: str | None = None) -> BaseChatModel:
    """Build the OpenAI-compatible LLM (vLLM, Ollama, etc.)."""
    actual_model = model or config.llm_model or DEFAULT_MODEL
    api_key = config.llm_api_key or "none"
    max_tokens = config.llm_max_tokens or OPENAI_COMPAT_MAX_OUTPUT_TOKENS

    return ChatOpenAI(
        model=actual_model,
        base_url=config.llm_base_url,
        api_key=api_key,
        max_retries=config.llm_max_retries,
        max_tokens=max_tokens,  # type: ignore[call-arg]
    )


def create_llm(model: str | None = None) -> Runnable:
    """Create an LLM instance based on config, with optional fallback.

    Provider priority:
    1. VERTEX_PROJECT (Anthropic via Google Vertex AI)
    2. ANTHROPIC_API_KEY (Anthropic direct)
    3. LLM_BASE_URL (OpenAI-compatible endpoint, e.g. vLLM)

    When both a cloud provider and LLM_BASE_URL are configured, the cloud
    provider is primary and the OpenAI-compatible endpoint is the fallback.
    Fallback triggers on retryable errors (429, 500, 502, 503, 529, network).

    Args:
        model: Model name to use. If not provided, uses the model from config.

    Returns:
        A configured LangChain chat model instance, potentially wrapped with
        fallback behavior.
    """
    config = load_config()

    # Try to build the cloud LLM (Anthropic/Vertex)
    cloud_llm = _build_cloud_llm(config, model)

    # If no cloud provider, use the OpenAI-compatible endpoint directly
    if cloud_llm is None:
        return _build_openai_compat_llm(config, model)

    # Cloud provider exists. Check if fallback is available and enabled.
    if config.has_fallback_provider:
        fallback_llm = _build_openai_compat_llm(config, model)
        retryable = _get_retryable_exceptions()

        logger.info(
            "LLM fallback enabled: primary=%s, fallback=%s (on %d exception types)",
            type(cloud_llm).__name__,
            type(fallback_llm).__name__,
            len(retryable),
        )

        return cloud_llm.with_fallbacks(
            [fallback_llm],
            exceptions_to_handle=retryable,
        )

    # Cloud-only, no fallback
    return cloud_llm


def strip_think_tags(text: str) -> str:
    """Remove Qwen3-style <think>...</think> reasoning blocks from LLM output.

    Some models (e.g. Qwen3) wrap chain-of-thought in <think> tags.
    This strips them so downstream parsing sees only the final answer.
    """
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()
