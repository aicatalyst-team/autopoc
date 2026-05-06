"""LLM factory for AutoPoC agents.

Centralizes LLM creation so the API key from our config is always used,
regardless of whether it's set as an environment variable.

Supported providers:
- Anthropic (direct): ANTHROPIC_API_KEY
- Anthropic via Vertex AI: VERTEX_PROJECT + VERTEX_LOCATION
- OpenAI-compatible (vLLM, Ollama, etc.): LLM_BASE_URL + LLM_MODEL
"""

import re

from langchain_core.language_models import BaseChatModel

from autopoc.config import load_config

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


def create_llm(model: str | None = None) -> BaseChatModel:
    """Create an LLM instance based on config.

    Provider priority:
    1. LLM_BASE_URL (OpenAI-compatible endpoint, e.g. vLLM)
    2. VERTEX_PROJECT (Anthropic via Google Vertex AI)
    3. ANTHROPIC_API_KEY (Anthropic direct)

    Args:
        model: Model name to use. If not provided, uses the model from config.

    Returns:
        A configured LangChain chat model instance.
    """
    config = load_config()

    # Use explicitly passed model, or config, or fallback to default
    actual_model = model or config.llm_model or DEFAULT_MODEL

    # OpenAI-compatible endpoint (vLLM, Ollama, etc.)
    if config.llm_base_url:
        from langchain_openai import ChatOpenAI

        # vLLM and similar servers often don't require an API key;
        # use "none" or any placeholder if no auth is needed.
        api_key = config.llm_api_key or "none"

        # Allow override via config; otherwise use the conservative default
        # that works with smaller-context models like Qwen3-32B (40K context).
        max_tokens = config.llm_max_tokens or OPENAI_COMPAT_MAX_OUTPUT_TOKENS

        return ChatOpenAI(
            model=actual_model,
            base_url=config.llm_base_url,
            api_key=api_key,
            max_retries=config.llm_max_retries,
            max_tokens=max_tokens,
        )

    # Anthropic via Vertex AI
    if config.vertex_project:
        from langchain_google_vertexai.model_garden import ChatAnthropicVertex

        # Map common Anthropic model names to Vertex equivalents if needed
        # (claude-3-5-sonnet-20241022 -> claude-3-5-sonnet-v2@20241022)
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
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model_name=actual_model,
        api_key=config.anthropic_api_key,
        max_retries=config.llm_max_retries,
        max_tokens=config.llm_max_tokens or ANTHROPIC_MAX_OUTPUT_TOKENS,
    )  # type: ignore[call-arg]


def strip_think_tags(text: str) -> str:
    """Remove Qwen3-style <think>...</think> reasoning blocks from LLM output.

    Some models (e.g. Qwen3) wrap chain-of-thought in <think> tags.
    This strips them so downstream parsing sees only the final answer.
    """
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()
