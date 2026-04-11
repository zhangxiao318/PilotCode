"""Conversation forking and summarization service.

This module implements Claude Code's conversation fork mechanism:
1. Generate a summary of the current conversation
2. Create a new conversation branch with the summary
3. Set summary token count to 0 to avoid context window warnings
4. Clean relevant caches

Forking allows users to start fresh while retaining important context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING
import time

from ..utils.model_router import quick_summarize
from ..services.file_metadata_cache import clear_file_metadata_cache

if TYPE_CHECKING:
    pass


@dataclass
class ForkResult:
    """Result of conversation fork operation."""

    success: bool
    summary: str
    original_message_count: int
    new_message_count: int
    tokens_saved: int
    error: str | None = None
    preserved_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationSummary:
    """Summary of a conversation."""

    content: str
    key_points: list[str] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    token_count: int = 0  # Set to 0 for forked summaries


class ConversationSummarizer:
    """Summarizes conversation for forking."""

    def __init__(self, summarize_fn: Callable[[str], str] | None = None):
        """Initialize summarizer.

        Args:
            summarize_fn: Function to use for summarization. If None,
                         uses the quick_summarize from model_router.
        """
        self._summarize_fn = summarize_fn or quick_summarize

    async def summarize_for_fork(
        self, messages: list[Any], include_tool_results: bool = False
    ) -> ConversationSummary:
        """Create a summary suitable for conversation forking.

        This generates a comprehensive summary that captures:
        - Overall conversation topic/purpose
        - Key decisions made
        - Important context that should be preserved

        Args:
            messages: Conversation messages to summarize
            include_tool_results: Whether to include tool results in summary

        Returns:
            ConversationSummary with token_count set to 0
        """
        # Extract relevant content
        user_assistant_pairs = []
        current_pair = {}

        for msg in messages:
            msg_type = getattr(msg, "type", "unknown")
            content = getattr(msg, "content", "")

            # Skip system messages for summary (but note their existence)
            if msg_type == "system":
                continue

            # Handle user messages
            if msg_type == "user":
                if current_pair:
                    user_assistant_pairs.append(current_pair)
                current_pair = {"user": str(content), "assistant": None}

            # Handle assistant messages
            elif msg_type == "assistant":
                if current_pair:
                    current_pair["assistant"] = str(content)
                else:
                    current_pair = {"user": None, "assistant": str(content)}

            # Handle tool results (optionally)
            elif msg_type == "tool_result" and include_tool_results:
                if current_pair:
                    if "tool_results" not in current_pair:
                        current_pair["tool_results"] = []
                    current_pair["tool_results"].append(str(content)[:200])  # Truncate

        # Add last pair if exists
        if current_pair:
            user_assistant_pairs.append(current_pair)

        if not user_assistant_pairs:
            return ConversationSummary(content="Empty conversation", token_count=0)

        # Build summary text
        summary_parts = []

        # Overall summary using model
        full_conversation = self._format_for_summarization(user_assistant_pairs)

        try:
            overall_summary = await self._summarize_fn(full_conversation, max_sentences=3)
            summary_parts.append(overall_summary)
        except Exception:
            # Fallback to simple summary
            summary_parts.append(self._simple_summary(user_assistant_pairs))

        # Extract key points
        key_points = self._extract_key_points(user_assistant_pairs)

        # Extract decisions
        decisions = self._extract_decisions(user_assistant_pairs)

        # Extract action items
        actions = self._extract_action_items(user_assistant_pairs)

        summary_text = summary_parts[0]

        # Add structured info if present
        if decisions:
            summary_text += "\n\nKey decisions: " + "; ".join(decisions[:3])
        if actions:
            summary_text += "\n\nAction items: " + "; ".join(actions[:3])

        return ConversationSummary(
            content=summary_text,
            key_points=key_points,
            decisions_made=decisions,
            action_items=actions,
            token_count=0,  # Important: set to 0 for fork
        )

    def _format_for_summarization(self, pairs: list[dict[str, Any]]) -> str:
        """Format conversation pairs for summarization."""
        parts = []
        for i, pair in enumerate(pairs[-10:], 1):  # Last 10 exchanges
            if pair.get("user"):
                parts.append(f"User: {pair['user'][:500]}")
            if pair.get("assistant"):
                parts.append(f"Assistant: {pair['assistant'][:500]}")
        return "\n\n".join(parts)

    def _simple_summary(self, pairs: list[dict[str, Any]]) -> str:
        """Create a simple summary without model call."""
        if not pairs:
            return "Empty conversation"

        # Count messages
        user_msgs = sum(1 for p in pairs if p.get("user"))
        assistant_msgs = sum(1 for p in pairs if p.get("assistant"))

        # Get first user message as topic hint
        first_user = next((p["user"] for p in pairs if p.get("user")), "Unknown topic")

        topic = first_user[:100] + "..." if len(first_user) > 100 else first_user

        return (
            f"Conversation about: {topic}. "
            f"({user_msgs} user messages, {assistant_msgs} assistant responses)"
        )

    def _extract_key_points(self, pairs: list[dict[str, Any]]) -> list[str]:
        """Extract key points from conversation."""
        points = []

        # Look for code blocks, file mentions, important statements
        for pair in pairs:
            content = ""
            if pair.get("user"):
                content += pair["user"] + " "
            if pair.get("assistant"):
                content += pair["assistant"]

            # Extract file mentions
            import re

            files = re.findall(r"[\w\-./]+\.(py|js|ts|json|md|txt|yml|yaml)", content)
            for f in files:
                if f not in points:
                    points.append(f"File: {f}")

        return points[:5]  # Limit to 5 key points

    def _extract_decisions(self, pairs: list[dict[str, Any]]) -> list[str]:
        """Extract decisions made during conversation."""
        decisions = []

        # Look for decision indicators
        decision_words = [
            "decide",
            "decided",
            "decision",
            "choose",
            "chose",
            "choice",
            "will use",
            "going with",
        ]

        for pair in pairs:
            content = pair.get("assistant", "")
            lower = content.lower()

            for word in decision_words:
                if word in lower:
                    # Extract sentence containing decision word
                    sentences = content.split(".")
                    for sent in sentences:
                        if word in sent.lower() and len(sent.strip()) > 20:
                            decisions.append(sent.strip())
                            break
                    break

        return decisions[:5]

    def _extract_action_items(self, pairs: list[dict[str, Any]]) -> list[str]:
        """Extract action items from conversation."""
        actions = []

        # Look for action indicators
        action_words = ["need to", "should", "must", "will", "todo", "action item", "follow up"]

        for pair in pairs:
            content = pair.get("assistant", "")
            lower = content.lower()

            for word in action_words:
                if word in lower:
                    sentences = content.split(".")
                    for sent in sentences:
                        if word in sent.lower() and len(sent.strip()) > 15:
                            actions.append(sent.strip())
                            break
                    break

        return actions[:5]


class ConversationForker:
    """Handles conversation forking operations."""

    def __init__(self, summarizer: ConversationSummarizer | None = None):
        self._summarizer = summarizer or ConversationSummarizer()
        self._fork_history: list[ForkResult] = []

    async def fork_conversation(
        self, messages: list[Any], preserve_caches: bool = False
    ) -> ForkResult:
        """Fork a conversation, creating a new branch with summary.

        This implements Claude Code's fork mechanism:
        1. Generate summary of current conversation
        2. Create new message list with summary as context
        3. Set summary token count to 0
        4. Clear caches unless preserve_caches is True

        Args:
            messages: Current conversation messages
            preserve_caches: Whether to preserve file metadata caches

        Returns:
            ForkResult with new conversation state
        """
        original_count = len(messages)

        if original_count == 0:
            return ForkResult(
                success=False,
                summary="",
                original_message_count=0,
                new_message_count=0,
                tokens_saved=0,
                error="No messages to fork",
            )

        try:
            # Generate summary
            summary = await self._summarizer.summarize_for_fork(messages)

            # Build new conversation
            new_messages = self._create_forked_messages(messages, summary)

            # Calculate tokens saved
            # (Rough estimate: original messages vs new messages)
            tokens_saved = self._estimate_tokens_saved(messages, new_messages)

            # Clear caches if requested
            if not preserve_caches:
                self._clear_relevant_caches()

            result = ForkResult(
                success=True,
                summary=summary.content,
                original_message_count=original_count,
                new_message_count=len(new_messages),
                tokens_saved=tokens_saved,
                preserved_context={
                    "key_points": summary.key_points,
                    "decisions": summary.decisions_made,
                    "actions": summary.action_items,
                    "fork_time": time.time(),
                },
            )

            self._fork_history.append(result)
            return result

        except Exception as e:
            return ForkResult(
                success=False,
                summary="",
                original_message_count=original_count,
                new_message_count=0,
                tokens_saved=0,
                error=str(e),
            )

    def _create_forked_messages(
        self, original_messages: list[Any], summary: ConversationSummary
    ) -> list[Any]:
        """Create new message list for forked conversation.

        Strategy:
        1. Keep system message if present
        2. Add summary as context message
        3. Keep last 2 user-assistant pairs for continuity
        """
        from ..types.message import SystemMessage

        new_messages = []

        # Keep system message (first if it's system)
        if original_messages:
            first = original_messages[0]
            if getattr(first, "type", "") == "system":
                new_messages.append(first)

        # Add summary as system message (token_count = 0 handled separately)
        if summary.content:
            summary_msg = SystemMessage(
                content=f"[Previous conversation summary]: {summary.content}"
            )
            # Note: In real implementation, we'd track token_count separately
            new_messages.append(summary_msg)

        # Keep last 2 exchanges for continuity
        recent_exchanges = []
        for msg in reversed(original_messages):
            msg_type = getattr(msg, "type", "")
            if msg_type in ("user", "assistant"):
                recent_exchanges.insert(0, msg)
                if len(recent_exchanges) >= 4:  # 2 pairs
                    break

        new_messages.extend(recent_exchanges)

        return new_messages

    def _estimate_tokens_saved(self, original: list[Any], new: list[Any]) -> int:
        """Estimate tokens saved by forking."""
        # Rough estimate: 4 chars per token
        original_chars = sum(len(str(getattr(m, "content", ""))) for m in original)
        new_chars = sum(len(str(getattr(m, "content", ""))) for m in new)

        return max(0, (original_chars - new_chars) // 4)

    def _clear_relevant_caches(self) -> None:
        """Clear caches that should be refreshed after fork."""
        # Clear file metadata cache (like Claude Code clears getContext/getCodeStyle)
        clear_file_metadata_cache()

    def get_fork_history(self) -> list[ForkResult]:
        """Get history of all forks."""
        return self._fork_history.copy()

    def get_fork_stats(self) -> dict[str, Any]:
        """Get fork statistics."""
        if not self._fork_history:
            return {"total_forks": 0, "total_tokens_saved": 0, "average_compression": 0.0}

        total_saved = sum(f.tokens_saved for f in self._fork_history)
        total_original = sum(f.original_message_count for f in self._fork_history)

        return {
            "total_forks": len(self._fork_history),
            "total_tokens_saved": total_saved,
            "average_compression": (
                total_saved / len(self._fork_history) if self._fork_history else 0
            ),
            "average_original_messages": (
                total_original / len(self._fork_history) if self._fork_history else 0
            ),
        }


# Global instances
_default_forker: ConversationForker | None = None
_default_summarizer: ConversationSummarizer | None = None


def get_conversation_forker() -> ConversationForker:
    """Get global conversation forker."""
    global _default_forker
    if _default_forker is None:
        _default_forker = ConversationForker()
    return _default_forker


def get_conversation_summarizer() -> ConversationSummarizer:
    """Get global conversation summarizer."""
    global _default_summarizer
    if _default_summarizer is None:
        _default_summarizer = ConversationSummarizer()
    return _default_summarizer


async def fork_current_conversation(
    messages: list[Any], preserve_caches: bool = False
) -> ForkResult:
    """Convenience function to fork conversation."""
    forker = get_conversation_forker()
    return await forker.fork_conversation(messages, preserve_caches)
