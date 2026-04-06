"""Context compression service.

Implements intelligent context window management:
1. Summarization of old messages using Brief tool
2. Priority-based message retention
3. Semantic chunking
"""

import asyncio
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..types.message import MessageType, UserMessage, AssistantMessage
    from ..tools.base import ToolResult


@dataclass
class CompressionResult:
    """Result of context compression."""

    original_count: int
    compressed_count: int
    summary: str | None
    removed_indices: list[int]


class ContextCompressor:
    """Compress conversation context to fit within token limits."""

    def __init__(self, target_tokens: int = 3000):
        self.target_tokens = target_tokens
        self.min_messages_to_keep = 4  # Always keep at least last 4 exchanges

    async def compress(
        self, messages: list["MessageType"], summarizer: Any | None = None
    ) -> CompressionResult:
        """Compress messages to target token count.

        Strategy:
        1. Keep system message (first) and recent messages (last N)
        2. Summarize middle section if needed
        3. If still over limit, truncate oldest non-essential messages
        """
        from ..services.token_estimation import estimate_tokens

        if len(messages) <= self.min_messages_to_keep:
            return CompressionResult(
                original_count=len(messages),
                compressed_count=len(messages),
                summary=None,
                removed_indices=[],
            )

        # Calculate current token count
        total_tokens = sum(estimate_tokens(str(msg.content)) for msg in messages)

        if total_tokens <= self.target_tokens:
            return CompressionResult(
                original_count=len(messages),
                compressed_count=len(messages),
                summary=None,
                removed_indices=[],
            )

        # Strategy: Keep first (system), summarize middle, keep last N
        keep_first = 1  # System message
        keep_last = self.min_messages_to_keep

        if len(messages) <= keep_first + keep_last:
            # Not enough messages to compress meaningfully
            return CompressionResult(
                original_count=len(messages),
                compressed_count=len(messages),
                summary=None,
                removed_indices=[],
            )

        # Messages to summarize/remove
        middle_start = keep_first
        middle_end = len(messages) - keep_last
        middle_messages = messages[middle_start:middle_end]

        # Try to create a summary
        summary = None
        if summarizer and len(middle_messages) > 2:
            try:
                summary_text = self._create_summary_text(middle_messages)
                # Use Brief tool if available
                result = await summarizer(summary_text)
                if result and not result.is_error:
                    summary = str(result.data)
            except Exception:
                pass

        # Build compressed message list
        compressed = messages[:keep_first].copy()
        removed_indices = list(range(middle_start, middle_end))

        if summary:
            # Add summary as a system/context message
            from ..types.message import SystemMessage

            compressed.append(SystemMessage(content=f"[Earlier conversation summary]: {summary}"))

        # Add recent messages
        compressed.extend(messages[-keep_last:])

        return CompressionResult(
            original_count=len(messages),
            compressed_count=len(compressed),
            summary=summary,
            removed_indices=removed_indices,
        )

    def _create_summary_text(self, messages: list["MessageType"]) -> str:
        """Create text for summarization from messages."""
        parts = []
        for msg in messages:
            content = str(msg.content)[:500]  # Limit per message
            parts.append(content)
        return "\n\n".join(parts)

    def simple_compact(
        self, messages: list["MessageType"], keep_recent: int = 6
    ) -> list["MessageType"]:
        """Simple compaction: keep system + N most recent messages.

        This is a fast fallback when summarization isn't available.
        """
        if len(messages) <= keep_recent + 1:
            return messages.copy()

        result = []
        # Keep system message if present (first message)
        if hasattr(messages[0], "type") and messages[0].type == "system":
            result.append(messages[0])
            keep_recent -= 1

        # Keep most recent messages
        result.extend(messages[-keep_recent:])
        return result


class PriorityBasedCompressor(ContextCompressor):
    """Compressor that considers message priority.

    Higher priority messages are less likely to be removed.
    """

    def __init__(self, target_tokens: int = 3000):
        super().__init__(target_tokens)
        self.priority_weights = {
            "system": 10,
            "user": 5,
            "assistant": 4,
            "tool_use": 3,
            "tool_result": 3,
        }

    def _get_priority(self, msg: "MessageType") -> int:
        """Get priority for a message."""
        msg_type = getattr(msg, "type", "unknown")
        return self.priority_weights.get(msg_type, 1)

    def compact_with_priority(
        self, messages: list["MessageType"], max_messages: int = 20
    ) -> list["MessageType"]:
        """Compact keeping high-priority messages."""
        if len(messages) <= max_messages:
            return messages.copy()

        # Score messages by priority and recency
        scored = []
        for i, msg in enumerate(messages):
            priority = self._get_priority(msg)
            recency = i / len(messages)  # 0 to 1, higher is more recent
            score = priority + recency * 10
            scored.append((score, i, msg))

        # Sort by score descending, take top N
        scored.sort(reverse=True)
        keep_indices = set(idx for _, idx, _ in scored[:max_messages])

        # Return in original order
        return [msg for i, msg in enumerate(messages) if i in keep_indices]


# Global compressor
_compressor: ContextCompressor | None = None


def get_context_compressor() -> ContextCompressor:
    """Get global context compressor."""
    global _compressor
    if _compressor is None:
        _compressor = ContextCompressor()
    return _compressor
