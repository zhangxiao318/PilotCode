"""Five-layer graduated compaction pipeline for context management.

Inspired by Claude Code's compaction pipeline (query.ts:365-453):
1. Budget reduction    — per-tool-result size limits (always active)
2. Snip                — lightweight older-history trimming
3. Microcompact        — fine-grained cache-aware compression
4. Context collapse    — read-time virtual projection over history
5. Auto-compact        — full model-generated semantic summary

Design principles:
- Lazy degradation: apply the least disruptive compression first,
  escalating only when cheaper strategies prove insufficient.
- Append-only: compaction never modifies previously written transcript
  lines; it only appends new boundary/summary events or creates
  virtual projections.
- Cache-aware: preserve message boundaries that are likely to benefit
  from prompt caching (system message, recent user message).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CompactionStats:
    """Statistics for a single compaction run."""

    layer_name: str
    messages_before: int
    messages_after: int
    tokens_before: int
    tokens_after: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Result of the full five-layer pipeline."""

    messages: list[Any]
    stats: list[CompactionStats]
    boundary_marker: str = ""
    did_compact: bool = False


@dataclass
class PipelineConfig:
    """Configuration for the compaction pipeline."""

    # Token thresholds (percentages of usable context)
    warning_pct: float = 0.75
    compact_pct: float = 0.85
    critical_pct: float = 0.98

    # Message thresholds
    min_messages_to_keep: int = 6
    max_messages_full_content: int = 20

    # Layer toggles
    enable_snip: bool = True
    enable_microcompact: bool = True
    enable_context_collapse: bool = True
    enable_auto_compact: bool = True

    # Budget reduction (always active)
    max_tool_result_chars: int = 20_000  # per tool result
    max_tool_result_chars_critical: int = 2_000

    # Snip
    snip_keep_recent_tool_results: int = 3

    # Microcompact
    microcompact_keep_recent_messages: int = 8
    microcompact_boundary_marker: str = "[··· context compacted ···]"

    # Context collapse
    collapse_keep_recent_messages: int = 4
    collapse_max_chars_per_message: int = 800

    # Auto-compact
    auto_compact_min_messages: int = 10
    auto_compact_summary_max_tokens: int = 500

    def get_thresholds(self, usable_context: int) -> tuple[int, int, int]:
        """Return (warning, compact, critical) token thresholds."""
        return (
            int(usable_context * self.warning_pct),
            int(usable_context * self.compact_pct),
            int(usable_context * self.critical_pct),
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Rough token estimation (1 token ≈ 4 chars for English/code)."""
    return max(1, len(text) // 4)


def _message_token_count(msg: Any) -> int:
    """Estimate tokens for a single message."""
    content = getattr(msg, "content", "")
    text = content if isinstance(content, str) else str(content)
    return _estimate_tokens(text) + 4  # format overhead


def _total_tokens(messages: list[Any]) -> int:
    """Estimate total tokens for a message list."""
    return sum(_message_token_count(m) for m in messages)


def _is_system(msg: Any) -> bool:
    return getattr(msg, "type", "") == "system" or type(msg).__name__ == "SystemMessage"


def _is_user(msg: Any) -> bool:
    return getattr(msg, "type", "") == "user" or type(msg).__name__ == "UserMessage"


def _is_tool_result(msg: Any) -> bool:
    return getattr(msg, "type", "") == "tool_result" or type(msg).__name__ == "ToolResultMessage"


def _is_tool_use(msg: Any) -> bool:
    return getattr(msg, "type", "") == "tool_use" or type(msg).__name__ == "ToolUseMessage"


def _is_assistant(msg: Any) -> bool:
    return getattr(msg, "type", "") == "assistant" or type(msg).__name__ == "AssistantMessage"


def _make_boundary_marker(
    head_uuid: str = "",
    anchor_uuid: str = "",
    tail_uuid: str = "",
) -> str:
    """Create a boundary marker with preserved-segment metadata."""
    parts = ["COMPACT_BOUNDARY"]
    if head_uuid:
        parts.append(f"head={head_uuid}")
    if anchor_uuid:
        parts.append(f"anchor={anchor_uuid}")
    if tail_uuid:
        parts.append(f"tail={tail_uuid}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Layer 1: Budget Reduction (always active)
# ---------------------------------------------------------------------------


class BudgetReductionShaper:
    """Layer 1: Limit per-tool-result size.

    This is applied proactively when tool results are added (see
    QueryEngine.add_tool_result), but the shaper also performs a
    retroactive pass during compaction to ensure compliance.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config

    def shape(
        self,
        messages: list[Any],
        token_count: int,
        usable_context: int,
    ) -> tuple[list[Any], CompactionStats]:
        _, compact_threshold, critical_threshold = self.config.get_thresholds(usable_context)
        is_critical = token_count > critical_threshold

        max_chars = (
            self.config.max_tool_result_chars_critical
            if is_critical
            else self.config.max_tool_result_chars
        )

        trimmed = 0
        total_chars_before = 0
        total_chars_after = 0
        result: list[Any] = []

        for msg in messages:
            if _is_tool_result(msg):
                content = getattr(msg, "content", "")
                text = content if isinstance(content, str) else str(content)
                total_chars_before += len(text)

                if len(text) > max_chars:
                    # Keep head and tail
                    half = max_chars // 2
                    new_text = (
                        text[:half]
                        + f"\n\n[··· {len(text) - max_chars} chars truncated by budget reduction ···]\n\n"
                        + text[-half:]
                    )
                    # Rebuild message preserving other fields
                    new_msg = self._rebuild_tool_result(msg, new_text)
                    result.append(new_msg)
                    total_chars_after += len(new_text)
                    trimmed += 1
                else:
                    result.append(msg)
                    total_chars_after += len(text)
            else:
                result.append(msg)
                content = getattr(msg, "content", "")
                text = content if isinstance(content, str) else str(content)
                total_chars_before += len(text)
                total_chars_after += len(text)

        stats = CompactionStats(
            layer_name="budget_reduction",
            messages_before=len(messages),
            messages_after=len(result),
            tokens_before=token_count,
            tokens_after=_total_tokens(result),
            details={
                "trimmed_tool_results": trimmed,
                "max_chars": max_chars,
                "chars_before": total_chars_before,
                "chars_after": total_chars_after,
            },
        )
        return result, stats

    def _rebuild_tool_result(self, msg: Any, new_text: str) -> Any:
        """Rebuild a ToolResultMessage with new content."""
        from ..types.message import ToolResultMessage

        if isinstance(msg, ToolResultMessage):
            return ToolResultMessage(
                tool_use_id=msg.tool_use_id,
                content=new_text,
                is_error=msg.is_error,
            )
        # Fallback: try to create via dict copy
        try:
            data = msg.model_dump() if hasattr(msg, "model_dump") else vars(msg)
            data["content"] = new_text
            return ToolResultMessage.model_validate(data)
        except Exception:
            return msg


# ---------------------------------------------------------------------------
# Layer 2: Snip
# ---------------------------------------------------------------------------


class SnipShaper:
    """Layer 2: Lightweight older-history trimming.

    Clears old tool result content beyond the most recent N results,
    replacing them with lightweight markers.
    """

    CLEARED_MARKER = "[Previous tool result cleared to save context space]"

    def __init__(self, config: PipelineConfig):
        self.config = config

    def shape(
        self,
        messages: list[Any],
        token_count: int,
        usable_context: int,
    ) -> tuple[list[Any], CompactionStats]:
        keep = self.config.snip_keep_recent_tool_results
        cleared = 0
        result: list[Any] = []

        # Count tool results from the end
        tool_result_indices: list[int] = []
        for i, msg in enumerate(messages):
            if _is_tool_result(msg):
                tool_result_indices.append(i)

        # Determine which to clear (oldest beyond keep)
        to_clear = set(tool_result_indices[:-keep]) if len(tool_result_indices) > keep else set()

        for i, msg in enumerate(messages):
            if i in to_clear:
                content = getattr(msg, "content", "")
                text = content if isinstance(content, str) else str(content)
                if len(text) > 100:  # Only clear if there's meaningful content
                    new_msg = self._rebuild_tool_result(msg, self.CLEARED_MARKER)
                    result.append(new_msg)
                    cleared += 1
                else:
                    result.append(msg)
            else:
                result.append(msg)

        stats = CompactionStats(
            layer_name="snip",
            messages_before=len(messages),
            messages_after=len(result),
            tokens_before=token_count,
            tokens_after=_total_tokens(result),
            details={"cleared_tool_results": cleared, "keep_recent": keep},
        )
        return result, stats

    def _rebuild_tool_result(self, msg: Any, new_text: str) -> Any:
        from ..types.message import ToolResultMessage

        if isinstance(msg, ToolResultMessage):
            return ToolResultMessage(
                tool_use_id=msg.tool_use_id,
                content=new_text,
                is_error=msg.is_error,
            )
        try:
            data = msg.model_dump() if hasattr(msg, "model_dump") else vars(msg)
            data["content"] = new_text
            return ToolResultMessage.model_validate(data)
        except Exception:
            return msg


# ---------------------------------------------------------------------------
# Layer 3: Microcompact
# ---------------------------------------------------------------------------


class MicrocompactShaper:
    """Layer 3: Fine-grained cache-aware compression.

    Preserves message boundaries that are likely to benefit from prompt
    caching (system message, recent user/assistant pair). Older messages
    are collapsed into boundary markers while keeping structural anchors.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config

    def shape(
        self,
        messages: list[Any],
        token_count: int,
        usable_context: int,
    ) -> tuple[list[Any], CompactionStats]:
        from ..types.message import SystemMessage

        keep = self.config.microcompact_keep_recent_messages
        if len(messages) <= keep + 1:
            stats = CompactionStats(
                layer_name="microcompact",
                messages_before=len(messages),
                messages_after=len(messages),
                tokens_before=token_count,
                tokens_after=token_count,
                details={"skipped": True, "reason": "too_few_messages"},
            )
            return messages.copy(), stats

        result: list[Any] = []
        preserved_uuids: list[str] = []

        # Always preserve first system message
        start_idx = 0
        if messages and _is_system(messages[0]):
            result.append(messages[0])
            preserved_uuids.append(str(getattr(messages[0], "uuid", uuid.uuid4())))
            start_idx = 1

        # Determine where to place boundary: everything between start_idx
        # and the last 'keep' messages gets collapsed.
        collapse_end = max(start_idx, len(messages) - keep)

        if collapse_end > start_idx:
            # Collect head and tail UUIDs for chain patching
            head_msg = messages[start_idx] if start_idx < len(messages) else None
            tail_msg = messages[collapse_end] if collapse_end < len(messages) else None
            head_uuid = str(getattr(head_msg, "uuid", "")) if head_msg else ""
            tail_uuid = str(getattr(tail_msg, "uuid", "")) if tail_msg else ""

            marker_text = _make_boundary_marker(
                head_uuid=head_uuid,
                anchor_uuid=(
                    str(getattr(messages[start_idx], "uuid", ""))
                    if start_idx < len(messages)
                    else ""
                ),
                tail_uuid=tail_uuid,
            )
            boundary_msg = SystemMessage(
                content=f"{self.config.microcompact_boundary_marker}\n{marker_text}"
            )
            result.append(boundary_msg)
            preserved_uuids.append(str(boundary_msg.uuid))

        # Append recent messages
        for i in range(collapse_end, len(messages)):
            result.append(messages[i])
            preserved_uuids.append(str(getattr(messages[i], "uuid", "")))

        stats = CompactionStats(
            layer_name="microcompact",
            messages_before=len(messages),
            messages_after=len(result),
            tokens_before=token_count,
            tokens_after=_total_tokens(result),
            details={
                "collapsed_messages": collapse_end - start_idx,
                "kept_recent": len(messages) - collapse_end,
                "boundary_marker": self.config.microcompact_boundary_marker,
                "preserved_uuids": preserved_uuids[:5],  # truncate for stats
            },
        )
        return result, stats


# ---------------------------------------------------------------------------
# Layer 4: Context Collapse
# ---------------------------------------------------------------------------


class ContextCollapseShaper:
    """Layer 4: Read-time virtual projection over history.

    Aggressively truncates old user/assistant messages to a max char limit.
    Unlike destructive deletion, this keeps the message skeleton but replaces
    large content with a virtual projection indicator.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config

    def shape(
        self,
        messages: list[Any],
        token_count: int,
        usable_context: int,
    ) -> tuple[list[Any], CompactionStats]:
        from ..types.message import UserMessage, AssistantMessage

        keep = self.config.collapse_keep_recent_messages
        max_chars = self.config.collapse_max_chars_per_message
        truncated = 0
        result: list[Any] = []

        for i, msg in enumerate(messages):
            # Always keep recent messages intact
            if i >= len(messages) - keep:
                result.append(msg)
                continue

            content = getattr(msg, "content", "")
            text = content if isinstance(content, str) else str(content)

            if len(text) > max_chars and (_is_user(msg) or _is_assistant(msg)):
                truncated_text = (
                    text[:max_chars]
                    + f"\n\n[··· truncated from {len(text)} chars by context collapse ···]"
                )
                if _is_user(msg):
                    result.append(UserMessage(content=truncated_text))
                elif _is_assistant(msg):
                    from ..utils.reasoning_compressor import compress_reasoning

                    result.append(
                        AssistantMessage(
                            content=truncated_text,
                            reasoning_content=compress_reasoning(
                                getattr(msg, "reasoning_content", None)
                            ),
                        )
                    )
                truncated += 1
            else:
                result.append(msg)

        stats = CompactionStats(
            layer_name="context_collapse",
            messages_before=len(messages),
            messages_after=len(result),
            tokens_before=token_count,
            tokens_after=_total_tokens(result),
            details={"truncated_messages": truncated, "max_chars": max_chars},
        )
        return result, stats


# ---------------------------------------------------------------------------
# Layer 5: Auto-compact
# ---------------------------------------------------------------------------


class AutoCompactShaper:
    """Layer 5: Full semantic summary generated by LLM or heuristic.

    When all cheaper layers have been exhausted and context is still
    critical, this layer generates a semantic summary of the oldest
    portion of the conversation and replaces those messages with a
    single summary message.

    If no summarizer is available, falls back to a structured heuristic
    summary built from message metadata.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config

    async def shape(
        self,
        messages: list[Any],
        token_count: int,
        usable_context: int,
        summarizer: Callable[[str], Any] | None = None,
    ) -> tuple[list[Any], CompactionStats]:
        from ..types.message import SystemMessage

        min_msgs = self.config.auto_compact_min_messages
        if len(messages) <= min_msgs:
            stats = CompactionStats(
                layer_name="auto_compact",
                messages_before=len(messages),
                messages_after=len(messages),
                tokens_before=token_count,
                tokens_after=token_count,
                details={"skipped": True, "reason": "too_few_messages"},
            )
            return messages.copy(), stats

        # Identify the oldest non-system messages to summarize
        start_idx = 1 if messages and _is_system(messages[0]) else 0
        keep_recent = self.config.collapse_keep_recent_messages
        summarize_end = max(start_idx, len(messages) - keep_recent - min_msgs)

        if summarize_end <= start_idx:
            stats = CompactionStats(
                layer_name="auto_compact",
                messages_before=len(messages),
                messages_after=len(messages),
                tokens_before=token_count,
                tokens_after=token_count,
                details={"skipped": True, "reason": "insufficient_history"},
            )
            return messages.copy(), stats

        # Build summary text from the messages to be summarized
        messages_to_summarize = messages[start_idx:summarize_end]
        summary_text = self._heuristic_summary(messages_to_summarize)

        # Try LLM summarizer if available
        if summarizer:
            try:
                llm_summary = await summarizer(summary_text)
                if llm_summary and len(llm_summary) > 10:
                    summary_text = llm_summary
            except Exception:
                pass

        summary_msg = SystemMessage(
            content=f"[Earlier conversation summary]\n{summary_text[:2000]}"
        )

        result: list[Any] = []
        if start_idx > 0:
            result.append(messages[0])  # Preserve system message
        result.append(summary_msg)
        result.extend(messages[summarize_end:])

        stats = CompactionStats(
            layer_name="auto_compact",
            messages_before=len(messages),
            messages_after=len(result),
            tokens_before=token_count,
            tokens_after=_total_tokens(result),
            details={
                "summarized_messages": len(messages_to_summarize),
                "summary_length": len(summary_text),
                "used_llm": summarizer is not None,
            },
        )
        return result, stats

    def _heuristic_summary(self, messages: list[Any]) -> str:
        """Build a structured summary from message metadata."""
        files_read: set[str] = set()
        files_modified: set[str] = set()
        errors: list[str] = []
        tools_used: dict[str, int] = {}
        user_requests: list[str] = []

        for msg in messages:
            if _is_user(msg):
                text = str(getattr(msg, "content", ""))[:200]
                if text:
                    user_requests.append(text)
            elif _is_tool_use(msg):
                name = getattr(msg, "name", "unknown")
                tools_used[name] = tools_used.get(name, 0) + 1
                input_data = getattr(msg, "input", {}) or {}
                if isinstance(input_data, dict):
                    path = input_data.get("path") or input_data.get("file_path", "")
                    if path and name in ("FileRead", "Glob", "Grep", "CodeSearch"):
                        files_read.add(str(path))
                    elif path and name in ("FileWrite", "FileEdit", "ApplyPatch"):
                        files_modified.add(str(path))
            elif _is_tool_result(msg):
                if getattr(msg, "is_error", False):
                    text = str(getattr(msg, "content", ""))[:150]
                    errors.append(text)

        parts: list[str] = []
        if user_requests:
            parts.append(f"User requests: {'; '.join(user_requests[:3])}")
        if files_read:
            parts.append(f"Files examined: {', '.join(sorted(files_read)[:10])}")
        if files_modified:
            parts.append(f"Files modified: {', '.join(sorted(files_modified)[:10])}")
        if tools_used:
            top_tools = sorted(tools_used.items(), key=lambda x: -x[1])[:5]
            parts.append(f"Tools used: {', '.join(f'{n}({c})' for n, c in top_tools)}")
        if errors:
            parts.append(f"Errors encountered: {len(errors)}")

        return "\n".join(parts) if parts else "Previous conversation context."


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


class CompactionPipeline:
    """Orchestrates the five-layer graduated compaction pipeline."""

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self._budget = BudgetReductionShaper(self.config)
        self._snip = SnipShaper(self.config)
        self._micro = MicrocompactShaper(self.config)
        self._collapse = ContextCollapseShaper(self.config)
        self._auto = AutoCompactShaper(self.config)

    def should_compact(self, messages: list[Any], token_count: int, usable_context: int) -> bool:
        """Check if compaction is needed."""
        if len(messages) < self.config.min_messages_to_keep:
            return False
        compact_threshold, _, _ = self.config.get_thresholds(usable_context)
        return token_count > compact_threshold

    def is_critical(self, token_count: int, usable_context: int) -> bool:
        """Check if context is in critical state."""
        _, _, critical_threshold = self.config.get_thresholds(usable_context)
        return token_count > critical_threshold

    async def run(
        self,
        messages: list[Any],
        token_count: int,
        usable_context: int,
        summarizer: Callable[[str], Any] | None = None,
        force: bool = False,
    ) -> PipelineResult:
        """Run the full pipeline.

        Returns:
            PipelineResult with compacted messages and per-layer stats.
        """
        if not force and not self.should_compact(messages, token_count, usable_context):
            return PipelineResult(messages=messages.copy(), stats=[], did_compact=False)

        stats: list[CompactionStats] = []
        current = messages.copy()
        current_tokens = token_count
        did_compact = False

        # Layer 1: Budget reduction (always active during compaction)
        current, stat = self._budget.shape(current, current_tokens, usable_context)
        stats.append(stat)
        current_tokens = stat.tokens_after
        if stat.tokens_after < stat.tokens_before:
            did_compact = True

        # Layer 2: Snip
        if self.config.enable_snip:
            current, stat = self._snip.shape(current, current_tokens, usable_context)
            stats.append(stat)
            current_tokens = stat.tokens_after
            if stat.tokens_after < stat.tokens_before:
                did_compact = True

        # Early exit if we've recovered enough
        warning_threshold, compact_threshold, _ = self.config.get_thresholds(usable_context)
        if current_tokens < warning_threshold:
            return PipelineResult(
                messages=current,
                stats=stats,
                boundary_marker="",
                did_compact=did_compact,
            )

        # Layer 3: Microcompact
        if self.config.enable_microcompact:
            current, stat = self._micro.shape(current, current_tokens, usable_context)
            stats.append(stat)
            current_tokens = stat.tokens_after
            if stat.tokens_after < stat.tokens_before:
                did_compact = True

        if current_tokens < compact_threshold:
            return PipelineResult(
                messages=current,
                stats=stats,
                boundary_marker="",
                did_compact=did_compact,
            )

        # Layer 4: Context collapse
        if self.config.enable_context_collapse:
            current, stat = self._collapse.shape(current, current_tokens, usable_context)
            stats.append(stat)
            current_tokens = stat.tokens_after
            if stat.tokens_after < stat.tokens_before:
                did_compact = True

        if current_tokens < compact_threshold:
            return PipelineResult(
                messages=current,
                stats=stats,
                boundary_marker="",
                did_compact=did_compact,
            )

        # Layer 5: Auto-compact (most expensive, last resort)
        if self.config.enable_auto_compact:
            current, stat = await self._auto.shape(
                current, current_tokens, usable_context, summarizer=summarizer
            )
            stats.append(stat)
            current_tokens = stat.tokens_after
            if stat.tokens_after < stat.tokens_before:
                did_compact = True

        boundary_marker = ""
        for stat in stats:
            if stat.layer_name == "microcompact" and stat.details.get("collapsed_messages", 0) > 0:
                boundary_marker = self.config.microcompact_boundary_marker
                break

        return PipelineResult(
            messages=current,
            stats=stats,
            boundary_marker=boundary_marker,
            did_compact=did_compact,
        )


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_default_pipeline: CompactionPipeline | None = None


def get_compaction_pipeline(config: PipelineConfig | None = None) -> CompactionPipeline:
    """Get global compaction pipeline instance."""
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = CompactionPipeline(config)
    return _default_pipeline
