"""LLM factory for AutoPoC agents.

Centralizes LLM creation so the API key from our config is always used,
regardless of whether it's set as an environment variable.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_vertexai.model_garden import ChatAnthropicVertex

from autopoc.config import load_config

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"


def create_llm(model: str | None = None) -> BaseChatModel:
    """Create a ChatAnthropic or ChatAnthropicVertex instance based on config.

    Args:
        model: Model name to use. If not provided, uses the model from config.

    Returns:
        A configured ChatAnthropic or ChatAnthropicVertex instance.
    """
    config = load_config()

    # Use explicitly passed model, or config, or fallback to default
    actual_model = model or config.llm_model or DEFAULT_MODEL

    if config.vertex_project:
        # Map common Anthropic model names to Vertex equivalents if needed
        # (claude-3-5-sonnet-20241022 -> claude-3-5-sonnet-v2@20241022)
        if actual_model == "claude-3-5-sonnet-20241022":
            actual_model = "claude-3-5-sonnet-v2@20241022"

        return ChatAnthropicVertex(
            project=config.vertex_project,
            location=config.vertex_location,
            model_name=actual_model,
            max_retries=config.llm_max_retries,
        )

    return ChatAnthropic(
        model_name=actual_model,
        api_key=config.anthropic_api_key,
        max_retries=config.llm_max_retries,
    )  # type: ignore[call-arg]
