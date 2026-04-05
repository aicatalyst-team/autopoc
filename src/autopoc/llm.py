"""LLM factory for AutoPoC agents.

Centralizes LLM creation so the API key from our config is always used,
regardless of whether it's set as an environment variable.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_vertexai.model_garden import ChatAnthropicVertex

from autopoc.config import load_config

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def create_llm(model: str = DEFAULT_MODEL) -> BaseChatModel:
    """Create a ChatAnthropic or ChatAnthropicVertex instance based on config.

    Args:
        model: Anthropic model name to use.

    Returns:
        A configured ChatAnthropic or ChatAnthropicVertex instance.
    """
    config = load_config()

    if config.vertex_project:
        # Vertex uses a different naming convention for the model
        if model == DEFAULT_MODEL:
            model = "claude-3-5-sonnet-v2@20241022"

        return ChatAnthropicVertex(
            project=config.vertex_project,
            location=config.vertex_location,
            model_name=model,
            max_retries=config.llm_max_retries,
        )

    return ChatAnthropic(
        model_name=model,
        api_key=config.anthropic_api_key,
        max_retries=config.llm_max_retries,
    )  # type: ignore[call-arg]
