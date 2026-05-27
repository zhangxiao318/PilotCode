"""Compaction management for QueryEngine.

Encapsulates the five-layer graduated compaction pipeline,
emergency fallback compaction, and smart compression.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from ..services.compaction_pipeline import (
    CompactionPipeline,
    PipelineConfig as CompactionPipelineConfig,
)
from ..services.context_compression import get_context_compressor, CompressionResult
from ..services.intelligent_compact import IntelligentContextCompactor, CompactConfig
from ..utils.reasoning_compressor import compress_reasoning

logger = logging.getLogger(__name__)


class CompactionManager:
    """Manages conversation compaction and context compression."""

    def __init__(
        self,
        messages_ref: list[Any],
        count_tokens_fn: Callable[[], int],
        usable_context: int,
        auto_compact: bool,
        on_notify: Callable[[str, dict[str, Any]], None] | None,
        summarizer: Callable[[str], Any] | None = None,
    ):
        self.messages = messages_ref
        self._count_tokens = count_tokens_fn
        self._usable_context = usable_context
        self._auto_compact = auto_compact
        self._on_notify = on_notify
        self._summarizer = summarizer

        self._context_compressor = get_context_compressor()

        # Legacy intelligent compactor (used by smart_compact)
        compact_config = CompactConfig()
        if self._usable_context > 0:
            compact_config.compact_threshold = max(1, int(self._usable_context * 0.85))
            compact_config.critical_threshold = max(1, int(self._usable_context * 0.98))
        self._intelligent_compactor = IntelligentContextCompactor(config=compact_config)

        # Five-layer graduated compaction pipeline (ClaudeCode-style)
        pipeline_config = CompactionPipelineConfig()
        if self._usable_context > 0:
            pipeline_config.compact_pct = 0.85
            pipeline_config.critical_pct = 0.98
        self._compaction_pipeline = CompactionPipeline(config=pipeline_config)

        # Tracking
        self._last_compaction_token_count: int = 0
        self._compaction_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def smart_compact(self) -> CompressionResult | None:
        """Intelligently compress conversation using summarization.

        Triggers at 85% of usable context to leave headroom for output.
        """
        token_count = self._count_tokens()
        threshold = int(self._usable_context * 0.85)
        if token_count < threshold:
            return None

        result = await self._context_compressor.compress(
            self.messages,
            summarizer=self._summarizer,
        )

        if result.summary or result.removed_indices:
            self.messages[:] = [
                m for i, m in enumerate(self.messages) if i not in result.removed_indices
            ]
            if result.summary:
                from ..types.message import SystemMessage

                self.messages.insert(
                    1, SystemMessage(content=f"[Earlier conversation]: {result.summary}")
                )

        return result

    async def auto_compact_if_needed(self) -> bool:
        """Auto-compact conversation if token count exceeds threshold.

        Uses the five-layer graduated compaction pipeline.
        Returns True if compaction was performed.
        """
        if not self._auto_compact:
            return False

        token_count = self._count_tokens()
        threshold = int(self._usable_context * 0.85)
        critical = int(self._usable_context * 0.98)
        if token_count < threshold:
            return False

        # Cooldown: don't re-compact if token count hasn't grown since last compaction
        if token_count <= self._last_compaction_token_count:
            if token_count < critical:
                return False

        logger.debug(
            "auto_compact triggered: tokens=%d threshold=%d critical=%d usable=%d msg_count=%d",
            token_count,
            threshold,
            critical,
            self._usable_context,
            len(self.messages),
        )

        tokens_before = self._count_tokens()

        pipeline_result = await self._compaction_pipeline.run(
            messages=self.messages,
            token_count=tokens_before,
            usable_context=self._usable_context,
            summarizer=self._summarizer,
        )

        if pipeline_result.did_compact:
            self.messages[:] = pipeline_result.messages
            tokens_after = self._count_tokens()
            self._compaction_count += 1

            layer_details = {
                stat.layer_name: {
                    "tokens_saved": stat.tokens_before - stat.tokens_after,
                    "details": stat.details,
                }
                for stat in pipeline_result.stats
            }

            tool_results_cleared = sum(
                stat.details.get("cleared_tool_results", 0)
                + stat.details.get("trimmed_tool_results", 0)
                for stat in pipeline_result.stats
            )

            if self._on_notify:
                self._on_notify(
                    "auto_compact",
                    {
                        "tokens_before": tokens_before,
                        "tokens_after": tokens_after,
                        "tokens_saved": tokens_before - tokens_after,
                        "tool_results_cleared": tool_results_cleared,
                        "layers": list(layer_details.keys()),
                        "layer_details": layer_details,
                        "boundary_marker": pipeline_result.boundary_marker,
                        "compaction_count": self._compaction_count,
                        "fallback": False,
                    },
                )
            self._last_compaction_token_count = tokens_after
            return True

        if self._count_tokens() >= threshold:
            return self._fallback_compaction(tokens_before, threshold, critical)

        return False

    async def intelligent_compact(self, force: bool = False) -> dict[str, Any]:
        """Intelligently compact conversation using the five-layer pipeline.

        Args:
            force: If True, skip the should_compact check and always compact.

        Returns:
            Compaction statistics
        """
        token_count = self._count_tokens()

        if not force and not self._compaction_pipeline.should_compact(
            self.messages, token_count, self._usable_context
        ):
            return {
                "compacted": False,
                "reason": "Compaction not needed",
                "token_count": token_count,
            }

        pipeline_result = await self._compaction_pipeline.run(
            messages=self.messages,
            token_count=token_count,
            usable_context=self._usable_context,
            summarizer=self._summarizer,
            force=force,
        )

        if pipeline_result.did_compact:
            self.messages[:] = pipeline_result.messages
            self._compaction_count += 1

        total_saved = sum(stat.tokens_before - stat.tokens_after for stat in pipeline_result.stats)
        return {
            "compacted": pipeline_result.did_compact,
            "original_messages": len(self.messages)
            + sum(stat.messages_before - stat.messages_after for stat in pipeline_result.stats),
            "compacted_messages": len(self.messages),
            "original_tokens": token_count + total_saved,
            "compacted_tokens": self._count_tokens(),
            "tool_results_cleared": getattr(pipeline_result, "tool_results_cleared", 0),
            "compaction_count": self._compaction_count,
        }

    def _force_emergency_compact(self) -> None:
        """Emergency compaction for ContextWindowError recovery."""
        from ..types.message import (
            SystemMessage,
            UserMessage,
            AssistantMessage,
            ToolResultMessage,
        )

        changed = False

        # Phase 1: Clear all tool results except the most recent 3
        tool_result_count = 0
        for i in range(len(self.messages) - 1, -1, -1):
            if isinstance(self.messages[i], ToolResultMessage):
                tool_result_count += 1
                if tool_result_count > 3:
                    content = self.messages[i].content
                    if isinstance(content, str) and len(content) > 200:
                        self.messages[i] = ToolResultMessage(
                            tool_use_id=self.messages[i].tool_use_id,
                            content=(
                                "[Previous tool result content cleared during "
                                f"emergency compact to free context space (was {len(content)} chars)]"
                            ),
                            is_error=self.messages[i].is_error,
                        )
                        changed = True

        # Phase 2: Truncate assistant/user messages with very long content
        for i, msg in enumerate(self.messages):
            content = getattr(msg, "content", "")
            text = content if isinstance(content, str) else str(content)
            if len(text) > 5000:
                truncated = text[:2000] + (
                    f"\n\n[...emergency truncated from {len(text)} chars to free context space]"
                )
                if isinstance(msg, UserMessage):
                    self.messages[i] = UserMessage(content=truncated)
                    changed = True
                elif isinstance(msg, AssistantMessage):
                    self.messages[i] = AssistantMessage(
                        content=truncated,
                        reasoning_content=compress_reasoning(
                            getattr(msg, "reasoning_content", None)
                        ),
                    )
                    changed = True

        # Phase 3: If still likely oversized, drop oldest non-essential messages
        if len(self.messages) > 6:
            preserved = []
            for msg in self.messages:
                if isinstance(msg, SystemMessage):
                    preserved.append(msg)
            last_user = None
            for i in range(len(self.messages) - 1, -1, -1):
                if isinstance(self.messages[i], UserMessage):
                    last_user = self.messages[i]
                    break
            if last_user:
                preserved.append(last_user)
            preserved.extend(self.messages[-2:])
            seen_ids = set(id(m) for m in preserved)
            self.messages[:] = preserved + [m for m in self.messages if id(m) not in seen_ids]
            changed = True

        if changed:
            logger.info(
                "Emergency compact performed: %d messages remaining",
                len(self.messages),
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fallback_compaction(self, tokens_before: int, threshold: int, critical: int) -> bool:
        """Emergency fallback compaction when pipeline fails to reduce enough."""
        from ..types.message import SystemMessage, UserMessage, AssistantMessage, ToolResultMessage

        did_compact = False
        token_count = self._count_tokens()

        # Fallback 1: simple compaction (keep system + recent)
        keep_recent = 4 if token_count > critical else 6
        compressed = self._context_compressor.simple_compact(self.messages, keep_recent=keep_recent)
        if len(compressed) < len(self.messages):
            self.messages[:] = compressed
            did_compact = True

        # Fallback 2: aggressive truncation preserving key messages
        if self._count_tokens() > critical and len(self.messages) > 3:
            to_preserve: set[int] = set()
            for i, msg in enumerate(self.messages):
                if isinstance(msg, SystemMessage):
                    to_preserve.add(i)
            for i in range(len(self.messages) - 1, -1, -1):
                if isinstance(self.messages[i], UserMessage):
                    to_preserve.add(i)
                    break
            recent: list[int] = []
            slots = max(0, 2 - len(to_preserve))
            for i in range(len(self.messages) - 1, -1, -1):
                if i not in to_preserve and len(recent) < slots:
                    recent.append(i)
            kept = sorted(to_preserve | set(recent))
            self.messages[:] = [self.messages[i] for i in kept]
            did_compact = True

        # Fallback 3: truncate message content
        if self._count_tokens() > threshold:
            allow_truncate_recent = len(self.messages) <= 3 and self._count_tokens() > critical
            for i, msg in enumerate(self.messages):
                if i >= len(self.messages) - 1 and not allow_truncate_recent:
                    continue
                content = getattr(msg, "content", "")
                text = content if isinstance(content, str) else str(content)
                if len(text) > 2000:
                    truncated_text = text[:1500] + f"\n\n[...truncated from {len(text)} chars]"
                    if isinstance(msg, UserMessage):
                        self.messages[i] = UserMessage(content=truncated_text)
                    elif isinstance(msg, AssistantMessage):
                        self.messages[i] = AssistantMessage(
                            content=truncated_text,
                            reasoning_content=compress_reasoning(
                                getattr(msg, "reasoning_content", None)
                            ),
                        )
                    elif isinstance(msg, ToolResultMessage):
                        self.messages[i] = ToolResultMessage(
                            tool_use_id=msg.tool_use_id,
                            content=truncated_text,
                            is_error=msg.is_error,
                        )
                    did_compact = True

        if did_compact:
            tokens_after = self._count_tokens()
            if self._on_notify:
                self._on_notify(
                    "auto_compact",
                    {
                        "tokens_before": tokens_before,
                        "tokens_after": tokens_after,
                        "tokens_saved": tokens_before - tokens_after,
                        "compaction_count": self._compaction_count,
                        "fallback": True,
                    },
                )
            self._last_compaction_token_count = tokens_after
            return True

        return False
