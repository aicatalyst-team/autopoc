"""LLM factory for AutoPoC agents.

Centralizes LLM creation so the API key from our config is always used,
regardless of whether it's set as an environment variable.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from autopoc.config import load_config

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def create_llm(model: str = DEFAULT_MODEL) -> BaseChatModel:
    """Create a ChatAnthropic instance with the API key from config.

    Args:
        model: Anthropic model name to use.

    Returns:
        A configured ChatAnthropic instance.
    """
    config = load_config()
    return ChatAnthropic(
        model_name=model,
        api_key=config.anthropic_api_key,
        max_retries=config.llm_max_retries,
    )  # type: ignore[call-arg]
