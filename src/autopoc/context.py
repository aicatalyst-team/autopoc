"""Context management for ReAct agents.

Provides a pre_model_hook that prevents context overflow by truncating
tool result messages when the accumulated context approaches the model's
token limit. Uses llm_input_messages so the full history is preserved
in state while only the trimmed version is sent to the LLM.
"""

import logging

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

# Rough estimate: 1 token ≈ 4 characters for English text.
# This is conservative — actual tokenization may be slightly more efficient.
CHARS_PER_TOKEN = 4

# Default token budget — leave headroom below the model's 200K limit
# for the response (~8K tokens) and safety margin.
DEFAULT_TOKEN_BUDGET = 180_000

# When truncating a tool result, keep this many characters at the start.
# Enough to see the structure of the response without consuming too much context.
TRUNCATED_TOOL_RESULT_CHARS = 500


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate from character count."""
    return len(text) // CHARS_PER_TOKEN


def _estimate_message_tokens(msg) -> int:
    """Estimate the token count of a single message."""
    content = msg.content
    if isinstance(content, list):
        # Multi-part content (Claude's format)
        text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    elif isinstance(content, str):
        text = content
    else:
        text = str(content)

    # Add overhead for role, tool_call metadata, etc.
    overhead = 20
    return _estimate_tokens(text) + overhead


def _truncate_tool_result(content: str) -> str:
    """Truncate a tool result to a short preview."""
    if len(content) <= TRUNCATED_TOOL_RESULT_CHARS:
        return content

    preview = content[:TRUNCATED_TOOL_RESULT_CHARS]
    original_tokens = _estimate_tokens(content)
    return (
        f"{preview}\n\n... [content truncated from ~{original_tokens} tokens "
        f"to save context. The full result contained {len(content)} characters.]"
    )


def make_context_trimmer(token_budget: int = DEFAULT_TOKEN_BUDGET):
    """Create a pre_model_hook that trims context to stay within token budget.

    The hook returns `llm_input_messages` so the actual state messages are
    not modified — only the messages sent to the LLM are trimmed.

    Strategy:
    1. Always keep the SystemMessage and first HumanMessage (the task description).
    2. Always keep the most recent messages (last 4) untouched — these contain
       the latest tool results the LLM needs to act on.
    3. For older ToolMessages that push us over budget, truncate their content
       to a short preview.

    Args:
        token_budget: Maximum tokens to send to the LLM.

    Returns:
        A pre_model_hook function for create_react_agent.
    """

    def context_trimmer(state: dict) -> dict:
        messages = state.get("messages", [])

        if not messages:
            return {"llm_input_messages": messages}

        # Estimate total tokens
        total_tokens = sum(_estimate_message_tokens(m) for m in messages)

        if total_tokens <= token_budget:
            # Under budget — pass through unchanged
            return {"llm_input_messages": messages}

        logger.warning(
            "Context approaching limit: ~%d tokens (budget: %d). Trimming tool results.",
            total_tokens,
            token_budget,
        )

        # Strategy: keep first 2 messages (system + user) and last 4 messages
        # (most recent interaction) intact. Truncate ToolMessages in the middle.
        protected_head = 2  # SystemMessage + initial HumanMessage
        protected_tail = 4  # Keep the latest messages for the LLM to act on

        trimmed = list(messages)  # shallow copy

        # Work from oldest to newest in the "middle" zone, truncating ToolMessages
        # until we're under budget.
        middle_start = protected_head
        middle_end = max(middle_start, len(trimmed) - protected_tail)

        for i in range(middle_start, middle_end):
            if total_tokens <= token_budget:
                break

            msg = trimmed[i]
            if not isinstance(msg, ToolMessage):
                continue

            content = msg.content
            if isinstance(content, str) and len(content) > TRUNCATED_TOOL_RESULT_CHARS:
                original_tokens = _estimate_message_tokens(msg)
                truncated_content = _truncate_tool_result(content)

                # Create a new ToolMessage with truncated content
                trimmed[i] = ToolMessage(
                    content=truncated_content,
                    tool_call_id=msg.tool_call_id,
                    name=getattr(msg, "name", None),
                )

                new_tokens = _estimate_message_tokens(trimmed[i])
                saved = original_tokens - new_tokens
                total_tokens -= saved

                logger.debug(
                    "Truncated tool result at position %d: saved ~%d tokens",
                    i,
                    saved,
                )

        # If still over budget after truncating tool results, start dropping
        # older middle messages entirely (tool calls + results).
        if total_tokens > token_budget:
            # Drop pairs of (AIMessage with tool_calls, ToolMessage) from the middle
            kept = []
            for i, msg in enumerate(trimmed):
                if i < protected_head or i >= middle_end:
                    kept.append(msg)
                elif total_tokens <= token_budget:
                    kept.append(msg)
                else:
                    dropped_tokens = _estimate_message_tokens(msg)
                    total_tokens -= dropped_tokens
                    logger.debug(
                        "Dropped message at position %d (%s): freed ~%d tokens",
                        i,
                        type(msg).__name__,
                        dropped_tokens,
                    )

            trimmed = kept

        logger.info(
            "Context trimmed: %d messages -> %d messages, ~%d tokens",
            len(messages),
            len(trimmed),
            total_tokens,
        )

        return {"llm_input_messages": trimmed}

    return context_trimmer
