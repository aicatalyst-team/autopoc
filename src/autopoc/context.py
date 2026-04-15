"""Context management for ReAct agents.

Provides a pre_model_hook that prevents context overflow by summarizing
old tool interactions when the accumulated context approaches the model's
token limit. Uses llm_input_messages so the full history is preserved
in state while only the compacted version is sent to the LLM.

Key invariant: Claude's API requires that every tool_result (ToolMessage)
has a matching tool_use (AIMessage with tool_calls) in the preceding
message. We must never orphan a ToolMessage by dropping its AIMessage,
or vice versa. Tool interactions are always dropped/kept as atomic groups.
"""

import logging
from dataclasses import dataclass, field

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

# Rough estimate: 1 token ≈ 3.5 characters for English/code text.
CHARS_PER_TOKEN = 3.5

# Default token budget — leave headroom below the model's 200K limit.
DEFAULT_TOKEN_BUDGET = 150_000

# When truncating a tool result, keep this many characters.
TRUNCATED_TOOL_RESULT_CHARS = 300

# Summary that replaces a dropped tool interaction group
DROPPED_GROUP_SUMMARY = (
    "[Earlier tool interaction removed to save context. "
    "The agent called {tool_names} and received results. "
    "See later interactions for current state.]"
)


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate from character count."""
    return int(len(text) / CHARS_PER_TOKEN)


def _message_text(msg) -> str:
    """Extract text content from a message."""
    content = msg.content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    elif isinstance(content, str):
        return content
    return str(content)


def _estimate_message_tokens(msg) -> int:
    """Estimate the token count of a single message including metadata."""
    text = _message_text(msg)
    # Add overhead for role, tool_call_id, name, etc.
    overhead = 30
    # AIMessages with tool_calls have JSON overhead for each call
    if isinstance(msg, AIMessage) and msg.tool_calls:
        overhead += 50 * len(msg.tool_calls)
    return _estimate_tokens(text) + overhead


@dataclass
class _ToolGroup:
    """An atomic group: one AIMessage with tool_calls + its ToolMessage responses."""

    ai_msg: AIMessage
    tool_msgs: list[ToolMessage] = field(default_factory=list)
    index_start: int = 0  # position of AIMessage in the original list
    index_end: int = 0  # position after last ToolMessage

    @property
    def tokens(self) -> int:
        total = _estimate_message_tokens(self.ai_msg)
        for tm in self.tool_msgs:
            total += _estimate_message_tokens(tm)
        return total

    @property
    def tool_names(self) -> str:
        names = []
        for tc in self.ai_msg.tool_calls:
            name = tc.get("name", "unknown")
            if name not in names:
                names.append(name)
        return ", ".join(names)


def _build_tool_groups(messages: list, middle_start: int, middle_end: int) -> list[_ToolGroup]:
    """Identify atomic tool interaction groups within the middle zone.

    A group is: AIMessage(tool_calls=[...]) followed by one or more ToolMessages
    whose tool_call_ids match the AIMessage's tool_calls.
    """
    groups = []
    i = middle_start

    while i < middle_end:
        msg = messages[i]

        if isinstance(msg, AIMessage) and msg.tool_calls:
            group = _ToolGroup(ai_msg=msg, index_start=i)
            i += 1
            # Collect following ToolMessages
            while i < middle_end and isinstance(messages[i], ToolMessage):
                group.tool_msgs.append(messages[i])
                i += 1
            group.index_end = i
            groups.append(group)
        else:
            i += 1

    return groups


def _truncate_tool_result(content: str) -> str:
    """Truncate a tool result to a short preview."""
    if len(content) <= TRUNCATED_TOOL_RESULT_CHARS:
        return content

    preview = content[:TRUNCATED_TOOL_RESULT_CHARS]
    original_chars = len(content)
    return f"{preview}\n\n... [truncated — original was {original_chars:,} chars]"


def _make_summary_messages(group: _ToolGroup) -> list:
    """Create a compact summary of a tool group that maintains API invariants.

    Returns an AIMessage with tool_calls + matching ToolMessages with
    truncated content, preserving the tool_use/tool_result pairing.
    """
    # Keep the AIMessage as-is (it's small — just tool_call metadata)
    summary = [group.ai_msg]

    # Truncate each ToolMessage content
    for tm in group.tool_msgs:
        content = tm.content if isinstance(tm.content, str) else str(tm.content)
        truncated = _truncate_tool_result(content)
        summary.append(
            ToolMessage(
                content=truncated,
                tool_call_id=tm.tool_call_id,
                name=getattr(tm, "name", None),
            )
        )

    return summary


def make_context_trimmer(token_budget: int = DEFAULT_TOKEN_BUDGET):
    """Create a pre_model_hook that trims context to stay within token budget.

    The hook returns `llm_input_messages` so the actual state messages are
    not modified — only the messages sent to the LLM are trimmed.

    Strategy:
    1. Always keep the SystemMessage and first HumanMessage intact.
    2. Always keep the most recent tool group and any trailing messages intact —
       the LLM needs these to decide its next action.
    3. For older tool groups in the "middle zone":
       a. First pass: truncate ToolMessage content to short previews.
       b. Second pass (if still over): drop entire tool groups, oldest first,
          replacing each with a compacted summary that preserves API invariants.

    Critical invariant: Never orphan a ToolMessage. Tool interactions are
    always kept/dropped as atomic groups (AIMessage + its ToolMessages).

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
            return {"llm_input_messages": messages}

        logger.warning(
            "Context ~%dk tokens exceeds %dk budget. Compacting.",
            total_tokens // 1000,
            token_budget // 1000,
        )

        # Identify protected zones
        # Head: SystemMessage + initial HumanMessage (always positions 0, 1)
        protected_head = min(2, len(messages))

        # Tail: find the last tool group boundary — protect from there onward.
        # We want to keep the most recent complete tool interaction plus any
        # trailing messages.
        protected_tail_start = len(messages)
        # Walk backward to find the start of the last tool group
        for i in range(len(messages) - 1, protected_head - 1, -1):
            msg = messages[i]
            if isinstance(msg, AIMessage) and msg.tool_calls:
                protected_tail_start = i
                break

        # If no tool group found in tail, just protect the last 2 messages
        if protected_tail_start == len(messages):
            protected_tail_start = max(protected_head, len(messages) - 2)

        # Build atomic tool groups from the middle zone
        middle_start = protected_head
        middle_end = protected_tail_start
        groups = _build_tool_groups(messages, middle_start, middle_end)

        if not groups:
            # No tool groups to compact — nothing we can safely do
            logger.info("No tool groups to compact in middle zone. Passing through.")
            return {"llm_input_messages": messages}

        # Pass 1: Truncate all tool results in middle zone groups
        truncated_groups = []
        tokens_saved = 0
        for group in groups:
            original_tokens = group.tokens
            summary_msgs = _make_summary_messages(group)
            new_tokens = sum(_estimate_message_tokens(m) for m in summary_msgs)
            saved = original_tokens - new_tokens
            tokens_saved += saved
            truncated_groups.append((group, summary_msgs, new_tokens))

        total_tokens -= tokens_saved

        if total_tokens <= token_budget:
            # Truncation alone was enough — rebuild message list
            result = list(messages[:protected_head])
            group_idx = 0
            i = middle_start
            while i < middle_end:
                if group_idx < len(truncated_groups):
                    grp, summary_msgs, _ = truncated_groups[group_idx]
                    if i == grp.index_start:
                        result.extend(summary_msgs)
                        i = grp.index_end
                        group_idx += 1
                        continue
                result.append(messages[i])
                i += 1
            result.extend(messages[protected_tail_start:])

            logger.info(
                "Compacted via truncation: %d -> %d messages, ~%dk tokens",
                len(messages),
                len(result),
                total_tokens // 1000,
            )
            return {"llm_input_messages": result}

        # Pass 2: Drop oldest groups entirely until under budget.
        # Replace dropped groups with nothing — but we must maintain
        # the invariant. Since we drop the entire atomic group
        # (AIMessage + ToolMessages), there are no orphans.
        kept_group_indices = set(range(len(truncated_groups)))

        for idx in range(len(truncated_groups)):
            if total_tokens <= token_budget:
                break
            _, _, group_tokens = truncated_groups[idx]
            total_tokens -= group_tokens
            kept_group_indices.discard(idx)
            grp = truncated_groups[idx][0]
            logger.debug(
                "Dropped tool group [%s] (positions %d-%d): freed ~%d tokens",
                grp.tool_names,
                grp.index_start,
                grp.index_end,
                group_tokens,
            )

        # Rebuild the message list
        result = list(messages[:protected_head])

        # Add a brief note about dropped context if any groups were dropped
        dropped_count = len(truncated_groups) - len(kept_group_indices)
        if dropped_count > 0:
            result.append(
                HumanMessage(
                    content=(
                        f"[Note: {dropped_count} earlier tool interaction(s) were "
                        f"removed to fit context. Focus on the remaining results.]"
                    )
                )
            )

        # Add surviving middle groups (truncated versions)
        i = middle_start
        group_idx = 0
        while i < middle_end:
            if group_idx < len(truncated_groups):
                grp, summary_msgs, _ = truncated_groups[group_idx]
                if i == grp.index_start:
                    if group_idx in kept_group_indices:
                        result.extend(summary_msgs)
                    i = grp.index_end
                    group_idx += 1
                    continue
            # Non-group message in the middle (rare but possible — e.g., AIMessage
            # with text content but no tool_calls)
            result.append(messages[i])
            i += 1

        # Add protected tail
        result.extend(messages[protected_tail_start:])

        logger.info(
            "Compacted: %d -> %d messages (~%dk tokens). Dropped %d tool group(s).",
            len(messages),
            len(result),
            total_tokens // 1000,
            dropped_count,
        )

        return {"llm_input_messages": result}

    return context_trimmer
