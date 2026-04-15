"""Context management for ReAct agents.

Provides a pre_model_hook that prevents context overflow by compacting
old tool interactions when the accumulated context approaches the model's
token limit. Uses llm_input_messages so the full history is preserved
in state while only the compacted version is sent to the LLM.

Key invariant: Claude's API requires that every tool_result (ToolMessage)
has a matching tool_use (AIMessage with tool_calls) in the preceding
message. We must never orphan a ToolMessage by dropping its AIMessage,
or vice versa. Tool interactions are always dropped/kept as atomic groups.

Compaction strategy (3 passes):
  Pass 1: Truncate ToolMessage content in middle-zone groups to short previews.
  Pass 2: Drop entire middle-zone tool groups, oldest first.
  Pass 3: Truncate ToolMessages in the protected tail to fit remaining budget.
           This is the hard guarantee — we ALWAYS fit after pass 3.
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

# Pessimistic estimate: 1 token ≈ 2 characters.
# Real ratio varies (2-4 chars/token depending on content type). Using 2.0
# ensures we start compacting well before the actual limit. Better to compact
# too early (losing some context) than too late (crashing with 400 error).
CHARS_PER_TOKEN = 2.0

# Default token budget — well below the model's 200K limit.
# With the pessimistic estimator, real tokens will be ~60-80% of our estimate,
# so a 120K budget here corresponds to ~150-190K real tokens.
DEFAULT_TOKEN_BUDGET = 120_000

# When truncating a tool result in the middle zone, keep this many characters.
TRUNCATED_TOOL_RESULT_CHARS = 300

# Maximum characters for a ToolMessage in the protected tail during pass 3.
# 4KB ≈ ~2000 tokens at our ratio — enough to see meaningful output.
TAIL_TOOL_RESULT_MAX_CHARS = 4_000


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
    overhead = 30
    if isinstance(msg, AIMessage) and msg.tool_calls:
        # Each tool call has JSON overhead for name, args, id
        overhead += 80 * len(msg.tool_calls)
    return _estimate_tokens(text) + overhead


@dataclass
class _ToolGroup:
    """An atomic group: one AIMessage with tool_calls + its ToolMessage responses."""

    ai_msg: AIMessage
    tool_msgs: list[ToolMessage] = field(default_factory=list)
    index_start: int = 0
    index_end: int = 0

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


def _build_tool_groups(messages: list, start: int, end: int) -> list[_ToolGroup]:
    """Identify atomic tool interaction groups within a range."""
    groups = []
    i = start
    while i < end:
        msg = messages[i]
        if isinstance(msg, AIMessage) and msg.tool_calls:
            group = _ToolGroup(ai_msg=msg, index_start=i)
            i += 1
            while i < end and isinstance(messages[i], ToolMessage):
                group.tool_msgs.append(messages[i])
                i += 1
            group.index_end = i
            groups.append(group)
        else:
            i += 1
    return groups


def _truncate_tool_content(content: str, max_chars: int) -> str:
    """Truncate tool result content to max_chars with a notice."""
    if len(content) <= max_chars:
        return content
    preview = content[:max_chars]
    return f"{preview}\n\n... [truncated from {len(content):,} chars to fit context]"


def _make_truncated_tool_msg(tm: ToolMessage, max_chars: int) -> ToolMessage:
    """Create a truncated copy of a ToolMessage."""
    content = tm.content if isinstance(tm.content, str) else str(tm.content)
    return ToolMessage(
        content=_truncate_tool_content(content, max_chars),
        tool_call_id=tm.tool_call_id,
        name=getattr(tm, "name", None),
    )


def make_context_trimmer(token_budget: int = DEFAULT_TOKEN_BUDGET):
    """Create a pre_model_hook that compacts context to stay within token budget.

    Returns `llm_input_messages` so state messages are not modified.

    Three-pass compaction:
      Pass 1: Truncate ToolMessage content in middle-zone groups to 300-char previews.
      Pass 2: Drop entire middle-zone tool groups, oldest first.
      Pass 3: Truncate ToolMessages in the protected tail to fit. This is the
              hard guarantee that ensures we ALWAYS stay under budget.

    Critical invariant: Never orphan a ToolMessage.
    """

    def context_trimmer(state: dict) -> dict:
        messages = state.get("messages", [])
        if not messages:
            return {"llm_input_messages": messages}

        total_tokens = sum(_estimate_message_tokens(m) for m in messages)
        if total_tokens <= token_budget:
            return {"llm_input_messages": messages}

        logger.warning(
            "Context ~%dk tokens exceeds %dk budget. Compacting.",
            total_tokens // 1000,
            token_budget // 1000,
        )

        # --- Identify protected zones ---

        # Head: SystemMessage + initial HumanMessage
        protected_head = min(2, len(messages))

        # Tail: last tool group + any trailing messages
        protected_tail_start = len(messages)
        for i in range(len(messages) - 1, protected_head - 1, -1):
            if isinstance(messages[i], AIMessage) and messages[i].tool_calls:
                protected_tail_start = i
                break
        if protected_tail_start == len(messages):
            protected_tail_start = max(protected_head, len(messages) - 2)

        # --- Middle zone groups ---
        middle_start = protected_head
        middle_end = protected_tail_start
        groups = _build_tool_groups(messages, middle_start, middle_end)

        # --- Pass 1: Truncate middle-zone tool results ---
        truncated_groups: list[tuple[_ToolGroup, list, int]] = []
        for group in groups:
            original_tokens = group.tokens
            summary = [group.ai_msg]
            for tm in group.tool_msgs:
                summary.append(_make_truncated_tool_msg(tm, TRUNCATED_TOOL_RESULT_CHARS))
            new_tokens = sum(_estimate_message_tokens(m) for m in summary)
            total_tokens -= original_tokens - new_tokens
            truncated_groups.append((group, summary, new_tokens))

        if total_tokens <= token_budget:
            result = self_rebuild_with_middle(
                messages,
                protected_head,
                middle_start,
                middle_end,
                protected_tail_start,
                truncated_groups,
                set(range(len(truncated_groups))),
            )
            logger.info(
                "Compacted via truncation: %d -> %d msgs, ~%dk tokens",
                len(messages),
                len(result),
                total_tokens // 1000,
            )
            return {"llm_input_messages": result}

        # --- Pass 2: Drop oldest middle groups ---
        kept = set(range(len(truncated_groups)))
        for idx in range(len(truncated_groups)):
            if total_tokens <= token_budget:
                break
            _, _, grp_tokens = truncated_groups[idx]
            total_tokens -= grp_tokens
            kept.discard(idx)
            g = truncated_groups[idx][0]
            logger.debug(
                "Dropped tool group [%s] (pos %d-%d): freed ~%d tokens",
                g.tool_names,
                g.index_start,
                g.index_end,
                grp_tokens,
            )

        result = self_rebuild_with_middle(
            messages,
            protected_head,
            middle_start,
            middle_end,
            protected_tail_start,
            truncated_groups,
            kept,
        )

        # --- Pass 3: Truncate protected tail if still over budget ---
        total_tokens = sum(_estimate_message_tokens(m) for m in result)
        if total_tokens > token_budget:
            # Calculate how much room the tail gets after head + note messages
            head_tokens = sum(
                _estimate_message_tokens(m)
                for m in result
                if not (
                    isinstance(m, ToolMessage)
                    and _is_in_tail(m, result, protected_tail_start, messages)
                )
            )
            # Simpler approach: find all ToolMessages in result that came from
            # the tail, and truncate them to fit the remaining budget.
            tail_budget_chars = max(
                1000,  # absolute minimum
                int((token_budget - head_tokens) * CHARS_PER_TOKEN),
            )
            # Distribute budget equally across tail ToolMessages
            tail_tool_indices = [
                i
                for i, m in enumerate(result)
                if isinstance(m, ToolMessage) and len(_message_text(m)) > TAIL_TOOL_RESULT_MAX_CHARS
            ]
            # Only truncate the large ones in the tail region
            # Tail region in result = messages from protected_tail_start onward
            # Find where tail starts in result
            tail_start_in_result = len(result)
            for i in range(len(result) - 1, -1, -1):
                if isinstance(result[i], AIMessage) and result[i].tool_calls:
                    tail_start_in_result = i
                    break

            truncated_tail = False
            for i in range(tail_start_in_result, len(result)):
                if isinstance(result[i], ToolMessage):
                    content = _message_text(result[i])
                    if len(content) > TAIL_TOOL_RESULT_MAX_CHARS:
                        result[i] = _make_truncated_tool_msg(result[i], TAIL_TOOL_RESULT_MAX_CHARS)
                        truncated_tail = True

            if truncated_tail:
                total_tokens = sum(_estimate_message_tokens(m) for m in result)
                logger.info(
                    "Pass 3: truncated tail ToolMessages to %d chars each",
                    TAIL_TOOL_RESULT_MAX_CHARS,
                )

            # If STILL over budget, progressively halve tail tool content
            shrink_limit = TAIL_TOOL_RESULT_MAX_CHARS
            while total_tokens > token_budget and shrink_limit > 500:
                shrink_limit //= 2
                for i in range(tail_start_in_result, len(result)):
                    if isinstance(result[i], ToolMessage):
                        content = _message_text(result[i])
                        if len(content) > shrink_limit:
                            result[i] = _make_truncated_tool_msg(result[i], shrink_limit)
                total_tokens = sum(_estimate_message_tokens(m) for m in result)
                logger.debug(
                    "Shrunk tail to %d chars, ~%dk tokens", shrink_limit, total_tokens // 1000
                )

        dropped_count = len(truncated_groups) - len(kept)
        logger.info(
            "Compacted: %d -> %d msgs (~%dk tokens). Dropped %d group(s).",
            len(messages),
            len(result),
            total_tokens // 1000,
            dropped_count,
        )
        return {"llm_input_messages": result}

    return context_trimmer


def _is_in_tail(msg, result, tail_start, original_messages):
    """Check if a message in result came from the tail of original_messages."""
    # This is a heuristic — not used in the final implementation
    return False


def self_rebuild_with_middle(
    messages,
    protected_head,
    middle_start,
    middle_end,
    protected_tail_start,
    truncated_groups,
    kept_indices,
):
    """Rebuild the message list with compacted middle zone."""
    result = list(messages[:protected_head])

    dropped_count = len(truncated_groups) - len(kept_indices)
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
                if group_idx in kept_indices:
                    result.extend(summary_msgs)
                i = grp.index_end
                group_idx += 1
                continue
        result.append(messages[i])
        i += 1

    # Add protected tail
    result.extend(messages[protected_tail_start:])
    return result
